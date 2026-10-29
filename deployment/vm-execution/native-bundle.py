#!/usr/bin/env python3
"""Verify/stage a pinned private HVF tool bundle; no host package manager and no VM startup."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import shutil
import subprocess
import tarfile
from vmctl import require, sha

REQUIRED = {'bin/qemu-system-aarch64', 'bin/qemu-img', 'share/AAVMF/AAVMF_CODE.fd', 'share/AAVMF/AAVMF_VARS.fd'}

def valid_path(name):
    p = PurePosixPath(name)
    return bool(re.fullmatch(r'[A-Za-z0-9_./+-]{1,300}', name) and not p.is_absolute() and '..' not in p.parts and str(p) == name and name.startswith(('bin/', 'lib/', 'share/')))

def validate(lock):
    require(lock.get('schemaVersion') == 1 and lock.get('status') == 'INTERNAL_ARM64_HVF_BUNDLE_FROZEN' and lock.get('platform') == 'darwin-arm64', 'Actual internal ARM64 bundle freeze required')
    require(re.fullmatch(r'10\.0\.[0-9]+', lock.get('qemuVersion', '')), 'Pin exact tested QEMU version')
    require(lock.get('sourceUrl') == 'https://download.qemu.org/qemu-' + lock['qemuVersion'] + '.tar.xz' and lock.get('sourceSignatureVerified') is True and lock.get('sourceSignatureFingerprint') == 'CEACC9E15534EBABB82D3FA03353C9CEF108B584', 'Official QEMU source/signature identity required')
    require(all(re.fullmatch('[a-f0-9]{64}', lock.get(k, '')) for k in ('sourceSha256', 'archiveSha256')), 'Pin source and complete archive SHA before staging')
    files = lock.get('files', {})
    require(REQUIRED <= set(files) and all(valid_path(k) and re.fullmatch('[a-f0-9]{64}', v) for k, v in files.items()), 'Safe file inventory including binaries/firmware required')

def stage(lock, archive, destination):
    validate(lock)
    require(archive.is_file() and not archive.is_symlink() and sha(archive) == lock['archiveSha256'], 'Archive SHA mismatch')
    require(destination.is_absolute() and not destination.exists() and not destination.is_symlink() and destination.parent.is_dir(), 'New private bundle destination required')
    with tarfile.open(archive) as tar:
        rows = tar.getmembers()
        files = [r for r in rows if not r.isdir()]
        require(all(r.isfile() and valid_path(r.name) for r in files) and len({r.name for r in files}) == len(files) and {r.name for r in files} == set(lock['files']) and sum(r.size for r in files) <= 1024**3, 'Archive must contain exactly frozen regular payload files; symlink/link/device/traversal rejected')
        require(all(r.isdir() and not PurePosixPath(r.name).is_absolute() and '..' not in PurePosixPath(r.name).parts for r in rows if r.isdir()), 'Unsafe directory header rejected')
        destination.mkdir(mode=0o700)
        for row in files:
            target = destination / row.name; target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tar.extractfile(row) as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            target.chmod(0o700 if row.name.startswith('bin/') else 0o600)
            require(sha(target) == lock['files'][row.name], 'Payload SHA mismatch; partial bundle retained')

def verify(lock, directory, runtime_checks=False):
    validate(lock)
    require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode & 0o777 == 0o700, 'Private real bundle directory required')
    files = {str(p.relative_to(directory)): p for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    require(set(files) == set(lock['files']) and all(not p.is_symlink() and sha(p) == lock['files'][name] for name, p in files.items()), 'Bundle bytes/inventory mismatch')
    if runtime_checks:
        require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Native ARM64 Mac required for loader/signature inspection')
        executable = directory / 'bin/qemu-system-aarch64'
        subprocess.run(['codesign', '--verify', '--strict', str(executable)], check=True, capture_output=True, timeout=10)
        result = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(executable)], check=True, capture_output=True, timeout=10)
        combined = result.stdout + result.stderr; xml = combined[combined.index(b'<?xml'):]; xml = xml[:xml.index(b'</plist>') + 8]
        require(plistlib.loads(xml).get('com.apple.security.hypervisor') is True, 'HVF entitlement required')
        for name, file in files.items():
            if not (name.startswith('bin/') or name.endswith('.dylib')):
                continue
            result = subprocess.check_output(['otool', '-L', str(file)], text=True, timeout=10)
            for row in result.splitlines()[1:]:
                dep = row.strip().split(' (', 1)[0]
                if dep.startswith(('/usr/lib/', '/System/Library/')):
                    continue
                if dep.startswith('@rpath/'):
                    resolved = directory / 'lib' / dep[len('@rpath/'):]
                elif dep.startswith('@loader_path/'):
                    resolved = file.parent / dep[len('@loader_path/'):]
                elif dep.startswith('@executable_path/'):
                    resolved = directory / 'bin' / dep[len('@executable_path/'):]
                else:
                    raise ValueError('Nonportable absolute dependency rejected')
                require(resolved.resolve().is_relative_to(directory.resolve()) and resolved.is_file(), 'Dependency must resolve inside frozen bundle')
    return {'verified': True, 'runtimeLoaderChecks': runtime_checks, 'files': len(files), 'vmStarted': False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', default='plan', choices=('plan', 'stage', 'verify'))
    p.add_argument('--lock', type=Path, default=Path(__file__).with_name('native-bundle.example.json'))
    p.add_argument('--archive', type=Path); p.add_argument('--directory', type=Path); p.add_argument('--runtime-checks', action='store_true')
    a = p.parse_args(); lock = json.loads(a.lock.read_text())
    if a.command == 'plan':
        try: validate(lock); ready = True
        except ValueError: ready = False
        print(json.dumps({'writes': False, 'bundleFrozen': ready, 'vmStarted': False})); return
    require(a.directory is not None and a.directory.is_absolute(), 'Explicit absolute bundle directory required')
    if a.command == 'stage':
        require(a.archive is not None and a.archive.is_absolute(), 'Explicit archive required')
        stage(lock, a.archive, a.directory)
    print(json.dumps(verify(lock, a.directory, a.runtime_checks)))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, tarfile.TarError):
        raise SystemExit('Native bundle rejected; no host packages installed; preserve any partial owned directory')
