#!/usr/bin/env python3
"""Offline Docker preparation inside an explicitly marked DEV guest only; dry-run by default."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from vmctl import private, read_config, validate, require, sha, validate_boot


def packages(lock, directory):
    names = {'docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin', 'docker-compose-plugin'}
    require(lock.get('schemaVersion') == 1 and lock.get('architecture') == 'arm64' and lock.get('status') == 'OFFICIAL_APT_DEPENDENCY_CLOSURE_FROZEN', 'Resolve and freeze official package dependency closure before install')
    rows = lock.get('packages', [])
    require(rows and names <= {r['name'] for r in rows}, 'All five explicit Docker packages required')
    require(len({r['name'] for r in rows}) == len(rows), 'Duplicate package names rejected')
    for r in rows:
        require(re.fullmatch('[a-z0-9][a-z0-9+.-]+', r['name']) and re.fullmatch('[A-Za-z0-9.+:~_-]+', r['version']), 'Pinned package identity required')
        require(re.fullmatch(r'(?:[A-Za-z0-9.+~_-]|%3[aA])+\.deb', r['file']) and re.fullmatch('[a-f0-9]{64}', r['sha256']), 'Safe package filename and exact SHA required')
        file = directory / r['file']
        require(file.is_file() and not file.is_symlink() and sha(file) == r['sha256'], 'Offline deb checksum mismatch')
    return rows


def install_command(rows, directory):
    # The frozen lock contains Depends/Pre-Depends, not optional Recommends.
    # Keep installation aligned with build-inside.sh's explicit closure scope.
    return ['apt-get', '--no-download', '--no-remove', '--no-install-recommends', '-y', 'install',
            *[str(directory / r['file']) for r in rows]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True); p.add_argument('--package-lock', type=Path, required=True)
    p.add_argument('--deb-directory', type=Path, required=True); p.add_argument('--apply', action='store_true'); p.add_argument('--confirm-instance')
    a = p.parse_args(); a.deb_directory = a.deb_directory.resolve(); c = read_config(a.config); validate(c, complete=False)
    lock = json.loads(private(a.package_lock).read_text()); rows = packages(lock, a.deb_directory.resolve())
    require(lock['dockerEngineVersion'] == c['preparedGuest']['dockerVersion'], 'Guest Docker version mismatch')
    if not a.apply:
        print(json.dumps({'writes': False, 'offlinePackagesVerified': len(rows), 'guestPrepared': False})); return
    validate_boot(c)
    require(c['stage'] == 'dev' and a.confirm_instance == c['name'] and os.geteuid() == 0 and os.uname().machine == 'aarch64', 'Apply only as root inside explicitly confirmed ARM64 dev guest')
    require(Path('/etc/sduoj-execution-vm').read_text().strip() == c['name'], 'Dedicated dev guest marker required')
    for r in rows:
        data = subprocess.check_output(['dpkg-deb', '-f', str(a.deb_directory / r['file']), 'Package', 'Version', 'Architecture'], text=True, timeout=5)
        require('Package: ' + r['name'] + '\n' in data and 'Version: ' + r['version'] + '\n' in data and any('Architecture: ' + x + '\n' in data for x in ('arm64', 'all')), 'Deb metadata differs from frozen lock')
    target = Path('/etc/docker/daemon.json'); desired = Path(__file__).with_name('daemon.json').read_bytes()
    require(not target.exists() or target.read_bytes() == desired, 'Refuse overriding another Docker daemon configuration')
    subprocess.run(install_command(rows, a.deb_directory), check=True, timeout=300)
    target.parent.mkdir(exist_ok=True); target.write_bytes(desired); target.chmod(0o600)
    subprocess.run(['systemctl', 'restart', 'docker'], check=True, timeout=60)
    print(json.dumps({'installed': True, 'guestQualified': False, 'next': 'guest-preflight; inventories; clean shutdown; standalone disk freeze'}))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        raise SystemExit('Guest package preparation rejected; private values suppressed')
