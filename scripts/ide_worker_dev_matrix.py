#!/usr/bin/env python3
"""Run bounded, serial single-Worker dev comparisons; never promote production.

Each profile has its own container and Nacos dataId. The original idle Worker
is stopped, never removed. Raw load reports are immutable after their writer
exits; summaries are separate. This command starts real workloads only when
explicitly invoked. Importing it and running its unit tests have no side effects.
"""
import argparse
import copy
from dataclasses import asdict, dataclass
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid


GiB = 1024 ** 3
LANGUAGES = ('c', 'cpp', 'java', 'python')
OWN_CONTAINER = re.compile(r'^sduoj-ide-[a-z0-9-]+-20261025(?:-[a-z0-9-]+)?$')
IMAGE_ID = re.compile(r'^sha256:[a-f0-9]{64}$')
PRIVATE_ROOT = re.compile(r'^/private/tmp/sduoj-ide-probe-[A-Za-z0-9_-]+$')
DATA_ID = re.compile(r'^ide-worker-matrix-dev-20261025-[a-z0-9-]+\.yml$')
EXISTING_WORKER = 'sduoj-ide-mbp-20261025-r6-worker-1'
MINI_GATEWAY = 'sduoj-ide-release-gates-20261025-gateway-1'
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Profile:
    name: str
    cpus: float
    memory_gib: int
    c_cpp_documents: int = 32
    java_python_documents: int = 32
    java_processors: object = 2

    @property
    def guard_bytes(self):
        return self.memory_gib * GiB * 7 // 8


PROFILES = {
    p.name: p for p in (
        Profile('p0', 1.5, 4),
        Profile('p1', 4, 4),
        Profile('p2', 4, 8),
        Profile('p3', 4, 8, 48),
        Profile('p4', 4, 8, 48, java_processors=None),
        Profile('p5', 2, 6, 48),
        Profile('p6', 4, 4, 48),
        Profile('p7', 4, 6, 48),
    )
}
DEFAULT_PROFILES = ('p0', 'p1', 'p2', 'p3', 'p4', 'p5')


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_frozen_sources(args):
    if any(sha256(path) != expected for path, expected in args.frozen_source_hashes.items()):
        raise RuntimeError('Matrix or workload source changed after validation')


