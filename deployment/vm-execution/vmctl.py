#!/usr/bin/env python3
"""Execution-only ARM64 VM pack. Default: read-only plan; never activates traffic."""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
DIGEST = re.compile(r'[^\s]+@sha256:[a-f0-9]{64}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
NAME = re.compile(r'sduoj-execution-[a-z0-9][a-z0-9-]{0,48}\Z')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def validate_preparation(c, receipt):
    p = c['preparedGuest']
    require(receipt.get('schemaVersion') == 1 and receipt.get('status') == 'PREPARED_NOT_GUEST_QUALIFIED', 'Explicit preparation status required')
    require(all(receipt.get(k) == p[v] for k, v in [('upstreamSha512', 'upstreamSha512'), ('diskSha256', 'sha256'), ('kernelRelease', 'kernelRelease'), ('dockerVersion', 'dockerVersion')]), 'Preparation identity mismatch')
    require(receipt.get('architecture') == 'aarch64' and receipt.get('cgroupVersion') == '2' and receipt.get('cgroupDriver') == 'cgroupfs', 'Prepared guest ARM64/cgroup2/cgroupfs contract required')
    require(all(SHA.fullmatch(receipt.get(k, '')) for k in ('packageLockSha256', 'kernelConfigSha256', 'dockerDaemonConfigSha256')), 'Preparation must bind package/kernel/Docker config inventories')

def private(path):
    p = Path(path)
    require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'Private regular absolute input required')
    require(stat.S_IMODE(p.stat().st_mode) == 0o600 and p.stat().st_uid == os.getuid(), 'Private input must be owned by current user and mode0600')
    return p

def read_config(path):
    return json.loads(private(path).read_text())

