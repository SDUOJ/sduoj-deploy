#!/usr/bin/env python3
"""One-time aggregate and exclusive execution CPU setup inside the dedicated guest only."""
import argparse
import json
import os
from pathlib import Path
from vmctl import read_config, validate, require
from ide_cgroup_v2_setup import provision, validate as validate_aggregate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True); p.add_argument('--apply', action='store_true'); p.add_argument('--confirm-instance')
    a = p.parse_args(); c = read_config(a.config); validate(c)
    require(os.uname().machine == 'aarch64' and Path('/etc/sduoj-execution-vm').read_text().strip() == c['name'], 'Dedicated ARM64 guest marker required')
    require(c['networkPhase'] == 'integrated', 'Executor aggregate only after integrated networking review')
    root = Path('/sys/fs/cgroup'); name = c['execution']['aggregate']
    require((root / 'cgroup.controllers').is_file() and {'cpu', 'memory', 'pids', 'cpuset'} <= set((root / 'cgroup.controllers').read_text().split()), 'Guest cgroup2 controllers required')
    require(not (root / name).exists(), 'Refuse existing aggregate; inspect active/recovery state')
    if not a.apply:
        print(json.dumps({'writes': False, 'aggregateWouldUseCpuSet': '0-3', 'debugSharesSameAggregate': True})); return
    require(a.confirm_instance == c['name'] and os.geteuid() == 0, 'Explicit guest-root confirmation required')
    # This root belongs to the dedicated guest, never the production physical host.
    (root / 'cgroup.subtree_control').write_text('+cpu +memory +pids +cpuset')
    report = provision(root, name)
    parent = root / name
    for target in (parent, parent / 'debug'):
        (target / 'cpuset.mems').write_text((root / 'cpuset.mems.effective').read_text().strip())
        (target / 'cpuset.cpus').write_text('0-3')
        require((target / 'cpuset.cpus.effective').read_text().strip() == '0-3', 'IDE/debug cpuset readback mismatch')
    (parent / 'cgroup.subtree_control').write_text('+cpu +memory +pids +cpuset')
    report.update(cpuset='0-3', scope='guest-only-candidate-requires-workload-qualification')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit('Guest cgroup setup rejected; retain partial aggregate for owned inspection')
