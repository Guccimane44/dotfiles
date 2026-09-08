#!/usr/bin/env python3
"""One authorized six-attempt pilot. Fixed ledger prevents silent reruns."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,BASE/'scripts'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
v=load('verify','agent-verify.py');a=v.a
ROOT=Path.home()/'.local/state/agent-work/evaluations/harness-pilot-2026-09-08'
FIXTURES=[
 ('duration', 'Implement parse_duration(value): accept only strings containing a nonnegative integer followed by ms, s or m (case insensitive, surrounding whitespace allowed). Return integer milliseconds. All other inputs, including floats, signs, booleans, empty strings and missing units, raise ValueError.',
  'def parse_duration(value):\n    return int(value[:-1]) * 1000\n',
  '''import unittest
from task import parse_duration
class T(unittest.TestCase):
 def test_values(self):
  for value, expected in [('12ms',12),('2s',2000),('3m',180000),(' 0MS ',0),('004s',4000)]:
   with self.subTest(value=value): self.assertEqual(parse_duration(value),expected)
 def test_invalid(self):
  for value in [None,True,3,'','1','-1s','+1s','1.5s','2h','1 s','1ss']:
   with self.subTest(value=value):
    with self.assertRaises(ValueError):parse_duration(value)
'''),
 ('dedupe', 'Implement dedupe_jobs(jobs): keep the first job for each id in input order; preserve distinct typed identifiers (1 and "1" are different). IDs must be strings or integers, excluding bool. Skip records with missing or invalid ids. Do not mutate the input or its dictionaries. Input is a list of dictionaries.',
  'def dedupe_jobs(jobs):\n    return list({str(job["id"]): job for job in jobs}.values())\n',
  '''import unittest,copy
from task import dedupe_jobs
class T(unittest.TestCase):
 def test_order_types_and_first(self):
  source=[{'id':1,'v':'first'},{'id':'1'},{'id':1,'v':'last'},{'id':2}]
  old=copy.deepcopy(source);self.assertEqual(dedupe_jobs(source),[source[0],source[1],source[3]]);self.assertEqual(source,old)
 def test_invalid(self):
  self.assertEqual(dedupe_jobs([{}, {'id':True},{'id':None},{'id':[]},{'id':1.0}]),[])
 def test_empty(self):self.assertEqual(dedupe_jobs([]),[])
'''),
 ('retry', 'Implement retry_delay(attempt, base=2, cap=60): attempt is a positive integer excluding bool; base and cap are positive integers excluding bool. Invalid arguments raise ValueError. Return min(cap, base * 2**(attempt-1)). Very large attempts such as 10**9 must return promptly without huge integer allocation.',
  'def retry_delay(attempt, base=2, cap=60):\n    return min(cap,base*2**attempt)\n',
  '''import unittest
from task import retry_delay
class T(unittest.TestCase):
 def test_delays(self):
  for args,expected in [((1,),2),((2,),4),((6,),60),((1,100,60),60),((4,3,100),24),((10**9,),60)]:
   with self.subTest(args=args):self.assertEqual(retry_delay(*args),expected)
 def test_invalid(self):
  for args in [(0,),(-1,),(True,),(1.5,),(1,0),(1,2,False),(1,2,-1)]:
   with self.subTest(args=args):
    with self.assertRaises(ValueError):retry_delay(*args)
''')]


def main():
    os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
    ledger=ROOT/'results.json'
    if ledger.exists():raise RuntimeError('Pilot ledger already exists; no automatic reruns or additional attempts')
    result={'model':a.MODEL,'cli':a.call([a.tool('codex'),'--version']), 'attempt_cap':6,'attempt_seconds':300,
            'started_at':a.stamp(),'attempts':[],'status':'running'}
    a.save(ledger,result)
    original_snapshot=a.snapshot
    try:
        for index,(name,task,source,grader) in enumerate(FIXTURES):
            for condition in (['raw','harness'] if index%2==0 else ['harness','raw']):
                a.quota_guard(a.quota(),25,3)
                folder=ROOT/f'{index}-{condition}';workspace=folder/'work';workspace.mkdir(parents=True)
                (workspace/'task.py').write_text(source)
                (workspace/'.gitignore').write_text('.agent-work/\n__pycache__/\n')
                subprocess.run(['git','init','-b','pilot',str(workspace)],check=True,capture_output=True)
                subprocess.run(['git','-C',str(workspace),'add','.'],check=True,capture_output=True)
                subprocess.run(['git','-C',str(workspace),'-c','user.name=Pilot','-c','user.email=pilot@example.invalid','commit','-m','Fixture'],check=True,capture_output=True)
                snap={'title':name,'body':'Fix task.py. '+task,'state':'open','labels':[],'comments':[],'url':'local fixture'}
                attempt={'fixture':name,'condition':condition,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                         'status':'started','started_at':a.stamp(),'usage':None}
                result['attempts'].append(attempt);a.save(ledger,result)
                started=time.monotonic()
                if condition=='harness':
                    number=index+1;statefolder=a.location('pilot/fixture',number)
                    if (statefolder/'state.json').exists():raise RuntimeError('Fixture state already exists; refusing overwrite')
                    (workspace/'.agent-work').mkdir();(workspace/'.agent-work/checkpoint.md').write_text('Not started. Next: inspect task.py, implement the specification and verify it.\n')
                    a.save(statefolder/'state.json',{'workspace':str(workspace),'branch':'pilot','attempts':0,'session_id':None})
                    a.snapshot=lambda *_:(snap,[])
                    def monitor(*_):
                        try:a.quota_guard(a.quota(),25,3)
                        except Exception:return 'quota-or-account-unavailable'
                    a.run(argparse.Namespace(repo='pilot/fixture',issue=number,minutes=5,reserve=25,weekly_reserve=3,monitor=monitor,workflow="standard"))
                    saved=json.loads((statefolder/'state.json').read_text())
                    attempt.update(status=saved['status'],usage=saved.get('last_usage'),session_id=saved.get('session_id'))
                    attempt['checkpoint_written']=(workspace/'.agent-work/checkpoint.md').read_text()!='Not started. Next: inspect task.py, implement the specification and verify it.\n'
                else:
                    prompt='Fix task.py. '+task+' Work only in this fixture. Do not install tools, browse, spawn agents, or make external mutations. Finish with a brief summary.'
                    command=[a.tool('codex'),'exec','--sandbox','workspace-write','--ignore-user-config','-c','sandbox_mode="workspace-write"','-c','approval_policy="never"','-c','model_reasoning_effort="medium"','--model',a.MODEL,'--json',prompt]
                    with a.lock() as fd:
                        ran=v.execute(command,workspace,folder/'events.jsonl',300,fd,limit=8*1024*1024,monitor=lambda:a.quota_guard(a.quota(),25,3))
                    attempt['status']=ran['reason'] if ran['result']=='failed' else 'completed'
                    for line in (folder/'events.jsonl').read_text(errors='replace').splitlines():
                        try:event=json.loads(line)
                        except ValueError:continue
                        if event.get('type')=='turn.completed':attempt['usage']=event.get('usage')
                        if event.get('type')=='thread.started':attempt['session_id']=event.get('thread_id')
                attempt['elapsed_seconds']=round(time.monotonic()-started,3)
                # Hidden grader is supplied after the model attempt and run externally.
                (folder/'grade.py').write_text('import sys\nsys.path.insert(0,'+repr(str(workspace))+')\n'+grader+'\nunittest.main()\n')
                grade=v.execute([sys.executable,str(folder/'grade.py')],folder,folder/'grade.log',10)
                attempt['correct']=grade['result']=='passed'
                attempt['grader_output']=(folder/'grade.log').read_text()
                a.save(ledger,result)
                print(json.dumps({k:attempt[k] for k in ('fixture','condition','status','correct','elapsed_seconds','usage')}),flush=True)
                if attempt['status'] not in ('completed','needs-review'):raise RuntimeError('Attempt stopped; no extra attempts or automatic retries')
        result['status']='complete'
    except BaseException as error:
        result.update(status='stopped',error=str(error));raise
    finally:
        a.snapshot=original_snapshot;result['finished_at']=a.stamp();a.save(ledger,result)

if __name__=='__main__':main()
