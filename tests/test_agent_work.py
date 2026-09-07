import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('agent_work', Path(__file__).resolve().parents[1] / 'scripts/agent-work.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class InfrastructureTests(unittest.TestCase):
    def test_path_validation(self):
        for repo in ('../../other', '../repo', 'owner/..', '/tmp/repo', 'a/b/c', 'a b/c'):
            with self.assertRaises(RuntimeError): a.location(repo, 1)
        with self.assertRaises(RuntimeError): a.location('owner/repo', 0)

    def test_weekly_three_percent_boundary_preserves_short_window(self):
        a.quota_guard({'rateLimits': {'primary': {'usedPercent': 74, 'windowDurationMins': 300},
                                     'secondary': {'usedPercent': 96, 'windowDurationMins': 10080}}}, 25)
        for primary, secondary in ((75, 90), (20, 97)):
            with self.assertRaises(RuntimeError):
                a.quota_guard({'rateLimits': {'primary': {'usedPercent': primary},
                                             'secondary': {'usedPercent': secondary}}}, 25)
        self.assertEqual(a.window_reserve({'windowDurationMins':10080},'primary',25),3)
        self.assertEqual(a.window_reserve({'windowDurationMins':300},'secondary',25),25)

    def test_unknown_quota_is_not_permission(self):
        with self.assertRaises(RuntimeError): a.quota_guard({}, 15)

    def test_secondary_exhaustion_blocks_dispatch(self):
        data = {'rateLimits': {'primary': {'usedPercent': 10}, 'secondary': {'usedPercent': 99}}}
        with self.assertRaises(RuntimeError): a.quota_guard(data, 15)
        a.quota_guard({'rateLimits': {'primary': {'usedPercent': 20}}}, 15)

    def test_paused_or_closed_issue_blocks_dispatch(self):
        for item in ({'state': 'closed', 'labels': []}, {'state': 'open', 'labels': ['agent:paused']}):
            with self.assertRaises(RuntimeError): a.eligible(item)

    def test_lock_blocks_second_process(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            with a.lock():
                code = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
                p = subprocess.run(['python3', '-c', code, str(Path(tmp)/'worker.lock')], capture_output=True)
                self.assertNotEqual(p.returncode, 0)

    def test_interrupted_run_keeps_session_and_next_run_resumes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)/'state'):
            work = Path(tmp)/'repo'; work.mkdir()
            subprocess.run(['git', 'init', '-b', 'agent/issue-1', str(work)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(work), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'Fixture'], check=True, capture_output=True)
            (work/'.agent-work').mkdir()
            (work/'.agent-work/checkpoint.md').write_text('Completed investigation. Next: edit code.')
            folder = a.location('owner/repo', 1)
            a.save(folder/'state.json', {'workspace': str(work), 'branch': 'agent/issue-1', 'attempts': 0, 'session_id': None})
            fake = Path(tmp)/'codex'
            fake.write_text('#!/usr/bin/env python3\nimport sys,json\nsys.stdin.read()\nif "resume" not in sys.argv:\n print(json.dumps({"type":"thread.started","thread_id":"saved-session"}),flush=True)\n print(json.dumps({"type":"turn.failed","error":{"message":"quota exceeded"}}),flush=True)\n sys.exit(1)\nassert "saved-session" in sys.argv\nprint(json.dumps({"type":"turn.completed","usage":{"output_tokens":10}}),flush=True)\n')
            fake.chmod(0o700)
            args = argparse.Namespace(repo='owner/repo', issue=1, minutes=1, reserve=15)
            with patch.object(a, 'tool', return_value=str(fake)), patch.object(a, 'quota', return_value={'rateLimits': {'primary': {'usedPercent': 0}}}), patch.object(a, 'snapshot', return_value=({'state': 'open', 'labels': []}, [])), contextlib.redirect_stdout(io.StringIO()):
                a.run(args)
                state = json.loads((folder/'state.json').read_text())
                self.assertEqual(state['status'], 'interrupted')
                self.assertEqual(state['session_id'], 'saved-session')
                a.run(args)
                state = json.loads((folder/'state.json').read_text())
                self.assertEqual(state['status'], 'needs-review')
                self.assertEqual(state['attempts'], 2)
            self.assertEqual(len(state['history']), 2)
            self.assertFalse(state['history'][0]['usage_complete'])
            self.assertTrue(state['history'][1]['usage_complete'])
            self.assertEqual(state['history'][1]['usage'], {'output_tokens': 10})
            self.assertIn('Completed investigation', json.loads((folder/'checkpoint-2-before.json').read_text())['text'])
            self.assertIn('Completed investigation', json.loads((folder/'checkpoint-2-after.json').read_text())['text'])
            self.assertIn('Completed investigation', (work/'.agent-work/checkpoint.md').read_text())

    def test_worker_inherits_lock_after_parent_releases_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            with a.lock() as fd:
                child = subprocess.Popen(['python3', '-c', 'import sys; sys.stdin.read()'],
                                         stdin=subprocess.PIPE, pass_fds=(fd,))
            try:
                with self.assertRaises(RuntimeError):
                    with a.lock(): pass
            finally:
                child.communicate(timeout=5)
            with a.lock(): pass

    def test_feedback_stops_real_child_and_preserves_session(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)/'state'):
            work=Path(tmp)/'repo'; work.mkdir(); (work/'.agent-work').mkdir()
            (work/'.agent-work/checkpoint.md').write_text('Durable checkpoint')
            folder=a.location('owner/repo',1)
            a.save(folder/'state.json',{'workspace':str(work),'branch':'agent/issue-1','attempts':0,'session_id':None})
            fake=Path(tmp)/'codex'
            fake.write_text('#!/usr/bin/env python3\nimport json,time,sys\nsys.stdin.read()\nprint(json.dumps({"type":"thread.started","thread_id":"preserved"}),flush=True)\ntime.sleep(60)\n')
            fake.chmod(0o700)
            args=argparse.Namespace(repo='owner/repo',issue=1,minutes=1,reserve=25,monitor=lambda *_:'feedback-received')
            with patch.object(a,'tool',return_value=str(fake)), patch.object(a,'git',side_effect=lambda path,*args:'agent/issue-1' if args[0]=='branch' else 'abc'), patch.object(a,'quota',return_value={'rateLimits':{'primary':{'usedPercent':0}}}), patch.object(a,'snapshot',return_value=({'state':'open','labels':[]},[])), contextlib.redirect_stdout(io.StringIO()):
                a.run(args)
            state=json.loads((folder/'state.json').read_text())
            self.assertEqual(state['status'],'feedback-received')
            self.assertEqual(state['session_id'],'preserved')
            self.assertLess(state['last_elapsed_seconds'],15)
            self.assertFalse(state['history'][0]['usage_complete'])
            self.assertIn('feedback-received',(work/'.agent-work/stop-request.txt').read_text())
            self.assertEqual((work/'.agent-work/checkpoint.md').read_text(),'Durable checkpoint')

    def test_failed_launch_retains_attempt_and_unknown_usage(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)/'state'):
            work = Path(tmp)/'repo'; work.mkdir(); (work/'.agent-work').mkdir()
            (work/'.agent-work/checkpoint.md').write_text('Saved milestone')
            folder = a.location('owner/repo', 1)
            a.save(folder/'state.json', {'workspace': str(work), 'branch': 'branch',
                                        'attempts': 0, 'session_id': None, 'last_usage': {'output_tokens': 999}})
            args = argparse.Namespace(repo='owner/repo', issue=1, minutes=1, reserve=25)
            with patch.object(a, 'git', return_value='branch'), patch.object(a, 'tool', return_value='/missing/codex'), patch.object(a, 'quota', return_value={'rateLimits': {'primary': {'usedPercent': 0}}}), patch.object(a, 'snapshot', return_value=({'state': 'open', 'labels': []}, [])):
                with self.assertRaises(OSError): a.run(args)
            state = json.loads((folder/'state.json').read_text())
            self.assertEqual(state['attempts'], 1)
            self.assertEqual(state['history'][0]['status'], 'launch-failed')
            self.assertIsNone(state['history'][0]['usage'])
            self.assertNotIn('last_usage', state)
            self.assertEqual(json.loads((folder/'checkpoint-1-before.json').read_text())['text'], 'Saved milestone')

    def test_atomic_state_has_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            a.save(path, {'session_id': 'one'}); a.save(path, {'session_id': 'two'})
            self.assertEqual(json.loads(path.read_text())['session_id'], 'two')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_suffix('.tmp').exists())


if __name__ == '__main__': unittest.main()
