#!/usr/bin/env python3
"""Six authorized attempts, matched deliverables; no retries or implicit reruns."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

spec=importlib.util.spec_from_file_location('prior',Path(__file__).with_name('run-harness-pilot.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
a=p.a;v=p.v
ROOT=Path.home()/'.local/state/agent-work/evaluations/lean-pilot-2026-09-08'


def continuation_keys(result):
    rows=result.get('attempts',[])
    keys={(r['fixture'],r['condition']) for r in rows}
    if result.get('status')!='stopped' or len(rows)>6 or len(keys)!=len(rows) or any(r.get('status')!='needs-review' for r in rows):
        raise RuntimeError('Only unstarted conditions may continue; started/interrupted attempts need review')
    return keys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--continue-unstarted',action='store_true')
    args=parser.parse_args()
    os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
    ledger=ROOT/'results.json'
    lockfile=(ROOT/'pilot.lock').open('a')
    import fcntl
    fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if args.continue_unstarted:
        result=json.loads(ledger.read_text())
        finished=continuation_keys(result)
        result['status']='running'
        result.setdefault('continuations',[]).append({'at':a.stamp(),'reserve':25,
            'source_revision':a.git(p.BASE,'rev-parse','HEAD'),'previous_error':result.pop('error',None)})
    else:
        # Atomic reservation prevents replay of the allowance.
        fd=os.open(ROOT/'reserved',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        result={'model':a.MODEL,'cli':a.call([a.tool('codex'),'--version']),
                'source_revision':a.git(p.BASE,'rev-parse','HEAD'),'attempt_cap':6,'attempt_seconds':300,
                'attempts':[],'status':'running','started_at':a.stamp()}
        finished=set()
    result['short_reserve']=25;result['weekly_reserve']=3
    a.save(ledger,result)
    original=a.snapshot
    try:
        for index,(name,task,source,grader) in enumerate(p.FIXTURES):
            test=grader+'\nif __name__=="__main__": unittest.main()\n'
            for condition in (['lean','standard'] if index%2==0 else ['standard','lean']):
                if (name,condition) in finished:continue
                a.quota_guard(a.quota(),25,3)
                folder=ROOT/f'{index}-{condition}';work=folder/'work';work.mkdir(parents=True)
                (work/'task.py').write_text(source);(work/'test_task.py').write_text(test)
                (work/'.gitignore').write_text('.agent-work/\n__pycache__/\n')
                for cmd in [['git','init','-b','pilot',str(work)],['git','-C',str(work),'add','.'],
                            ['git','-C',str(work),'-c','user.name=Pilot','-c','user.email=pilot@example.invalid','commit','-m','Matched fixture']]:
                    subprocess.run(cmd,check=True,capture_output=True)
                number=index*2+(1 if condition=='lean' else 2)
                statefolder=a.location('pilot/lean-comparison',number)
                if (statefolder/'state.json').exists():raise RuntimeError('Existing fixture state; refusing overwrite')
                (work/'.agent-work').mkdir();(work/'.agent-work/checkpoint.md').write_text('Not started. Next: implement task.py and run provided tests.\n')
                a.save(statefolder/'state.json',{'workspace':str(work),'branch':'pilot','attempts':0,'session_id':None})
                snap={'title':name,'body':'Fix only task.py. '+task+' Required verification: run python3 -B -m unittest -v test_task and git diff --check. Do not add or change test files. Do not browse or install dependencies. Workflow recovery files are permitted.',
                      'state':'open','labels':[],'comments':[],'url':'local fixture'}
                a.snapshot=lambda *_:(snap,[])
                row={'fixture':name,'condition':condition,'status':'started','usage':None,
                     'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'tests_sha256':hashlib.sha256(test.encode()).hexdigest(),'started_at':a.stamp()}
                result['attempts'].append(row);a.save(ledger,result)
                def monitor(*_):
                    try:a.quota_guard(a.quota(),25,3)
                    except Exception:return 'quota-or-account-unavailable'
                started=time.monotonic()
                a.run(argparse.Namespace(repo='pilot/lean-comparison',issue=number,minutes=5,reserve=25,weekly_reserve=3,workflow=condition,monitor=monitor))
                saved=json.loads((statefolder/'state.json').read_text())
                row.update(status=saved['status'],usage=saved.get('last_usage'),session_id=saved.get('session_id'),elapsed_seconds=round(time.monotonic()-started,3))
                row['tests_unchanged']=(work/'test_task.py').read_text()==test
                row['extra_files']=a.git(work,'ls-files','--others','--exclude-standard').splitlines()
                (folder/'grade.py').write_text('import sys\nsys.path.insert(0,'+repr(str(work))+')\n'+grader+'\nunittest.main()\n')
                grade=v.execute([sys.executable,str(folder/'grade.py')],folder,folder/'grade.log',10)
                row['correct']=grade['result']=='passed' and row['tests_unchanged'] and not row['extra_files']
                row['grader_output']=(folder/'grade.log').read_text()
                a.save(ledger,result)
                print(json.dumps({k:row[k] for k in ['fixture','condition','status','usage','correct']}),flush=True)
                if saved['status']!='needs-review':raise RuntimeError('Attempt stopped; no automatic retry or replacement')
        result['status']='complete'
    except BaseException as error:
        result.update(status='stopped',error=str(error));raise
    finally:
        a.snapshot=original;result['finished_at']=a.stamp();a.save(ledger,result);lockfile.close()

if __name__=='__main__':main()
