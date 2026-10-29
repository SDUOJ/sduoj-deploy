#!/usr/bin/env python3
"""Manage only the continuation lab; share dependencies, isolate IDE keys/ports."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

from ide_unified_dev import environment


ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'sduoj-ide-release-gates-20261025'
DATA_ID = 'ide-worker-release-gates-dev-20261025.yml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up', 'check', 'down'])
    parser.add_argument('--dev-env', required=True)
    parser.add_argument('--gateway-jar', required=True)
    args = parser.parse_args()
    jar = Path(args.gateway_jar).resolve(strict=True)
    env = {**environment(args.dev_env), 'IDE_GATEWAY_JAR': str(jar)}
    command = ['docker', 'compose', '-p', PROJECT, '-f', str(ROOT / 'compose.ide-release-gates.dev.yaml')]
    if args.action == 'up':
        content = (ROOT / 'templates/ide-worker.nacos.release-gates.dev.json').read_text()
        data = urllib.parse.urlencode({'dataId': DATA_ID, 'group': 'DEFAULT_GROUP',
            'tenant': 'dev', 'type': 'json', 'content': content}).encode()
        request = urllib.request.Request('http://127.0.0.1:8848/nacos/v1/cs/configs', data=data)
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.read() != b'true':
                raise RuntimeError('Nacos did not confirm isolated lab configuration')
        subprocess.run(command + ['up', '-d'], env=env, check=True)
    elif args.action == 'down':
        subprocess.run(command + ['down'], env=env, check=True)
    else:
        subprocess.run(command + ['ps'], env=env, check=True)
        with urllib.request.urlopen('http://127.0.0.1:8848/nacos/v1/ns/instance/list?' +
                urllib.parse.urlencode({'serviceName': 'ide-worker-release-gates-20261025',
                    'namespaceId': 'dev'}), timeout=5) as response:
            hosts = json.loads(response.read())['hosts']
        print(json.dumps({'registeredInstances': len(hosts),
                         'healthy': sum(bool(host['healthy']) for host in hosts)}))


if __name__ == '__main__':
    main()
