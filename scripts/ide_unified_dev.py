#!/usr/bin/env python3
"""Start/check/stop only the isolated unified-worker correctness lab.

Uses the already provisioned local SDUOJ dependencies. Never prints credentials.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote
import urllib.request
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
DATA_ID = 'ide-worker-unified-dev-20261025.yml'


def environment(filename):
    values = {}
    for line in Path(filename).read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            values[name] = value.strip().strip('\"\'')
    password = quote(values['DEV_AUTOLAB_REDIS_PASSWORD'], safe='')
    return {**os.environ, 'DEV_RPC_TOKEN': values['DEV_RPC_TOKEN'],
            'AUTOLAB_REDIS_URL': f'redis://:{password}@autolab-redis:6379/14'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'check', 'down'])
    parser.add_argument('--dev-env', required=True)
    args = parser.parse_args()
    env = environment(args.dev_env)
    command = ['docker', 'compose', '-p', 'sduoj-ide-unified-dev',
               '-f', str(ROOT / 'compose.ide-unified.dev.yaml')]
    if args.action == 'up':
        data = urllib.parse.urlencode({'dataId': DATA_ID, 'group': 'DEFAULT_GROUP', 'tenant': 'dev',
            'type': 'json', 'content': (ROOT / 'templates/ide-worker.nacos.dev.json').read_text()}).encode()
        request = urllib.request.Request('http://127.0.0.1:8848/nacos/v1/cs/configs', data=data)
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.read() == b'true', 'Nacos did not confirm local config'
        subprocess.run(command + ['up', '-d'], env=env, check=True)
    elif args.action == 'down':
        subprocess.run(command + ['down'], env=env, check=True)
    else:
        subprocess.run(command + ['ps'], env=env, check=True)
        with urllib.request.urlopen('http://127.0.0.1:8848/nacos/v1/ns/instance/list?' +
                urllib.parse.urlencode({'serviceName': 'ide-worker', 'namespaceId': 'dev'}), timeout=5) as response:
            hosts = json.loads(response.read())['hosts']
        print(json.dumps({'registeredInstances': len(hosts),
                         'healthy': sum(bool(host['healthy']) for host in hosts)}))


if __name__ == '__main__':
    main()
