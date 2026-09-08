#!/usr/bin/env python3
"""Single-Mac, opt-in issue dispatch. No automatic retries of started attempts."""
import argparse
import contextlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time
import threading

spec = importlib.util.spec_from_file_location('agent_work', Path(__file__).with_name('agent-work.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
REPO = 'Guccimane44/dotfiles'
SOURCE = Path.home() / '.local/state/agent-work/scheduler-source'
# One fixed lock/state domain on this Mac, shared with the manual launcher.
a.ROOT = Path.home() / '.local/state/agent-work'
SERVICE = 'local.agent-work.scheduler'
QUOTA_POLICY = {'short_reserve': 25, 'weekly_reserve': 3}


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


def heartbeat(status, detail=''):
    a.save(paths()[0] / 'heartbeat.json', {'epoch': time.time(), 'updated_at': a.stamp(),
                                          'status': status, 'detail': detail})


def rotate_logs(limit=2 * 1024 * 1024):
    # Copy/truncate preserves launchd's open log descriptors. Keep two older copies.
    import shutil
    for name in ('service.log', 'service-error.log'):
        path = paths()[0] / name
        if path.exists() and path.stat().st_size > limit:
            older = path.with_name(name + '.1')
            if older.exists():
                older.replace(path.with_name(name + '.2'))
            shutil.copyfile(path, older)
            with path.open('w'):
                pass


def ensure_source():
    if not SOURCE.exists():
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        a.call(['git', 'clone', 'https://github.com/' + REPO + '.git', str(SOURCE)])
    # prepare also verifies repository identity and a clean checkout before use.
    return SOURCE


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
              if w and w.get('usedPercent', 0) is not None and w.get('usedPercent', 0) >= 100 - a.window_reserve(w, k, QUOTA_POLICY['short_reserve'], QUOTA_POLICY['weekly_reserve'])]
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
    feedback_path = folder / 'feedback.json'
    if feedback_path.exists():
        feedback = json.loads(feedback_path.read_text())
        body += ('\nFeedback acknowledged: changes to the issue or comments were detected at '
                 + feedback['detected_at'] + '. The attempt stopped for review; acknowledgment does not mean implementation.\n')
        if feedback['comment_ids']:
            body += 'Observed comment IDs: ' + ', '.join(str(i) for i in feedback['comment_ids'][-20:]) + '.\n'
    if checkpoint.exists():
        body += '\nSaved milestone checkpoint (may precede the latest handoff):\n' + checkpoint.read_text()[:16000]
    state_path = folder / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        handoff = folder / f'attempt-{state["attempts"]}-handoff.json'
        if handoff.exists():
            data = json.loads(handoff.read_text())
            body += '\n\nLatest worker handoff (unverified, ' + data['status'] + '):\n' + data['message'][:8000]
        body += f'\n\nBranch: `{state["branch"]}`. Attempt: {state["attempts"]}.\n'
        workspace = Path(state['workspace'])
        head = a.git(workspace, 'rev-parse', 'HEAD')
        body += f'Base/current HEAD: `{head}`. Changes may be uncommitted.\n'
        body += 'Local edits require review; a completed turn is not verification. No code was published.\n'
    payload = a.location(REPO, issue) / 'publication.json'
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
        heartbeat('running', f'Issue #{issue}')
        if not paths()[2].exists():
            return 'paused'
        snap, _ = a.snapshot(REPO, issue)
        try:
            allowed(snap)
        except RuntimeError:
            return 'paused'
        if fingerprint(snap) != baseline:
            a.save(a.location(REPO, issue)/'feedback.json', {
                'detected_at': a.stamp(), 'fingerprint': fingerprint(snap),
                'comment_ids': [c['id'] for c in snap.get('comments', []) if 'id' in c]})
            return 'feedback-received'
        try:
            a.quota_guard(a.quota(), QUOTA_POLICY['short_reserve'], QUOTA_POLICY['weekly_reserve'])
        except Exception:
            return "quota-or-account-unavailable"
        if time.monotonic() - last_publish[0] >= 120:
            publish(issue, 'running', 'One bounded attempt is active. Remove agent:ready or add agent:paused to stop it. New issue feedback also stops this attempt for review.')
            last_publish[0] = time.monotonic()
        return None
    return check


def attempt(args, saved, previous):
    try:
        a.run(args)
        status = json.loads(saved.read_text())['status']
        final = 'needs-review' if status == 'needs-review' else 'needs-approval'
        note = ('Attempt finished. Review local changes and verification before publishing code.' if final == 'needs-review'
                else f'Attempt stopped ({status}). Inspect saved work before authorizing another attempt.')
        return {'status': final, 'worker_status': status, 'publication': [final, note]}
    except a.WorkerBusy:
        # No attempt started; preserve authorization instead of consuming a retry.
        return {'status': previous, 'publication': ['waiting-capacity', 'Issue or worker capacity is busy. No attempt started.']}
    except BaseException as error:
        return {'status': 'needs-approval', 'error': str(error),
                'publication': ['needs-approval', 'Dispatch stopped. Inspect saved work before authorizing another attempt.']}


def tick():
    with scheduler_lock():
        futures = {}
        cancel = threading.Event()
        with ThreadPoolExecutor(max_workers=a.WORKER_LIMIT) as pool:
            try:
                dispatch(pool, futures, cancel)
            except BaseException:
                cancel.set()
                raise
            finally:
                # Only this controller thread writes scheduler state; workers write their own task state.
                errors = []
                try:
                    for future in as_completed(futures):
                        state = load()
                        state['jobs'][str(futures[future])].update(future.result())
                        persist(state)
                        try: flush(state)
                        except Exception as error: errors.append(error)
                except BaseException:
                    cancel.set()
                    raise
                if errors: raise errors[0]


def dispatch(pool, futures, cancel):
    if not paths()[2].exists():
        return
    with (a.ROOT/'worker.lock').open('a') as lease:
        try: fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError: raise a.WorkerBusy('Runtime maintenance is in progress')
    state = load()
    if state.get('quota_policy') != QUOTA_POLICY:
        state['quota_policy'] = dict(QUOTA_POLICY)
        state.pop('next_check', None)
        state.pop('last_error', None)
        persist(state)
    # Maintenance exclusion is checked before scheduling, without excluding other workers.
    for number, job in state['jobs'].items():
        if job['status'] == 'dispatching':
            try:
                with a.task_lock(REPO, int(number), slot=False):
                    job.update(status='needs-approval', publication=['needs-approval', 'Scheduler restart detected. Inspect saved work/session before explicitly authorizing another attempt.'])
            except a.WorkerBusy:
                continue  # A live/orphaned worker still owns this issue.
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
        if job['status'] == 'approved':
            try:
                revision, _ = review_snapshot(issue)
                if job.get('review', {}).get('revision') != revision:
                    raise RuntimeError('Workspace or feedback changed after retry review')
            except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
                job.update(status='needs-approval', publication=['needs-approval', str(error) + '. Review again before retrying.'])
                state['jobs'][key] = job
                persist(state); flush(state)
                continue
        try:
            data = a.quota()
            a.quota_guard(data, QUOTA_POLICY['short_reserve'], QUOTA_POLICY['weekly_reserve'])
        except Exception as error:
            state['next_check'] = wait_until(data) if 'data' in locals() else time.time() + 300
            # Preserve approved retry permission; no attempt was started.
            state['last_error'] = str(error)
            job['publication'] = ['waiting-quota', 'Quota is unavailable or the 25% short-window or 3% weekly reserve is reached. No model turn started; the controller will recheck after its saved waiting period.']
            state['jobs'][key] = job
            persist(state)
            flush(state)
            return
        state.pop('next_check', None)
        # Durable reservation BEFORE preparation or launching. Failures consume this authorization.
        previous = job['status']
        job.update(status='dispatching', started_at=a.stamp())
        state['jobs'][key] = job
        persist(state)
        args = argparse.Namespace(repo=REPO, issue=issue, checkout=str(SOURCE), minutes=20, reserve=QUOTA_POLICY['short_reserve'], weekly_reserve=QUOTA_POLICY['weekly_reserve'])
        try:
            if not saved.exists():
                args.checkout = str(ensure_source())
                a.prepare(args)
            # Publish before starting so lack of tracker write access prevents invisible work.
            publish(issue, 'starting', 'Starting one GPT-6 Astra attempt with a 20-minute limit and quota monitoring. Routine review belongs to the supervising agent; high-level architectural choices go to the user. Publication remains within the task authorization.')
            check = monitor(issue, fingerprint(snap))
            args.monitor = lambda worker, initial, check=check: 'paused' if cancel.is_set() else check(worker, initial)
            future = pool.submit(attempt, args, saved, previous)
            futures[future] = issue
            if len(futures) >= a.WORKER_LIMIT:
                return
            continue
        except a.WorkerBusy:
            job['status'] = previous
            persist(state)
            continue
        except Exception as error:
            job.update(status='needs-approval', error=str(error))
            note = 'Dispatch stopped. Inspect local scheduler status and saved work before authorizing another attempt.'
        job['publication'] = [job['status'], note]
        persist(state)
        flush(state)
        # Continue admitting distinct issues up to the shared worker capacity.


def review_snapshot(issue):
    folder, worker = a.read_state(argparse.Namespace(repo=REPO, issue=issue))
    workspace = Path(worker['workspace'])
    if not workspace.is_dir():
        raise RuntimeError('Saved workspace is missing')
    # Include HEAD, index and every nonignored working file, including untracked files.
    files = subprocess.check_output(['git', '-C', str(workspace), 'ls-files', '-co', '--exclude-standard', '-z']).split(b'\0')
    entries = {}
    for raw in sorted(set(files) - {b''}):
        name = os.fsdecode(raw)
        path = workspace / name
        if not path.parent.resolve().is_relative_to(workspace.resolve()):
            raise RuntimeError('Tracked path escapes through a directory symlink')
        if path.is_symlink():
            value = 'symlink:' + os.readlink(path)
        elif path.is_file():
            value = hashlib.sha256(path.read_bytes()).hexdigest() + ':' + str(path.stat().st_mode & 0o777)
        elif path.exists():
            raise RuntimeError('Review of submodules or special files requires a separate policy')
        else:
            value = 'deleted'
        entries[name] = value
    index = subprocess.check_output(['git', '-C', str(workspace), 'ls-files', '--stage', '-z'])
    snap, _ = a.snapshot(REPO, issue)
    data = {'head': a.git(workspace, 'rev-parse', 'HEAD'),
            'branch': a.git(workspace, 'branch', '--show-current'),
            'files': entries, 'index': hashlib.sha256(index).hexdigest(),
            'feedback': fingerprint(snap), 'attempt': worker['attempts']}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(), data


def require_verification(issue, identifier, revision):
    import re
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise RuntimeError('Acceptance requires an automated verification ID')
    directory = a.location(REPO, issue)/'verifications'/identifier
    report = json.loads((directory/'report.json').read_text())
    if report.get('status') != 'passed' or report.get('revision') != revision or report.get('revision_after') != revision:
        raise RuntimeError('Automated verification failed or is stale')
    checks = report.get('checks', [])
    if not checks or any(c.get('result') != 'passed' for c in checks):
        raise RuntimeError('Automated checks did not pass')
    for check in checks:
        name = check.get('output', '')
        if not name or Path(name).name != name or name in ('.', '..'):
            raise RuntimeError('Invalid verification output path')
        path = directory/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != check.get('output_sha256'):
            raise RuntimeError('Verification output changed')


def record_review(issue, evidence_path, decision):
    with scheduler_lock(), a.task_lock(REPO, issue, slot=False):
        state = load()
        job = state['jobs'].get(str(issue), {})
        if job.get('status') not in ('needs-review', 'needs-approval'):
            raise RuntimeError('Only stopped work can be reviewed')
        evidence = json.loads(Path(evidence_path).read_text())
        revision, snapshot = review_snapshot(issue)
        if evidence.get('revision') != revision:
            raise RuntimeError('Review evidence is stale; inspect current changes and feedback again')
        checks = evidence.get('checks')
        if not isinstance(checks, list) or not checks:
            raise RuntimeError('Review requires actual check results')
        for check in checks:
            if not isinstance(check, dict) or not check.get('name') or not check.get('evidence') or check.get('result') not in ('passed', 'failed', 'skipped'):
                raise RuntimeError('Each check needs name, result and evidence')
        if decision == 'accept' and any(c['result'] != 'passed' for c in checks):
            raise RuntimeError('Acceptance requires passing checks; resolve failures or skipped checks')
        if not isinstance(evidence.get('summary'), str) or not evidence['summary'].strip():
            raise RuntimeError('Explain the review conclusion and next action')
        if decision == 'accept':
            require_verification(issue, evidence.get('verification'), revision)
        record = {'revision': revision, 'head': snapshot['head'], 'decision': decision,
                  'reviewed_at': a.stamp(), 'reviewer': 'supervising-agent', 'evidence': evidence}
        a.save(a.location(REPO, issue)/'review.json', record)
        job['review'] = record
        if decision == 'accept':
            job['status'] = 'accepted'
            job['publication'] = ['accepted', 'Supervising-agent review accepted workspace revision ' + revision +
                                  ' at HEAD ' + snapshot['head'] + '. Review evidence is retained locally. No merge or deployment was performed.']
        persist(state)
        print('Review recorded for ' + revision + '. No code published.')


def approve(issue):
    with scheduler_lock(), a.task_lock(REPO, issue, slot=False):
        state = load()
        key = str(issue)
        if key not in state['jobs'] or state['jobs'][key]['status'] not in ('needs-approval', 'needs-review'):
            raise RuntimeError('Only a stopped task can be explicitly authorized again')
        saved = a.location(REPO, issue) / 'state.json'
        if saved.exists():
            worker = json.loads(saved.read_text())
            if worker.get('attempts') and not worker.get('session_id'):
                raise RuntimeError('Missing saved session ID: recover deliberately; no fresh automatic run')
        review = state['jobs'][key].get('review', {})
        revision, _ = review_snapshot(issue)
        if review.get('decision') != 'retry' or review.get('revision') != revision:
            raise RuntimeError('A current retry review is required; inspect and record evidence first')
        state['jobs'][key].update(status='approved', approved_at=a.stamp())
        persist(state)
        print('One additional attempt authorized; issue must also have agent:ready and no blocking labels.')


def install(entrypoint=None):
    # Nix's Python is supplied by the Nix-managed agent-scheduler launcher.
    target = Path.home() / 'Library/LaunchAgents' / (SERVICE + '.plist')
    target.parent.mkdir(parents=True, exist_ok=True)
    root = paths()[0]
    obj = {'Label': SERVICE, 'ProgramArguments': [str(Path.home() / '.nix-profile/bin/python3') if (Path.home() / '.nix-profile/bin/python3').exists() else '/etc/profiles/per-user/' + Path.home().name + '/bin/python3', *([str(entrypoint), 'scheduler', 'tick'] if entrypoint else [str(Path(__file__).resolve()), 'tick'])],
           'StartInterval': 60, 'RunAtLoad': True, 'ProcessType': 'Background',
           'WorkingDirectory': str(root),
           'EnvironmentVariables': {'PATH': '/etc/profiles/per-user/' + Path.home().name + '/bin:/opt/homebrew/bin:/usr/bin:/bin'},
           'StandardOutPath': str(root/'service.log'), 'StandardErrorPath': str(root/'service-error.log')}
    previous = target.read_bytes() if target.exists() else None
    service = f'gui/{os.getuid()}/{SERVICE}'
    try:
        target.write_bytes(plistlib.dumps(obj)); target.chmod(0o600)
        subprocess.run(['launchctl', 'bootout', service], capture_output=True)
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
    except BaseException:
        if previous:
            target.write_bytes(previous)
            subprocess.run(['launchctl', 'bootout', service], capture_output=True)
            subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], capture_output=True)
        else:
            target.unlink(missing_ok=True)
        raise
    print('Installed login-session scheduler. Use enable/disable to control dispatch; laptop sleep pauses polling.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tick', 'status', 'enable', 'disable', 'approve', 'install', 'inspect', 'review'])
    parser.add_argument('issue', type=int, nargs='?')
    parser.add_argument('--evidence')
    parser.add_argument('--decision', choices=['accept', 'retry'])
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.command == 'tick':
            heartbeat('checking')
            try:
                tick()
                heartbeat('idle' if paths()[2].exists() else 'disabled')
            except Exception as error:
                heartbeat('error', str(error))
                raise
            finally:
                sys.stdout.flush(); sys.stderr.flush()
                rotate_logs()
        elif args.command == 'status':
            print(json.dumps({'enabled': paths()[2].exists(), **load()}, indent=2))
        elif args.command == 'enable':
            paths()[2].touch(mode=0o600)
        elif args.command == 'disable':
            paths()[2].unlink(missing_ok=True)
        elif args.command == 'inspect':
            if not args.issue or args.issue < 1: parser.error('inspect requires a positive issue number')
            with scheduler_lock(), a.task_lock(REPO, args.issue, slot=False):
                revision, snapshot = review_snapshot(args.issue)
                print(json.dumps({'revision': revision, 'snapshot': snapshot}, indent=2))
        elif args.command == 'review':
            if not args.issue or args.issue < 1 or not args.evidence or not args.decision:
                parser.error('review requires issue, --evidence FILE and --decision accept|retry')
            record_review(args.issue, args.evidence, args.decision)
        elif args.command == 'approve':
            if not args.issue or args.issue < 1:
                parser.error('approve needs a positive issue number')
            approve(args.issue)
        elif args.command == 'install':
            with scheduler_lock(), a.lock():
                entry = Path.home() / '.local/share/agent-work/launch.py'
                install(entry if entry.exists() else None)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # API outages fail closed. launchd retries control-plane reads only, never spent attempts.
        print(f'agent-scheduler: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
