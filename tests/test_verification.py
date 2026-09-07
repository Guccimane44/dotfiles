import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('verifier',Path(__file__).resolve().parents[1]/'scripts/agent-verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

class VerificationTests(unittest.TestCase):
    def test_real_pass_failure_timeout_output_limit_and_missing_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for index, code, expected in [(0,'print("passed")','passed'),(1,'raise SystemExit(2)','failed'),
                                         (2,'import time; time.sleep(5)','failed'),(3,'print("x"*10000)','failed')]:
                result=v.execute([sys.executable,'-c',code],root,root/f'{index}.log',.3,limit=1000)
                self.assertEqual(result['result'],expected)
                self.assertLessEqual((root/f'{index}.log').stat().st_size,1000)
            self.assertEqual(v.execute(['/missing/command'],root,root/'missing.log',1)['reason'],'launch-failed')

    def test_changed_revision_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); file=root/'contract.json'
            data={'repository':v.s.REPO,'checks':[{'name':'fixture','command':[sys.executable,'-c','print("ok")']}]}
            file.write_text(json.dumps(data))
            with patch.object(v.a,'ROOT',root/'state'),patch.object(v.contract,'validate',return_value=[]),patch.object(v.s,'load',return_value={'jobs':{'1':{'status':'needs-review'}}}),patch.object(v.a,'read_state',return_value=(root/'task',{'workspace':str(root)})),patch.object(v.s,'review_snapshot',side_effect=[('before',{}),('after',{})]),contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(v.verify(1,file,2))
            report=json.loads(next((root/'task/verifications').glob('*/report.json')).read_text())
            self.assertEqual(report['status'],'failed')

    def test_result_tampering_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(v.a,'ROOT',Path(tmp)):
            directory=v.a.location(v.s.REPO,1)/'verifications'/('a'*32)
            directory.mkdir(parents=True);(directory/'0.log').write_text('altered')
            v.a.save(directory/'report.json',{'status':'passed','revision':'r','revision_after':'r',
                        'checks':[{'result':'passed','output':'0.log','output_sha256':'wrong'}]})
            with self.assertRaises(RuntimeError):v.s.require_verification(1,'a'*32,'r')

    def test_unknown_verification_cannot_be_accepted(self):
        with self.assertRaises(RuntimeError):v.s.require_verification(1,None,'r')

    def test_complete_verification_can_support_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(v.a,'ROOT',Path(tmp)/'state'):
            root=Path(tmp); work=root/'work'
            subprocess.run(['git','init','-b','task',str(work)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(work),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','fixture'],check=True,capture_output=True)
            folder=v.a.location(v.s.REPO,1)
            v.a.save(folder/'state.json',{'workspace':str(work),'attempts':0,'branch':'task','session_id':None})
            v.s.persist({'jobs':{'1':{'status':'needs-review'}}})
            file=root/'contract.json'
            file.write_text(json.dumps({'repository':v.s.REPO,'checks':[{'name':'fixture','command':[sys.executable,'-c','print("passed")']}]}))
            snap={'title':'fixture','body':'','comments':[]}
            with patch.object(v.contract,'validate',return_value=[]),patch.object(v.a,'snapshot',return_value=(snap,[])),contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(v.verify(1,file,2))
                report_path=next((folder/'verifications').glob('*/report.json'))
                report=json.loads(report_path.read_text())
                evidence=root/'review.json'
                evidence.write_text(json.dumps({'verification':report['id'],'revision':report['revision'],'summary':'Checked fixture',
                                'checks':[{'name':'Review','result':'passed','evidence':'Inspected fixture'}]}))
                v.s.record_review(1,evidence,'accept')
                self.assertEqual(v.s.load()['jobs']['1']['status'],'accepted')