def loopback_url(value):
    parsed = urllib.parse.urlparse(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('Only an explicit HTTP loopback base URL is accepted')
    if not parsed.port:
        raise ValueError('A dev port is required')
    return value.rstrip('/')


def private_file(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError('Private input must be a regular mode0600 file')
    return path


def validate_template(template, expected_prefix):
    if (not isinstance(template, dict) or template.get('schemaVersion') != 1
            or not isinstance(template.get('environment'), dict)):
        raise ValueError('Expected schemaVersion1 environment template')
    env = template['environment']
    if env.get('SDUOJ_IDE_PREFIX') != expected_prefix:
        raise ValueError('Redis prefix must exactly match the declared dev prefix')
    if (not expected_prefix.startswith('sduoj:ide:') or not expected_prefix.endswith(':')
            or not any(t in expected_prefix for t in ('dev', 'release-gates', 'tuning', 'matrix'))
            or 'prod' in expected_prefix.lower()):
        raise ValueError('Only an isolated IDE dev prefix is accepted')
    for name, value in env.items():
        if any(word in name.upper() for word in ('PASSWORD', 'TOKEN', 'SECRET')):
            if not isinstance(value, str) or not re.fullmatch(r'\$\{[A-Z_][A-Z0-9_]*\}', value):
                raise ValueError('Secret template settings must remain local placeholders')
    if str(env.get('AUTOLAB_DEBUG_RESIDENT')) != '8':
        raise ValueError('The fixed dev Debug resident contract must remain8')
    return template


def profile_config(template, profile):
    result = copy.deepcopy(template)
    env = result['environment']
    env.update(SDUOJ_IDE_LSP_PROCESSES='1', SDUOJ_IDE_CLANGD_JOBS='2',
               SDUOJ_IDE_MAX_DOCUMENTS='32', SDUOJ_IDE_JAVA_HEAP_MB='384',
               SDUOJ_IDE_C_CONCURRENCY='2', SDUOJ_IDE_CPP_CONCURRENCY='2',
               SDUOJ_IDE_JAVA_CONCURRENCY='1', SDUOJ_IDE_PYTHON_CONCURRENCY='2')
    for language in LANGUAGES:
        env['SDUOJ_IDE_' + language.upper() + '_MAX_DOCUMENTS'] = str(
            profile.c_cpp_documents if language in ('c', 'cpp') else profile.java_python_documents)
    if profile.java_processors is None:
        env.pop('SDUOJ_IDE_JAVA_PROCESSORS', None)
    else:
        env['SDUOJ_IDE_JAVA_PROCESSORS'] = str(profile.java_processors)
    return result


def is_idle(health):
    components = health.get('components', [])
    seen, debug = set(), None
    for component in components:
        metrics = component.get('metrics', {})
        if component.get('role') == 'lsp':
            language = component.get('language')
            rows = metrics.get('languages', {})
            if language not in LANGUAGES or not isinstance(rows, dict):
                return False
            # Empty language metrics before lazy server startup still mean0 docs.
            if any(row.get('documents') != 0 for row in rows.values()):
                return False
            seen.add(language)
        elif component.get('role') == 'debug':
            debug = metrics
    return (seen == set(LANGUAGES) and debug is not None
            and all(debug.get(k) == 0 for k in ('resident', 'active', 'queued', 'grantedBytes')))


def assert_identity(identity, image_id, profile=None):
    if identity.get('image') != image_id or identity.get('status') != 'running':
        raise RuntimeError('Worker image or running state changed')
    if profile and (identity.get('NanoCpus') != int(profile.cpus * 1e9)
                    or identity.get('Memory') != profile.memory_gib * GiB
                    or identity.get('PidsLimit') != 1024):
        raise RuntimeError('Worker cgroup resource contract changed')
    if identity.get('oomKilled'):
        raise RuntimeError('Worker OOM was observed')


def guard_reason(sample, profile, worker_id, image_id):
    try:
        assert_identity(sample['remote']['identity'], image_id, profile)
    except (KeyError, RuntimeError):
        return 'worker_identity_or_running_failure'
    remote, mini = sample['remote'], sample['mini']
    if not remote['health'].get('ready'):
        return 'worker_not_ready'
    if not is_idle_debug(remote['health']):
        return 'unexpected_debug_activity'
    probe = remote['probe']
    expected = {f'lsp:{lang}': [worker_id + '-' + lang] for lang in LANGUAGES}
    expected['debug:all'] = [worker_id + '-debug']
    if probe.get('registry') != expected:
        return 'registry_not_single_expected_worker'
    if int(probe['cgroup']['memory.current']) > profile.guard_bytes:
        return 'worker_memory_guard'
    events = parse_counters(probe['cgroup'].get('memory.events', ''))
    if events.get('oom', 0) or events.get('oom_kill', 0) or events.get('max', 0):
        return 'worker_cgroup_memory_event'
    if min(probe['memory']['MemAvailable'], mini['memory']['MemAvailable']) < GiB:
        return 'VM_available_below1GiB'
    if not mini.get('gatewayHealthy') or not sample.get('nacosReady'):
        return 'dependency_unhealthy'
    return None


def is_idle_debug(health):
    debug = [c.get('metrics', {}) for c in health.get('components', []) if c.get('role') == 'debug']
    return len(debug) == 1 and all(debug[0].get(k) == 0
                                  for k in ('resident', 'active', 'queued', 'grantedBytes'))


def parse_counters(text):
    return {key: int(value) for key, value in (line.split() for line in text.splitlines() if line.strip())}


def memory_events_clear(probe):
    try:
        events = parse_counters(probe['cgroup']['memory.events'])
        return all(key in events and events[key] == 0 for key in ('oom', 'oom_kill', 'max'))
    except (KeyError, TypeError, ValueError):
        return False


def may_continue_memory_guard(enabled, result, current, following):
    """Allow only a fully contained quota-capacity result, never infrastructure loss."""
    if not enabled or following is None or result.get('stopReason') != 'worker_memory_guard':
        return False
    before, after = asdict(current), asdict(following)
    before.pop('name')
    after.pop('name')
    if before == after:
        return False
    if any(result.get(key) for key in ('failureCategory', 'cleanupProbeCategory', 'stopCategory')):
        return False
    final = result.get('cleanupHealth', {})
    stopped = result.get('stopped', {}).get('identity', {})
    return bool(result.get('executed') and result.get('allSamplesMemoryEventsClear')
        and result.get('cleanupDependenciesHealthy')
        and result.get('cleanup') == {'attempted': 500, 'closed': 500}
        and final.get('health', {}).get('ready') and is_idle(final.get('health', {}))
        and memory_events_clear(final.get('probe', {}))
        and stopped.get('status') == 'exited' and stopped.get('oomKilled') is False
        and stopped.get('image') == result.get('imageId'))


def ssh_command(args):
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
            '-o', 'ConnectionAttempts=1', '-o', 'ForwardAgent=no',
            '-o', 'ProxyJump=none', '-o', 'ProxyCommand=none',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'UserKnownHostsFile=' + str(args.known_hosts),
            '-o', 'StrictHostKeyChecking=yes', '-o', 'HostName=' + args.host_address,
            args.ssh_host, '/usr/bin/python3 -']


# This is a fixed remote program, not arbitrary shell supplied by CLI arguments.
# It never reads worker.env: Docker alone consumes that mode0600 env file.
REMOTE = r'''
import os,pathlib,stat,json,subprocess,time,urllib.request,asyncio,hashlib
P=pathlib.Path;D='/usr/local/bin/docker';a=PAYLOAD;root=P(a['remote_root'])
def docker(args,timeout=15):
 p=subprocess.run([D,*args],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError('docker_'+args[0]+'_exit_'+str(p.returncode))
 return p.stdout
def private_setup():
 if root.is_symlink() or str(root.resolve())!=str(root) or not root.is_dir():raise RuntimeError('remote_root_not_canonical_directory')
 if root.stat().st_uid!=os.getuid() or stat.S_IMODE(root.stat().st_mode)!=0o700:raise RuntimeError('remote_root_owner_or_mode')
 env=root/'worker.env'
 if env.is_symlink() or not env.is_file() or stat.S_IMODE(env.stat().st_mode)!=0o600 or env.stat().st_uid!=os.getuid():raise RuntimeError('worker_env_owner_or_mode')
def inspect(name):
 x=json.loads(docker(['inspect',name]))[0]
 if x.get('Config',{}).get('Labels',{}).get('owner')!=str(root):raise RuntimeError('container_owner_mismatch')
 return x
def identity(x):
 h=x['HostConfig'];s=x['State']
 return {'image':x['Image'],'status':s['Status'],'oomKilled':s['OOMKilled'],'NanoCpus':h['NanoCpus'],'Memory':h['Memory'],'PidsLimit':h['PidsLimit']}
def frozen_image():
 # The daemon can report a tag in RepoTags while refusing to resolve that tag.
 # Validate the content-addressed object that Docker run actually uses. Never
 # retag, pull, or accept a different ID to repair a mutable-name index.
 image=json.loads(docker(['image','inspect',a['image_id']]))[0]
 if image['Id']!=a['image_id']:raise RuntimeError('frozen_image_ID_mismatch')
 if image['Config'].get('Entrypoint')!=['python3','/opt/sduoj-ide/scripts/entrypoint.py']:raise RuntimeError('unexpected_image_entrypoint')
 return image
def health():
 try:
  with urllib.request.urlopen('http://127.0.0.1:19086/health',timeout=3) as response:return json.load(response)
 except __import__('urllib.error',fromlist=['HTTPError']).HTTPError as error:
  if error.code!=503:raise
  return json.load(error)
def idle(h):
 seen=set();debug=None
 for c in h.get('components',[]):
  m=c.get('metrics',{})
  if c.get('role')=='lsp':
   if any(v.get('documents')!=0 for v in m.get('languages',{}).values()):return False
   seen.add(c.get('language'))
  if c.get('role')=='debug':debug=m
 return seen=={'c','cpp','java','python'} and debug is not None and all(debug.get(k)==0 for k in ('resident','active','queued','grantedBytes'))
private_setup();op=a['operation'];name=a.get('name');result={}
if name:
 import re
 if not re.fullmatch(r'sduoj-ide-[a-z0-9-]+-20261025(?:-[a-z0-9-]+)?',name):raise RuntimeError('container_name_not_scoped')
if op=='setup':
 image=frozen_image()
 network=json.loads(docker(['network','inspect',a['network']]))[0]
 if network.get('Labels',{}).get('owner')!=str(root):raise RuntimeError('network_owner_mismatch')
 x=inspect(name)
 if x['Image']!=a['image_id']:raise RuntimeError('existing_worker_image_mismatch')
 h=health() if x['State']['Running'] else None
 if x['State']['Running'] and (not h.get('ready') or not idle(h)):raise RuntimeError('existing_worker_not_idle')
 result={'imageId':image['Id'],'referenceTag':a['image_tag'],'referenceTagRecorded':a['image_tag'] in (image.get('RepoTags') or []),'identityMethod':'immutable_image_ID','existing':identity(x),'health':h,'workerEnvMode':'0600','workerEnvRead':False}
elif op=='stop':
 x=inspect(name);h=None
 if x['State']['Running']:
  try:h=health()
  except Exception:
   if a.get('require_idle',True):raise
 if x['Image']!=a['image_id']:raise RuntimeError('stop_image_mismatch')
 if x['State']['Running']:
  if a.get('require_idle',True) and (not h or not h.get('ready') or not idle(h)):raise RuntimeError('stop_refused_not_idle')
  docker(['stop','--time','25',name],timeout=35)
 result={'identity':identity(inspect(name)),'preStopHealth':h,'removed':False}
elif op=='start':
 # Refuse any existing name, including an exited container. Do not recreate it.
 p=subprocess.run([D,'inspect',name],capture_output=True,text=True,timeout=10)
 if p.returncode==0:raise RuntimeError('container_name_already_exists')
 if p.returncode!=1 or 'no such' not in p.stderr.lower():raise RuntimeError('container_name_probe_failed')
 frozen_image()
 network=json.loads(docker(['network','inspect',a['network']]))[0]
 if network.get('Labels',{}).get('owner')!=str(root):raise RuntimeError('network_owner_changed')
 # Unset the optional APC setting before normal entrypoint/bootstrap. Nacos
 # alone then supplies2 or leaves it absent for P4; inherited env cannot leak2.
 options=['run','-d','--pull','never','--name',name,'--label','owner='+str(root),'--label','ide.matrix='+a['run_id'],'--network',a['network'],'--cpus',str(a['cpus']),'--memory',str(a['memory_gib'])+'g','--pids-limit','1024','--init','--read-only','--user','root','--privileged','--security-opt','label=disable','--tmpfs','/tmp:size=256m,uid=10001,gid=10001,mode=1777','--tmpfs','/run:size=64m,mode=0755','--tmpfs','/home/ide:size=32m,uid=10001,gid=10001,mode=0700','--env-file',str(root/'worker.env'),'-e','ACTIVE=dev','-e','NACOS_NAMESPACE=dev','-e','NACOS_GROUP=DEFAULT_GROUP','-e','SDUOJ_IDE_NACOS_ENABLED=1','-e','SDUOJ_IDE_DEV_DEBUG_LAB=1','-e','NACOS_DATA_ID='+a['data_id'],'-e','NACOS_SERVICE='+a['service'],'-e','SDUOJ_IDE_WORKER_ID='+a['worker_id'],'-p','127.0.0.1:19086:9086','--entrypoint','/usr/bin/env',a['image_id'],'-u','SDUOJ_IDE_JAVA_PROCESSORS','python3','/opt/sduoj-ide/scripts/entrypoint.py','--role','all']
 docker(options,timeout=30);x=inspect(name)
 result={'identity':identity(x),'id':x['Id']}
elif op=='sample':
 x=inspect(name);result={'identity':identity(x)}
 if not x['State']['Running']:result['health']={};result['probe']={}
 else:
  result['health']=health()
  probe=r"""
import asyncio,json,os,pathlib,time
from sduoj_ide_worker.redis_client import create_redis
P=pathlib.Path
def read(path):
 try:return P(path).read_text()
 except OSError:return ''
async def run():
 url=os.environ.get('AUTOLAB_REDIS_URL') or os.environ.get('SDUOJ_IDE_REDIS_URL')
 if not url or '${' in url:raise RuntimeError('missing_local_redis_URL')
 redis=create_redis(url,decode_responses=True,socket_connect_timeout=2,socket_timeout=2,max_connections=2)
 try:
  await redis.ping();regs={}
  for role,lang in [('lsp',l) for l in ('c','cpp','java','python')]+[('debug','all')]:
   members=await redis.zrangebyscore(PREFIX+'registry:'+role+':'+lang,int(time.time()*1000),'+inf');alive=[]
   for m in members:
    if await redis.exists(PREFIX+'node:'+m):alive.append(m)
   regs[role+':'+lang]=sorted(alive)
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','MemTotal:','SwapFree:','SwapTotal:'))}
  java=[]
  for path in P('/proc').iterdir():
   if not path.name.isdigit():continue
   try:argv=[part.decode(errors='replace') for part in (path/'cmdline').read_bytes().split(b'\0') if part]
   except OSError:continue
   if '-Declipse.product=org.eclipse.jdt.ls.core.product' in argv:
    java.append({'pid':int(path.name),'flags':[arg for arg in argv if arg.startswith(('-Xms','-Xmx','-XX:ActiveProcessorCount='))]})
  print(json.dumps({'registry':regs,'memory':mem,'jdtls':java,'pressure':{k:read('/proc/pressure/'+k) for k in ('cpu','memory','io')},'cgroup':{k:read('/sys/fs/cgroup/'+k) for k in ('memory.current','memory.peak','memory.events','memory.pressure','cpu.stat','cpu.pressure')}}))
 finally:await redis.close()
asyncio.run(run())
"""
  raw=docker(['exec',name,'python3','-c','PREFIX='+repr(a['prefix'])+'\n'+probe],timeout=15)
  result['probe']=json.loads(raw)
else:raise RuntimeError('unknown_operation')
print(json.dumps(result))
'''


class Remote:
    def __init__(self, args):
        self.args = args

    def call(self, operation, **values):
        data = dict(operation=operation, remote_root=self.args.remote_root,
                    image_id=self.args.image_id, image_tag=self.args.image_tag,
                    network=self.args.network, **values)
        payload = 'PAYLOAD=' + repr(data) + '\n' + REMOTE
        result = subprocess.run(ssh_command(self.args), input=payload,
                                capture_output=True, text=True, timeout=50)
        if result.returncode:
            # Do not print remote command or environment file diagnostics.
            codes = re.findall(r'^RuntimeError: ([A-Za-z0-9_]+)$', result.stderr, flags=re.MULTILINE)
            suffix = ':' + codes[-1] if codes else ''
            raise RuntimeError('Remote operation failed: ' + operation + suffix)
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError) as error:
            raise RuntimeError('Invalid remote JSON result: ' + operation) from error


