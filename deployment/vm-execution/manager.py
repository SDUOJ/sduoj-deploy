#!/usr/bin/env python3
"""Confined QEMU process manager; no Docker socket, TAP, host package install or traffic activation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time
from vmctl import read_config, validate, require, sha, validate_preparation, verify_render, verify_boot_assets


def probe(c, state):
    require(state.is_dir() and state.stat().st_uid == os.getuid() and (state.stat().st_mode & 0o777) == 0o700, 'Owned private state required')
    verify_render(c, state)
    p = c['preparedGuest']
    require(sha(state / p['file']) == p['sha256'] and sha(state / 'preparation-receipt.json') == p['preparationReceiptSha256'], 'Prepared disk/receipt mismatch')
    validate_preparation(c, json.loads((state / 'preparation-receipt.json').read_text()))
    verify_boot_assets(c, state)
    require((state / p['file']).stat().st_mode & 0o222 == 0, 'Frozen base disk must be read-only')
    output = subprocess.check_output(['qemu-system-aarch64', '--version'], text=True, timeout=5)
    require(re.search(r'QEMU emulator version ' + re.escape(c['qemuVersion']) + r'(?:\s|\()', output), 'Exact QEMU version required')


def argv(c, state, backend):
    health = c['healthPort']
    network = f"user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:{c['sshPort']}-:22,hostfwd=tcp:{c['healthBindAddress']}:{health}-:{health}"
    if c['networkPhase'] == 'bootstrap':
        network += ',restrict=on'
    # Judger/Run are MQ consumers without an HTTP server. Their Nacos ports are
    # registration identities; only SSH and the real IDE ready listener forward.
    return ['qemu-system-aarch64', '-name', c['name'], '-machine', c['machine'] + ',gic-version=3',
            '-accel', backend, '-cpu', 'host', '-smp', str(c['vcpus']), '-m', str(c['memoryMiB']),
            '-kernel', str(state / 'kernel.Image'), '-initrd', str(state / 'initrd.img'), '-append', c['boot']['commandLine'],
            '-drive', f'if=none,id=osdisk,format=qcow2,file={state / "disk.qcow2"}', '-device', 'virtio-blk-pci,drive=osdisk',
            '-drive', f'if=none,id=seed,format=raw,readonly=on,file={state / "seed.iso"}', '-device', 'virtio-blk-pci,drive=seed',
            '-netdev', network, '-device', 'virtio-net-pci,netdev=net0,romfile=', '-device', 'virtio-rng-pci',
            '-display', 'none', '-monitor', 'none', '-serial', f'file:{state / "serial.log"}',
            '-qmp', f'unix:{state / "qmp.sock"},server=on,wait=off', '-no-reboot']


def prepare(c, state, backend):
    outputs = [state / x for x in ('disk.qcow2', 'seed.iso')]
    require(all(not p.exists() and not p.is_symlink() for p in outputs), 'Refuse existing VM overlay/firmware/seed')
    info = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', str(state / c['preparedGuest']['file'])], timeout=10))
    require(info.get('format') == 'qcow2' and not info.get('backing-filename'), 'Prepared base must be standalone QCOW2')
    subprocess.run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(state / c['preparedGuest']['file']), str(outputs[0]), str(c['diskGiB']) + 'G'], check=True, timeout=30)
    if backend == 'hvf':
        seed_input = state / 'seed-input'
        seed_input.mkdir(mode=0o700)
        for name in ('user-data', 'meta-data'):
            shutil.copyfile(state / name, seed_input / name)
            (seed_input / name).chmod(0o600)
        subprocess.run(['hdiutil', 'makehybrid', '-iso', '-joliet', '-default-volume-name', 'cidata', '-o', str(outputs[1]), str(seed_input)], check=True, timeout=30)
    else:
        subprocess.run(['cloud-localds', str(outputs[1]), str(state / 'user-data'), str(state / 'meta-data')], check=True, timeout=30)
    for p in outputs:
        p.chmod(0o600)
    (state / 'prepared-overlay.json').write_text(json.dumps({'instance': c['name'], 'baseSha256': c['preparedGuest']['sha256'], 'seedSha256': sha(outputs[1]), 'bootMode': 'direct-kernel', 'boot': c['boot'], 'booted': False}, indent=2))


def request_shutdown(path):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(3); s.connect(str(path))
        stream = s.makefile('rwb', buffering=0)
        json.loads(stream.readline())
        for command in ('qmp_capabilities', 'system_powerdown'):
            stream.write((json.dumps({'execute': command}) + '\n').encode())
            while True:
                response = json.loads(stream.readline())
                if 'error' in response:
                    raise RuntimeError('QMP shutdown rejected')
                if 'return' in response:
                    break


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', default='plan', choices=('plan', 'prepare', 'start'))
    p.add_argument('--state', type=Path, default=Path('/vm'))
    p.add_argument('--backend', choices=('kvm', 'hvf'), default='kvm')
    p.add_argument('--execute', action='store_true'); p.add_argument('--confirm-instance')
    a = p.parse_args(); state = a.state.resolve(); c = read_config(state / 'config.json'); validate(c)
    if a.command == 'plan':
        print(json.dumps({'instance': c['name'], 'backend': a.backend, 'writes': False, 'vmStarted': False, 'resourceStatus': 'candidate-not-capacity-qualified'})); return
    require(a.execute and a.confirm_instance == c['name'], 'Explicit execution confirmation required')
    require(a.backend != 'hvf' or c['stage'] == 'dev', 'HVF is dev only')
    require(a.backend != 'kvm' or os.access('/dev/kvm', os.R_OK | os.W_OK), 'Native KVM device required; never fall back to TCG')
    probe(c, state)
    os.umask(0o077)
    if a.command == 'prepare':
        prepare(c, state, a.backend); return
    require(all((state / x).is_file() and not (state / x).is_symlink() for x in ('disk.qcow2', 'seed.iso', 'prepared-overlay.json')), 'Explicit prepare required before start')
    receipt = json.loads((state / 'prepared-overlay.json').read_text())
    require(receipt['instance'] == c['name'] and receipt['baseSha256'] == c['preparedGuest']['sha256'] and receipt['seedSha256'] == sha(state / 'seed.iso') and receipt.get('bootMode') == 'direct-kernel' and receipt.get('boot') == c['boot'], 'Overlay source/seed drift')
    require(not (state / 'qmp.sock').exists(), 'Refuse retained QMP socket; inspect existing VM')
    require(not (state / 'runtime.json').exists(), 'Runtime record retained; reconcile stopped/active instance before restart')
    child = subprocess.Popen(argv(c, state, a.backend))
    def stop(signum, frame):
        try:
            request_shutdown(state / 'qmp.sock')
        except (OSError, RuntimeError, ValueError):
            print('QMP shutdown not confirmed; inspect private VM state; do not discard overlay', flush=True)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    (state / 'runtime.json').write_text(json.dumps({'pid': child.pid, 'instance': c['name'], 'started': time.time(), 'backend': a.backend, 'argv': argv(c, state, a.backend), 'launcherSha256': sha(Path(__file__)), 'guestQualified': False}))
    rc = child.wait()
    print(json.dumps({'instance': c['name'], 'qemuExitcode': rc, 'trafficActivated': False}))
    raise SystemExit(rc)

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        raise SystemExit('VM manager refused operation; private values suppressed')
