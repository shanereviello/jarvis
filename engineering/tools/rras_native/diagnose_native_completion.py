"""Read-only completion-command classification, never prints raw commands or output."""
import argparse
import json
from pathlib import Path
import re


def summarize(text):
    calls={};outputs={}
    for line in text.splitlines():
        try: r=json.loads(line)
        except ValueError: continue
        p=r.get('payload',{}) if isinstance(r,dict) else {}
        if not isinstance(p,dict):continue
        ident=p.get('call_id')
        if not isinstance(ident,str):continue
        if p.get('type')=='function_call':
            try: args=json.loads(p.get('arguments','{}'))
            except (ValueError,TypeError):continue
            command=args.get('cmd',args.get('command','')) if isinstance(args,dict) else ''
            if isinstance(command,list):command=' '.join(str(x) for x in command)
            if not isinstance(command,str):continue
            if re.search(r'\bkanban\s+(?:show|complete)\b',command):
                calls[ident]={'operation':'complete' if re.search(r'\bkanban\s+complete\b',command) else 'show',
                             'uses_native_module':'hermes_cli.main' in command,
                             'uses_task_variable':'HERMES_KANBAN_TASK' in command,
                             'uses_run_variable':'HERMES_KANBAN_RUN_ID' in command,
                             'presence_guard':bool(re.search(r'(?:test|\[)\s+-[nz]\s+[^\n;]*HERMES_KANBAN_TASK',command)),
                             'explicit_exit_one':bool(re.search(r'\bexit\s+1\b',command)),
                             'and_chain':'&&' in command,
                             'requested_nonlogin_shell':args.get('login') is False}

        elif p.get('type')=='function_call_output':
            output=p.get('output','')
            if not isinstance(output,str):output=json.dumps(output)
            codes=re.findall(r'Process exited with code (-?\d{1,3})',output)
            outputs[ident]={'exit_codes':[int(x) for x in codes],
                           'missing_task_context_marker':bool(re.search(r'(?:HERMES_KANBAN_TASK[^\n]{0,100}(?:missing|not set|unset|empty|unavailable)|(?:missing|not set|unset|empty|unavailable)[^\n]{0,100}HERMES_KANBAN_TASK)',output,re.I)),
                           'output_body_empty':not output.split('Output:',1)[-1].strip() if 'Output:' in output else not output.strip(),
                           'missing_module':bool(re.search(r'No module named',output,re.I)),
                           'write_denied':bool(re.search(r'read.only file system|permission denied',output,re.I)),
                           'run_mismatch':bool(re.search(r'stale run|run mismatch|run.id mismatch|expected run',output,re.I)),
                           'sqlite_locked':bool(re.search(r'database is locked',output,re.I)),
                           'task_not_found':bool(re.search(r'no such task|task not found',output,re.I)),
                           'database_open_failed':bool(re.search(r'unable to open database file',output,re.I)),
                           'readonly_database':bool(re.search(r'readonly database|read.only database',output,re.I)),
                           'cli_usage_error':bool(re.search(r'unrecognized arguments|invalid choice|arguments are required',output,re.I)),
                           'fork_failed':bool(re.search(r'failed to fork|resource temporarily unavailable',output,re.I)),
                           'exceptions':sorted(set(re.findall(r'\b(?:OperationalError|ImportError|ModuleNotFoundError|FileNotFoundError|PermissionError|RuntimeError|ValueError|KeyError|TypeError|AttributeError|NameError|AssertionError)\b',output)))}
    return [{**v,'result_observed':k in outputs,**outputs.get(k,{})} for k,v in calls.items()]


def inspect(work):
    root=Path(work).resolve(strict=True);results=[]
    for p in (root/'home/codex/sessions').rglob('*.jsonl'):
        if p.is_symlink() or not p.is_file():continue
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-2097152));text=f.read(2097152).decode(errors='replace')
        results.append({'file_number':len(results)+1,'native_cli_commands':summarize(text)})
    return {'scope':'native-completion-sanitized-read-only','sessions':results,'scan_limit_per_file':2097152,
            'api_calls_made':0,'raw_payloads_printed':False,'lifecycle_mutated':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',required=True)
    a=p.parse_args();print(json.dumps(inspect(a.work),indent=2))
