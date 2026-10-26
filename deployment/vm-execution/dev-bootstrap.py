#!/usr/bin/env python3
"""Prepare the FIRST Docker-free dev guest from the pinned upstream disk.

This entry is deliberately separate from qualified prepared-guest deployment.
Default plan is read-only; prepare/start require an exact dev instance.
"""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import struct
import subprocess
import time
from vmctl import require, sha, private, config_hash, write
from manager import request_shutdown

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


source = module('bootstrap_source', 'fetch-source.py')
native = module('bootstrap_native', 'native-bundle.py')


def real_path(value):
    p = Path(value)
    require(p.is_absolute() and str(p) == str(p.resolve()) and re.fullmatch(r'/[A-Za-z0-9_./+-]+', str(p)), 'Canonical absolute path required')
    return p


def validate(c):
    require(c.get('schemaVersion') == 1 and c.get('stage') == 'dev-bootstrap', 'Dev bootstrap only; production is rejected')
    require(re.fullmatch(r'sduoj-execution-dev-bootstrap-[a-z0-9][a-z0-9-]{0,32}', c.get('name', '')), 'Explicit dev bootstrap identity required')
    for key in ('stateDirectory', 'sourceImage', 'nativeLock', 'nativeDirectory'):
        real_path(c[key])
    require(c['stateDirectory'] != '/' and Path(c['stateDirectory']).parent.is_dir(), 'Existing private-state parent required')
    require(len(str(Path(c['stateDirectory']) / 'qmp.sock').encode()) <= 100, 'Use a short private state path within the native Unix-socket limit')
    require((c.get('vcpus'), c.get('memoryMiB'), c.get('diskGiB')) == (16, 24576, 120), 'Keep candidate 16 CPU/24 GiB/120 GiB envelope')
    require(type(c.get('sshPort')) is int and 1024 <= c['sshPort'] <= 65535, 'Explicit nonprivileged loopback SSH port required')
    key = c.get('guestSshPublicKey', '')
    require(re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{40,100}={0,2}(?: [A-Za-z0-9._@-]+)?', key), 'Only an explicit Ed25519 public key is accepted')
    decoded = base64.b64decode(key.split()[1], validate=True)
    require(len(decoded) == 51 and decoded.startswith(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32)) and decoded[-32:] != bytes(32), 'Valid Ed25519 wire-format required')
    require(set(c) == {'schemaVersion', 'stage', 'name', 'stateDirectory', 'sourceImage', 'nativeLock', 'nativeDirectory', 'vcpus', 'memoryMiB', 'diskGiB', 'sshPort', 'guestSshPublicKey'}, 'Unexpected fields, endpoints and credentials rejected')


def tools(c, runtime=False):
    lock = json.loads(private(c['nativeLock']).read_text())
    native.verify(lock, real_path(c['nativeDirectory']), runtime_checks=runtime)
    return lock, real_path(c['nativeDirectory'])


def host_capacity():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Native ARM64 Mac HVF required; no TCG fallback')
    def sysctl(name):
        return int(subprocess.check_output(['sysctl', '-n', name], text=True, timeout=5).strip())
    require(sysctl('kern.hv_support') == 1 and sysctl('hw.ncpu') >= 16 and sysctl('hw.memsize') >= 32 * 1024**3, 'Host must support HVF and the candidate envelope; sole runtime owner must also reconcile current resource availability')


def identity(c, source_lock, native_lock):
    return {'configurationSha256': config_hash(c), 'upstreamSha256': source_lock['sha256'], 'upstreamSha512': source_lock['sha512'],
            'nativeLockSha256': sha(c['nativeLock']), 'qemuVersion': native_lock['qemuVersion'],
            'firmwareCodeSha256': native_lock['files']['share/AAVMF/AAVMF_CODE.fd'],
            'firmwareVarsSha256': native_lock['files']['share/AAVMF/AAVMF_VARS.fd']}