class Nacos:
    def __init__(self, base):
        self.base, self.token = base, None

    def request(self, path, values=None):
        params = dict(values or {})
        if self.token:
            params['accessToken'] = self.token
        request = urllib.request.Request(self.base + '/nacos/v1/' + path,
            data=urllib.parse.urlencode(params).encode() if values is not None else None)
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.read().decode()

    def ready(self):
        with urllib.request.urlopen(self.base + '/nacos/v1/console/health/readiness', timeout=3) as response:
            return response.status == 200

    def publish(self, data_id, config):
        if not DATA_ID.fullmatch(data_id):
            raise ValueError('Nacos dataId is outside the matrix dev namespace')
        # Credentials are optional caller environment, never worker.env or artifacts.
        if os.getenv('NACOS_USERNAME'):
            self.token = json.loads(self.request('auth/login', {
                'username': os.environ['NACOS_USERNAME'],
                'password': os.environ['NACOS_PASSWORD']}))['accessToken']
        query = urllib.parse.urlencode(dict(dataId=data_id, group='DEFAULT_GROUP', tenant='dev',
            **({'accessToken': self.token} if self.token else {})))
        try:
            with urllib.request.urlopen(self.base + '/nacos/v1/cs/configs?' + query, timeout=4):
                raise RuntimeError('Matrix Nacos dataId already exists; refusing overwrite')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        content = json.dumps(config, sort_keys=True, separators=(',', ':'))
        if self.request('cs/configs', dict(dataId=data_id, group='DEFAULT_GROUP', tenant='dev',
                                         type='json', content=content)).strip() != 'true':
            raise RuntimeError('Nacos did not confirm matrix configuration')
        query = urllib.parse.urlencode(dict(dataId=data_id, group='DEFAULT_GROUP', tenant='dev',
            **({'accessToken': self.token} if self.token else {})))
        # Nacos can acknowledge the durable write before its config-read cache
        # observes the new dataId (real dev probe:404 at71/125ms,200 at239ms).
        # Retry only that bounded visibility gap, never auth errors or mismatch.
        deadline, delay = time.monotonic() + 4, .05
        while True:
            try:
                with urllib.request.urlopen(self.base + '/nacos/v1/cs/configs?' + query, timeout=4) as response:
                    observed = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code != 404 or time.monotonic() >= deadline:
                    raise
                time.sleep(min(delay, max(0, deadline - time.monotonic())))
                delay = min(.8, delay * 2)
        if observed != config:
            raise RuntimeError('Nacos configuration readback differs')
        return hashlib.sha256(content.encode()).hexdigest()


