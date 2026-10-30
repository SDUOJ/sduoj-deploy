#!/usr/bin/env python3
"""Provision one empty owned aggregate. Run once on Linux as root, never in Worker.

The ancestor already supplies cpu/memory/pids; this tool never edits it.
Docker's cgroupfs driver places management below this aggregate, while Debug
uses its delegated sibling. Both remain charged to the 4 CPU/6 GiB envelope.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

LIMITS = {'memory.max': '6442450944', 'memory.swap.max': '0',
          'cpu.max': '400000 100000', 'pids.max': '1024'}
DEBUG_LIMITS = {'memory.max': '1610612736', 'cpu.max': '100000 100000',
                'pids.max': '512'}


def validate(root, name):
    root = Path(root)
    if root.is_symlink() or not root.is_absolute() or '..' in root.parts:
        raise ValueError('Explicit real cgroup mount required')
    if not re.fullmatch(r'sduoj-ide-[a-z0-9][a-z0-9-]{0,60}', name):
        raise ValueError('A dedicated sduoj-ide deployment name is required')
    if not (root / 'cgroup.controllers').is_file():
        raise ValueError('cgroup-v2 is required')
    # statfs avoids mistaking an ordinary directory with forged control files
    # for a delegated kernel cgroup tree. Unit tests replace this OS boundary.
    if filesystem_type(root) != 0x63677270:
        raise ValueError('A real cgroup2 filesystem is required')
    if not {'cpu', 'memory', 'pids'} <= set((root / 'cgroup.subtree_control').read_text().split()):
        raise ValueError('Administrator must enable ancestor controllers first')
    parent = root / name
    if parent.exists() or parent.is_symlink():
        raise ValueError('Refusing existing aggregate; inspect/recover it separately')
    return parent


def filesystem_type(path):
    import ctypes
    storage = ctypes.create_string_buffer(256)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.statfs(os.fsencode(path), ctypes.byref(storage)) != 0:
        raise OSError(ctypes.get_errno(), 'statfs failed')
    return ctypes.c_long.from_buffer(storage).value


def provision(root, name):
    parent = validate(root, name)
    if os.geteuid() != 0:
        raise PermissionError('One-time host provisioning requires root')
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    for name, value in LIMITS.items():
        (parent / name).write_text(value)
        if (parent / name).read_text().strip() != value:
            raise RuntimeError('Aggregate limit readback mismatch: ' + name)
    (parent / 'cgroup.subtree_control').write_text('+cpu +memory +pids')
    # Only membership at the common ancestor is delegated. In particular the
    # service cannot modify aggregate limits or create arbitrary root children.
    os.chown(parent / 'cgroup.procs', 10001, 10001)
    debug = parent / 'debug'
    debug.mkdir(mode=0o755)
    debug.chmod(0o755)
    for name, value in DEBUG_LIMITS.items():
        (debug / name).write_text(value)
        if (debug / name).read_text().strip() != value:
            raise RuntimeError('Debug limit readback mismatch: ' + name)
    (debug / 'cgroup.subtree_control').write_text('+cpu +memory +pids')
    os.chown(debug, 10001, 10001)
    for name in ('cgroup.procs', 'cgroup.threads', 'cgroup.subtree_control'):
        os.chown(debug / name, 10001, 10001)
    return {'aggregate': str(parent), 'uid': 10001, 'gid': 10001,
            'limits': LIMITS, 'debugLimits': DEBUG_LIMITS,
            'scope': 'shared-permission-candidate-not-node-acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/sys/fs/cgroup')
    parser.add_argument('--name', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--docker', default='docker')
    args = parser.parse_args()
    info = json.loads(subprocess.check_output(
        [args.docker, 'info', '--format', '{{json .}}'], text=True, timeout=10))
    if (info.get('CgroupVersion') != '2' or info.get('CgroupDriver') != 'cgroupfs'
            or info.get('Architecture') != 'aarch64'):
        parser.error('Requires ARM64 Docker cgroup-v2 with cgroupfs driver')
    if args.apply:
        report = provision(args.root, args.name)
    else:
        report = {'aggregate': str(validate(args.root, args.name)), 'apply': False,
                  'limits': LIMITS, 'debugLimits': DEBUG_LIMITS}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
