#!/usr/bin/env python3
"""Read-only host identity checks for one shared cgroup-v2 deployment.

No secrets or full docker inspect environment are returned. Docker cgroupfs is
an explicit supported prerequisite, not an inferred property of all hosts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def check_contract(info, instance, all_instances, expected):
    if info.get('CgroupVersion') != '2' or info.get('CgroupDriver') != 'cgroupfs':
        raise ValueError('Requires Docker cgroup-v2 with cgroupfs driver')
    if info.get('Architecture') != 'aarch64':
        raise ValueError('Accepted architecture is ARM64')
    host = instance['HostConfig']
    config = instance['Config']
    if (instance['Image'] != expected['image'] or config['User'] != '10001:10001'
            or instance['State'].get('Running') is not True
            or config.get('Labels', {}).get('owner') != expected['owner']
            or host.get('Privileged') or host.get('ReadonlyRootfs') is not True
            or host.get('PidMode') == 'host' or host.get('NetworkMode') == 'host'
            or host.get('CgroupnsMode') != 'host'):
        raise ValueError('Runtime identity or permission mismatch')
    options = set(host.get('SecurityOpt') or [])
    # Docker consumes systempaths=unconfined into empty path masks rather than
    # retaining that spelling in inspect.SecurityOpt.
    if (options != {'seccomp=unconfined', 'apparmor=unconfined'}
            or host.get('MaskedPaths') or host.get('ReadonlyPaths')
            or host.get('Devices') or host.get('DeviceCgroupRules')
            or host.get('DeviceRequests')):
        raise ValueError('Outer security/device contract drifted')
    caps = lambda xs: {v.removeprefix('CAP_') for v in xs or []}
    if caps(host.get('CapAdd')) != {'SETUID', 'SETGID'} or caps(host.get('CapDrop')) != {'ALL'}:
        raise ValueError('Only identity-helper bounding capabilities permitted')
    if (host['NanoCpus'] != 4000000000 or host['Memory'] != 6442450944
            or host['PidsLimit'] != 1024):
        raise ValueError('Management group quotas drifted')
    parent = '/' + expected['name']
    if host.get('CgroupParent') != parent:
        raise ValueError('Wrong aggregate parent')
    for other in all_instances:
        if (other['Id'] != instance['Id'] and other['State']['Running']
                and other['HostConfig'].get('CgroupParent') == parent):
            raise ValueError('An aggregate must be exclusive to one live Worker')
    env = dict(s.split('=', 1) for s in config.get('Env', []) if '=' in s)
    if env.get('SDUOJ_IDE_DEV_DEBUG_LAB') != '0':
        raise ValueError('Developer automatic acceptance must be disabled')
    mounts = instance['Mounts']
    if len(mounts) != 2 or any(m.get('Type') != 'bind' for m in mounts):
        raise ValueError('Only own cgroup and qualification binds are allowed')
    cgroup = [m for m in mounts if m['Destination'] == '/sys/fs/cgroup']
    if (len(cgroup) != 1 or not cgroup[0]['RW']
            or cgroup[0]['Source'] != '/sys/fs/cgroup/' + expected['name']):
        raise ValueError('Only the own aggregate may be bound as cgroup root')
    if any('docker.sock' in m['Destination'] for m in mounts):
        raise ValueError('Docker socket is forbidden')
    qualification = [m for m in mounts if m['Destination'] == '/run/ide-config']
    if len(qualification) != 1 or qualification[0]['RW']:
        raise ValueError('Read-only node qualification mount required')
    if (expected.get('qualification_source')
            and qualification[0]['Source'] != expected['qualification_source']):
        raise ValueError('Qualification source mismatch')
    return {'passed': True, 'containerId': instance['Id'], 'image': instance['Image'],
            'aggregate': parent, 'privileged': False, 'user': config['User'],
            'driver': info['CgroupDriver'], 'scope': 'identity-check-not-capacity-proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--container', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--qualification-source')
    args = parser.parse_args()
    if not re.fullmatch(r'sduoj-ide-[a-z0-9-]{1,61}', args.name):
        parser.error('Dedicated aggregate name required')
    def docker(*values):
        return subprocess.check_output([args.docker, *values], text=True, timeout=10)
    info = json.loads(docker('info', '--format', '{{json .}}'))
    ids = docker('ps', '-q').split()
    instances = json.loads(docker('inspect', *ids)) if ids else []
    instance = json.loads(docker('inspect', args.container))[0]
    print(json.dumps(check_contract(info, instance, instances, vars(args))))


if __name__ == '__main__':
    main()
