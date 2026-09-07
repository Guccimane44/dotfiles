#!/usr/bin/env python3
"""Install a reviewed skill profile into a project; never overwrite existing skills."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[1]


def manifest():
    data = json.loads((REPO/'skills-lock.json').read_text())
    root = REPO/'vendor/skills'
    entries = list(root.rglob('*'))
    if any(p.is_symlink() for p in entries):
        raise RuntimeError('Vendored skills must not contain symlinks')
    actual = {str(p.relative_to(root)) for p in entries if p.is_file()}
    if actual != set(data['files']):
        raise RuntimeError('Vendored skill inventory differs from its lock')
    for name, digest in data['files'].items():
        file = REPO/'vendor/skills'/name
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Skill integrity mismatch: ' + name)
    return data


def install(profile, project):
    data = manifest()
    selected = data['profiles'][profile]
    project = Path(project).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise RuntimeError('Project must be an existing directory')
    dest = project/'.agents/skills'
    # Never follow an existing project skill-directory symlink outside the project.
    if not dest.resolve().is_relative_to(project):
        raise RuntimeError('Skill destination escapes the project')
    lock = project/'.agents/dotfiles-skills.json'
    if lock.exists() or lock.is_symlink():
        raise RuntimeError('An existing skill profile requires a deliberate update')
    for name in selected:
        target = dest/name
        if target.exists() or target.is_symlink():
            raise RuntimeError(f'{target} already exists; review updates deliberately')
    for name in selected:
        shutil.copytree(REPO/'vendor/skills'/name, dest/name)
    lock = project/'.agents/dotfiles-skills.json'
    lock.write_text(json.dumps({'profile':profile,'revision':data['revision'],
        'guidelines_revision':data['guidelines_revision'],
        'files':{k:v for k,v in data['files'].items() if k.split('/')[0] in selected}},indent=2)+'\n')
    print(f'Installed {profile} into {dest}. Available to new Codex turns/sessions in this project.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['verify','install'])
    p.add_argument('--profile',choices=['web-review','react'])
    p.add_argument('--project')
    args=p.parse_args()
    if args.command=='verify':
        data=manifest(); print(f'Verified {len(data["files"])} pinned files. Profiles: '+', '.join(data['profiles']))
    else:
        if not args.profile or not args.project: p.error('install requires --profile and --project')
        install(args.profile,args.project)

if __name__=='__main__': main()
