#!/usr/bin/env python3
"""Run inside the exact runtime, without modifying its service process.

Tests a real child's cross-sibling migration, not merely empty group creation.
This is a prerequisite probe; four-language sandbox acceptance is separate.
"""
import json
import os
from pathlib import Path
import subprocess


def main():
    from ide_debug.config import Policy
    from ide_debug.cgroups import Cgroups, delegated_paths, preflight
    if (os.getuid(), os.getgid()) != (10001, 10001):
        raise RuntimeError('Dedicated non-root runtime identity required')
    policy = Policy(cgroup_version=2, cgroup_parent='debug', subuid=100000,
                    subgid=100000, budget=1342177280, hard=1610612736,
                    reserve=67108864, host_floor=0, pid_budget=512,
                    nsjail='/opt/sduoj-ide/scripts/nsjail')
    preflight(policy)
    root = Path('/sys/fs/cgroup')
    expected = {'memory.max': '6442450944', 'memory.swap.max': '0',
                'cpu.max': '400000 100000', 'pids.max': '1024'}
    for name, value in expected.items():
        if (root / name).read_text().strip() != value or os.access(root / name, os.W_OK):
            raise RuntimeError('Aggregate envelope not pinned or writable by Worker')
    if os.access(root, os.W_OK):
        raise RuntimeError('Worker must not own aggregate root directory')
    group = Cgroups(delegated_paths(policy, 'permission-probe'), 2)
    group.create(33554432, 8)
    child = None
    try:
        child = subprocess.Popen(['python3', '-c', 'import time;time.sleep(30)'])
        group.attach(child.pid)
        if str(child.pid) not in (root / 'debug/permission-probe/cgroup.procs').read_text().split():
            raise RuntimeError('Actual child migration failed')
    finally:
        if child is not None:
            try:
                child.terminate()
                child.wait(timeout=5)
            finally:
                group.remove()
        else:
            group.remove()
    return {'passed': True, 'uid': os.getuid(), 'gid': os.getgid(),
            'actualChildMigration': True, 'aggregateLimits': expected,
            'aggregateLimitsWritable': False, 'cleanup': True}


if __name__ == '__main__':
    print(json.dumps(main()))
