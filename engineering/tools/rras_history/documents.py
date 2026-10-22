"""Deterministic private draft rendering; not protected capture or publication."""
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / 'docs/engineering-history-phase1/templates'
MAX_DOCUMENT = 256 * 1024


def contract():
    s = importlib.util.spec_from_file_location('history_contract', Path(__file__).with_name('contract.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def render(request, work):
    c = contract(); request = c.validate(request); body = request['body']
    if request['operation'] != 'document.render': raise ValueError('document operation required')
    c.validate({**request, 'operation': 'work.create', 'body': work})
    if (c.digest(c.encoded(work)) != body['work_revision_sha256'] or
            request['expected_head'] != body['work_revision_sha256'] or
            work['work_item_id'] != body['work_item_id']):
        raise ValueError('document content must bind exact work revision')
    template_raw = (TEMPLATES / (body['document_type'] + '.md')).read_bytes()
    template = template_raw.decode('utf-8')
    metadata = dict(work_item_id=body['work_item_id'], work_revision=str(work['revision']),
                    document_id=body['document_id'], document_version=str(body['document_version']),
                    repository_id=work['repository_id'], created_at_or_unknown=request['occurred_at'] or 'unknown')
    fields = body['fields']
    expected = set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}', template))
    if set(fields) != expected - set(metadata):
        raise ValueError('exact template field set required')
    if '\n' in fields['title'] or '\r' in fields['title'] or len(fields['title']) > 200:
        raise ValueError('bounded single-line document title required')
    values = {**fields, **metadata}
    # Metadata placeholders already have YAML quotes in the pinned templates;
    # the injected metadata syntax is bounded IDs/dates/numbers, never free text.
    text = re.sub(r'\{\{([a-z][a-z0-9_]*)\}\}', lambda match: values[match[1]], template)
    raw = text.encode('utf-8')
    if len(raw) > MAX_DOCUMENT: raise ValueError('document exceeds bound')
    content = {'request': request, 'work': work}
    manifest = dict(contract='engineering-document.v1', document_id=body['document_id'],
        document_version=body['document_version'], document_type=body['document_type'],
        work_item_id=body['work_item_id'], work_revision_sha256=body['work_revision_sha256'],
        markdown_sha256=c.digest(raw), content_sha256=c.digest(c.encoded(content)),
        template_sha256=c.digest(template_raw), renderer_sha256=c.digest(Path(__file__).read_bytes()),
        visibility='operator_private', status='draft_not_approval')
    return raw, manifest
