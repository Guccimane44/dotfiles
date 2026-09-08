#!/usr/bin/env python3
"""Verified local runtime releases, activation, rollback, and health."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

spec=importlib.util.spec_from_file_location('scheduler',Path(__file__).with_name('agent-scheduler.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
a=s.a
HOME=Path.home()/'.local/share/agent-work'


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.relative_to(root).as_posix()!='release.json'}


def verify(release):
    release=Path(release).resolve(strict=True)
    data=json.loads((release/'release.json').read_text())
    if any(p.is_symlink() for p in release.rglob('*')):
        raise RuntimeError('Release contains a symlink')
    if data.get('schema') != 1 or not isinstance(data.get('revision'), str):
        raise RuntimeError('Unsupported release manifest')
    if not data['files'] or inventory(release)!=data['files']:
        raise RuntimeError('Runtime integrity check failed')
    return data


def build(source):
    source=Path(source).expanduser().resolve()
    if a.git(source,'status','--porcelain'):
        raise RuntimeError('Commit the reviewed source before building a runtime')
    revision=a.git(source,'rev-parse','HEAD')
    destination=HOME/'releases'/revision
    if destination.exists():
        verify(destination);return destination
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=destination.parent))
    try:
        raw=subprocess.check_output(['git','-C',str(source),'archive',revision,'scripts','tests','vendor','skills-lock.json'])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise RuntimeError('Only regular files/directories may enter a release')
            archive.extractall(stage,filter='data')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        checked=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-q'],cwd=stage,env=env,capture_output=True,text=True)
        if checked.returncode:raise RuntimeError('Release tests failed: '+checked.stdout+checked.stderr)
        a.save(stage/'release.json',{'schema':1,'revision':revision,'built_at':a.stamp(),'tests':'passed','files':inventory(stage)})
        verify(stage)
        for p in stage.rglob('*'):
            p.chmod(0o555 if p.is_dir() or os.access(p,os.X_OK) else 0o444)
        stage.chmod(0o555)
        stage.rename(destination)
    except BaseException:
        if stage.exists():
            for p in stage.rglob('*'):
                if p.is_dir():p.chmod(0o700)
            stage.chmod(0o700);shutil.rmtree(stage)
        raise
    return destination


def pointer(name, target):
    HOME.mkdir(parents=True,exist_ok=True)
    temporary=HOME/(name+'.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(HOME/name)


def select(release):
    release=Path(release).resolve(strict=True)
    if release.parent != (HOME/'releases').resolve():
        raise RuntimeError('Select a release built in the local release store')
    verify(release)
    current=HOME/'current'
    old=current.resolve() if current.exists() else None
    if old==release:return
    # No state migrations in schema 1; rollback shares the same compatible state.
    if old:pointer('previous',old)
    pointer('current',release)


def activate(release):
    with s.scheduler_lock(),a.lock():
        current = HOME/'current'
        previous = HOME/'previous'
        old = current.resolve() if current.exists() else None
        old_previous = previous.resolve() if previous.exists() else None
        select(release)
        # launchd executes this stable entry point, never the working checkout.
        entry=HOME/'launch.py'
        content='''import hashlib,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent
release=(root/'current').resolve(strict=True)
if release.parent != root/'releases': raise RuntimeError('Invalid active release')
meta=json.loads((release/'release.json').read_text())
files={str(p.relative_to(release)):hashlib.sha256(p.read_bytes()).hexdigest() for p in release.rglob('*') if p.is_file() and p.relative_to(release).as_posix()!='release.json'}
if any(p.is_symlink() for p in release.rglob('*')) or files != meta['files']: raise RuntimeError('Runtime integrity check failed')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['AGENT_WORK_DEPLOYED']='1'
os.execv(sys.executable,[sys.executable,str(release/'scripts/agent-work.py'),*sys.argv[1:]])
'''
        temp=entry.with_suffix('.new');temp.write_text(content);temp.chmod(0o444);temp.replace(entry)
        # This install is protected by both locks; no worker is killed during upgrade.
        try:
            s.install(entrypoint=entry)
        except BaseException:
            if old:
                pointer('current', old)
            else:
                current.unlink(missing_ok=True)
            if old_previous:
                pointer('previous', old_previous)
            else:
                previous.unlink(missing_ok=True)
            # Restore the previous runtime's service when activation failed.
            if old:
                try:
                    s.install(entrypoint=entry)
                except Exception as restore_error:
                    print('Service restoration failed: ' + str(restore_error), file=sys.stderr)
            raise
    print('Active runtime: '+str(release))


def rollback():
    previous=HOME/'previous'
    if not previous.exists():raise RuntimeError('No previous release available')
    activate(previous.resolve())


def health():
    result={'worker_limit':a.WORKER_LIMIT,'enabled':s.paths()[2].exists(),'quota_policy':s.QUOTA_POLICY,'problems':[]}
    try:
        release=(HOME/'current').resolve(strict=True)
        result['release']=verify(release)['revision']
    except (OSError,ValueError,RuntimeError) as error:result['problems'].append(str(error))
    for name in ('codex','gh','git'):
        try:result[name]=a.tool(name)
        except RuntimeError as error:result['problems'].append(str(error))
    try:
        state=s.load()
        result['jobs']={key:job['status'] for key,job in state['jobs'].items()}
        result['next_quota_check']=state.get('next_check')
    except (OSError,ValueError) as error:result['problems'].append('Unreadable scheduler state: '+str(error))
    heartbeat=s.paths()[0]/'heartbeat.json'
    if heartbeat.exists():
        data=json.loads(heartbeat.read_text());result['controller']=data
        if result['enabled'] and time.time()-data['epoch']>180:
            result['problems'].append('Controller heartbeat is older than three minutes')
        if data.get('status')=='error':result['problems'].append('Controller reported an error: '+data.get('detail',''))
    elif result['enabled']:result['problems'].append('No controller heartbeat recorded')
    service=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{s.SERVICE}'],capture_output=True,text=True)
    result['service_loaded']=service.returncode==0
    if result['enabled'] and service.returncode:result['problems'].append('Scheduler service is not loaded')
    print(json.dumps(result,indent=2))
    return not result['problems']


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','activate','rollback','health','verify'])
    parser.add_argument('path',nargs='?')
    args=parser.parse_args()
    if args.command in ('build','activate','verify') and not args.path:parser.error('This command needs a path')
    if args.command=='build':print(build(args.path))
    elif args.command=='activate':activate(args.path)
    elif args.command=='rollback':rollback()
    elif args.command=='health':return 0 if health() else 1
    elif args.command=='verify':print(json.dumps(verify(args.path),indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as error:
        print('agent-release: '+str(error),file=sys.stderr);sys.exit(1)
