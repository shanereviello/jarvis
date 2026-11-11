import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/hermes_capture_selection.py'
spec = importlib.util.spec_from_file_location('hermes_capture_selection', PATH)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
spec = importlib.util.spec_from_file_location('hermes_capture_workflow', PATH.with_name('n8n_hermes_capture_sessions.py'))
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
spec = importlib.util.spec_from_file_location('hermes_future_coordinator', PATH.with_name('hermes_future_coordinator.py'))
coordinator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinator)
spec = importlib.util.spec_from_file_location('hermes_future_transport', PATH.with_name('hermes_future_transport.py'))
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)

ORG = '00000000-0000-4000-8000-000000000001'
SESSION = '00000000-0000-4000-8000-000000000002'
ISSUE = '00000000-0000-4000-8000-000000000003'
CUTOFF = '2026-11-10T18:00:00Z'


def row(created='2026-11-10T18:00:01Z'):
    return dict(organization_id=ORG, agent_session_id=SESSION, issue_id=ISSUE,
                hermes_session_id='linear:' + ORG + ':' + SESSION, created_at=created)


class FutureSessionTests(unittest.TestCase):
    def test_metadata_reader_accepts_only_the_explicit_loopback_or_private_bridge(self):
        token = b'x' * 32
        route = '/webhook/rras-hermes-future-session-metadata'
        for host in ('127.0.0.1', '172.19.0.8'):
            with self.subTest(host=host):
                self.assertTrue(callable(transport.reader(f'http://{host}:5678{route}', token)))
        for host in ('127.0.0.2', '172.20.0.1', '192.168.30.3', 'localhost'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                transport.reader(f'http://{host}:5678{route}', token)
        for url in (f'http://127.0.0.1:5679{route}',
                    'http://127.0.0.1:5678/webhook/unrelated',
                    f'http://127.0.0.1:5678{route}?extra=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                transport.reader(url, token)

    def test_loopback_metadata_reader_sends_the_existing_authenticated_request(self):
        page = dict(contract='hermes-future-session-page.v1', sessions=[])
        cursor = dict(after_time=CUTOFF, after_id='00000000-0000-0000-0000-000000000000')
        class Response:
            status = 200
            def read(self, limit):
                return json.dumps(page).encode()
        class Connection:
            def __init__(self, host, port, timeout):
                self.address = (host, port, timeout)
                calls.append(self)
            def request(self, method, path, body, headers):
                self.requested = (method, path, json.loads(body), headers)
            def getresponse(self):
                return Response()
            def close(self):
                pass
        calls = []
        with patch.object(transport.http.client, 'HTTPConnection', Connection):
            query = transport.reader('http://127.0.0.1:5678' + transport.ROUTE, b'x' * 32)
            self.assertEqual(query(cursor), page)
        self.assertEqual(calls[0].address, ('127.0.0.1', 5678, 20))
        self.assertEqual(calls[0].requested[:3], ('POST', transport.ROUTE, cursor))
        self.assertEqual(calls[0].requested[3]['Authorization'], 'Bearer ' + 'x' * 32)

    def test_only_sessions_created_strictly_after_fixed_cutoff_are_eligible(self):
        for created in ('2026-11-10T17:59:59Z', CUTOFF):
            self.assertIsNone(selection.select(row(created), organization_id=ORG, cutoff=CUTOFF))
        self.assertEqual(selection.select(row(), organization_id=ORG, cutoff=CUTOFF), row())

    def test_spoofed_identity_and_noncanonical_metadata_are_rejected(self):
        for changes in (
            {'hermes_session_id': 'linear:' + ORG + ':' + ISSUE},
            {'organization_id': ISSUE}, {'issue_id': 'REV-34'},
            {'created_at': '2026-11-10T18:00:01'}, {'unexpected': 'value'},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                selection.select(dict(row(), **changes), organization_id=ORG, cutoff=CUTOFF)

    def test_cutoff_must_be_explicit_utc(self):
        for cutoff in ('2026-11-10', '2026-11-10T18:00:00+00:00', None):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                selection.select(row(), organization_id=ORG, cutoff=cutoff)

    def test_workflow_fixes_cutoff_and_never_selects_conversation_content(self):
        result = workflow.render(ORG, CUTOFF, 'readonly-postgres', 'private-header')
        self.assertFalse(result['active'])
        query = next(node['parameters']['query'] for node in result['nodes'] if node['type'] == 'n8n-nodes-base.postgres')
        self.assertIn("created_at>'" + CUTOFF + "'::timestamptz", query)
        self.assertIn("organization_id='" + ORG + "'", query)
        self.assertIn('LIMIT 4', query)
        self.assertNotIn('content', query.lower())
        self.assertEqual(result['settings']['saveDataSuccessExecution'], 'none')
        with self.assertRaises(ValueError):
            workflow.render(ORG, CUTOFF + "' OR true --", 'readonly-postgres', 'private-header')

    def test_whole_page_is_checked_before_opening_any_source(self):
        def page(rows):
            return dict(contract='hermes-future-session-page.v1', sessions=rows)
        args = dict(organization_id=ORG, cutoff=CUTOFF, after_time=CUTOFF,
                    after_id='00000000-0000-0000-0000-000000000000')
        self.assertEqual(selection.select_page(page([row()]), **args), [row()])
        for rows in ([row(), row()], [row(), row(CUTOFF)], [row(), dict(row(), issue_id='REV-34')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                selection.select_page(page(rows), **args)

    def test_coordinator_refuses_to_advance_on_unconfirmed_delivery(self):
        page = dict(contract='hermes-future-session-page.v1', sessions=[row()])
        cursor = dict(after_time=CUTOFF, after_id='00000000-0000-0000-0000-000000000000')
        worker = lambda request: dict(contract='hermes-future-capture-page.v1',
                                     sessions=[dict(session_id=SESSION, changed=True)], models_started=0)
        args = dict(organization_id=ORG, cutoff=CUTOFF, cursor=cursor, query=lambda _: page, worker=worker)
        with self.assertRaises(ValueError):
            coordinator.run_once(**args, flush=lambda: dict(failed=0, pending=1))
        result = coordinator.run_once(**args, flush=lambda: dict(failed=0, pending=0))
        self.assertEqual(result['cursor'], cursor)
        self.assertEqual(result['models_started'], 0)

    def test_interrupted_cursor_never_discards_conflicting_state(self):
        cursor = dict(after_time=CUTOFF, after_id='00000000-0000-0000-0000-000000000000')
        with tempfile.TemporaryDirectory() as root:
            coordinator.save_cursor(root, cursor)
            self.assertTrue((Path(root) / 'hermes-future-cursor.json').is_file())
            pending = Path(root) / 'hermes-future-cursor.pending'
            pending.write_bytes(b'conflicting cursor')
            pending.chmod(0o600)
            with self.assertRaises(ValueError):
                coordinator.save_cursor(root, cursor)
            self.assertEqual(pending.read_bytes(), b'conflicting cursor')

    def test_worker_uses_unmapped_category_and_checks_the_whole_page(self):
        calls = []
        def execute(argv, **kwargs):
            calls.append(argv)
            output = json.dumps(dict(session_id=SESSION, changed=True, models_started=0)).encode()
            return type('Result', (), dict(returncode=0, stdout=output))()
        worker = transport.existing_hermes_worker(organization_id=ORG, cutoff=CUTOFF, mappings={},
            authorization_reference='synthetic fixture', entry_source=b'synthetic', execute=execute)
        request = dict(page=dict(contract='hermes-future-session-page.v1', sessions=[row()]),
            after_time=CUTOFF, after_id='00000000-0000-0000-0000-000000000000')
        result = worker(request)
        self.assertEqual(result['models_started'], 0)
        self.assertEqual(calls[0][-4:-2], ['non_git', 'jarvis-non-git'])
        with self.assertRaises(ValueError):
            worker(dict(request, page=dict(contract='hermes-future-session-page.v1', sessions=[row(), row()])))
        self.assertEqual(len(calls), 1)



if __name__ == '__main__':
    unittest.main()
