"""Protected-adapter semantics using fake root custody/service, never real sudo/API."""
import unittest
from unittest.mock import patch
import test_operator_control as fixtures

m=fixtures.m


class DocumentApprovalTests(unittest.TestCase):
    git=fixtures.OperatorTests.git
    bind=fixtures.OperatorTests.bind
    save_config=fixtures.OperatorTests.save_config
    candidate=fixtures.OperatorTests.candidate
    capture=fixtures.OperatorTests.capture
    legacy_approve=fixtures.OperatorTests.approve
    invoke=fixtures.OperatorTests.invoke
    assert_unconsumed=fixtures.OperatorTests.assert_unconsumed

    def setUp(self):
        fixtures.OperatorTests.setUp(self)
        p=patch.object(m,'require_operator',return_value=self.state)
        p.start();self.addCleanup(p.stop)
        self.d=m.local('document_approval')
        real=m.local
        p=patch.object(m,'local',side_effect=lambda name:self.d if name=='document_approval' else self.approval if name=='approval' else real(name))
        p.start();self.addCleanup(p.stop)
        real_doc=self.d.local
        p=patch.object(self.d,'local',side_effect=lambda name,family='rras_native':m if name=='operator_control' else
                       self.approval if name=='approval' and family=='rras_native' else real_doc(name,family))
        p.start();self.addCleanup(p.stop)
        real_approval=self.approval.local
        p=patch.object(self.approval,'local',side_effect=lambda name:self.d if name=='document_approval' else real_approval(name))
        p.start();self.addCleanup(p.stop)
        real_launch=self.l.local
        p=patch.object(self.l,'local',side_effect=lambda name:self.approval if name=='approval' else real_launch(name))
        p.start();self.addCleanup(p.stop)
        # No root ownership claim: only custody reads are replaced for disposable
        # files. Live admission, code hashing, document checks and fake launch run.
        p=patch.object(self.d,'private_read',side_effect=lambda path:self.a.load(path))
        p.start();self.addCleanup(p.stop)
        p=patch.object(self.d,'private_bytes',side_effect=lambda path:path.read_bytes())
        p.start();self.addCleanup(p.stop)
        self.captured=self.capture();self.rid=self.captured['review_id']
        w=self.work
        self.engineering={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'explicit-work',
            'expected_head':None,'source':{'kind':'agent_reported','namespace':'fixture','id':None},'occurred_at':None,
            'body':{'work_item_id':w['work_item_id'],'repository_id':w['repository_id'],'revision':1,
                'title':'Review fixture','objective':w['objective'],'rationale':'Preserve exact review intent',
                'acceptance_criteria':[{'id':'AC1','description':'Bound review bytes'}],
                'allowed_paths':w['requested_paths'],'baseline':w['baseline']}}
        self.narrative={key:'unknown' for key in self.d.local('managed_review','rras_history').NARRATIVE}
        self.docid='doc_'+'9'*32

    def prepare_document(self):
        return self.d.prepare(self.state,self.rid,self.config_path,self.engineering,self.narrative,self.docid)

    def approve_document(self,prepared=None):
        prepared=prepared or self.prepare_document()
        with patch.object(self.d.os,'getuid',return_value=0):
            return self.d.approve(self.state,self.rid,self.config_path,prepared['document_binding_sha256'],
                                  prepared['markdown_sha256'],approve_one_execution=True)

    def test_v2_review_approve_launch_replay_and_evidence(self):
        before=list(self.jobs.iterdir());prepared=self.prepare_document()
        self.assertEqual(prepared,self.prepare_document())
        view=self.d.view(self.state,self.rid,self.config_path)
        self.assertEqual(self.a.digest(view['markdown'].encode()),prepared['markdown_sha256'])
        self.assertFalse(view['execution_authorized']);self.assertEqual(list(self.jobs.iterdir()),before)
        auth=self.approve_document(prepared);self.assertEqual(auth['schema_version'],2)
        result,calls=self.invoke(auth['authorization_id'])
        self.assertTrue(result['host_stop_verified'])
        self.assertEqual(len([c for c in calls if c[0]=='/usr/bin/systemd-run']),1)
        self.assertEqual(m.evidence(self.state,auth['authorization_id'])['state'],'service_returned')
        with self.assertRaises(FileExistsError):self.invoke(auth['authorization_id'])

    def test_new_legacy_approval_refused_after_document_attached(self):
        self.prepare_document()
        with self.assertRaisesRegex(ValueError,'document-bound'):self.legacy_approve(self.rid)
        self.assertEqual(list(self.state.glob('*.approval.json')),[])

    def test_preexisting_legacy_authorization_retains_original_semantics(self):
        old=self.legacy_approve(self.rid);self.prepare_document()
        self.assertEqual(old['schema_version'],1)
        result,_=self.invoke(old['authorization_id']);self.assertTrue(result['host_stop_verified'])

    def test_explicit_approval_and_exact_both_digests_required(self):
        prepared=self.prepare_document()
        for binding,markdown,flag in ((prepared['document_binding_sha256'],prepared['markdown_sha256'],False),
                                     ('a'*64,prepared['markdown_sha256'],True),
                                     (prepared['document_binding_sha256'],'b'*64,True)):
            with self.assertRaises(ValueError):self.d.approve(self.state,self.rid,self.config_path,binding,markdown,approve_one_execution=flag)
        self.assertEqual(list(self.state.glob('*.approval.json')),[])

    def test_changed_package_refuses_before_consumption_or_fake_service(self):
        auth=self.approve_document();path=self.d.marker(self.state,self.rid);value=self.a.load(path)
        value['package']['markdown']+='altered';path.write_bytes(self.a.encoded(value))
        with self.assertRaises(ValueError):self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_missing_package_refuses_and_does_not_consume(self):
        auth=self.approve_document();self.d.marker(self.state,self.rid).unlink()
        with self.assertRaises(OSError):self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_changed_live_configuration_revokes_document_approval(self):
        prepared=self.prepare_document();self.config['hermes_project']='changed';self.save_config()
        with self.assertRaises(ValueError):self.approve_document(prepared)
        self.assertEqual(list(self.state.glob('*.approval.json')),[])

    def test_changed_live_configuration_revokes_before_consumption(self):
        auth=self.approve_document();self.config['hermes_project']='changed';self.save_config()
        with self.assertRaises(ValueError):self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_immutable_attachment_cannot_be_replaced_by_new_narrative(self):
        self.prepare_document();before=self.d.marker(self.state,self.rid).read_bytes()
        self.narrative['approach']='Changed proposal'
        with self.assertRaises(ValueError):self.prepare_document()
        self.assertEqual(self.d.marker(self.state,self.rid).read_bytes(),before)

    def test_wrong_engineering_identity_refused(self):
        self.engineering['body']['work_item_id']='wrk_'+'e'*32
        with self.assertRaisesRegex(ValueError,'identity'):self.prepare_document()
        self.assertFalse(self.d.marker(self.state,self.rid).exists())

    def test_v2_hash_mutation_and_version_downgrade_refused(self):
        auth=self.approve_document();path=self.state/(auth['authorization_id']+'.approval.json')
        for change in ({'markdown_sha256':'f'*64},{'schema_version':1},{'schema_version':3}):
            path.write_bytes(self.a.encoded(dict(auth,**change)))
            with self.assertRaises(ValueError):self.invoke(auth['authorization_id'])
            self.assert_unconsumed(auth['authorization_id'])

    def test_sibling_capture_cannot_use_other_document_approval(self):
        auth=self.approve_document()
        other=m.capture(self.config_path,self.proposals,self.candidate(),self.state,'codex/other')
        bad=dict(auth,review_id=other['review_id']);path=self.state/(auth['authorization_id']+'.approval.json')
        path.write_bytes(self.a.encoded(bad))
        with self.assertRaises(OSError):self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_busy_protocol_lock_preserves_approval_state(self):
        self.prepare_document()
        with self.approval.protocol_lock(self.state):
            with self.assertRaisesRegex(ValueError,'another approval'):self.approve_document()
        self.assertEqual(list(self.state.glob('*.approval.json')),[])

    def test_unprivileged_operator_denied(self):
        # Remove the unit fixture's operator adapter for this direct denial check.
        original=fixtures.ROOT/'operator_control.py'
        import importlib.util
        spec=importlib.util.spec_from_file_location('real_operator_boundary',original)
        real=importlib.util.module_from_spec(spec);spec.loader.exec_module(real)
        with patch.object(real.os,'getuid',return_value=1000),patch.object(real.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(ValueError,'root operator'):real.require_operator(self.state)

    def test_changed_markdown_sidecar_refuses_before_consumption(self):
        auth=self.approve_document();path=self.state/(self.rid+'.review.md');path.write_text('altered')
        with self.assertRaisesRegex(ValueError,'Markdown bytes'):self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_proposal_reader_refuses_nonregular_symlink_and_public_inputs(self):
        path=self.root/'proposal.json';path.write_text('{}');path.chmod(0o600)
        self.assertEqual(self.d.read_proposal(path),{})
        path.chmod(0o644)
        with self.assertRaises(ValueError):self.d.read_proposal(path)
        link=self.root/'link';link.symlink_to(path)
        with self.assertRaises(ValueError):self.d.read_proposal(link)
        import os
        fifo=self.root/'fifo';os.mkfifo(fifo,0o600)
        with self.assertRaises(ValueError):self.d.read_proposal(fifo)

    def test_proposal_reader_refuses_duplicate_and_oversized_json(self):
        path=self.root/'proposal.json';path.write_text('{"key":1,"key":2}');path.chmod(0o600)
        with self.assertRaises(ValueError):self.d.read_proposal(path)
        path.write_bytes(b' '* (128*1024+1))
        with self.assertRaises(ValueError):self.d.read_proposal(path)
