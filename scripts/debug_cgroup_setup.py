#!/usr/bin/env python3
"""Inspect or provision only the explicitly named, empty debugger resource parent.

Run as root on a prepared Linux node after review. Default is read-only.
Does not alter mount layout, boot arguments, host swap or unrelated controllers.
"""
import argparse
import json
import os
from pathlib import Path

GIB=1024**3
parser=argparse.ArgumentParser()
parser.add_argument('--root',default='/sys/fs/cgroup')
parser.add_argument('--parent',default='sduoj-debug')
parser.add_argument('--version',type=int,choices=(1,2),default=1)
parser.add_argument('--uid',type=int,required=True,help='Dedicated runtime service uid')
parser.add_argument('--hard-gib',type=int,default=64)
parser.add_argument('--cpus',type=int,default=32)
parser.add_argument('--pids',type=int,default=65536)
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
if not args.parent.replace('-','').isalnum() or args.uid<=0 or not 1<=args.hard_gib<=64 or not 1<=args.cpus<=64 or not 1<=args.pids<=131072:
    parser.error('Invalid resource parent or limits')
root=Path(args.root).resolve()
if not root.is_dir():parser.error('Missing cgroup mount')
names=['memory','cpu,cpuacct','pids','freezer'] if args.version==1 else ['']
parents=[root/name/args.parent for name in names]
report={'apply':args.apply,'version':args.version,'parents':list(map(str,parents)),
        'hardBytes':args.hard_gib*GIB,'cpus':args.cpus,'pids':args.pids}
if args.apply:
    if os.geteuid()!=0:parser.error('Root is required for explicit provisioning')
    for parent in parents:
        if parent.exists() and ((parent/'cgroup.procs').read_text().strip() or any(p.is_dir() for p in parent.iterdir())):
            parser.error('Refusing to alter a populated debugger parent: '+str(parent))
    for parent in parents:parent.mkdir(exist_ok=True)
    if args.version==1:
        memory,cpu,pids,freezer=parents
        (memory/'memory.use_hierarchy').write_text('1')
        (memory/'memory.limit_in_bytes').write_text(str(args.hard_gib*GIB))
        (cpu/'cpu.cfs_period_us').write_text('100000')
        (cpu/'cpu.cfs_quota_us').write_text(str(args.cpus*100000))
        (pids/'pids.max').write_text(str(args.pids))
    else:
        parent=parents[0]
        # Controllers must already be delegated by the node administrator.
        for name,value in [('memory.max',args.hard_gib*GIB),('cpu.max',f'{args.cpus*100000} 100000'),('pids.max',args.pids),('cgroup.subtree_control','+memory +cpu +pids')]:
            (parent/name).write_text(str(value))
    for parent in parents:
        os.chown(parent,args.uid,-1)
        # Delegation needs the parent control files as well as child mkdir.
        for name in ('cgroup.procs','tasks','cgroup.subtree_control'):
            target=parent/name
            if target.exists():os.chown(target,args.uid,-1)
for parent in parents:
    report[str(parent)]={'exists':parent.is_dir(),'writable':os.access(parent,os.W_OK)}
print(json.dumps(report,indent=2))
