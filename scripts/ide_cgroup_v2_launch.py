#!/usr/bin/env python3
"""Start one qualified Worker using the shared dev/production Compose contract.
Production mode refuses candidate manifests. No secret values are printed.
"""
import argparse,fcntl,json,os,re,subprocess
from pathlib import Path
from ide_cgroup_v2_release import validate_bundle,sha

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--docker',default='docker');p.add_argument('--mode',choices=['dev','production'],required=True)
 p.add_argument('--qualification',type=Path,required=True);p.add_argument('--compose',type=Path,default=Path(__file__).resolve().parents[1]/'compose.ide-worker.cgroup-v2.yaml')
 a=p.parse_args();lock=validate_bundle(a.qualification)
 if sha(a.compose)!=lock['files']['permission-compose.yaml']:raise RuntimeError('Compose differs from qualification')
 name=os.environ.get('IDE_CGROUP_NAME','')
 if not re.fullmatch(r'sduoj-ide-[a-z0-9-]{1,61}',name):raise RuntimeError('Dedicated aggregate required')
 if os.environ.get('IDE_WORKER_IMAGE')!=lock['image']:raise RuntimeError('Pinned qualified image required')
 if Path(os.environ.get('IDE_ACCEPTED_CONFIG_DIR','')).resolve()!=a.qualification.resolve():raise RuntimeError('Qualification source mismatch')
 def docker(*args):return subprocess.check_output([a.docker,*args],text=True,timeout=20)
 info=json.loads(docker('info','--format','{{json .}}'))
 if (info.get('Architecture'),info.get('CgroupVersion'),info.get('CgroupDriver'))!=('aarch64','2','cgroupfs'):raise RuntimeError('ARM64 cgroup-v2/cgroupfs required')
 # A root-owned host lock serializes operators before checking the live parent.
 # One parent is never reused by Compose scale or another project.
 if os.geteuid()!=0:raise RuntimeError('Operator launch requires root for host deployment lock')
 directory=Path('/run/sduoj-ide-deploy');directory.mkdir(mode=0o700,exist_ok=True)
 if directory.is_symlink() or directory.stat().st_uid!=0 or directory.stat().st_mode&0o077:raise RuntimeError('Root-owned private deployment lock directory required')
 lock_path=directory/(name+'.lock')
 descriptor=os.open(lock_path,os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(descriptor,'a') as guard:
  fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
  ids=docker('ps','-q').split();instances=json.loads(docker('inspect',*ids)) if ids else []
  if any(x['HostConfig'].get('CgroupParent')=='/'+name for x in instances):raise RuntimeError('Aggregate already has a running Worker; use controlled stop/restart')
  root=Path('/sys/fs/cgroup')/name
  if not root.is_dir() or (root/'cgroup.procs').read_text().strip():raise RuntimeError('Provision empty aggregate before launching')
  if any(x.is_dir() for x in (root/'debug').iterdir()):raise RuntimeError('Debug recovery required before launch')
  for n,v in {'memory.max':'6442450944','memory.swap.max':'0','cpu.max':'400000 100000','pids.max':'1024'}.items():
   if (root/n).read_text().strip()!=v:raise RuntimeError('Aggregate quota mismatch')
  result=subprocess.run([a.docker,'compose','-f',str(a.compose),'up','-d','--no-build','--pull','never','--scale','worker=1','worker'],capture_output=True,text=True,timeout=60)
  if result.returncode:raise RuntimeError('Compose failed; inspect private operator logs')
  print(json.dumps({'started':True,'mode':a.mode,'image':lock['image'],'aggregate':name,'qualificationStatus':lock['status']}))
if __name__=='__main__':main()
