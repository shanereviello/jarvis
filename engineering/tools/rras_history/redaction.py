"""Owned engineering-redaction-v1 patterns; recognized secrets only."""
import re
MAX_EXPORT=64*1024**2


def redact(raw):
    if type(raw) is not bytes or len(raw)>MAX_EXPORT:raise ValueError('bounded collector bytes required')
    text=raw.decode('utf-8');counts={}
    rules=[
        ('private_key',r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'),
        ('authorization',r'(?im)\b(?:authorization|proxy-authorization)\s*[:=]\s*[^\r\n]+'),
        ('cookie',r'(?im)\b(?:set-cookie|cookie)\s*:\s*[^\r\n]+'),
        ('credential_value',r'''(?im)(?:["']?\b(?:client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key|password|cf_access_client_secret|codex_n8n_bridge_secret|n8n_bridge_secret|linear_webhook_secret|codex_webhook_secret)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;\r\n]+)'''),
        ('provider_token',r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
        ('jwt',r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b'),
    ]
    for name,pattern in rules:
        text,count=re.subn(pattern,'[REDACTED:'+name+']',text)
        if count:counts[name]=count
    return text.encode(),counts


def redact_object(value):
    """Filter strings before JSON escaping can hide line/header boundaries."""
    counts={}
    def clean(item):
        if type(item) is str:
            raw,found=redact(item.encode())
            for k,n in found.items():counts[k]=counts.get(k,0)+n
            return raw.decode()
        if type(item) is list:return [clean(x) for x in item]
        if type(item) is dict:
            result={}
            for k,v in item.items():
                if re.fullmatch(r'(?i)(authorization|proxy-authorization|set-cookie|cookie|client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key|password)',k):
                    result[k]='[REDACTED:credential_value]';counts['credential_value']=counts.get('credential_value',0)+1
                else:result[k]=clean(v)
            return result
        return item
    return clean(value),counts