def mini_sample():
    result = subprocess.run(['docker', 'inspect', MINI_GATEWAY], capture_output=True, text=True, timeout=6)
    result.check_returncode()
    container = json.loads(result.stdout)[0]
    if container.get('Config', {}).get('Labels', {}).get('com.docker.compose.project') != 'sduoj-ide-release-gates-20261025':
        raise RuntimeError('Mini Gateway does not belong to this dev lab')
    process = subprocess.run(['docker', 'exec', MINI_GATEWAY, 'sh', '-c',
        'cat /proc/meminfo; cat /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io'],
        capture_output=True, text=True, timeout=6)
    process.check_returncode()
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in process.stdout.splitlines()
              if line.startswith(('MemAvailable:', 'MemTotal:', 'SwapFree:', 'SwapTotal:'))}
    return {'gatewayHealthy': container['State']['Running'] and
            container['State'].get('Health', {}).get('Status') == 'healthy',
            'memory': memory, 'pressure': '\n'.join(line for line in process.stdout.splitlines()
                                                 if line.startswith(('some ', 'full ')))}


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def warmup(args, directory):
    # Use real actors, real Gateway sessions and actual completion responses.
    from ide_redis_dev_acceptance import Client, CASES
    import requests
    users = json.loads(args.users.read_text())['users'][:4]
    operations, checks = [], {}
    for language, credential in zip(LANGUAGES, users):
        # Client's normal acceptance UA is shared; give each matrix actor its
        # own UA before real login, without weakening server admission limits.
        client = Client.__new__(Client)
        client.base, client.report, client.last = args.gateway_base, operations, 0.0
        client.http = requests.Session()
        client.http.trust_env = False
        client.http.headers['User-Agent'] = 'SDUOJ-IDE-Matrix-Warmup/' + directory.parent.name + '/' + directory.name + '/' + language
        response = client.http.post(args.gateway_base + '/api/user/login',
            json={key: credential[key] for key in ('username', 'password')}, timeout=15)
        if response.status_code != 200 or response.json().get('code') != 0:
            raise RuntimeError('Warmup real login failed')
        marked = CASES[language]['complete']
        before = marked[:marked.index('|')]
        session = client.create_lsp(language, marked.replace('|', ''))
        sid = session['sessionId']
        try:
            end, found = time.monotonic() + 45, False
            while time.monotonic() < end:
                data = client.call('/session/' + sid + '/completion', {
                    'revision': session['revision'], 'line': before.count('\n') + 1,
                    'column': len(before.rsplit('\n', 1)[-1]) + 1, 'triggerKind': 'invoked'})
                expected = CASES[language]['label']
                found = bool(isinstance(data, dict) and data.get('status') == 'ready' and
                    any(isinstance(item, dict) and any(isinstance(item.get(field), str)
                        and item[field].startswith(expected) for field in ('label', 'filterText', 'insertText'))
                        for item in data.get('items', [])))
                if found:
                    break
                time.sleep(1)
            checks[language] = found
            if not found:
                raise RuntimeError('Warmup did not produce a valid ' + language + ' completion')
        finally:
            client.call('/session/' + sid + '/close', {})
    write_new(directory / 'warmup.json', {'checks': checks, 'operations': operations})


