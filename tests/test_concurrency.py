import contextlib
import importlib.util
import json
import os
import selectors
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('scheduler',Path(__file__).resolve().parents[1]/'scripts/agent-scheduler.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
a=s.a

class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        p=patch.object(a,'ROOT',self.root);p.start();self.addCleanup(p.stop)

    def test_four_distinct_workers_and_fifth_blocked(self):
        with contextlib.ExitStack() as stack:
            for number in range(1,5):stack.enter_context(a.task_lock('owner/repo',number))
            with self.assertRaises(a.WorkerBusy):
                with a.task_lock('owner/repo',5):pass
            with self.assertRaises(a.WorkerBusy):
                with a.task_lock('owner/repo',1,slot=False):pass
            with self.assertRaises(RuntimeError):
                with a.lock():pass
        with a.task_lock('owner/repo',5):pass
        with a.lock():pass

    def test_four_separate_processes_share_the_same_limit(self):
        script = """import importlib.util,sys
spec=importlib.util.spec_from_file_location('worker',sys.argv[1])
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
with a.task_lock('owner/repo',int(sys.argv[2])):
 print('ready',flush=True)
 sys.stdin.read()
"""
        children=[]
        try:
            for number in range(1,5):
                child=subprocess.Popen([sys.executable,'-c',script,str(Path(a.__file__).resolve()),str(number)],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    env=dict(os.environ,AGENT_WORK_STATE=str(self.root),PYTHONDONTWRITEBYTECODE='1'))
                children.append(child)
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout,selectors.EVENT_READ)
                    self.assertTrue(selector.select(5),'Child did not acquire its slot')
                    self.assertEqual(child.stdout.readline(),b'ready\n')
            with self.assertRaises(a.WorkerBusy):
                with a.task_lock('owner/repo',5):pass
        finally:
            for child in children:child.communicate(timeout=5)
        with a.task_lock('owner/repo',5):pass

    def test_distinct_issues_cannot_share_workspace(self):
        for number in (1,2):a.save(a.location('owner/repo',number)/'state.json',{'workspace':str(self.root/'same')})
        with a.task_lock('owner/repo',1):
            with self.assertRaises(a.WorkerBusy):
                with a.task_lock('owner/repo',2):pass

    def test_orphan_keeps_issue_slot_and_upgrade_locks(self):
        with a.task_lock('owner/repo',1) as fds:
            child=subprocess.Popen([sys.executable,'-c','import sys; sys.stdin.read()'],stdin=subprocess.PIPE,pass_fds=fds)
        try:
            with self.assertRaises(a.WorkerBusy):
                with a.task_lock('owner/repo',1):pass
            with contextlib.ExitStack() as stack:
                for number in (2,3,4):stack.enter_context(a.task_lock('owner/repo',number))
                with self.assertRaises(a.WorkerBusy):
                    with a.task_lock('owner/repo',5):pass
            with self.assertRaises(RuntimeError):
                with a.lock():pass
        finally:child.communicate(timeout=5)
        with a.lock():pass

    def test_scheduler_runs_four_in_parallel_and_preserves_all_results(self):
        for number in range(1,6):
            a.save(a.location(s.REPO,number)/'state.json',{'attempts':0,'session_id':None,'status':'prepared'})
        s.paths()[2].touch()
        barrier=threading.Barrier(4);seen=[];guard=threading.Lock()
        def worker(args):
            with a.task_lock(args.repo,args.issue):
                with guard:seen.append(args.issue)
                barrier.wait(timeout=5)
                a.save(a.location(args.repo,args.issue)/'state.json',{'attempts':1,'session_id':'saved','status':'needs-review'})
        snap={'state':'open','labels':['agent:ready'],'title':'fixture','body':'','comments':[]}
        with patch.object(a,'gh',return_value=json.dumps([[{'number':i} for i in range(1,6)]])),patch.object(a,'snapshot',return_value=(snap,[])),patch.object(a,'quota',return_value={'rateLimits':{'primary':{'usedPercent':0}}}),patch.object(a,'run',side_effect=worker),patch.object(s,'publish'):
            s.tick()
        self.assertEqual(sorted(seen),[1,2,3,4])
        self.assertEqual([s.load()['jobs'][str(i)]['status'] for i in range(1,5)],['needs-review']*4)
        self.assertNotIn('5',s.load()['jobs'])

    def test_capacity_does_not_consume_retry_authorization(self):
        with patch.object(a,'run',side_effect=a.WorkerBusy('full')):
            result=s.attempt(None,None,'approved')
        self.assertEqual(result['status'],'approved')

    def test_restart_leaves_live_issue_reserved(self):
        s.paths()[2].touch();s.persist({'jobs':{'1':{'status':'dispatching'}}})
        with a.task_lock(s.REPO,1),patch.object(a,'gh',return_value='[[]]'),patch.object(s,'publish'):
            s.tick()
        self.assertEqual(s.load()['jobs']['1']['status'],'dispatching')
