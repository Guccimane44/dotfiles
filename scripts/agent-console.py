#!/usr/bin/env python3
"""Local operator views. Herdr never owns or resumes scheduler worker processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import time

ROOT=Path.home()/'.local/state/agent-work'
REPO='Guccimane44/dotfiles'
BIN=Path('/etc/profiles/per-user')/Path.home().name/'bin/agent-work'
HERDR='/opt/homebrew/bin/herdr'


def jobs():
    p=ROOT/'scheduler/state.json'
    return json.loads(p.read_text()).get('jobs',{}) if p.exists() else {}


def show():
    enabled=(ROOT/'scheduler/enabled').exists()
    print('DOTFILES AGENT WORK\n')
    print('Dispatch: '+('enabled' if enabled else 'paused'))
    print('One worker | 25% five-hour / 3% weekly reserve | agent-reviewed retries\n')
    for issue,job in jobs().items():
        print(f'Issue #{issue}: {job["status"]}')
        if job.get('error'): print('  Attention: '+job['error'])
        print(f'  https://github.com/{REPO}/issues/{issue}')
    print('\nControls: agent-work console review N | pause [N] | resume N')
    print('Review required before resume. Ctrl-C exits this view; workers keep their scheduler policy.')


def run(*args):
    subprocess.run([str(x) for x in args],check=True)


def api(*args):
    return json.loads(subprocess.check_output([HERDR,*args],text=True))['result']


def workspace():
    if os.environ.get('HERDR_ENV')!='1':
        raise RuntimeError('Run this command from a pane inside Herdr; no outside session will be controlled.')
    if os.environ.get('HERDR_SESSION') != 'dotfiles':
        raise RuntimeError('Open the dedicated dotfiles Herdr session first.')
    # Work only in the caller's pane. A local marker prevents duplicate layout creation.
    marker=ROOT/('herdr-layout-'+os.environ['HERDR_WORKSPACE_ID'].replace(':','-')+'.json')
    if marker.exists():
        saved = json.loads(marker.read_text())
        live = api('pane','list','--workspace',os.environ['HERDR_WORKSPACE_ID'])['panes']
        names = {p['pane_id']:p.get('label') for p in live}
        if names.get(saved['status']) == 'Scheduler status' and names.get(saved['logs']) == 'Worker output':
            print('Operator layout already initialized. Use the existing status/log panes.'); return
        raise RuntimeError('Saved layout changed. Inspect the panes before clearing its local layout marker.')
    pane=os.environ['HERDR_PANE_ID']
    cwd=str(Path.home()/'.dotfiles')
    wide = shutil.get_terminal_size().columns >= 120
    result = (api('pane','split','--current','--direction','right','--cwd',cwd,'--no-focus') if wide
              else api('tab','create','--workspace',os.environ['HERDR_WORKSPACE_ID'],'--cwd',cwd,'--label','Status','--no-focus'))
    status=result['pane' if wide else 'root_pane']['pane_id']
    run(HERDR,'pane','rename',status,'Scheduler status')
    run(HERDR,'pane','run',status,'~/.dotfiles/scripts/agent-console status --watch')
    result = (api('pane','split',status,'--direction','down','--cwd',cwd,'--no-focus') if wide
              else api('tab','create','--workspace',os.environ['HERDR_WORKSPACE_ID'],'--cwd',cwd,'--label','Logs','--no-focus'))
    logs=result['pane' if wide else 'root_pane']['pane_id']
    run(HERDR,'pane','rename',logs,'Worker output')
    run(HERDR,'pane','run',logs,'tail -n 30 -F ~/.local/state/agent-work/scheduler/service.log ~/.local/state/agent-work/scheduler/service-error.log')
    run(HERDR,'pane','rename',pane,'Review and controls')
    marker.write_text(json.dumps({'status':status,'logs':logs})+'\n')
    print('Status and log panes created. Use this pane for review and explicit controls.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['status','review','pause','resume','open','workspace'])
    p.add_argument('issue',type=int,nargs='?');p.add_argument('--watch',action='store_true')
    args=p.parse_args()
    if args.issue is not None and args.issue<1: p.error('issue must be positive')
    if args.command=='status':
        while True:
            if args.watch: print('\033[2J\033[H',end='')
            show()
            if not args.watch: break
            time.sleep(3)
    elif args.command=='review':
        if not args.issue: p.error('review requires an issue number')
        run(BIN,'status',REPO,args.issue)
        state=json.loads((ROOT/REPO/str(args.issue)/'state.json').read_text())
        run('git','-C',state['workspace'],'diff','--stat')
    elif args.command=='pause':
        if args.issue: run('/opt/homebrew/bin/gh','issue','edit',args.issue,'--repo',REPO,'--add-label','agent:paused')
        else: run(BIN,'scheduler','disable')
        print('Pause requested. Active work stops at its next successful control check or control-access failure.')
    elif args.command=='resume':
        if not args.issue: p.error('resume requires an issue number; review saved work first')
        run(BIN,'scheduler','approve',args.issue)
        run('/opt/homebrew/bin/gh','issue','edit',args.issue,'--repo',REPO,'--remove-label','agent:paused','--add-label','agent:ready')
        print('One attempt authorized. Global pause or other blocking labels still apply.')
    elif args.command=='open':
        os.chdir(Path.home()/'.dotfiles')
        os.execv(HERDR,[HERDR,'--session','dotfiles'])
    elif args.command=='workspace': workspace()

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass
