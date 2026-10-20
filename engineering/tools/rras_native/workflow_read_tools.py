"""Jarvis tools over explicitly exported files only; no journal/control access."""
import importlib.util
from pathlib import Path
import re


def journal():
    spec = importlib.util.spec_from_file_location('workflow_journal', Path(__file__).with_name('workflow_journal.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pages(directory):
    root = Path(directory)
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('fixed absolute projection directory required')
    j = journal()
    index = j.load_json(root / 'index.json')
    if (not isinstance(index, dict) or set(index) != {'schema_version', 'pages'} or
            type(index['schema_version']) is not int or index['schema_version'] != 1 or
            not isinstance(index['pages'], list) or len(index['pages']) > 256):
        raise ValueError('invalid projection index')
    result, seen = [], set()
    for entry in index['pages']:
        if (not isinstance(entry, dict) or set(entry) != {'work_item_id', 'after', 'file'} or
                not re.fullmatch('wrk_[0-9a-f]{32}', entry['work_item_id']) or
                type(entry['after']) is not int or entry['after'] < 0 or
                not re.fullmatch('[a-z0-9][a-z0-9_.-]{0,127}\\.json', entry['file']) or entry['file'] == 'index.json'):
            raise ValueError('invalid projection index entry')
        key = (entry['work_item_id'], entry['after'])
        if key in seen:
            raise ValueError('duplicate projection cursor')
        seen.add(key)
        view = j.read_projection(root / entry['file'])
        summary = view['summary']
        if summary['work_item_id'] != entry['work_item_id']:
            raise ValueError('projection work identity mismatch')
        facts = summary['facts']
        if facts:
            if [fact['sequence'] for fact in facts] != list(range(entry['after'] + 1, summary['next_after'] + 1)):
                raise ValueError('projection cursor mismatch')
        elif summary['next_after'] != entry['after']:
            raise ValueError('empty projection cursor mismatch')
        result.append((entry, view))
    return sorted(result, key=lambda item: (item[0]['work_item_id'], item[0]['after']))


def register(server, *, directory):
    """Register only bounded projection list/read; no execution or writes."""
    @server.tool()
    def workflow_pages(offset: int = 0, limit: int = 100):
        """List available sanitized work-history pages; exports may be stale."""
        journal().bounds(offset, limit)
        rows = pages(directory)
        selected = rows[offset:offset + limit]
        return {'pages': [{key: view['summary'][key] for key in
                 ('work_item_id', 'repository_id', 'mode', 'revision', 'next_after', 'has_more')} |
                 {'after': entry['after']} for entry, view in selected],
                'next_offset': offset + len(selected), 'has_more': offset + len(selected) < len(rows),
                'source': 'explicit_projection_snapshot'}

    @server.tool()
    def workflow_history(work_item_id: str, after: int = 0):
        """Read one existing sanitized page. Never reads private journal or artifacts."""
        if not isinstance(work_item_id, str) or not re.fullmatch('wrk_[0-9a-f]{32}', work_item_id):
            raise ValueError('exact work identity required')
        journal().bounds(after, 100)
        for entry, view in pages(directory):
            if entry['work_item_id'] == work_item_id and entry['after'] == after:
                return view
        raise ValueError('requested projection page unavailable')