def warmup_bounded(args, directory):
    source = ('import sys; from pathlib import Path; from types import SimpleNamespace; '
              'sys.path.insert(0, ' + repr(str(SCRIPT_DIR)) + '); '
              'from ide_worker_dev_matrix import warmup; '
              'warmup(SimpleNamespace(users=Path(' + repr(str(args.users)) + '), gateway_base='
              + repr(args.gateway_base) + '), Path(' + repr(str(directory)) + '))')
    with (directory / 'warmup.log').open('x') as log:
        process = subprocess.Popen([str(args.python), '-c', source], stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True)
        (directory / 'warmup.pid').write_text(str(process.pid) + '\n')
        try:
            process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            stop_load(process)
            raise RuntimeError('Warmup120s deadline')
        finally:
            (directory / 'warmup.exitcode').write_text(str(process.returncode) + '\n')
    if process.returncode:
        raise RuntimeError('Warmup child failed')


def assert_java_flags(sample, profile):
    rows = sample['remote']['probe'].get('jdtls', [])
    if len(rows) != 1:
        raise RuntimeError('Exactly one warmed JDTLS process must be observed')
    flags = rows[0]['flags']
    processors = [flag for flag in flags if flag.startswith('-XX:ActiveProcessorCount=')]
    expected = [] if profile.java_processors is None else ['-XX:ActiveProcessorCount=' + str(profile.java_processors)]
    if processors != expected or next((f for f in reversed(flags) if f.startswith('-Xmx')), None) != '-Xmx384m':
        raise RuntimeError('Actual JDTLS flags differ from selected profile')


def stop_load(process):
    if process.poll() is not None:
        return process.returncode
    os.killpg(process.pid, signal.SIGINT)
    try:
        return process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(timeout=5)


