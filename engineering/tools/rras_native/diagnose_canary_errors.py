"""Read-only sanitized canary error classification. Never prints raw content."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

CODES={'insufficient_quota','credit_balance_exhausted','organization_spend_limit_exceeded',
       'project_spend_limit_exceeded','organization_usage_limit_exceeded','usage_limit_exceeded',
       'rate_limit_exceeded','slow_down','invalid_api_key','model_not_found','server_is_overloaded'}
BILLING=CODES-{'rate_limit_exceeded','slow_down','invalid_api_key','model_not_found','server_is_overloaded'}


def classify(text):
    structured=Counter();mentions=Counter()
    def walk(value,error=False):
        if isinstance(value,dict):
            context=error or value.get('type')=='error'
            if context:
                for key in ('code','type'):
                    v=value.get(key)
                    if isinstance(v,str) and v in CODES:structured[v]+=1
            for k,v in value.items():walk(v,context or k in ('error','last_error','error_info'))
        elif isinstance(value,list):
            for v in value:walk(v,error)
        elif isinstance(value,str) and value.lstrip().startswith('{'):
            try:walk(json.loads(value),error)
            except (ValueError,RecursionError):pass
    for line in text.splitlines():
        try:walk(json.loads(line))
        except (ValueError,RecursionError):pass
    for code in CODES:
        count=len(re.findall(r'(?<![A-Za-z0-9_])'+re.escape(code)+r'(?![A-Za-z0-9_])',text))
        if count:mentions[code]=count
    return structured,mentions


def inspect(root):
    root=Path(root).resolve(strict=True)
    structured=Counter();mentions=Counter();examined=0
    for p in (root/'home').rglob('*'):
        if p.is_symlink() or not p.is_file() or p.suffix not in ('.log','.jsonl'):continue
        with p.open('rb') as f:
            f.seek(max(0,p.stat().st_size-2097152));text=f.read(2097152).decode(errors='replace')
        s,m=classify(text);structured.update(s);mentions.update(m);examined+=1
    confirmed=set(structured)
    decision='billing_or_quota' if confirmed & BILLING else ('temporary_rate_limit' if confirmed & {'rate_limit_exceeded','slow_down'} else 'unresolved')
    return {'scope':'retained-canary-read-only-error-classification','files_examined':examined,
            'structured_error_codes':dict(structured),'text_code_mentions':dict(mentions),
            'classification':decision,'request_count_established':False,'spend_established':False,
            'raw_content_printed':False,'api_calls_made':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',required=True)
    x=p.parse_args();print(json.dumps(inspect(x.work),indent=2))
