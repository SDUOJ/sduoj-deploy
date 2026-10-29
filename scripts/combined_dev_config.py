#!/usr/bin/env python3
"""Render the isolated rehearsal configuration; publish only with --apply.

This helper never targets a production namespace or remote network address.
Actual credentials belong in an operator-owned mode0600 environment file.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


def render(value, environment):
    if isinstance(value, dict):
        return {key: render(item, environment) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, environment) for item in value]
    if not isinstance(value, str):
        return value

    def substitute(match):
        result = environment[match[1]]
        if not result or '\x00' in result or '\n' in result or '\r' in result:
            raise ValueError('Invalid private configuration value')
        return result

    result = re.sub(r'\$\{([A-Z][A-Z0-9_]*)\}', substitute, value)
    if '${' in result:
        raise ValueError('Unresolved configuration placeholder')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--template', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'templates/combined-release.dev.nacos.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--nacos-url', default='http://127.0.0.1:38848')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'release-dev-[a-z0-9-]{1,48}', args.namespace):
        raise ValueError('A dedicated release-dev namespace is required')
    endpoint = urlsplit(args.nacos_url)
    if (endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', 'localhost')
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
            or endpoint.path not in ('', '/')):
        raise ValueError('Only the explicit loopback dev Nacos endpoint is accepted')
    if (args.env_file.is_symlink() or not args.env_file.is_file()
            or stat.S_IMODE(args.env_file.stat().st_mode) != 0o600):
        raise ValueError('A regular private mode0600 environment file is required')
    environment = dict(line.split('=', 1) for line in args.env_file.read_text().splitlines()
                       if line and not line.startswith('#') and '=' in line)
    config = render(json.loads(args.template.read_text()), environment)
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(config, stream, indent=2)
        stream.write('\n')
    if args.apply:
        opener = build_opener(ProxyHandler({}))

        def publish(path, body):
            request = Request(args.nacos_url.rstrip('/') + '/nacos/v1/' + path,
                              data=urlencode(body).encode())
            with opener.open(request, timeout=5) as response:
                return response.read()

        publish('console/namespaces', {'customNamespaceId': args.namespace,
                'namespaceName': args.namespace, 'namespaceDesc': 'Isolated dev release rehearsal'})
        for data_id, content in config.items():
            if publish('cs/configs', {'tenant': args.namespace, 'group': 'DEFAULT_GROUP',
                       'dataId': data_id, 'type': 'json', 'content': json.dumps(content)}) != b'true':
                raise ValueError('Dev Nacos rejected a configuration entry')
    print(json.dumps({'rendered': len(config), 'published': args.apply,
                      'namespace': args.namespace, 'privateOutput': True}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError):
        raise SystemExit('Combined dev configuration rejected; private values suppressed')