def summarize_raw(raw, metadata):
    stages = []
    for stage in raw.get('stages', []):
        rows = [row for row in stage.get('results', []) if row.get('phase') == 'steady']
        from ide_gateway_capacity import summary
        stages.append({'activeUsers': stage['activeUsers'], 'complete': bool(stage.get('complete')),
                       'metrics': summary(rows), 'source': 'raw steady results; no reclassification'})
    return {'profile': metadata['profile'], 'stages': stages, 'cleanup': raw.get('cleanup'),
            'stopReason': metadata.get('stopReason'), 'loadExitcode': metadata.get('loadExitcode'),
            'executed': metadata.get('executed'), 'diagnosticQualified': metadata.get('qualified'),
            'scope': 'dev single Worker; capacity excludes browser and Debug; not production admission'}


def run_profile(args, profile, run_id, remote, nacos):
    directory = args.output_dir / profile.name
    directory.mkdir(mode=0o700)
    config = profile_config(args.template, profile)
    data_id = 'ide-worker-matrix-dev-20261025-' + run_id + '-' + profile.name + '.yml'
    worker_id = 'matrix-' + run_id + '-' + profile.name
    name = 'sduoj-ide-matrix-20261025-' + run_id + '-' + profile.name
    metadata = {'started': stamp(), 'monitorPid': os.getpid(), 'profile': asdict(profile),
                'guardBytes': profile.guard_bytes, 'container': name, 'workerId': worker_id,
                'nacosDataId': data_id, 'namespace': 'dev', 'imageId': args.image_id,
                'sourceHashes': {path.name: sha256(path) for path in (
                    Path(__file__), args.load_script, SCRIPT_DIR / 'ide_redis_dev_acceptance.py',
                    SCRIPT_DIR / 'ide_capacity_lifecycle.py')},
                'configSha256': None, 'stopReason': None}
    write_new(directory / 'profile.json', metadata)
    write_new(directory / 'nacos.json', config)
    process, started_container, start_attempted = None, False, False
    failure, raw, memory_safety = None, None, []
    try:
        assert_frozen_sources(args)
        metadata['configSha256'] = nacos.publish(data_id, config)
        start_attempted = True
        result = remote.call('start', name=name, run_id=run_id, cpus=profile.cpus,
            memory_gib=profile.memory_gib, data_id=data_id, worker_id=worker_id,
            service='ide-worker-matrix-dev-20261025-' + run_id + '-' + profile.name)
        started_container = True
        assert_identity(result['identity'], args.image_id, profile)
        deadline, delay = time.monotonic() + 120, 2
        while True:
            try:
                sample = {'time': stamp(), 'remote': remote.call('sample', name=name,
                    prefix=args.expected_redis_prefix), 'mini': mini_sample(), 'nacosReady': nacos.ready()}
            except Exception:
                reason = 'startup_dependency_not_ready'
            else:
                reason = guard_reason(sample, profile, worker_id, args.image_id)
                if reason is None:
                    break
                if reason not in ('worker_not_ready', 'registry_not_single_expected_worker'):
                    raise RuntimeError('Startup guard: ' + reason)
            if time.monotonic() >= deadline:
                raise RuntimeError('Startup120s deadline: ' + reason)
            time.sleep(min(delay, max(0, deadline - time.monotonic())))
            delay = min(10, delay * 2)
        write_new(directory / 'startup.json', sample)
        memory_safety.append(memory_events_clear(sample['remote']['probe']))
        if not is_idle(sample['remote']['health']):
            raise RuntimeError('New candidate is not empty before warmup')
        warmup_bounded(args, directory)
        warmed = {'remote': remote.call('sample', name=name, prefix=args.expected_redis_prefix)}
        assert_java_flags(warmed, profile)
        if not is_idle(warmed['remote']['health']):
            raise RuntimeError('Warmup documents have not closed')
        write_new(directory / 'warmed-state.json', warmed)
        memory_safety.append(memory_events_clear(warmed['remote']['probe']))
        assert_frozen_sources(args)
        command = [str(args.python), str(args.load_script), '--base', args.gateway_base,
                   '--users', str(args.users), '--online', '500', '--active', *map(str, args.active_list),
                   '--stage-seconds', '75', '--ramp-seconds', '20', '--output', str(directory / 'raw.json')]
        with (directory / 'load.log').open('x') as log, (directory / 'samples.jsonl').open('x') as samples:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            (directory / 'load.pid').write_text(str(process.pid) + '\n')
            metadata['loadPid'] = process.pid
            began = time.monotonic()
            while process.poll() is None:
                try:
                    assert_frozen_sources(args)
                    sample = {'time': stamp(), 'elapsed': time.monotonic() - began,
                        'remote': remote.call('sample', name=name, prefix=args.expected_redis_prefix),
                        'mini': mini_sample(), 'nacosReady': nacos.ready()}
                    samples.write(json.dumps(sample) + '\n')
                    samples.flush()
                    memory_safety.append(memory_events_clear(sample['remote']['probe']))
                    failure = guard_reason(sample, profile, worker_id, args.image_id)
                except Exception as error:
                    failure = 'sample_failure:' + type(error).__name__
                if time.monotonic() - began > args.load_timeout:
                    failure = 'load_deadline'
                if failure:
                    metadata['stopReason'] = failure
                    stop_load(process)
                    break
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            metadata['loadExitcode'] = process.returncode
            (directory / 'load.exitcode').write_text(str(process.returncode) + '\n')
        if not (directory / 'raw.json').is_file():
            raise RuntimeError('Load did not preserve a raw report')
        raw = json.loads((directory / 'raw.json').read_text())
        metadata['rawSha256'] = sha256(directory / 'raw.json')
        metadata['cleanup'] = raw.get('cleanup')
        if raw.get('cleanup') != {'attempted': 500, 'closed': 500}:
            failure = failure or 'session_cleanup_not_confirmed'
        if any(not stage.get('complete') for stage in raw.get('stages', [])):
            failure = failure or 'incomplete_stage'
        if [s.get('activeUsers') for s in raw.get('stages', [])] != args.active_list:
            failure = failure or 'missing_or_unexpected_stages'
        # Exit1 represents completed but low diagnostic validity, not infra failure.
        if process.returncode not in (0, 1):
            failure = failure or 'load_process_failure'
    except KeyboardInterrupt:
        failure = 'operator_interrupt'
        if process:
            stop_load(process)
    except Exception as error:
        failure = failure or 'profile_failure:' + type(error).__name__
        metadata['failureCategory'] = type(error).__name__
        if isinstance(error, RuntimeError):
            metadata['failureCode'] = str(error)[:160]
        if process:
            stop_load(process)
    finally:
        metadata['stopReason'] = failure
        if started_container:
            deadline = time.monotonic() + 45
            while True:
                try:
                    final = remote.call('sample', name=name, prefix=args.expected_redis_prefix)
                    assert_identity(final['identity'], args.image_id, profile)
                    if is_idle(final.get('health', {})):
                        metadata['cleanupHealth'] = final
                        memory_safety.append(memory_events_clear(final.get('probe', {})))
                        break
                except Exception as error:
                    metadata['cleanupProbeCategory'] = type(error).__name__
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(min(5, max(0, deadline - time.monotonic())))
            if not metadata.get('cleanupHealth'):
                failure = failure or 'worker_documents_cleanup_not_confirmed'
                metadata['stopReason'] = failure
            try:
                metadata['cleanupDependenciesHealthy'] = bool(mini_sample()['gatewayHealthy'] and nacos.ready())
            except Exception:
                metadata['cleanupDependenciesHealthy'] = False
            if not metadata['cleanupDependenciesHealthy']:
                failure = failure or 'cleanup_dependency_unhealthy'
                metadata['stopReason'] = failure
        if start_attempted:
            try:
                # An unhealthy candidate is also ours; stop it to contain the
                # failed experiment. Never delete it or touch another container.
                metadata['stopped'] = remote.call('stop', name=name, require_idle=False)
            except Exception as error:
                failure = failure or 'owned_candidate_stop_failed'
                metadata['stopReason'] = failure
                metadata['stopCategory'] = type(error).__name__
        metadata.update(finished=stamp(), completed=not bool(failure),
            executed=process is not None and isinstance(raw, dict) and bool(raw.get('stages')),
            qualified=not bool(failure) and isinstance(raw, dict) and raw.get('passed') is True,
            allSamplesMemoryEventsClear=bool(memory_safety) and all(memory_safety))
        write_new(directory / 'result.json', metadata)
        if (directory / 'raw.json').is_file():
            try:
                write_new(directory / 'summary.json', summarize_raw(
                    json.loads((directory / 'raw.json').read_text()), metadata))
            except (ValueError, KeyError, TypeError):
                write_new(directory / 'summary-error.json', {'category': 'invalid_raw_report'})
    return metadata


