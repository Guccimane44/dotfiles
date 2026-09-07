import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scheduler', Path(__file__).resolve().parents[1]/'scripts/agent-scheduler.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve(); self.work = self.root/'work'
        subprocess.run(['git', 'init', '-b', 'task', str(self.work)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.work), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'fixture'], check=True, capture_output=True)
        self.snap = {'title':'Task', 'body':'Outcome', 'comments':[], 'state':'open', 'labels':['agent:ready']}
        for obj, name, value in ((s.a, 'ROOT', self.root/'state'),):
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(s.a, 'snapshot', side_effect=lambda *_:(self.snap, [])); p.start(); self.addCleanup(p.stop)
        s.a.save(s.a.location(s.REPO, 1)/'state.json', {'workspace':str(self.work), 'attempts':1, 'session_id':'saved', 'branch':'task'})
        s.persist({'jobs':{'1':{'status':'needs-review'}}})
        self.evidence = self.root/'evidence.json'

    def evidence_for(self, result='passed'):
        revision, _ = s.review_snapshot(1)
        self.evidence.write_text(json.dumps({'revision':revision, 'summary':'Checked fixture; next step is review.',
                                           'checks':[{'name':'fixture check', 'result':result, 'evidence':'Observed expected fixture contents'}]}))

    def test_changed_untracked_content_or_feedback_invalidates_evidence(self):
        self.evidence_for()
        (self.work/'new.txt').write_text('new')
        with self.assertRaises(RuntimeError): s.record_review(1, self.evidence, 'accept')
        self.evidence_for()
        self.snap['comments'].append({'id':2, 'body':'Change direction'})
        with self.assertRaises(RuntimeError): s.record_review(1, self.evidence, 'retry')

    def test_acceptance_requires_passing_checks_and_records_revision(self):
        for result in ('failed', 'skipped'):
            self.evidence_for(result)
            with self.assertRaises(RuntimeError): s.record_review(1, self.evidence, 'accept')
        self.evidence_for()
        with contextlib.redirect_stdout(io.StringIO()): s.record_review(1, self.evidence, 'accept')
        job = s.load()['jobs']['1']
        self.assertEqual(job['status'], 'accepted')
        self.assertEqual(job['review']['revision'], s.review_snapshot(1)[0])

    def test_retry_requires_current_review(self):
        with self.assertRaises(RuntimeError): s.approve(1)
        self.evidence_for('failed')
        with contextlib.redirect_stdout(io.StringIO()): s.record_review(1, self.evidence, 'retry')
        (self.work/'changed').write_text('new work')
        with self.assertRaises(RuntimeError): s.approve(1)

    def test_approved_retry_revalidated_at_dispatch(self):
        self.evidence_for()
        with contextlib.redirect_stdout(io.StringIO()):
            s.record_review(1, self.evidence, 'retry'); s.approve(1)
        self.snap['body'] = 'Revised outcome'
        s.paths()[2].touch()
        with patch.object(s.a, 'gh', return_value='[[{"number":1}]]'), patch.object(s, 'publish'), patch.object(s.a, 'quota') as quota, patch.object(s.a, 'run') as worker:
            s.tick(); worker.assert_not_called(); quota.assert_not_called()
        self.assertEqual(s.load()['jobs']['1']['status'], 'needs-approval')

    def test_feedback_saved_before_stop(self):
        s.paths()[2].touch()
        check = s.monitor(1, s.fingerprint(self.snap))
        self.snap['comments'].append({'id':42, 'body':'Pause and rethink'})
        self.assertEqual(check({}, {}), 'feedback-received')
        saved = json.loads((s.a.location(s.REPO, 1)/'feedback.json').read_text())
        self.assertEqual(saved['comment_ids'], [42])

    def test_workpad_explicitly_acknowledges_detected_feedback(self):
        s.a.save(s.a.location(s.REPO, 1)/'feedback.json', {'detected_at':'fixture-time', 'comment_ids':[42]})
        with patch.object(s.a, 'gh', return_value='{"login":"operator"}'):
            s.publish(1, 'needs-approval', 'Stopped')
        body = json.loads((s.paths()[0]/'publication.json').read_text())['body']
        self.assertIn('Feedback acknowledged', body)
        self.assertIn('acknowledgment does not mean implementation', body)
        self.assertIn('42', body)


if __name__ == '__main__': unittest.main()