def config_hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def validate(c, complete=True):
    require(c.get('schemaVersion') == 1 and NAME.fullmatch(c.get('name', '')), 'Invalid explicit instance identity')
    require(c.get('stage') in ('dev', 'production-staging'), 'Only dev/production-staging; no activation command exists')
    root = Path(c.get('stateDirectory', ''))
    require(root.is_absolute() and root != Path('/') and str(root) == str(root.resolve()) and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(root)), 'Canonical owned state path required')
    require(c.get('machine') == 'virt-10.0', 'Versioned virt-10.0 machine required')
    require((c.get('vcpus'), c.get('memoryMiB'), c.get('diskGiB')) == (16, 24576, 120), 'Candidate VM envelope must remain 16vCPU/24GiB/120GiB until retested')
    for k in ('managerUid', 'managerGid', 'kvmGid'):
        require(type(c.get(k)) is int and c[k] >= (1 if k == 'managerUid' else 0), 'Explicit nonroot manager identity and KVM group required')
    require(c.get('networkPhase') in ('bootstrap', 'integrated'), 'Explicit network phase required')
    for k in ('sshPort', 'healthPort'):
        require(type(c.get(k)) is int and 1024 <= c[k] <= 65535, 'Nonprivileged explicit ports required')
    require(c['sshPort'] != c['healthPort'], 'SSH and health ports must differ')
    ip = ipaddress.ip_address(c['healthBindAddress'])
    require(ip.version == 4 and not ip.is_unspecified and (ip.is_loopback or ip.is_private), 'Health bind must be explicit loopback/private IPv4')
    e = c['execution']
    require(all(type(e.get(k)) is int and 1024 <= e[k] <= 65535 for k in ('judgerPort', 'runPort')) and len({c['sshPort'], c['healthPort'], e['judgerPort'], e['runPort']}) == 4, 'Distinct nonprivileged SSH and executor service ports required')
    require((e.get('redisDatabase'), e.get('ideCpuset'), e.get('judgerCpuset'), e.get('runCpuset')) == (2, '0-3', '4-5', '6-7'), 'Redis DB2 and disjoint executor cores required')
    require(re.fullmatch(r'[A-Za-z0-9:_-]{4,100}:', e.get('redisPrefix', '')), 'Explicit bounded Redis prefix required')
    require(re.fullmatch(r'sduoj-ide-[a-z0-9][a-z0-9-]{0,60}', e.get('aggregate', '')), 'Dedicated aggregate required')
    for k in ('privateGuestDirectory', 'qualificationDirectory'):
        require(re.fullmatch(r'/opt/sduoj-execution(?:/[a-z0-9-]+)*', e.get(k, '')), 'Guest paths must be under dedicated /opt/sduoj-execution')
    require(e['judgerSnowflakeNode'] != e['runSnowflakeNode'] and all(type(e[k]) is int and 0 <= e[k] <= 31 for k in ('judgerSnowflakeNode', 'runSnowflakeNode')), 'Distinct approved Snowflake nodes required')
    if not complete:
        return
    require(DIGEST.fullmatch(c.get('managerImage', '')), 'Pin manager registry digest; tags/local IDs rejected')
    require(re.fullmatch(r'10\.0\.[0-9]+', c.get('qemuVersion', '')), 'Pin tested QEMU10.0 patch version')
    p = c['preparedGuest']
    require(p['file'] == 'prepared-guest.qcow2' and all(SHA.fullmatch(p.get(k, '')) for k in ('sha256', 'preparationReceiptSha256', 'firmwareCodeSha256', 'firmwareVarsSha256')), 'Freeze prepared disk, receipt and firmware hashes before rendering')
    source = json.loads((HERE / 'source.lock.json').read_text())
    require(p['upstreamSha512'] == source['sha512'] and p['kernelRelease'] == '6.12.113+deb13-cloud-arm64', 'Prepared guest must derive from the fixed source/kernel')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', p.get('dockerVersion', '')), 'Pin exact Docker version')
    require(re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{40,100}={0,2}(?: [A-Za-z0-9._@-]+)?', c.get('guestSshPublicKey', '')), 'Explicit single Ed25519 public key required')
    key_bytes = base64.b64decode(c['guestSshPublicKey'].split()[1], validate=True)
    require(len(key_bytes) == 51 and key_bytes.startswith(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32)) and key_bytes[-32:] != bytes(32), 'Valid Ed25519 wire-format public key required')
    require(all(DIGEST.fullmatch(e.get(k, '')) for k in ('ideImage', 'judgerImage')), 'Pin accepted executor registry digests')
    for k in ('environment', 'nacosNamespace', 'nacosDataId', 'nacosService', 'workerId'):
        require(re.fullmatch(r'[A-Za-z0-9._-]{1,100}', e.get(k, '')), 'Explicit namespaced service identities required')
    for k in ('nacosHost', 'redisHost', 'rabbitHost'):
        address = ipaddress.ip_address(e[k])
        require(address.version == 4 and address.is_private and not address.is_link_local and not address.is_multicast and not address.is_reserved and not address.is_loopback and not address.is_unspecified and str(address) not in ('10.0.2.2', '10.0.2.15'), 'Existing service endpoints require real internal IPv4, not guest aliases')
    for k in ('nacosPort', 'redisPort', 'rabbitPort'):
        require(type(e[k]) is int and 1 <= e[k] <= 65535, 'Explicit service ports required')
    require(e.get('rabbitVirtualHost') and not any(x in e['rabbitVirtualHost'] for x in ('\n', '\r')), 'Explicit staging Rabbit vhost required')
    for k in ('filesysUrl', 'problemRpcUrl', 'runRpcUrl'):
        u = urlsplit(e[k])
        require(u.scheme in ('http', 'https') and not u.username and not u.password and not u.query and not u.fragment and u.path in ('', '/'), 'Explicit internal RPC origin required')
        ip = ipaddress.ip_address(u.hostname)
        require(ip.is_private and not ip.is_link_local and not ip.is_multicast and not ip.is_reserved and not ip.is_loopback and not ip.is_unspecified and str(ip) not in ('10.0.2.2', '10.0.2.15'), 'RPC must address existing internal service, not SSH topology')
    if c['networkPhase'] == 'integrated':
        address = ipaddress.ip_address(e['advertiseAddress'])
        require(address.version == 4 and address.is_private and not address.is_link_local and not address.is_multicast and not address.is_reserved and not address.is_loopback and not address.is_unspecified and str(address) == c['healthBindAddress'], 'Integrated Nacos advertise must match explicitly approved private host health bind')
    else:
        require(c['healthBindAddress'] == '127.0.0.1', 'Bootstrap health is loopback-only')

