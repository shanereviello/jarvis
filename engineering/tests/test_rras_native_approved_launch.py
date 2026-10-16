import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_rras_native_approval as fixtures
ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
s=importlib.util.spec_from_file_location('launcher',ROOT/'approved_launch.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class SlotTests(unittest.TestCase):
    def test_busy_unknown_and_ambiguous_uid_refused(self):
        def reply(code,text):return SimpleNamespace(returncode=code,stdout=text)
        for state in (reply(0,'loaded'),reply(1,'not-found'),reply(0,'')):
            with self.assertRaises(ValueError):m.slot(lambda args:state)
        for processes in (reply(0,'123'),reply(2,'')):
            responses=iter((reply(0,'not-found'),processes))
            with self.assertRaises(ValueError):m.slot(lambda args:next(responses))
        responses=iter((reply(0,'not-found'),reply(1,'')));m.slot(lambda args:next(responses))
    def test_fixed_slot_and_credential_delivery_argv(self):
        r={'profile':'/profile','codex_config':'/config'}
        args=m.argv(Path('/work'),Path('/job'),r,Path('/private/key'))
        self.assertEqual(args[args.index('--unit')+1],'rras-coding-task.service')
        self.assertIn('KillMode=control-group',args);self.assertIn('ReadOnlyPaths=/srv/git',args)
        self.assertIn('CREDENTIALS_DIRECTORY=${CREDENTIALS_DIRECTORY}',args)
        self.assertEqual(args[args.index('--credential')+1],'${CREDENTIALS_DIRECTORY}/rras-api')
        self.assertNotIn('PrivateNetwork=yes',args)
        import argparse,textwrap
        code=(ROOT/'manual_runner.py').read_text().split("if __name__=='__main__':\n",1)[1].split("    if not args.authorize_one_paid_task",1)[0]
        ns={'argparse':argparse,'__doc__':'fixture'}
        with patch('sys.argv',['manual_runner.py',*args[args.index('--source'):]]):exec(textwrap.dedent(code),ns)
        self.assertTrue(ns['args'].authorize_one_paid_task)

class LaunchIntegrationTests(unittest.TestCase):
    setUp=fixtures.ApprovalTests.setUp
    proposal=fixtures.ApprovalTests.proposal
    capture=fixtures.ApprovalTests.capture
    def fixture(self):
        result=self.capture()
        with patch.object(m.os,'getuid',return_value=0):approval=m.local('approval').approve(self.state,result['review_id'])
        jobs=self.root/'jobs';jobs.mkdir();workers=self.root/'workers';workers.mkdir(mode=0o700)
        key=self.root/'key';key.write_text('harmless-not-a-provider-key');key.chmod(0o600)
        return approval['authorization_id'],jobs,workers,key
    def invoke(self,authorization,jobs,workers,key,fail=False):
        calls=[]
        def command(argv,timeout=30):
            calls.append(argv)
            if argv[0]=='/usr/bin/systemctl':return SimpleNamespace(returncode=0,stdout='not-found',stderr='')
            if argv[0]=='/usr/bin/pgrep':return SimpleNamespace(returncode=1,stdout='',stderr='')
            if fail:raise TimeoutError('lost service-client response fixture')
            return SimpleNamespace(returncode=0,stdout='fixture service response; no worker started',stderr='')
        with patch.object(m,'trusted',side_effect=lambda p:Path(p)),patch.object(m,'worker_root',return_value=workers),patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_name='fixture',pw_uid=996,pw_gid=996)),patch.object(m.os,'getgrouplist',return_value=[996]),patch.object(m.os,'chown'),patch.object(m,'command',side_effect=command):
            result=m.launch(self.state,authorization,jobs,workers,self.policy,key)
        return result,calls
    def test_approval_to_clone_request_and_service_contract(self):
        auth,jobs,workers,key=self.fixture();result,calls=self.invoke(auth,jobs,workers,key)
        self.assertTrue(result['host_stop_verified']);self.assertFalse(result['publication_authorized'])
        link=json.loads((self.state/(auth+'.launch.json')).read_text());job=Path(link['job'])
        self.assertEqual(json.loads((job/'request.json').read_text()),self.r)
        registry=json.loads((job/'registry.json').read_text());repo=Path(registry['repositories'][0]['path'])
        self.assertEqual(m.local('activity').git(repo,'remote').strip(),b'')
        self.assertEqual(m.local('activity').git(repo,'rev-parse','HEAD').decode().strip(),self.capture()['review']['baseline_commit'])
        self.assertNotEqual(repo,self.repo);self.assertEqual((job/'request.json').stat().st_mode&0o777,0o440)
        with self.assertRaises(FileExistsError):self.invoke(auth,jobs,workers,key)
        self.assertEqual(len(list(jobs.iterdir())),1)
    def test_lost_service_response_never_reuses_approval(self):
        auth,jobs,workers,key=self.fixture()
        with self.assertRaises(TimeoutError):self.invoke(auth,jobs,workers,key,fail=True)
        self.assertTrue((self.state/(auth+'.consumed.json')).exists());self.assertTrue((self.state/(auth+'.launch.json')).exists())
        with self.assertRaises(FileExistsError):self.invoke(auth,jobs,workers,key)
    def test_changed_profile_refused_before_consumption(self):
        auth,jobs,workers,key=self.fixture();self.profile.write_text('changed')
        with self.assertRaises(ValueError):self.invoke(auth,jobs,workers,key)
        self.assertFalse((self.state/(auth+'.consumed.json')).exists());self.assertEqual(list(jobs.iterdir()),[])

