#!/usr/bin/env python3
"""Read pinned optional expertise without installing skills or injecting prompts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1] / 'vendor/expertise'


def verify():
    data = json.loads((BASE / 'harness-engineering.lock.json').read_text())
    root = BASE / 'harness-engineering'
    entries = list(root.rglob('*'))
    if root.is_symlink() or any(p.is_symlink() for p in entries):
        raise RuntimeError('Expertise snapshot contains a symlink')
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in entries if p.is_file()}
    if not actual or actual != data['files']:
        raise RuntimeError('Expertise inventory or hashes differ from the pin')
    return root, data


def read_document(name, start=1, lines=80):
    root, data = verify()
    if name not in data['files'] or not name.endswith('.md') or '..' in Path(name).parts or Path(name).is_absolute():
        raise RuntimeError('Select a pinned Markdown path from the index')
    if start < 1 or not 1 <= lines <= 200:
        raise RuntimeError('start must be positive; lines must be between 1 and 200')
    content = (root / name).read_text().splitlines()
    excerpt = '\n'.join(f'{i+1}: {line}' for i, line in enumerate(content) if start <= i+1 < start+lines)
    return (f"External reference: {data['upstream']}/blob/{data['revision']}/{name}\n"
            f"{data['attribution']}\nAdvisory only; target instructions and authority govern.\n"
            f"Lines {start}–{min(start+lines-1, len(content))} of {len(content)}.\n" + excerpt[:16000]
            + ('\n[Character limit reached; request fewer lines.]' if len(excerpt) > 16000 else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['index', 'read', 'verify'])
    parser.add_argument('path', nargs='?')
    parser.add_argument('--start', type=int, default=1)
    parser.add_argument('--lines', type=int, default=80)
    args = parser.parse_args()
    if args.command == 'read':
        if not args.path: parser.error('read requires a pinned path')
        print(read_document(args.path, args.start, args.lines))
    else:
        _, data = verify()
        print(f"{data['upstream']} @ {data['revision']}\nVerified {len(data['files'])} files. {data['attribution']}")
        if args.command == 'index':
            print('Optional reference only. Start with AGENTS.md; then choose one relevant route.')
            print('\n'.join(name for name in data['files'] if name.endswith('.md') and not name.startswith('sources/')))


if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, ValueError) as error:
        print('agent-expertise: ' + str(error), file=sys.stderr); sys.exit(1)