def write(path, value):
    with Path(path).open('x') as f:
        os.chmod(path, 0o600)
        f.write(value)

def verify_render(c, state):
    expected = {'config.json', 'compose.manager.json', 'compose.executors.json', 'user-data', 'meta-data'}
    receipt = json.loads(private(state / 'render-receipt.json').read_text())
    require(receipt.get('configurationSha256') == config_hash(c) and set(receipt.get('files', {})) == expected, 'Rendered bundle identity mismatch')
    require(all(sha(private(state / name)) == digest for name, digest in receipt['files'].items()), 'Rendered bundle file drift')

def compose_manager(c):
    return {'name': c['name'], 'services': {'manager': {
        'image': c['managerImage'], 'platform': 'linux/arm64', 'pull_policy': 'never',
        'user': f"{c['managerUid']}:{c['managerGid']}", 'group_add': [str(c['kvmGid'])],
        'privileged': False, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'read_only': True, 'network_mode': 'host', 'devices': ['/dev/kvm:/dev/kvm:rw'],
        'volumes': [{'type': 'bind', 'source': c['stateDirectory'], 'target': '/vm', 'bind': {'create_host_path': False}}],
        'tmpfs': ['/tmp:size=64m,mode=1777'], 'working_dir': '/vm', 'command': ['plan'],
        'cpus': 16, 'mem_limit': '26g', 'memswap_limit': '26g', 'pids_limit': 256, 'stop_grace_period': '120s',
        'restart': 'no', 'labels': {'owner': c['name'], 'scope': 'execution-only-no-traffic-activation'}
    }}}

