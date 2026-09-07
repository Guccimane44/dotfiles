#!/usr/bin/env python3
"""Explicit supervisor-run checks with durable results; no model calls or registration."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

s = module('scheduler', 'agent-scheduler.py')
a = s.a
contract = module('contract', 'project-contract.py')


def execute(command, cwd, output, seconds, lock_fd=None, limit=1024*1024, monitor=None):
    started = time.monotonic()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('OPENAI_API_KEY', None)
    result = {'command':command, 'result':'failed', 'reason':'launch-failed'}
    with output.open('xb') as log:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       start_new_session=True, pass_fds=() if lock_fd is None else (lock_fd,))
        except OSError as error:
            log.write(str(error).encode())
        else:
            reason = None
            size = 0
            next_monitor = started
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        if monitor and time.monotonic() >= next_monitor:
                            try: monitor()
                            except Exception:
                                reason = 'control-stop'; break
                            next_monitor = time.monotonic()+30
                        if time.monotonic()-started >= seconds:
                            reason = 'timeout'; break
                        events = selector.select(.1)
                        if not events: continue
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk: break
                        log.write(chunk[:max(0, limit-size)]); log.flush(); size += len(chunk)
                        if size > limit:
                            reason = 'output-limit'; break
                remaining = max(.01, seconds-(time.monotonic()-started))
                if reason is None:
                    try: process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired: reason = 'timeout'
            finally:
                # Kill descendants as well, even if the command's parent already exited.
                with contextlib.suppress(ProcessLookupError): os.killpg(process.pid, signal.SIGKILL)
                process.wait(); process.stdout.close()
            result.update(exit_code=process.returncode, reason=reason or 'completed',
                          result='passed' if reason is None and process.returncode == 0 else 'failed')
        log.flush(); os.fsync(log.fileno())
    result.update(elapsed_seconds=round(time.monotonic()-started, 3),
                  output=output.name, output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    return result


def verify(issue, file, seconds):
    data = json.loads(Path(file).read_text())
    errors = contract.validate(data)
    if errors: raise RuntimeError('; '.join(errors))
    if data['repository'] != s.REPO: raise RuntimeError('Only the dotfiles repository is authorized')
    with s.scheduler_lock(), a.lock() as lock_fd:
        job = s.load()['jobs'].get(str(issue), {})
        if job.get('status') not in ('needs-review', 'needs-approval'):
            raise RuntimeError('Only stopped task work can be verified')
        folder, worker = a.read_state(argparse.Namespace(repo=s.REPO, issue=issue))
        revision, _ = s.review_snapshot(issue)
        identifier = uuid.uuid4().hex
        destination = folder/'verifications'/identifier
        report = {'schema':1, 'id':identifier, 'revision':revision, 'status':'running',
                  'started_at':a.stamp(), 'contract':data, 'checks':[]}
        a.save(destination/'report.json', report)
        started = time.monotonic()
        try:
            for index, check in enumerate(data['checks']):
                remaining = seconds-(time.monotonic()-started)
                if remaining <= 0:
                    report['checks'].append({'name':check['name'], 'result':'failed', 'reason':'total-timeout'})
                    break
                result = execute(check['command'], worker['workspace'], destination/f'{index}.log', remaining, lock_fd)
                result['name'] = check['name']; report['checks'].append(result)
                a.save(destination/'report.json', report)
                if result['result'] != 'passed': break
            after, _ = s.review_snapshot(issue)
            report['status'] = ('passed' if after == revision and len(report['checks']) == len(data['checks'])
                                and all(c['result'] == 'passed' for c in report['checks']) else 'failed')
            report['revision_after'] = after
        except BaseException:
            report['status'] = 'interrupted'
            raise
        finally:
            report['finished_at'] = a.stamp()
            a.save(destination/'report.json', report)
        print(json.dumps({'verification':identifier, 'revision':revision, 'status':report['status'], 'report':str(destination/'report.json')}, indent=2))
        return report['status'] == 'passed'


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('issue', type=int); p.add_argument('--contract', required=True)
    p.add_argument('--seconds', type=int, default=300)
    args = p.parse_args()
    if args.issue < 1 or not 1 <= args.seconds <= 600: p.error('positive issue and 1–600 seconds required')
    return 0 if verify(args.issue, args.contract, args.seconds) else 1

if __name__ == '__main__':
    try: sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('agent-verify: '+str(error), file=sys.stderr); sys.exit(1)
