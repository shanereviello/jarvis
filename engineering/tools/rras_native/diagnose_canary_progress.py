"""Read-only allowlisted event/command failure summary; no raw payload output."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re

EVENTS={'session_meta','turn_context','response_item','event_msg','error','turn_started','task_started','task_complete','turn_complete','agent_message','agent_reasoning','token_count','rate_limits','exec_command_begin','exec_command_end','exec_command_output_delta','item/started','item/completed','turn/completed','commandExecution'}
TOOLS={'exec_command','apply_patch','shell','shell_command','update_plan','write_stdin'}
PHRASES={'http_429':r'(?:HTTP(?:/\S+)?\s*|status(?: code)?[=: ]+|error code[=: ]+)429\b',
 'quota_message':r'exceeded your current quota|check your plan and billing|credit balance exhausted',
 'rate_message':r'rate limit reached|too many requests',
 'readonly_failure':r'read.only file system',
 'permission_failure':r'permission denied|operation not permitted',
 'missing_command':r'command not found|No module named',
 'retry_notice':r'reconnecting|retrying|retry after',
 'telemetry_field':r'"rate_limits"|"rate_limit"'}


def summarize(text):
    events=Counter();tools=Counter();exits=Counter();timeline=[]
    def walk(value):
        if isinstance(value,dict):
            t=value.get('type')
            if isinstance(t,str) and t in EVENTS:events[t]+=1
            name=value.get('name')
            if isinstance(name,str) and name in TOOLS:tools[name]+=1
            for k in ('exit_code','exitCode'):
                v=value.get(k)
                if isinstance(v,int) and not isinstance(v,bool) and -255<=v<=255:exits[str(v)]+=1
            for v in value.values():walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    for line in text.splitlines():
        try:
            record=json.loads(line);walk(record)
            if isinstance(record,dict):
                p=record.get('payload')
                t=p.get('type') if isinstance(p,dict) else record.get('type')
                stamp=record.get('timestamp')
                if isinstance(t,str) and t in EVENTS and isinstance(stamp,str) and re.fullmatch(r'[0-9T:.+Z-]{10,40}',stamp):
                    timeline.append({'timestamp':stamp,'event':t})
        except (ValueError,RecursionError):pass
    for code in re.findall(r'Process exited with code (-?[0-9]{1,3})',text):
        if -255<=int(code)<=255:exits[code]+=1
    return {'events':dict(events),'tools':dict(tools),'exit_codes':dict(exits),
            'markers':{k:len(re.findall(p,text,re.I)) for k,p in PHRASES.items()},
            'last_events':timeline[-12:]}


def inspect(root):
    root=Path(root).resolve(strict=True);summaries=[]
    for p in (root/'home').rglob('*'):
        if p.is_symlink() or not p.is_file() or p.suffix not in ('.jsonl','.log'):continue
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-2097152));data=f.read(2097152).decode(errors='replace')
        summaries.append({'file_number':len(summaries)+1,'format':p.suffix,**summarize(data)})
    calc=root/'repo/.worktrees/t_630b3df3/calc.py'
    receipt=root/'evidence.json'
    if receipt.is_file() and not receipt.is_symlink():
        candidate=Path(json.loads(receipt.read_text()).get('workspace',''))/'calc.py'
        if candidate.is_absolute() and candidate.resolve().is_relative_to(root/'repo/.worktrees'):
            calc=candidate
    code={'present':calc.is_file() and not calc.is_symlink()}
    if code['present'] and calc.stat().st_size<=16384:
        try:
            tree=ast.parse(calc.read_text())
            code['addition_operator_present']=any(isinstance(n,ast.Add) for n in ast.walk(tree))
            code['subtraction_operator_present']=any(isinstance(n,ast.Sub) for n in ast.walk(tree))
        except (SyntaxError,UnicodeError):code['parse_failed']=True
    return {'scope':'canary-progress-sanitized-read-only','files':summaries,'calc_structure':code,'api_calls_made':0,'raw_payloads_printed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',required=True)
    a=p.parse_args();print(json.dumps(inspect(a.work),indent=2))
