#!/usr/bin/env python3
"""Validate a local onboarding contract; never run its commands or register a repository."""
import argparse
import json
from pathlib import Path
import re
import sys


def validate(data):
    errors = []
    if not isinstance(data, dict): return ['Contract must be a JSON object']
    if data.get('schema') != 1: errors.append('schema must be 1')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', str(data.get('repository', ''))):
        errors.append('repository must be OWNER/REPO')
    for field in ('default_branch', 'scope', 'stack'):
        if not isinstance(data.get(field), str) or not data[field].strip(): errors.append(field + ' is required')
    setup = data.get('setup')
    if not isinstance(setup, list) or not setup or not all(isinstance(x, str) and x.strip() for x in setup):
        errors.append('setup must be a nonempty argument list')
    checks = data.get('checks')
    if not isinstance(checks, list) or not checks:
        errors.append('At least one verification check is required')
    else:
        for check in checks:
            if not isinstance(check, dict): errors.append('Checks must be objects'); continue
            command = check.get('command')
            if not check.get('name') or not isinstance(command, list) or not command or not all(isinstance(x, str) and x.strip() for x in command):
                errors.append('Each check requires a name and command argument list')
    policy = data.get('policy', {})
    if not isinstance(policy, dict): return errors + ['policy must be an object']
    for key, value in {'workers':4, 'attempt_minutes':20, 'weekly_reserve':3, 'short_reserve':25,
                       'retry_authority':'supervising-agent', 'automatic_publication':False, 'dispatch_enabled':False}.items():
        if type(policy.get(key)) != type(value) or policy.get(key) != value:
            errors.append(f'Initial policy requires {key}={value}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate']); parser.add_argument('file')
    args = parser.parse_args()
    errors = validate(json.loads(Path(args.file).read_text()))
    print(json.dumps({'valid': not errors, 'errors':errors, 'registered':False,
                      'note':'Structural validation only; commands were not executed and recovery is not yet proven.'}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    try: sys.exit(main())
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
