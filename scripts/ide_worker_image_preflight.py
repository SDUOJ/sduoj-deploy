#!/usr/bin/env python3
"""Verify every local build input against its frozen image ID before building."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', default='desktop-linux')
    parser.add_argument('--lock', default=str(Path(__file__).resolve().parents[1] / 'build/sduoj-ide-tools/redis-worker-dev.lock.json'))
    parser.add_argument('--prepare-aliases', action='store_true')
    args = parser.parse_args()
    lock = json.loads(Path(args.lock).read_text())
    docker = ['docker', '--context', args.context]
    rows = []
    for entry in lock['images']:
        expected = entry['imageId']
        if not expected.startswith('sha256:') or len(expected) != 71:
            raise ValueError('Lock must contain complete immutable image IDs')
        if args.prepare_aliases:
            actual = subprocess.check_output([*docker, 'image', 'inspect', expected, '--format', '{{.Id}}'], text=True).strip()
            if actual != expected:
                raise RuntimeError('Image identity mismatch')
            subprocess.run([*docker, 'tag', expected, entry['reference']], check=True)
        actual = subprocess.check_output([*docker, 'image', 'inspect', entry['reference'], '--format', '{{.Id}}'], text=True).strip()
        if actual != expected:
            raise RuntimeError('Frozen input alias mismatch: ' + entry['role'])
        rows.append(dict(role=entry['role'], reference=entry['reference'], imageId=actual, matched=True))
    print(json.dumps(dict(scope=lock['scope'], images=rows), indent=2))


if __name__ == '__main__':
    main()
