#!/usr/bin/env python3
"""Render a new dev business-network candidate. Never starts or updates services."""
import argparse
import copy
import ipaddress
import json
import os
from pathlib import Path
from vmctl import private, require, sha

OWNER = 'sduoj-combined-release-20261026'
JAVA_PORTS = {'gateway': 38080, 'problem-service': 38082,
              'filesys-service': 38083, 'contest-service': 38084,
              'user-service': 38085, 'websocket': 38089}
DEPENDENCY_PORTS = {'redis': [(6379, 36379)], 'rabbit': [(5672, 35672)],
                    'nacos': [(8848, 38848), (9848, 39848)]}


def candidate(base, address):
    ip = ipaddress.ip_address(address)
    require(ip.version == 4 and ip.is_private and not any((ip.is_loopback,
            ip.is_link_local, ip.is_unspecified, ip.is_multicast, ip.is_reserved)),
            'Explicit real private IPv4 required; caller must verify interface ownership')
    require(str(ip) not in ('10.0.2.2', '10.0.2.15'), 'Guest aliases are not host interfaces')
    require(base.get('name') == OWNER, 'Exact isolated dev project required')
    out = copy.deepcopy(base)
    services = out['services']
    ports = {**{k: [(8080, v)] for k, v in JAVA_PORTS.items()}, **DEPENDENCY_PORTS}
    for name, mappings in ports.items():
        service = services[name]
        require(service.get('labels', {}).get('owner') == OWNER, 'Owned dev service required')
        require(not service.get('network_mode'), 'Expected existing dev bridge network')
        published = service.setdefault('ports', [])
        # Use resolved `docker compose config --format json`, not raw YAML/interpolation.
        require(all(isinstance(row, dict) and row.get('host_ip') == '127.0.0.1'
                    and row.get('protocol', 'tcp') == 'tcp' for row in published),
                'Only resolved pre-existing loopback TCP bindings accepted')
        for target, host_port in mappings:
            published.append({'host_ip': address, 'target': target,
                              'published': str(host_port), 'protocol': 'tcp'})
        if name in JAVA_PORTS:
            command = service['command']
            require(isinstance(command, list) and all(isinstance(x, str) for x in command),
                    'Resolved Java argv required')
            require(not any(x.startswith('--spring.cloud.nacos.discovery.' + key + '=')
                            for x in command for key in ('ip', 'port')),
                    'Existing discovery override requires manual reconciliation')
            command += ['--spring.cloud.nacos.discovery.ip=' + address,
                        '--spring.cloud.nacos.discovery.port=' + str(JAVA_PORTS[name])]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resolved-compose', type=Path, required=True)
    parser.add_argument('--host-address', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = private(args.resolved_compose)
    result = candidate(json.loads(source.read_text()), args.host_address)
    require(args.output.is_absolute() and not args.output.exists(), 'New absolute output required')
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'rendered': True, 'sourceSha256': sha(source),
                      'outputSha256': sha(args.output), 'servicesStarted': False,
                      'networkQualified': False, 'productionChanged': False,
                      'scope': 'dev-network-candidate-interface-routing-ports-auth-discovery-not-tested'}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit('Dev network candidate rejected; private values suppressed')
