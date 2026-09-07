#!/usr/bin/env python3
"""Single-Mac, opt-in issue dispatch. No automatic retries of started attempts."""
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('agent_work', Path(__file__).with_name('agent-work.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
REPO = 'Guccimane44/dotfiles'
SOURCE = Path.home() / '.dotfiles'
# One fixed lock/state domain on this Mac, shared with the manual launcher.
a.ROOT = Path.home() / '.local/state/agent-work'
SERVICE = 'local.agent-work.scheduler'


def paths():
    root = a.ROOT / 'scheduler'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root, root / 'state.json', root / 'enabled'


def load():
    _, path, _ = paths()
    return json.loads(path.read_text()) if path.exists() else {'jobs': {}}


def persist(state):
    a.save(paths()[1], state)


@contextlib.contextmanager
def scheduler_lock():
    with (paths()[0] / 'scheduler.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Scheduler is already active')
        yield


def fingerprint(snap):
    return json.dumps({k: snap.get(k) for k in ('title', 'body', 'comments')}, sort_keys=True)


def allowed(snap):
    a.eligible(snap)
    if 'agent:ready' not in snap['labels']:
        raise RuntimeError('agent:ready label is required')


def wait_until(data):
    now = time.time()
    buckets = data.get('rateLimitsByLimitId') or {'codex': data.get('rateLimits')}
    resets = [w.get('resetsAt') for b in buckets.values() if b
              for k in ('primary', 'secondary') for w in [b.get(k)]
              if w and w.get('usedPercent', 0) is not None and w.get('usedPercent', 0) >= 75]
    return max([now + 300] + [r + 60 if isinstance(r, (int, float)) else now + 3600 for r in resets])


def publish(issue, status, note):
    """Only one workpad per authenticated owner, with bounded checkpoint text."""
    snap, comments = a.snapshot(REPO, issue)
    me = json.loads(a.gh('api', 'user'))['login']
    own = [c for c in comments if a.MARKER in (c.get('body') or '') and c['user']['login'] == me]
    if len(own) > 1:
        raise RuntimeError('Multiple workpads need manual reconciliation')
    folder = a.location(REPO, issue)
    checkpoint = folder / 'checkout/.agent-work/checkpoint.md'
    body = f'{a.MARKER}\n## Agent workpad\n\nStatus: **{status}**\nUpdated: {a.stamp()}\n\n{note}\n'
    if checkpoint.exists():
        body += '\n' + checkpoint.read_text()[:16000]
    state_path = folder / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        body += f'\n\nBranch: `{state["branch"]}`. Attempt: {state["attempts"]}.\n'
        workspace = Path(state['workspace'])
        head = a.git(workspace, 'rev-parse', 'HEAD')
        body += f'Base/current HEAD: `{head}`. Changes may be uncommitted.\n'
        body += 'Local edits require review; a completed turn is not verification. No code was published.\n'
    payload = paths()[0] / 'publication.json'
    a.save(payload, {'body': body})
    endpoint = f'repos/{REPO}/issues/comments/{own[0]["id"]}' if own else f'repos/{REPO}/issues/{issue}/comments'
    a.gh('api', '--method', 'PATCH' if own else 'POST', endpoint, '--input', str(payload))


def flush(state):
    for number, job in state['jobs'].items():
        if job.get('publication'):
            status, note = job['publication']
            publish(int(number), status, note)
            del job['publication']
            persist(state)


def monitor(issue, baseline):
    last_publish = [time.monotonic()]
    def check(worker, initial):
        if not paths()[2].exists():
            return 'paused'
        snap, _ = a.snapshot(REPO, issue)
        try:
            allowed(snap)
        except RuntimeError:
            return 'paused'
        if fingerprint(snap) != baseline:
            return 'feedback-received'
        try:
            a.quota_guard(a.quota(), 25)
        except Exception:
            return "quota-or-account-unavailable"
        if time.monotonic() - last_publish[0] >= 120:
            publish(issue, 'running', 'One bounded attempt is active. Remove agent:ready or add agent:paused to stop it. New issue feedback also stops this attempt for review.')
            last_publish[0] = time.monotonic()
        return None
    return check


def tick():
    with scheduler_lock():
        if not paths()[2].exists():
            return
        state = load()
        # The child inherits the worker lock: a scheduler crash cannot free a live worker's lock.
        with a.lock():
            for job in state['jobs'].values():
                if job['status'] == 'dispatching':
                    job.update(status='needs-approval', publication=['needs-approval', 'Scheduler restart detected. Inspect saved work/session before explicitly authorizing another attempt.'])
            persist(state)
        flush(state)
        if time.time() < state.get('next_check', 0):
            return
        pages = json.loads(a.gh('api', '--paginate', '--slurp', f'repos/{REPO}/issues?state=open&labels=agent%3Aready&per_page=100'))
        candidates = sorted((i for page in pages for i in page if 'pull_request' not in i), key=lambda i: i['number'])
        for item in candidates:
            issue = item['number']
            key = str(issue)
            job = state['jobs'].get(key, {'status': 'new'})
            if job['status'] not in ('new', 'approved', 'waiting-quota'):
                continue
            snap, _ = a.snapshot(REPO, issue)
            try:
                allowed(snap)
            except RuntimeError:
                continue
            # An existing manually-run task needs explicit retry authorization too.
            saved = a.location(REPO, issue) / 'state.json'
            if saved.exists() and json.loads(saved.read_text()).get('attempts', 0) and job['status'] != 'approved':
                job.update(status='needs-approval', publication=['needs-approval', 'Existing task has previous attempts. Inspect its checkpoint and authorize a retry explicitly.'])
                state['jobs'][key] = job
                persist(state)
                flush(state)
                continue
            try:
                data = a.quota()
                a.quota_guard(data, 25)
            except Exception as error:
                state['next_check'] = wait_until(data) if 'data' in locals() else time.time() + 300
                # Preserve approved retry permission; no attempt was started.
                state['last_error'] = str(error)
                job['publication'] = ['waiting-quota', 'Quota is unavailable or the 25% reserve is reached. No model turn started; the controller will recheck after its saved waiting period.']
                state['jobs'][key] = job
                persist(state)
                flush(state)
                return
            state.pop('next_check', None)
            # Durable reservation BEFORE preparation or launching. Failures consume this authorization.
            job.update(status='dispatching', started_at=a.stamp())
            state['jobs'][key] = job
            persist(state)
            args = argparse.Namespace(repo=REPO, issue=issue, checkout=str(SOURCE), minutes=20, reserve=25)
            try:
                if not saved.exists():
                    a.prepare(args)
                # Publish before starting so lack of tracker write access prevents invisible work.
                publish(issue, 'starting', 'Starting one GPT-6 Astra attempt with a 20-minute limit and quota monitoring. Code publication and merging require human review.')
                args.monitor = monitor(issue, fingerprint(snap))
                a.run(args)
                worker = json.loads(saved.read_text())
                status = worker['status']
                job.update(status='needs-review' if status == 'needs-review' else 'needs-approval', worker_status=status)
                note = ('Attempt finished. Review local changes and verification before publishing code.' if status == 'needs-review'
                        else f'Attempt stopped ({status}). New feedback, if any, was detected; it has not been implemented. Inspect saved work before authorizing another attempt.')
            except Exception as error:
                job.update(status='needs-approval', error=str(error))
                note = 'Dispatch stopped. Inspect local scheduler status and saved work before authorizing another attempt.'
            job['publication'] = [job['status'], note]
            persist(state)
            flush(state)
            return  # At most one attempt per invocation.


def approve(issue):
    with scheduler_lock(), a.lock():
        state = load()
        key = str(issue)
        if key not in state['jobs'] or state['jobs'][key]['status'] not in ('needs-approval', 'needs-review'):
            raise RuntimeError('Only a stopped task can be explicitly authorized again')
        saved = a.location(REPO, issue) / 'state.json'
        if saved.exists():
            worker = json.loads(saved.read_text())
            if worker.get('attempts') and not worker.get('session_id'):
                raise RuntimeError('Missing saved session ID: recover deliberately; no fresh automatic run')
        state['jobs'][key].update(status='approved', approved_at=a.stamp())
        persist(state)
        print('One additional attempt authorized; issue must also have agent:ready and no blocking labels.')


def install():
    # Nix's Python is supplied by the Nix-managed agent-scheduler launcher.
    target = Path.home() / 'Library/LaunchAgents' / (SERVICE + '.plist')
    target.parent.mkdir(parents=True, exist_ok=True)
    root = paths()[0]
    obj = {'Label': SERVICE, 'ProgramArguments': [str(Path.home() / '.nix-profile/bin/python3') if (Path.home() / '.nix-profile/bin/python3').exists() else '/etc/profiles/per-user/' + Path.home().name + '/bin/python3', str(Path(__file__).resolve()), 'tick'],
           'StartInterval': 60, 'RunAtLoad': True, 'ProcessType': 'Background',
           'WorkingDirectory': str(SOURCE.resolve()),
           'EnvironmentVariables': {'PATH': '/etc/profiles/per-user/' + Path.home().name + '/bin:/opt/homebrew/bin:/usr/bin:/bin'},
           'StandardOutPath': str(root/'service.log'), 'StandardErrorPath': str(root/'service-error.log')}
    target.write_bytes(plistlib.dumps(obj)); target.chmod(0o600)
    service = f'gui/{os.getuid()}/{SERVICE}'
    subprocess.run(['launchctl', 'bootout', service], capture_output=True)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
    print('Installed login-session scheduler. Use enable/disable to control dispatch; laptop sleep pauses polling.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tick', 'status', 'enable', 'disable', 'approve', 'install'])
    parser.add_argument('issue', type=int, nargs='?')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.command == 'tick':
            tick()
        elif args.command == 'status':
            print(json.dumps({'enabled': paths()[2].exists(), **load()}, indent=2))
        elif args.command == 'enable':
            paths()[2].touch(mode=0o600)
        elif args.command == 'disable':
            paths()[2].unlink(missing_ok=True)
        elif args.command == 'approve':
            if not args.issue or args.issue < 1:
                parser.error('approve needs a positive issue number')
            approve(args.issue)
        elif args.command == 'install':
            install()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # API outages fail closed. launchd retries control-plane reads only, never spent attempts.
        print(f'agent-scheduler: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