def validate_args(args):
    args.gateway_base, args.nacos_base = loopback_url(args.gateway_base), loopback_url(args.nacos_base)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.ssh_host):
        raise ValueError('Use a configured SSH Host alias')
    ipaddress.ip_address(args.host_address)
    args.known_hosts = Path(args.known_hosts).expanduser().resolve(strict=True)
    if not args.known_hosts.is_file():
        raise ValueError('Explicit known_hosts file required')
    if not PRIVATE_ROOT.fullmatch(args.remote_root):
        raise ValueError('Remote root must be an existing isolated /private/tmp/sduoj-ide-probe-* directory')
    if (not IMAGE_ID.fullmatch(args.image_id)
            or not re.fullmatch(r'sduoj-ide-unified:[A-Za-z0-9_.-]+', args.image_tag)):
        raise ValueError('Explicit frozen sha256 image ID and a local image tag are required')
    if not OWN_CONTAINER.fullmatch(args.existing_worker) or args.existing_worker != EXISTING_WORKER:
        raise ValueError('Only the named original R6 dev container may be stopped')
    if args.network != 'sduoj-ide-mbp-20261025':
        raise ValueError('Only the isolated MacBook IDE dev network is accepted')
    if not args.active_list or any(type(n) is not int or not 10 <= n <= 100 or n % 10 for n in args.active_list):
        raise ValueError('Matrix scope is10..100 active, in multiples of10')
    if len(set(args.active_list)) != len(args.active_list):
        raise ValueError('Active stages must be unique')
    if not args.profiles or len(set(args.profiles)) != len(args.profiles) or any(p not in PROFILES for p in args.profiles):
        raise ValueError('Choose distinct named profiles p0..p7')
    if not 120 <= args.load_timeout <= 900:
        raise ValueError('Load timeout must be between120 and900seconds')
    if args.load_timeout < len(args.active_list) * 95 + 60:
        raise ValueError('Load timeout must cover all bounded stages and preparation')
    args.users = private_file(args.users)
    private = json.loads(args.users.read_text())
    if len(private.get('users', [])) < 500:
        raise ValueError('500 independent private dev accounts are required')
    names = [user.get('username') for user in private['users'][:500]]
    if len(set(names)) != 500 or any(not name for name in names):
        raise ValueError('500 distinct account identities are required')
    args.config_template = Path(args.config_template).expanduser().resolve(strict=True)
    args.template = validate_template(json.loads(args.config_template.read_text()), args.expected_redis_prefix)
    # Keep the venv symlink path: resolving it to a system Python changes its
    # sys.prefix and can silently discard the workload's installed dependencies.
    args.python = Path(args.python).expanduser().absolute()
    args.python.resolve(strict=True)
    args.load_script = Path(args.load_script).expanduser().resolve(strict=True)
    if not args.python.is_file() or not args.load_script.is_file():
        raise ValueError('Python and load script must exist')
    args.frozen_source_hashes = {str(path): sha256(path) for path in (
        Path(__file__), args.load_script, SCRIPT_DIR / 'ide_redis_dev_acceptance.py',
        SCRIPT_DIR / 'ide_capacity_lifecycle.py')}
    args.output_dir = Path(args.output_dir).expanduser().resolve()
    if args.output_dir.exists():
        raise ValueError('Output directory already exists; artifacts must never be overwritten')
    return args


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ('ssh-host', 'host-address', 'known-hosts', 'remote-root', 'image-id', 'image-tag',
                 'output-dir', 'users', 'gateway-base', 'nacos-base', 'config-template', 'python'):
        result.add_argument('--' + name, required=True)
    result.add_argument('--profiles', nargs='+', choices=tuple(PROFILES), default=list(DEFAULT_PROFILES))
    result.add_argument('--active-list', nargs='+', type=int, default=[100])
    result.add_argument('--expected-redis-prefix', default='sduoj:ide:release-gates:20261025:')
    result.add_argument('--network', default='sduoj-ide-mbp-20261025')
    result.add_argument('--existing-worker', default=EXISTING_WORKER)
    result.add_argument('--load-script', default=str(SCRIPT_DIR / 'ide_gateway_capacity.py'))
    result.add_argument('--load-timeout', type=int, default=300)
    result.add_argument('--continue-memory-guard', action='store_true',
        help='Continue only after an owned, cleaned, OOM-free memory-guard result into a different profile')
    return result


