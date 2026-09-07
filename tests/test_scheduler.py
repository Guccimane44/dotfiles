import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scheduler', Path(__file__).resolve().parents[1]/'scripts/agent-scheduler.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        p = patch.object(s.a, 'ROOT', self.root); p.start(); self.addCleanup(p.stop)
        self.snap = {'state': 'open', 'labels': ['agent:ready'], 'title': 'Test', 'body': '', 'comments': []}
        for name, value in [('snapshot', (self.snap, [])), ('quota', {'rateLimits': {'primary': {'usedPercent': 0}}}), ('gh', json.dumps([[{'number': 5}]]))]:
            p = patch.object(s.a, name, return_value=value); p.start(); self.addCleanup(p.stop)
        self.pub = patch.object(s, 'publish'); self.publish = self.pub.start(); self.addCleanup(self.pub.stop)
        s.paths()[2].touch()

    def saved(self, attempts=0, session=None):
        path = s.a.location(s.REPO, 5)/'state.json'
        s.a.save(path, {'attempts': attempts, 'session_id': session, 'status': 'prepared'})
        return path

    def test_no_label_or_paused_never_runs(self):
        for labels in ([], ['agent:ready', 'agent:paused']):
            self.snap['labels'] = labels
            with patch.object(s.a, 'run') as run:
                s.tick(); run.assert_not_called()

    def test_disabled_is_noop(self):
        s.paths()[2].unlink()
        with patch.object(s.a, 'quota') as quota:
            s.tick(); quota.assert_not_called()

    def test_one_attempt_then_no_automatic_retry(self):
        path = self.saved()
        def run(args):
            s.a.save(path, {'attempts': 1, 'session_id': 'saved', 'status': 'interrupted'})
        with patch.object(s.a, 'run', side_effect=run) as worker:
            s.tick(); s.tick()
            self.assertEqual(worker.call_count, 1)
        self.assertEqual(s.load()['jobs']['5']['status'], 'needs-approval')
        s.approve(5)
        self.assertEqual(s.load()['jobs']['5']['status'], 'approved')

    def test_restart_reconciles_without_new_model_attempt(self):
        s.persist({'jobs': {'5': {'status': 'dispatching'}}})
        with patch.object(s.a, 'run') as run:
            s.tick(); run.assert_not_called()
        self.assertEqual(s.load()['jobs']['5']['status'], 'needs-approval')

    def test_quota_wait_survives_restart(self):
        with patch.object(s.a, 'quota', return_value={'rateLimits': {'primary': {'usedPercent': 99, 'resetsAt': 9999999999}}}), patch.object(s.a, 'run') as run:
            s.tick(); run.assert_not_called()
        self.assertGreater(s.load()['next_check'], 9999999999)
        with patch.object(s.a, 'quota') as quota:
            s.tick(); quota.assert_not_called()

    def test_wait_ignores_weekly_window_above_new_reserve(self):
        with patch.object(s.time, 'time', return_value=1000):
            self.assertEqual(s.wait_until({'rateLimits': {'primary': {'usedPercent':80, 'resetsAt':2000},
                                                         'secondary': {'usedPercent':90, 'resetsAt':9000}}}),2060)

    def test_policy_change_discards_old_wait_without_approving_work(self):
        s.persist({'jobs':{'5':{'status':'needs-approval'}},'next_check':9999999999,
                   'quota_policy':{'short_reserve':25,'weekly_reserve':25}})
        with patch.object(s.a, 'run') as run:
            s.tick(); run.assert_not_called()
        self.assertNotIn('next_check',s.load())
        self.assertEqual(s.load()['jobs']['5']['status'],'needs-approval')

    def test_unknown_quota_waits_without_model(self):
        with patch.object(s.a, 'quota', side_effect=RuntimeError('offline')), patch.object(s.a, 'run') as run:
            s.tick(); run.assert_not_called()
        self.assertIn('next_check', s.load())

    def test_api_failure_never_starts_work(self):
        with patch.object(s.a, 'gh', side_effect=RuntimeError('offline')), patch.object(s.a, 'run') as run:
            with self.assertRaises(RuntimeError): s.tick()
            run.assert_not_called()

    def test_publication_failure_preserves_consumed_authorization(self):
        self.saved()
        with patch.object(s, 'publish', side_effect=RuntimeError('offline')), patch.object(s.a, 'run') as run:
            with self.assertRaises(RuntimeError): s.tick()
            run.assert_not_called()
        self.assertEqual(s.load()['jobs']['5']['status'], 'needs-approval')

    def test_missing_session_cannot_be_approved(self):
        self.saved(attempts=1)
        s.persist({'jobs': {'5': {'status': 'needs-approval'}}})
        with self.assertRaises(RuntimeError): s.approve(5)

    def test_live_feedback_pause_and_quota_stop(self):
        baseline = s.fingerprint(self.snap)
        check = s.monitor(5, baseline)
        self.assertIsNone(check({}, {}))
        self.snap['comments'].append({'body': 'Change direction'})
        self.assertEqual(check({}, {}), 'feedback-received')
        self.snap['comments'] = []
        self.snap['labels'] = ['agent:paused']
        self.assertEqual(check({}, {}), 'paused')
        self.snap['labels'] = ['agent:ready']
        with patch.object(s.a, 'quota', return_value={}):
            self.assertEqual(check({}, {}), 'quota-or-account-unavailable')

    def test_manual_worker_lock_blocks_scheduler(self):
        with s.a.lock(), patch.object(s.a, 'run') as run:
            with self.assertRaises(RuntimeError): s.tick()
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
