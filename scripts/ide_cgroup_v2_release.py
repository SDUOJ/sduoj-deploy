#!/usr/bin/env python3
"""Validate a node evidence bundle. Never activates production.
This is a local provenance gate, not a signature or a remote attestation.
"""
import argparse,hashlib,json,math
from pathlib import Path

LANGUAGES={'c','cpp','java','python'}
PROFILE_IDS={'19','32','38','51'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def percentile(rows,fraction):
 values=sorted(row['seconds'] for row in rows)
 return values[max(0,math.ceil(len(values)*fraction)-1)] if values else None

def validate_capacity(raw):
 if raw.get('passed') is not True or raw.get('onlineUsers')!=500 or raw.get('createdSessions')!=500 or raw.get('preflightErrors')!=[]:raise ValueError('500 real online sessions required')
 contract=raw.get('contract',{})
 expected={'stageSeconds':75.,'rampSeconds':20.,'cycleSeconds':2.5,'browserIntervalMs':300,'codeBytes':4096,'languagePattern':['c']*4+['cpp']*4+['java','python']}
 if any(contract.get(k)!=v for k,v in expected.items()):raise ValueError('Workload contract mismatch')
 stages=raw.get('stages',[])
 if len(stages)!=3 or [s.get('activeUsers') for s in stages]!=[20,50,100]:raise ValueError('All 20/50/100 active stages required')
 for stage in stages:
  if stage.get('complete') is not True or stage.get('passed') is not True:raise ValueError('Incomplete capacity stage')
  rows=stage.get('results',[])
  if not rows or any(not finite(r.get('seconds')) or r['seconds']<0 or r.get('language') not in LANGUAGES for r in rows):raise ValueError('Finite raw timing samples required')
  steady=[r for r in rows if r.get('phase')=='steady']
  if len(steady)<stage['activeUsers']*29:raise ValueError('Insufficient steady samples')
  if set(stage.get('byLanguage',{}))!=LANGUAGES:raise ValueError('Missing language metrics')
  for language in [None,*sorted(LANGUAGES)]:
   selected=steady if language is None else [r for r in steady if r['language']==language]
   valid=[r for r in selected if r.get('outcome')=='valid']
   metric=stage['overall'] if language is None else stage['byLanguage'][language]
   rate=len(valid)/len(selected) if selected else 0.;p95=percentile(valid,.95)
   if metric.get('count')!=len(selected) or not finite(metric.get('validRate')) or metric['validRate']!=rate or not finite(metric.get('validP95')) or metric['validP95']!=p95:raise ValueError('Raw and summary metrics disagree')
   if rate<.95 or p95 is None or p95>1:raise ValueError('Capacity engineering reference failed')
 if raw.get('cleanup')!={'attempted':500,'closed':500}:raise ValueError('All online sessions must be cleaned')

def browser_tests(suites):
 out=[]
 for suite in suites:
  for spec in suite.get('specs',[]):
   for test in spec.get('tests',[]):out.append((spec.get('title',''),test))
  out.extend(browser_tests(suite.get('suites',[])))
 return out

def validate_receipts(receipts,image):
 required={'api1','api2','browser','capacity','isolation','identity','mixed','recovery','execution'}
 if set(receipts)!=required:raise ValueError('Exact qualification receipt set required')
 if digest(receipts['api1'])==digest(receipts['api2']):raise ValueError('Independent API rounds required')
 for name in ('api1','api2'):
  value=receipts[name]
  if value.get('passed') is not True or set(value.get('cases',{}))!=LANGUAGES or any(value['cases'][lang].get(part,{}).get('passed') is not True for lang in value['cases'] for part in ('lsp','debug')):raise ValueError('Two complete four-language API rounds required')
 browser=receipts['browser'];stats=browser.get('stats',{})
 if stats.get('expected')!=4 or any(stats.get(k)!=0 for k in ('unexpected','skipped','flaky')) or browser.get('errors'):raise ValueError('Four browser cases without skips/retries required')
 tests=browser_tests(browser.get('suites',[]))
 if len(tests)!=4 or any(len(t.get('results',[]))!=1 or t['results'][0].get('status')!='passed' or t['results'][0].get('retry')!=0 or t['results'][0].get('errors') for _,t in tests):raise ValueError('Complete browser test results required')
 for language in LANGUAGES:
  if sum(title.startswith('real '+language+' ') for title,_ in tests)!=1:raise ValueError('Four different browser languages required')
 isolation=receipts['isolation']
 if isolation.get('passed') is not True or not isolation.get('checks') or any(v is not True for v in isolation['checks'].values()):raise ValueError('Real isolation acceptance required')
 identity=receipts['identity']
 if identity.get('passed') is not True or identity.get('image')!=image:raise ValueError('Identity mismatch')
 execution=receipts['execution']
 if not execution.get('containerId') or execution.get('image')!=image or not execution.get('permissionSha256') or not execution.get('configurationSha256'):raise ValueError('Execution identity binding required')
 for label in ('initial','final'):
  snapshot=execution[label]
  if snapshot['identity']['id']!=execution['containerId'] or snapshot['identity']['image']!=image or snapshot['identity']['privileged'] or snapshot['identity']['user']!='10001:10001' or snapshot['health']['ready'] is not True:raise ValueError('Execution start/end identity drift')
 for monitor in execution['monitors']:
  if monitor.get('passed') is not True or monitor.get('exitcode')!=0 or any(s.get('exitcode')!=0 for s in monitor['stages']):raise ValueError('Failed execution monitor')
 for name in required-{'execution'}:
  if execution['receiptDigests'].get(name)!=digest(receipts[name]):raise ValueError('Receipt binding mismatch')
 mixed=receipts['mixed']
 if mixed.get('passed') is not True or mixed.get('createdCount')!=1 or mixed.get('debugCleanup') is not True or not finite(mixed.get('actualSteadyOverlapSeconds')) or mixed['actualSteadyOverlapSeconds']<20:raise ValueError('Mixed Debug/LSP acceptance required')
 if mixed.get('debugOutput')!='ECHO:47\n':raise ValueError('Mixed business output mismatch')
 recovery=receipts['recovery']
 if recovery.get('passed') is not True or recovery.get('graceful') is not True or recovery.get('restartCount')!=1 or recovery.get('newSceneOutput')!='ECHO:47\n':raise ValueError('Graceful recovery acceptance required')
 validate_capacity(receipts['capacity'])

REQUIRED_FILES={'debug-profiles.json','receipts.json','permission-compose.yaml'}
def validate_bundle(directory):
 root=Path(directory);lock=json.loads((root/'qualification-lock.json').read_text())
 if lock.get('status')!='NODE_QUALIFIED_NOT_PRODUCTION_ACTIVATED' or lock.get('productionActivated') is not False or set(lock.get('files',{}))!=REQUIRED_FILES:raise ValueError('Complete node qualification required')
 for name,expected in lock['files'].items():
  path=root/name
  if path.is_symlink() or not path.is_file() or sha(path)!=expected:raise ValueError('Qualification drift: '+name)
 profiles=json.loads((root/'debug-profiles.json').read_text())
 if set(profiles)!=PROFILE_IDS or any(p.get('acceptanceScope')!='node-qualified-arm64-cgroup-v2-shared-v1' or p.get('verified') is not True for p in profiles.values()):raise ValueError('Candidate/developer manifest rejected')
 receipts=json.loads((root/'receipts.json').read_text());validate_receipts(receipts,lock['image'])
 if sha(root/'permission-compose.yaml')!=receipts['execution']['permissionSha256']:raise ValueError('Permission contract drift')
 return lock

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('candidate','receipts','permission-compose','output','verify'):parser.add_argument('--'+name,type=Path)
 parser.add_argument('--image');a=parser.parse_args()
 if a.verify:
  lock=validate_bundle(a.verify);print(json.dumps({'passed':True,'status':lock['status'],'image':lock['image']}));return
 if any(x is None for x in (a.candidate,a.receipts,a.permission_compose,a.image,a.output)):parser.error('All qualification inputs required')
 if a.output.exists():parser.error('Refuse existing output')
 receipts=json.loads(a.receipts.read_text());validate_receipts(receipts,a.image)
 if sha(a.permission_compose)!=receipts['execution']['permissionSha256']:raise ValueError('Compose differs from execution contract')
 profiles=json.loads(a.candidate.read_text())
 if set(profiles)!=PROFILE_IDS:raise ValueError('Four pinned templates required')
 for p in profiles.values():
  if not str(p.get('acceptanceScope','')).startswith('operator-candidate-'):raise ValueError('Explicit operator candidate required')
  p.update(acceptanceScope='node-qualified-arm64-cgroup-v2-shared-v1',verified=True)
 a.output.mkdir(mode=0o700)
 for name,value in [('debug-profiles.json',profiles),('receipts.json',receipts)]:(a.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
 (a.output/'permission-compose.yaml').write_bytes(a.permission_compose.read_bytes())
 lock={'status':'NODE_QUALIFIED_NOT_PRODUCTION_ACTIVATED','image':a.image,'productionActivated':False,'files':{name:sha(a.output/name) for name in sorted(REQUIRED_FILES)},'scope':'tested node and workload; other nodes require local qualification'}
 (a.output/'qualification-lock.json').write_text(json.dumps(lock,indent=2)+'\n');validate_bundle(a.output);print(json.dumps(lock))
if __name__=='__main__':main()
