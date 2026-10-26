#!/usr/bin/env python3
"""Read-only guest feature/network identity probe. No VM boot or executor startup."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
from urllib.parse import urlsplit
from vmctl import read_config, validate, config_hash, require, sha


def syscall_features():
    libc = ctypes.CDLL(None, use_errno=True)
    # aarch64 syscall numbers; version-only Landlock does not create a ruleset.
    landlock = libc.syscall(444, 0, 0, 1)
    require(landlock >= 3, 'Landlock ABI>=3 required')
    fd = libc.syscall(434, os.getpid(), 0)
    require(fd >= 0, 'pidfd_open required')
    os.close(fd)
    # Test a deliberately unused descriptor range, not current process descriptors.
    require(libc.syscall(436, 1000000, 1000000, 0) == 0, 'close_range required')
    return {'landlockAbi': landlock, 'pidfdOpen': True, 'closeRange': True}


def validate_probe_config(c, network=False, preparation=False):
    validate(c, complete=not preparation)
    if preparation:
        require(c['stage'] == 'dev' and not network, 'Preparation probe is dev-only and never probes business endpoints')
        source = json.loads(Path(__file__).with_name('source.lock.json').read_text())
        build = json.loads(Path(__file__).with_name('manager-build.lock.json').read_text())
        version = re.fullmatch(r'(?:\d+:)?(\d+\.\d+\.\d+)-[^\s]+', build['dockerPackages']['docker-ce'])
        require(version and c['preparedGuest']['dockerVersion'] == version.group(1), 'Preparation must use the frozen Docker package version')
        require(c['preparedGuest']['kernelRelease'] == source['kernelPackage'].removeprefix('linux-image-'), 'Preparation must use the frozen source kernel')


def probe(c, network=False, preparation=False):
    validate_probe_config(c, network, preparation)
    require(platform.system() == 'Linux' and platform.machine() == 'aarch64', 'Native ARM64 guest required')
    require(Path('/etc/sduoj-execution-vm').read_text().strip() == c['name'], 'Dedicated cloud-init guest marker required')
    require(platform.release() == c['preparedGuest']['kernelRelease'], 'Frozen guest kernel release required')
    info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True, timeout=15))
    require((info.get('Architecture'), info.get('CgroupVersion'), info.get('CgroupDriver'), info.get('ServerVersion')) == ('aarch64', '2', 'cgroupfs', c['preparedGuest']['dockerVersion']), 'Exact guest Docker/cgroup identity required')
    require({'cpu', 'memory', 'pids', 'cpuset'} <= set(Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()), 'Guest controllers required')
    kernel = Path('/boot/config-' + platform.release())
    values = dict(line.split('=', 1) for line in kernel.read_text().splitlines() if '=' in line and not line.startswith('#'))
    require(all(values.get(k) == 'y' for k in ('CONFIG_SECURITY_LANDLOCK', 'CONFIG_USER_NS', 'CONFIG_PID_NS', 'CONFIG_CGROUPS', 'CONFIG_MEMCG', 'CONFIG_CGROUP_PIDS', 'CONFIG_SECCOMP', 'CONFIG_SECCOMP_FILTER')), 'Required guest kernel config missing')
    lsm = Path('/sys/kernel/security/lsm').read_text().strip().split(',')
    require('landlock' in lsm, 'Landlock must be active in guest LSM, not only compiled')
    features = syscall_features()
    r = {'passed': True, 'instance': c['name'], 'configurationSha256': config_hash(c), 'kernelRelease': platform.release(),
         'kernelConfigSha256': sha(kernel), 'dockerVersion': info['ServerVersion'], 'cgroupVersion': '2', 'cgroupDriver': 'cgroupfs',
         'features': features, 'lsm': lsm, 'scope': ('dev-preparation-feature-probe-not-workload-qualification' if preparation else 'feature-and-network-preflight-not-workload-qualification'),
         'preparedDiskQualified': False, 'executorStarted': False}
    if network:
        e = c['execution']
        targets = [(k, e[k + 'Host'], e[k + 'Port']) for k in ('nacos', 'redis', 'rabbit')]
        targets += [(k, urlsplit(e[k]).hostname, urlsplit(e[k]).port or (443 if urlsplit(e[k]).scheme == 'https' else 80)) for k in ('filesysUrl', 'problemRpcUrl', 'runRpcUrl')]
        for label, host, port in targets:
            with socket.create_connection((host, port), timeout=3):
                pass
        r['networkTcpReachable'] = [x[0] for x in targets]
        r['networkAuthenticationVerified'] = False
        r['reverseNacosHealthVerified'] = False
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True); p.add_argument('--network', action='store_true')
    p.add_argument('--preparation', action='store_true', help='Dev guest only: verify fixed kernel/Docker before a prepared disk or executor registry digests exist; no business network probes')
    a = p.parse_args(); print(json.dumps(probe(read_config(a.config), a.network, a.preparation), indent=2))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        raise SystemExit('Guest preflight rejected; endpoint/credential values suppressed')