def prepare(c):
    host_capacity()
    lock, bundle = tools(c, runtime=True)
    upstream = json.loads(source.LOCK.read_text()); source.validate(upstream)
    disk = real_path(c['sourceImage'])
    require(disk.is_file() and not disk.is_symlink(), 'Real verified source disk required')
    source.audit(disk, upstream)
    state = real_path(c['stateDirectory'])
    require(not state.exists() and not state.is_symlink(), 'New private state only; partial state is preserved')
    os.umask(0o077); state.mkdir(mode=0o700)
    write(state / 'config.json', json.dumps(c, indent=2) + '\n')
    shutil.copyfile(disk, state / 'source.qcow2'); (state / 'source.qcow2').chmod(0o400)
    source.audit(state / 'source.qcow2', upstream)
    shutil.copyfile(bundle / 'share/AAVMF/AAVMF_VARS.fd', state / 'vars.fd')
    (state / 'vars.fd').chmod(0o600)
    subprocess.run([str(bundle / 'bin/qemu-img'), 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(state / 'source.qcow2'), str(state / 'disk.qcow2'), str(c['diskGiB']) + 'G'], check=True, timeout=30)
    (state / 'disk.qcow2').chmod(0o600)
    seed = state / 'seed-input'; seed.mkdir(mode=0o700)
    # Only public identity and marker: no apt/network installs, credentials or consumers.
    data = {'hostname': c['name'], 'manage_etc_hosts': True, 'disable_root': True, 'ssh_pwauth': False,
            'ssh_deletekeys': True, 'ssh_genkeytypes': ['ed25519'], 'package_update': False, 'package_upgrade': False,
            'users': [{'name': 'executor-admin', 'groups': ['sudo'], 'sudo': ['ALL=(ALL) NOPASSWD:ALL'], 'shell': '/bin/bash', 'lock_passwd': True, 'ssh_authorized_keys': [c['guestSshPublicKey']]}],
            'write_files': [{'path': '/etc/sduoj-execution-vm', 'permissions': '0600', 'owner': 'root:root', 'content': c['name'] + '\n'}]}
    write(seed / 'user-data', '#cloud-config\n' + json.dumps(data, indent=2) + '\n')
    write(seed / 'meta-data', json.dumps({'instance-id': c['name'], 'local-hostname': c['name']}) + '\n')
    subprocess.run(['hdiutil', 'makehybrid', '-iso', '-joliet', '-default-volume-name', 'cidata', '-o', str(state / 'seed.iso'), str(seed)], check=True, timeout=30)
    (state / 'seed.iso').chmod(0o600)
    receipt = identity(c, upstream, lock)
    receipt.update(schemaVersion=1, status='UPSTREAM_OVERLAY_PREPARED_NOT_BOOTED', instance=c['name'], guestQualified=False, dockerInstalled=False,
                   files={name: sha(state / name) for name in ('config.json', 'seed.iso', 'vars.fd', 'seed-input/user-data', 'seed-input/meta-data')})
    write(state / 'bootstrap-receipt.json', json.dumps(receipt, indent=2) + '\n')
    return {'prepared': True, 'guestBooted': False, 'guestQualified': False, 'instance': c['name']}


def verify_state(c, lock):
    state = real_path(c['stateDirectory'])
    require(state.is_dir() and stat.S_IMODE(state.stat().st_mode) == 0o700 and state.stat().st_uid == os.getuid(), 'Owned mode0700 dev state required')
    receipt = json.loads(private(state / 'bootstrap-receipt.json').read_text())
    upstream = json.loads(source.LOCK.read_text()); source.validate(upstream)
    expected = identity(c, upstream, lock)
    require(all(receipt.get(k) == v for k, v in expected.items()) and receipt.get('instance') == c['name'] and receipt.get('status') == 'UPSTREAM_OVERLAY_PREPARED_NOT_BOOTED', 'Bootstrap identity drift')
    names = {'config.json', 'seed.iso', 'vars.fd', 'seed-input/user-data', 'seed-input/meta-data'}
    require(set(receipt.get('files', {})) == names, 'Exact initial file inventory required')
    require(all(sha(private(state / name)) == receipt['files'][name] for name in names), 'Bootstrap file drift')
    require(not (state / 'source.qcow2').is_symlink() and (state / 'source.qcow2').stat().st_mode & 0o222 == 0, 'Frozen source must remain read-only')
    source.audit(state / 'source.qcow2', upstream)
    require((state / 'disk.qcow2').is_file() and not (state / 'disk.qcow2').is_symlink(), 'Real overlay required')
    require(not (state / 'runtime.json').exists() and not (state / 'qmp.sock').exists(), 'Prior runtime retained; inspect instance before any restart')
    return state