def main(argv=None):
    args = validate_args(parser().parse_args(argv))
    args.output_dir.mkdir(mode=0o700)
    run_id = uuid.uuid4().hex[:10]
    metadata = {'started': stamp(), 'monitorPid': os.getpid(), 'runId': run_id,
                'scope': 'authorized dev-only resource matrix', 'namespace': 'dev',
                'imageId': args.image_id, 'profiles': args.profiles, 'activeList': args.active_list,
                'online': 500, 'configTemplateSha256': sha256(args.config_template),
                'loadScriptSha256': sha256(args.load_script), 'sourceSha256': sha256(__file__)}
    write_new(args.output_dir / 'matrix.json', metadata)
    (args.output_dir / 'monitor.pid').write_text(str(os.getpid()) + '\n')
    results, code = [], 2
    try:
        remote, nacos = Remote(args), Nacos(args.nacos_base)
        # Check dependencies before stopping the known-idle original container.
        if not mini_sample()['gatewayHealthy'] or not nacos.ready():
            raise RuntimeError('Dev dependencies are not healthy')
        preflight = remote.call('setup', name=args.existing_worker)
        write_new(args.output_dir / 'preflight.json', preflight)
        write_new(args.output_dir / 'original-stop.json', remote.call('stop', name=args.existing_worker,
                                                                    require_idle=True))
        for index, profile_name in enumerate(args.profiles):
            result = run_profile(args, PROFILES[profile_name], run_id, remote, nacos)
            results.append(result)
            print(json.dumps({'profile': profile_name, 'completed': result['completed'],
                              'stopReason': result.get('stopReason')}), flush=True)
            if not result['completed']:
                following = PROFILES[args.profiles[index + 1]] if index + 1 < len(args.profiles) else None
                allowed = may_continue_memory_guard(args.continue_memory_guard, result,
                    PROFILES[profile_name], following)
                write_new(args.output_dir / (profile_name + '-continuation.json'),
                    {'allowed': allowed, 'reason': result.get('stopReason'),
                     'nextProfile': following.name if following else None})
                if not allowed:
                    break
        all_executed = len(results) == len(args.profiles) and all(r.get('executed') for r in results)
        # Low SLO validity alone does not make execution fail. A final guard or
        # infrastructure failure still returns2, including when all were attempted.
        code = 0 if all_executed and results[-1].get('completed') else 2
    except KeyboardInterrupt:
        metadata['stopReason'] = 'operator_interrupt'
        code = 130
    except Exception as error:
        metadata['failureCategory'] = type(error).__name__
        if isinstance(error, RuntimeError):
            metadata['failureCode'] = str(error)[:160]
    finally:
        metadata.update(finished=stamp(), exitcode=code, results=results,
                        allProfilesExecuted=len(results) == len(args.profiles) and all(r.get('executed') for r in results),
                        allProfilesQualified=len(results) == len(args.profiles) and all(r.get('qualified') for r in results),
                        originalWorkerRestored=False, containersRemoved=False)
        write_new(args.output_dir / 'matrix-result.json', metadata)
        (args.output_dir / 'matrix.exitcode').write_text(str(code) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
