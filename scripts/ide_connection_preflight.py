#!/usr/bin/env python3
"""Compare private Gateway/Worker Redis settings without printing credentials.

Inputs are operator-owned files, never HTTP request parameters. This check must
run before either service starts; a matching prefix alone cannot join two Redis
logical databases.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def endpoint(value):
    uri = urlsplit(value)
    if uri.scheme != 'redis' or not uri.hostname or uri.query or uri.fragment:
        raise ValueError('Expected a supported Redis endpoint')
    database = uri.path.lstrip('/') or '0'
    if not database.isascii() or not database.isdecimal():
        raise ValueError('Expected a numeric Redis database')
    return uri.hostname.lower(), uri.port or 6379, int(database)


def compare(gateway, worker):
    left = endpoint(gateway['redis-url'])
    right = endpoint(worker['SDUOJ_IDE_REDIS_URL'])
    if left != right:
        raise ValueError('Gateway and Worker Redis host, port or database differ')
    prefix = gateway['prefix']
    if not prefix or prefix != worker['SDUOJ_IDE_PREFIX']:
        raise ValueError('Gateway and Worker Redis prefixes differ')
    return {'matched': True, 'database': left[2],
            'scope': 'connection identity only; authentication and live transport still require acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-config', type=Path, required=True)
    parser.add_argument('--worker-effective-environment', type=Path, required=True)
    args = parser.parse_args()
    gateway = json.loads(args.gateway_config.read_text())['sduoj']['ide']
    worker = json.loads(args.worker_effective_environment.read_text())
    print(json.dumps(compare(gateway, worker)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError):
        raise SystemExit('IDE connection preflight rejected operator configuration; private values suppressed')