def compose_executors(c):
    e = c['execution']; guest = e['privateGuestDirectory']
    ide = {'image': e['ideImage'], 'platform': 'linux/arm64', 'pull_policy': 'never', 'user': '10001:10001',
           'privileged': False, 'cap_drop': ['ALL'], 'cap_add': ['SETUID', 'SETGID'],
           'security_opt': ['seccomp=unconfined', 'apparmor=unconfined', 'systempaths=unconfined'],
           'cgroup': 'host', 'cgroup_parent': '/' + e['aggregate'], 'read_only': True, 'init': True,
           'cpus': 4, 'mem_limit': '6g', 'memswap_limit': '6g', 'pids_limit': 1024, 'cpuset': e['ideCpuset'], 'stop_grace_period': '60s',
           'network_mode': 'host', 'env_file': [guest + '/private/ide.env'],
           'environment': {'ACTIVE': e['environment'], 'NACOS_NAMESPACE': e['nacosNamespace'], 'NACOS_GROUP': 'DEFAULT_GROUP',
                           'NACOS_DATA_ID': e['nacosDataId'], 'NACOS_SERVICE': e['nacosService'], 'NACOS_IP': e['advertiseAddress'],
                           'NACOS_ADDR': f"{e['nacosHost']}:{e['nacosPort']}", 'SDUOJ_IDE_WORKER_ID': e['workerId'],
                           'SDUOJ_IDE_HEALTH_PORT': str(c['healthPort']), 'SDUOJ_IDE_NACOS_ENABLED': '1', 'SDUOJ_IDE_DEV_DEBUG_LAB': '0'},
           'entrypoint': ['/usr/bin/env', '-u', 'SDUOJ_IDE_JAVA_PROCESSORS', 'python3', '/opt/sduoj-ide/scripts/entrypoint.py'], 'command': ['--role', 'all'],
           'volumes': [{'type': 'bind', 'source': '/sys/fs/cgroup/' + e['aggregate'], 'target': '/sys/fs/cgroup', 'bind': {'create_host_path': False}},
                       {'type': 'bind', 'source': e['qualificationDirectory'], 'target': '/run/ide-config', 'read_only': True, 'bind': {'create_host_path': False}}],
           'healthcheck': {'test': ['CMD', 'python3', '-c', f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{c['healthPort']}/ready',timeout=2)"], 'interval': '10s', 'timeout': '3s', 'retries': 3},
           'tmpfs': ['/tmp:size=256m,uid=10001,gid=10001,mode=1777', '/run/sduoj-debug:size=128m,uid=10001,gid=10001,mode=0700', '/home/ide:size=32m,uid=10001,gid=10001,mode=0700']}
    services = {'ide-worker': ide}
    for role, worker, cpuset, node, service_port in [('judger', 'false', e['judgerCpuset'], e['judgerSnowflakeNode'], e['judgerPort']), ('run-worker', 'true', e['runCpuset'], e['runSnowflakeNode'], e['runPort'])]:
        services[role] = {'image': e['judgerImage'], 'platform': 'linux/arm64', 'pull_policy': 'never', 'user': '0:0',
                          'privileged': False, 'cpus': 2, 'mem_limit': '2560m', 'memswap_limit': '2560m', 'pids_limit': 1024, 'cpuset': cpuset,
                          'cap_add': ['SYS_ADMIN'], 'cgroup': 'private', 'security_opt': ['apparmor=unconfined'],
                          'network_mode': 'host', 'env_file': [guest + '/private/judger.env'],
                          'entrypoint': ['/usr/bin/tini', '--', '/usr/local/bin/sduoj-judge-entrypoint', '/opt/java/openjdk17/bin/java'],
                          'command': ['-jar', '/app/sduoj-judger.jar', '--sduoj.run.worker=' + worker, '--sduoj.config.active=' + e['environment'], f"--sduoj.config.nacos-addr={e['nacosHost']}:{e['nacosPort']}", f'--server.port={service_port}', f'--sduoj.config.port={service_port}', '--spring.cloud.nacos.discovery.ip=' + e['advertiseAddress'], f'--spring.cloud.nacos.discovery.port={service_port}', '--spring.rabbitmq.host=' + e['rabbitHost'], f"--spring.rabbitmq.port={e['rabbitPort']}", '--spring.rabbitmq.virtual-host=' + e['rabbitVirtualHost']],
                          'environment': {'JAVA_TOOL_OPTIONS': '-Xms64m -Xmx384m -XX:ActiveProcessorCount=2', 'CPU_PER_JUDGER': '1', 'SDUOJ_SNOWFLAKE_NODE': str(node)}}
    for service in services.values():
        service['profiles'] = ['explicit-executor-start']
        service['labels'] = {'owner': c['name'], 'scope': 'candidate-requires-same-guest-qualification'}
    return {'name': c['name'] + '-executors', 'services': services}

def render(c, output):
    validate(c)
    require(not output.exists() and output.is_absolute(), 'New absolute output directory required')
    output.mkdir(mode=0o700)
    write(output / 'config.json', json.dumps(c, indent=2) + '\n')
    for name, data in [('compose.manager.json', compose_manager(c)), ('compose.executors.json', compose_executors(c) if c['networkPhase'] == 'integrated' else {'name': c['name'] + '-executors', 'services': {}, 'x-sduoj-status': 'BOOTSTRAP_ONLY_EXECUTORS_DISABLED'})]:
        write(output / name, json.dumps(data, indent=2) + '\n')
    user_data = {'hostname': c['name'], 'manage_etc_hosts': True, 'disable_root': True, 'ssh_pwauth': False, 'ssh_deletekeys': True, 'ssh_genkeytypes': ['ed25519'],
                 'users': [{'name': 'executor-admin', 'groups': ['sudo'], 'sudo': ['ALL=(ALL) NOPASSWD:ALL'], 'shell': '/bin/bash', 'lock_passwd': True, 'ssh_authorized_keys': [c['guestSshPublicKey']]}],
                 'package_update': False, 'package_upgrade': False,
                 'write_files': [{'path': '/etc/sduoj-execution-vm', 'permissions': '0600', 'owner': 'root:root', 'content': c['name'] + '\n'}]}
    write(output / 'user-data', '#cloud-config\n' + json.dumps(user_data, indent=2) + '\n')
    write(output / 'meta-data', json.dumps({'instance-id': c['name'], 'local-hostname': c['name']}) + '\n')
    write(output / 'render-receipt.json', json.dumps({'configurationSha256': config_hash(c), 'scope': 'rendered-only-not-booted-not-qualified', 'files': {p.name: sha(p) for p in output.iterdir()}}, indent=2))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', default='plan', choices=('plan', 'render', 'verify-assets', 'prepare', 'start'))
    p.add_argument('--config', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--confirm-instance')
    p.add_argument('--authorization', type=Path)
    a = p.parse_args()
    if not a.config:
        p.print_help(); return
    c = read_config(a.config)
    validate(c, complete=a.command != 'plan')
    if a.command == 'plan':
        try:
            validate(c); ready = True
        except ValueError:
            ready = False
        print(json.dumps({'writes': False, 'instance': c['name'], 'stage': c['stage'], 'fullyPinned': ready, 'vmStarted': False, 'resourceStatus': 'candidate-not-capacity-qualified'})); return
    if a.command == 'render':
        require(a.output is not None, 'Explicit output required')
        render(c, a.output); print(json.dumps({'rendered': True, 'vmStarted': False})); return
    state = Path(c['stateDirectory'])
    require(state.is_dir() and not state.is_symlink() and stat.S_IMODE(state.stat().st_mode) == 0o700 and state.stat().st_uid == os.getuid(), 'Owned mode0700 state directory required')
    require(sha(state / c['preparedGuest']['file']) == c['preparedGuest']['sha256'], 'Prepared image SHA mismatch')
    require(sha(private(state / 'preparation-receipt.json')) == c['preparedGuest']['preparationReceiptSha256'], 'Prepared image receipt SHA mismatch')
    validate_preparation(c, json.loads((state / 'preparation-receipt.json').read_text()))
    require(read_config(state / 'config.json') == c, 'Rendered and invoked config differ')
    verify_render(c, state)
    if a.command == 'verify-assets':
        print(json.dumps({'verified': True, 'vmStarted': False, 'scope': 'disk-and-receipt-only'})); return
    require(a.execute and a.confirm_instance == c['name'], 'Writes/start require --execute --confirm-instance EXACT_NAME')
    if c['stage'] == 'production-staging':
        require(a.authorization is not None, 'Production staging requires separate dispatch authorization')
        auth = json.loads(private(a.authorization).read_text())
        require(auth.get('operation') == 'VM_STAGING_APPROVED' and auth.get('instance') == c['name'] and auth.get('configurationSha256') == config_hash(c), 'Dispatch authorization mismatch')
    require(sys.platform == 'linux' and os.uname().machine == 'aarch64', 'Container manager start requires native ARM64 Linux KVM; Mac must use independent native HVF')
    require(os.access('/dev/kvm', os.R_OK | os.W_OK), 'Current user requires KVM access')
    require(os.getuid() == c['managerUid'] and os.getgid() == c['managerGid'], 'Manager uid/gid must match owned state uid/gid')
    command = ['docker', 'compose', '-f', str(state / 'compose.manager.json'), 'run', '--no-deps', '--name', c['name'] + '-manager']
    if a.command == 'start': command.append('-d')
    else: command.append('--rm')
    command += ['manager', a.command, '--execute', '--confirm-instance', c['name']]
    subprocess.run(command, check=True, timeout=180)
    print(json.dumps({'operation': a.command, 'instance': c['name'], 'trafficActivated': False}))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        raise SystemExit('Execution VM guard rejected input/operation; private values suppressed')
