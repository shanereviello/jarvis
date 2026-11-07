"""Run inside the installed Hermes container using synthetic dictionaries only.

Never imports SessionDB, opens a real session, starts a gateway or invokes a model.
The exact inspected export helper is pinned before it is loaded.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

EXPECTED_SHA256 = '750953cd48cd8cf7435a1c7427f5ff3e1c5d10fda9519cc7a4d3889e7d1b2ffa'


def run(source):
    source = Path(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256: raise ValueError('review installed exporter revision first')
    spec = importlib.util.spec_from_file_location('shrr_hermes_native_md_fixture', source)
    exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
    session = dict(id='shrr-synthetic-session', title='Synthetic export; no real session', source='shrr_fixture',
        message_count=4, started_at=1794067200, last_active=1794067300, lineage_session_ids=['synthetic-parent', 'synthetic-child'],
        segments=[dict(id='synthetic-parent', messages=[dict(role='user', content='SYNTHETIC-PROMPT'),
            dict(role='assistant', content='SYNTHETIC-FAILED-APPROACH', tool_calls=[dict(name='fixture', arguments='synthetic')])]),
            dict(id='synthetic-child', messages=[dict(role='tool', name='fixture', content='SYNTHETIC-ERROR'),
                dict(role='assistant', content='SYNTHETIC-RESOLUTION')])])
    # Native writer inherits caller umask; require private output explicitly.
    previous = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix='shrr-native-export-fixture-') as folder:
            path = exporter.write_session_markdown(session, folder)
            text = path.read_text()
            exact = hashlib.sha256(path.read_bytes()).hexdigest()
            result = dict(contract='reporting-hermes-fixture.v1', exporter_sha256=digest,
                exporter_version=exporter.EXPORTER_VERSION, source_dictionary_only=True,
                real_sessions_read=False, paid_model_calls=0, credentials_read=False,
                exact_export_sha256=exact, native_verification=exporter.verify_export_file(path, session)[0],
                visible_exchange_retained=all(token in text for token in ['SYNTHETIC-PROMPT', 'SYNTHETIC-FAILED-APPROACH',
                    'SYNTHETIC-ERROR', 'SYNTHETIC-RESOLUTION']),
                tool_calls_retained='## Tool calls' in text, lineage_retained=all(x in text for x in session['lineage_session_ids']),
                output_private=path.stat().st_mode & 0o777 == 0o600,
                limitations=['Renderer fixture only; actual SessionDB export authorization and selected-source adapter remain.',
                    'No real compression recovery, installed gateway message delivery or secret-filtering guarantee.',
                    'Native export embeds export time; unchanged source should be deduplicated before rendering.'])
            if not all(result[k] for k in ['native_verification', 'visible_exchange_retained', 'tool_calls_retained', 'lineage_retained', 'output_private']):
                raise ValueError('native fixture export incomplete')
            path.write_text(text + 'SYNTHETIC-TAMPER\n')
            result['tampered_export_refused'] = not exporter.verify_export_file(path, session)[0]
        result['temporary_fixture_removed'] = not Path(folder).exists()
        return result
    finally: os.umask(previous)


if __name__ == '__main__':
    print(json.dumps(run('/opt/hermes/hermes_cli/session_export_md.py'), sort_keys=True))
