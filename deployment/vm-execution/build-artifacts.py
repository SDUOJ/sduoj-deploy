#!/usr/bin/env python3
"""Sole artifact build owner. Default plan; explicit local Docker Desktop ARM64 build only, never a VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent


def require(ok, text):
    if not ok: raise ValueError(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-build', action='store_true'); p.add_argument('--output', type=Path)
    p.add_argument('--owner'); p.add_argument('--memory-mib', type=int, default=768)
    a = p.parse_args(); lock = json.loads((HERE / 'manager-build.lock.json').read_text())
    require(re.fullmatch(r'docker.io/library/debian@sha256:[a-f0-9]{64}', lock['debianBaseDigest']), 'Fixed native Debian digest required')
    require(512 <= a.memory_mib <= 2048, 'Bounded builder memory512..2048MiB required')
    if not a.execute_build:
        print(json.dumps({'writes': False, 'network': False, 'builderCpus': 1, 'builderMemoryMiB': a.memory_mib, 'base': lock['debianBaseDigest'], 'guestStarted': False, 'next': '--execute-build --output NEW_ABSOLUTE_DIRECTORY --owner sduoj-vm-build-UNIQUE'})); return
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Only authorized local ARM64 Mac preparation; production remote contexts rejected')
    require(a.owner and re.fullmatch(r'sduoj-vm-build-[a-z0-9-]{1,48}', a.owner), 'Explicit unique owner required')
    require(a.output and a.output.is_absolute() and str(a.output) == str(a.output.resolve()) and not a.output.exists() and a.output.parent.is_dir() and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(a.output)), 'New canonical private output required')
    require(not os.getenv('DOCKER_HOST') and not os.getenv('DOCKER_CONTEXT'), 'Docker endpoint override rejected')
    context = subprocess.check_output(['docker', 'context', 'inspect'], text=True, timeout=10)
    endpoint = json.loads(context)[0]['Endpoints']['docker']['Host']
    require(endpoint.startswith('unix://'), 'Only local Docker socket permitted')
    info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True, timeout=15))
    require(info.get('Architecture') == 'aarch64' and 'Docker Desktop' in info.get('OperatingSystem', ''), 'Local native Docker Desktop required')
    os.umask(0o077); a.output.mkdir(mode=0o700); src = a.output / 'source'; src.mkdir(mode=0o700)
    names = ['build-inside.sh', 'freeze-build.py', 'manager.py', 'vmctl.py', 'source.lock.json', 'manager-build.lock.json']
    hashes = {}
    for name in names:
        shutil.copyfile(HERE / name, src / name); hashes[name] = hashlib.sha256((src / name).read_bytes()).hexdigest()
    (src / 'debian-snapshot').write_text(lock['debianSnapshot'] + '\n')
    rows = [name + '=' + item['Version'] for name, item in lock['packages'].items()]
    (src / 'manager-packages').write_text('\n'.join(rows) + '\n')
    (src / 'docker-packages').write_text('\n'.join(k + '=' + v for k, v in lock['dockerPackages'].items()) + '\n')
    receipt = {'monitorPid': os.getpid(), 'owner': a.owner, 'started': time.time(), 'sourceSha256': hashes, 'base': lock['debianBaseDigest'], 'cpus': 1, 'memoryMiB': a.memory_mib, 'vmStarted': False, 'containerRunsOnlyPackageBuild': True, 'productionConnected': False, 'stages': []}
    def run(label, command, timeout):
        with (a.output / (label + '.log')).open('x') as f:
            child = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            record = {'stage': label, 'pid': child.pid, 'command': command, 'started': time.time()}; receipt['stages'].append(record)
            (a.output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2))
            try: rc = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=20); rc = 124
            record.update(exitcode=rc, finished=time.time())
            (a.output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2))
            require(rc == 0, label + ' failed; preserve owned builder/output for diagnosis')
    try:
        run('pull-fixed-base', ['docker', 'pull', '--platform', 'linux/arm64', lock['debianBaseDigest']], 300)
        run('build-packages', ['docker', 'run', '--name', a.owner, '--platform', 'linux/arm64', '--label', 'owner=' + a.owner,
                              '--cpus', '1', '--memory', str(a.memory_mib) + 'm', '--memory-swap', str(a.memory_mib) + 'm', '--pids-limit', '256',
                              '--mount', 'type=bind,src=' + str(src) + ',dst=/src,readonly', '--mount', 'type=bind,src=' + str(a.output) + ',dst=/output',
                              '-e', 'VM_BUILD_SCOPE=SDUOJ_ISOLATED_VM_ARTIFACTS_ONLY', '--entrypoint', '/bin/bash', lock['debianBaseDigest'], '/src/build-inside.sh'], 3600)
        inspect = json.loads(subprocess.check_output(['docker', 'inspect', a.owner], text=True, timeout=10))[0]
        require(inspect['Config']['Labels'].get('owner') == a.owner and inspect['State']['ExitCode'] == 0 and not inspect['State']['Running'], 'Owned stopped builder identity required')
        tag = 'sduoj-vm-manager:' + a.owner
        run('commit-manager', ['docker', 'commit', '--change', 'LABEL owner=' + a.owner, '--change', 'USER 10001:10001', '--change', 'WORKDIR /vm',
                               '--change', 'ENTRYPOINT ["python3","/opt/sduoj-vm/manager.py"]', '--change', 'CMD ["plan"]', a.owner, tag], 120)
        image_config = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True, timeout=10))[0]
        require(image_config['Config']['User'] == '10001:10001', 'Final image must default to nonroot manager')
        require(not inspect['HostConfig']['Privileged'] and not inspect['HostConfig'].get('Devices') and inspect['HostConfig'].get('NanoCpus') == 1000000000 and inspect['HostConfig']['Memory'] == a.memory_mib * 1024**2, 'Builder resource/device contract mismatch')
        image = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True, timeout=10).strip()
        run('save-manager', ['docker', 'save', '--output', str(a.output / 'manager-image.tar'), image], 300)
        receipt.update(passed=True, managerLocalImageId=image, managerTag=tag, registryDigest=None, registryPushed=False, guestImagePrepared=False,
                       sourceUnchanged=all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == value for name, value in hashes.items()))
        require(receipt['sourceUnchanged'], 'Source changed during build; do not qualify result')
    except Exception:
        receipt['passed'] = False; raise
    finally:
        receipt['finished'] = time.time(); (a.output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'passed': True, 'managerImageId': image, 'guestStarted': False, 'offlineClosureDownloadedNotGuestInstalled': True, 'registryPushed': False}))

if __name__ == '__main__':
    try: main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        raise SystemExit('Artifact preparation failed/guarded; inspect private build-receipt and stage logs; no VM was started')
