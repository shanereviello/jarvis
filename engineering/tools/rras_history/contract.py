"""Strict passive engineering envelopes. No transport, enrollment or authority."""
import hashlib
from datetime import datetime
import json
from pathlib import Path
import re
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/engineering-history-v1.schema.json'
MAX_REQUEST = 128 * 1024


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw, *, max_bytes=MAX_REQUEST):
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise ValueError('bounded UTF-8 request required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid JSON number')))
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > 32: raise ValueError('bounded JSON nesting required')
            if isinstance(item, dict): stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list): stack.extend((child, depth + 1) for child in item)
        return value
    except (RecursionError, UnicodeError):
        raise ValueError('bounded UTF-8 JSON nesting required') from None


def validate(value):
    # Round-trip before callers can mutate a request while it is being recorded.
    try: raw = encoded(value)
    except RecursionError: raise ValueError('bounded JSON nesting required') from None
    value = decode(raw)
    Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker()).validate(value)
    stamp = value['occurred_at']
    if stamp is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', stamp):
            raise ValueError('exact UTC timestamp required')
        try: datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        except ValueError: raise ValueError('valid UTC calendar timestamp required') from None
    def inspect(item):
        if isinstance(item, str):
            if '\0' in item:
                raise ValueError('NUL refused')
        elif isinstance(item, dict):
            for key, child in item.items():
                inspect(key); inspect(child)
        elif isinstance(item, list):
            for child in item: inspect(child)
    inspect(value)
    if value['operation'].startswith('work.'):
        body = value['body']
        if '\n' in body['title'] or '\r' in body['title']:
            raise ValueError('single-line title required')
        criteria = [row['id'] for row in body['acceptance_criteria']]
        if len(criteria) != len(set(criteria)):
            raise ValueError('duplicate criterion identity')
        for name in body['allowed_paths']:
            p = Path(name)
            if (p.is_absolute() or str(p) != name or not name or name == '.' or
                    any(part in ('.', '..', '.git') for part in p.parts)):
                raise ValueError('canonical relative engineering path required')
    # Labels and digests also refuse surrounding whitespace explicitly.
    def identifiers(item, key=''):
        if isinstance(item, dict):
            for name, child in item.items(): identifiers(child, name)
        elif isinstance(item, list):
            for child in item: identifiers(child, key)
        elif isinstance(item, str) and (key.endswith('_sha256') or key in {
                'work_item_id', 'document_id', 'repository_id', 'client_namespace', 'namespace'}):
            if item != item.strip(): raise ValueError('exact identifier required')
    identifiers(value)
    return value