def argv(c, state, bundle):
    return [str(bundle / 'bin/qemu-system-aarch64'), '-name', c['name'], '-machine', 'virt-10.0,gic-version=3', '-accel', 'hvf', '-cpu', 'host',
            '-smp', str(c['vcpus']), '-m', str(c['memoryMiB']),
            '-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={bundle / "share/AAVMF/AAVMF_CODE.fd"}',
            '-drive', f'if=pflash,format=raw,unit=1,file={state / "vars.fd"}',
            '-drive', f'if=none,id=osdisk,format=qcow2,file={state / "disk.qcow2"}', '-device', 'virtio-blk-pci,drive=osdisk',
            '-drive', f'if=none,id=seed,format=raw,readonly=on,file={state / "seed.iso"}', '-device', 'virtio-blk-pci,drive=seed',
            '-netdev', f'user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:{c["sshPort"]}-:22', '-device', 'virtio-net-pci,netdev=net0,romfile=', '-device', 'virtio-rng-pci',
            '-display', 'none', '-monitor', 'none', '-serial', f'file:{state / "serial.log"}', '-qmp', f'unix:{state / "qmp.sock"},server=on,wait=off', '-no-reboot']


def start(c):
    host_capacity(); lock, bundle = tools(c, runtime=True); state = verify_state(c, lock)
    version = subprocess.check_output([str(bundle / 'bin/qemu-system-aarch64'), '--version'], text=True, timeout=5)
    require(re.search(r'QEMU emulator version ' + re.escape(lock['qemuVersion']) + r'(?:\s|\()', version), 'Fixed native QEMU version required')
    info = json.loads(subprocess.check_output([str(bundle / 'bin/qemu-img'), 'info', '--output=json', str(state / 'disk.qcow2')], timeout=10))
    require(info.get('format') == 'qcow2' and info.get('full-backing-filename') == str(state / 'source.qcow2'), 'Overlay backing identity mismatch')
    child = subprocess.Popen(argv(c, state, bundle))
    def stop(signum, frame):
        try:
            request_shutdown(state / 'qmp.sock')
        except (OSError, RuntimeError, ValueError):
            print('Shutdown not confirmed; retain dev overlay and inspect the owned process', flush=True)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    write(state / 'runtime.json', json.dumps({'instance': c['name'], 'pid': child.pid, 'started': time.time(), 'backend': 'hvf', 'guestQualified': False}))
    rc = child.wait()
    write(state / 'exit.json', json.dumps({'instance': c['name'], 'qemuExitCode': rc, 'finished': time.time(), 'guestQualified': False}))
    return rc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', choices=('plan', 'prepare', 'start'), default='plan')
    p.add_argument('--config', type=Path); p.add_argument('--execute', action='store_true'); p.add_argument('--confirm-instance')
    a = p.parse_args()
    if not a.config:
        require(a.command == 'plan', 'Explicit private config required')
        print(json.dumps({'writes': False, 'guestStarted': False, 'preparedGuestRequired': False, 'scope': 'initial-dev-only'})); return
    c = json.loads(private(a.config).read_text()); validate(c)
    if a.command == 'plan':
        print(json.dumps({'writes': False, 'guestStarted': False, 'instance': c['name'], 'scope': 'initial-dev-only', 'configurationSha256': config_hash(c)})); return
    require(a.execute and a.confirm_instance == c['name'], 'Explicit execution and exact dev identity required')
    if a.command == 'prepare':
        print(json.dumps(prepare(c)))
    else:
        raise SystemExit(start(c))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        raise SystemExit('Initial dev bootstrap rejected; preserve any partial state; no production changes')