class AssignedBranchLaunchTests(unittest.TestCase):
    setUp=fixtures.ApprovalTests.setUp
    proposal=fixtures.ApprovalTests.proposal
    fixture=LaunchIntegrationTests.fixture
    invoke=LaunchIntegrationTests.invoke
    def capture(self):
        return m.local('approval').capture(self.proposals,self.proposal(),self.policy,self.registry,self.state,self.profile,self.codex,review_branch='codex/docs-task')
    def test_operator_branch_retained_in_launch_and_result(self):
        auth,jobs,workers,key=self.fixture();result,_=self.invoke(auth,jobs,workers,key)
        self.assertEqual(result['review_branch'],'codex/docs-task')
        self.assertEqual(json.loads((self.state/(auth+'.launch.json')).read_text())['review_branch'],'codex/docs-task')

    def test_named_dev_baseline_is_the_actual_worker_clone_head(self):
        a=m.local('activity');head=a.git(self.repo,'rev-parse','HEAD').decode().strip()
        a.git(self.repo,'checkout','-qb','dev');(self.repo/'code.py').write_text('dev baseline\n');a.git(self.repo,'add','code.py')
        a.git(self.repo,'-c','user.name=Fixture','-c','user.email=f@localhost','commit','-qm','dev')
        dev=a.git(self.repo,'rev-parse','HEAD').decode().strip();a.git(self.repo,'checkout','--detach',head)
        def capture():return m.local('approval').capture(self.proposals,self.proposal(),self.policy,self.registry,self.state,self.profile,self.codex,baseline_ref='refs/heads/dev',expected_baseline=dev,review_branch='codex/docs-task')
        self.capture=capture
        auth,jobs,workers,key=self.fixture();result,_=self.invoke(auth,jobs,workers,key)
        registry=json.loads((Path(result['job'])/'registry.json').read_text());clone=Path(registry['repositories'][0]['path'])
        self.assertEqual(a.git(clone,'rev-parse','HEAD').decode().strip(),dev)
        self.assertEqual(a.git(self.repo,'rev-parse','HEAD').decode().strip(),head)

class BundleSourceCleanupTests(unittest.TestCase):
    setUp=fixtures.ApprovalTests.setUp
    proposal=fixtures.ApprovalTests.proposal
    capture=fixtures.ApprovalTests.capture
    fixture=LaunchIntegrationTests.fixture
    invoke=LaunchIntegrationTests.invoke
    def test_private_source_bundle_removed_and_source_unchanged(self):
        baseline=m.local('activity').git(self.repo,'rev-parse','HEAD')
        auth,jobs,workers,key=self.fixture();result,_=self.invoke(auth,jobs,workers,key)
        self.assertFalse(list(Path(result['job']).glob('.source-*')))
        self.assertEqual(m.local('activity').git(self.repo,'rev-parse','HEAD'),baseline)
