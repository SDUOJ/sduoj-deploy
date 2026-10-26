#!/usr/bin/env python3
"""Frozen Mini-only native QEMU build; one monitor, no package install, no VM, no MBP changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_inputs(lock, sources):
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Native ARM64 Mac required')
    require(lock.get('status') == 'MINI_FIXED_EXISTING_BUILD_DEPS_NOT_NATIVE_OUTPUT', 'Explicit Mini dependency freeze required')
    for name, item in lock['sources'].items():
        path = sources / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'Pinned source mismatch: ' + name)
    for name, item in lock['tools'].items():
        require(Path(item['path']).is_file() and sha(item['path']) == item['sha256'], 'Existing fixed tool drift: ' + name)
    for name, expected in lock['buildDependencyFiles'].items():
        require(Path(name).is_file() and sha(name) == expected, 'Existing fixed header/library drift')
    require(subprocess.check_output([lock['tools']['xcrun']['path'], '--show-sdk-version'], text=True, timeout=10).strip() == lock['sdkVersion'], 'SDK version drift')
    require(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.model'], text=True, timeout=10).strip() == lock['buildHostModel'], 'This dependency snapshot is owned by the Mini, never run this builder on MBP')


def available_memory():
    value = subprocess.check_output(['/usr/bin/vm_stat'], text=True, timeout=10)
    page = int(re.search(r'page size of (\d+) bytes', value)[1])
    counts = dict((name, int(amount)) for name, amount in re.findall(r'^([^:\n]+):\s+(\d+)\.', value, re.M))
    return page * sum(counts.get(k, 0) for k in ('Pages free', 'Pages inactive', 'Pages speculative'))


def verify_linux_build(directory):
    receipt_path = directory / 'build-receipt.json'
    linux = json.loads(receipt_path.read_text())
    require(re.fullmatch(r'sduoj-vm-build-[a-z0-9-]{1,48}', linux.get('owner', '')), 'Owned Linux builder identity required')
    require(linux.get('passed') is True and linux.get('vmStarted') is False and linux.get('stages') and all(row.get('exitcode') == 0 for row in linux['stages']), 'Linux sole builder must finish successfully first')
    for name, expected in linux.get('sourceSha256', {}).items():
        require(re.fullmatch(r'[A-Za-z0-9._-]+', name) and re.fullmatch(r'[a-f0-9]{64}', expected), 'Safe Linux source inventory required')
        file = directory / 'source' / name
        require(file.is_file() and not file.is_symlink() and sha(file) == expected, 'Linux build source file drift')
    require(linux.get('sourceSha256'), 'Linux source inventory missing')
    if linux.get('sourceUnchanged') is True:
        return linux
    require(linux.get('sourcePinsUnchanged') is True, 'Linux builder source drift prevents binding firmware')
    require(all(re.fullmatch(r'[a-f0-9]{40}', linux.get(key, '')) for key in ('frozenOriginalSourceCommit', 'permissionFixCommit')), 'Composite Linux original/permission-fix commit binding required')
    expected = linux.get('parentFailedBuildReceiptSha256', '')
    require(re.fullmatch(r'[a-f0-9]{64}', expected), 'Composite Linux parent failure binding required')
    siblings = [p / 'build-receipt.json' for p in directory.parent.iterdir() if p.is_dir() and p != directory and (p / 'build-receipt.json').is_file()]
    parents = [p for p in siblings if sha(p) == expected]
    require(len(parents) == 1 and json.loads(parents[0].read_text()).get('passed') is False, 'Exact retained failed parent receipt required')
    required = ('manager-build.lock.json', 'build-inside.sh', 'source.lock.json', 'freeze-build.py', 'manager.py', 'vmctl.py')
    require(set(required) <= set(linux['sourceSha256']), 'Complete original and patched source inventory required')
    return linux

def pressure():
    report = subprocess.check_output(['/usr/bin/memory_pressure', '-Q'], text=True, timeout=10)
    level = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True, timeout=10).strip())
    return {'rawLevel': level, 'query': report, 'freeInactiveSpeculativeBytes': available_memory()}

def extract(file, destination, top):
    destination.mkdir(mode=0o700)
    with tarfile.open(file) as archive:
        require(all(row.name == top or row.name.startswith(top + '/') for row in archive.getmembers()), 'Unexpected archive root')
        skipped = []
        members = []
        for row in archive.getmembers():
            if (file.name == 'qemu-10.0.13.tar.xz' and top == 'qemu-10.0.13'
                    and row.name == top + '/roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack'
                    and row.issym() and row.linkname == '/opt/X11/include'):
                # This unused edk2 host-build convenience link is absolute. The
                # frozen AAVMF comes from Linux; never extract a host X11 link.
                skipped.append({'member': row.name, 'linkname': row.linkname,
                                'reason': 'Unused edk2 host X11 link; no firmware compilation'})
                continue
            members.append(row)
        archive.extractall(destination, members=members, filter='data')
    (destination.parent / (destination.name + '.extraction.json')).write_text(json.dumps(
        {'sourceArchiveSha256': sha(file), 'skippedExactMembers': skipped}, indent=2))
    return destination / top


def dependencies(file):
    output = subprocess.check_output(['/usr/bin/otool', '-L', str(file)], text=True, timeout=10)
    return [line.strip().split(' (', 1)[0] for line in output.splitlines()[1:]]


def portable_bundle(build, bundle, firmware, source_lock, run):
    (bundle / 'bin').mkdir(parents=True, mode=0o700)
    (bundle / 'lib').mkdir(mode=0o700)
    (bundle / 'share/AAVMF').mkdir(parents=True, mode=0o700)
    for name in ('qemu-system-aarch64', 'qemu-img'):
        shutil.copyfile(build / name, bundle / 'bin' / name)
        (bundle / 'bin' / name).chmod(0o700)
    queue = list((bundle / 'bin').iterdir())
    originals = {}
    seen = set()
    while queue:
        file = queue.pop()
        if file in seen:
            continue
        seen.add(file)
        for dependency in dependencies(file):
            if dependency.startswith(('/usr/lib/', '/System/Library/')):
                continue
            require(dependency.startswith('/'), 'Unresolved original dependency: ' + dependency)
            source = Path(dependency).resolve()
            require(source.is_file(), 'Missing dynamic library input')
            require(source.is_relative_to(Path('/opt/homebrew/Cellar')) or source.is_relative_to(build.parent), 'Unreviewed dynamic library source')
            destination = bundle / 'lib' / source.name
            if destination.name in originals:
                require(originals[destination.name] == source, 'Portable dylib basename collision')
            else:
                originals[destination.name] = source
                shutil.copyfile(source, destination); destination.chmod(0o600); queue.append(destination)
    for file in sorted(seen):
        if file.parent.name == 'lib':
            run('id-' + file.name, ['/usr/bin/install_name_tool', '-id', '@loader_path/' + file.name, str(file)], 30)
        for dependency in dependencies(file):
            if dependency.startswith(('/usr/lib/', '/System/Library/')):
                continue
            target = Path(dependency).resolve().name
            replacement = ('@loader_path/' if file.parent.name == 'lib' else '@loader_path/../lib/') + target
            run('relocate-' + file.name + '-' + target, ['/usr/bin/install_name_tool', '-change', dependency, replacement, str(file)], 30)
    entitlements = bundle.parent / 'hvf-entitlements.plist'
    entitlements.write_bytes(plistlib.dumps({'com.apple.security.hypervisor': True}))
    for file in sorted(seen):
        if file.name == 'qemu-system-aarch64':
            command = ['/usr/bin/codesign', '--force', '--sign', '-', '--entitlements', str(entitlements), str(file)]
        else:
            command = ['/usr/bin/codesign', '--force', '--sign', '-', str(file)]
        run('sign-' + file.name, command, 30)
    for name in ('AAVMF_CODE.fd', 'AAVMF_VARS.fd'):
        shutil.copyfile(firmware / name, bundle / 'share/AAVMF' / name)
        (bundle / 'share/AAVMF' / name).chmod(0o600)
    return {name: str(path) for name, path in originals.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--linux-artifacts', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--owner')
    p.add_argument('--execute-build', action='store_true')
    p.add_argument('--allow-warning-pressure', action='store_true', help='Permit one-job build at observed warning level2 after sole owner coordinates; critical pressure is always rejected')
    a = p.parse_args()
    lock_path = HERE / 'native-build.lock.json'; lock = json.loads(lock_path.read_text())
    verify_inputs(lock, a.sources)
    memory = pressure()
    free = memory['freeInactiveSpeculativeBytes']
    if not a.execute_build:
        print(json.dumps({'writes': False, 'sourcesVerified': True, 'frozenBuildInputs': len(lock['buildDependencyFiles']), 'availableMemoryBytes': free, 'hostMemoryPressure': memory, 'singleJob': True, 'estimatedDurationMinutes': lock['estimatedDurationMinutes'], 'vmStarted': False, 'linuxBuilderMustHaveFinished': True})); return
    require(memory['rawLevel'] == 1 or (memory['rawLevel'] == 2 and a.allow_warning_pressure), 'Host pressure must be normal or explicitly admitted warning; critical/unknown levels reject build')
    require(a.owner and re.fullmatch(r'sduoj-native-build-[a-z0-9-]{1,50}', a.owner), 'Explicit owned build identity required')
    require(a.output and a.output.is_absolute() and str(a.output) == str(a.output.resolve()) and not a.output.exists() and a.output.parent.is_dir() and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(a.output)), 'New canonical private output required')
    require(a.linux_artifacts and a.linux_artifacts.is_absolute(), 'Finished Linux builder artifacts required')
    linux = verify_linux_build(a.linux_artifacts)
    require('QEMU emulator version ' + lock['qemuVersion'] in (a.linux_artifacts / 'qemu-version.txt').read_text(), 'Same Linux/native QEMU patch required')
    firmware = a.linux_artifacts / 'firmware'
    require((a.linux_artifacts / 'firmware.sha256').is_file(), 'Linux firmware checksum receipt required')
    require(all((firmware / name).is_file() and not (firmware / name).is_symlink() for name in ('AAVMF_CODE.fd', 'AAVMF_VARS.fd')), 'Identical verified Linux AAVMF files required')
    firmware_checks = (a.linux_artifacts / 'firmware.sha256').read_text()
    require(all(sha(firmware / name) in firmware_checks for name in ('AAVMF_CODE.fd', 'AAVMF_VARS.fd')), 'Linux firmware hash mismatch')
    os.umask(0o077); a.output.mkdir(mode=0o700); os.nice(10)
    receipt = {'owner': a.owner, 'monitorPid': os.getpid(), 'started': time.time(), 'builderSourceSha256': sha(Path(__file__)), 'sourceLockSha256': sha(lock_path), 'linuxBuildReceiptSha256': sha(a.linux_artifacts / 'build-receipt.json'), 'stages': [], 'vmStarted': False, 'mbpModified': False, 'packageInstalledToSystem': False, 'singleJob': True, 'hostMemoryAdmission': memory, 'warningPressureExplicitlyAdmitted': a.allow_warning_pressure}
    logs = a.output / 'logs'; logs.mkdir(mode=0o700); stage_number = 0
    env = {key: value for key, value in os.environ.items() if key not in ('CFLAGS', 'CXXFLAGS', 'LDFLAGS', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'PYTHONPATH', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR')}
    prefix = a.output / 'prefix'; prefix.mkdir(mode=0o700)
    venv = a.output / 'venv'; work = a.output / 'work'; work.mkdir(mode=0o700)
    env.update(CC=lock['tools']['clang']['path'], CXX=lock['tools']['clang++']['path'], SDKROOT=lock['sdkPath'], MACOSX_DEPLOYMENT_TARGET='26.0', CMAKE_BUILD_PARALLEL_LEVEL='1', MAKEFLAGS='-j1', PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PKG_CONFIG_LIBDIR=':'.join([str(prefix / 'lib/pkgconfig'), *lock['pkgConfigDirectories']]), PKG_CONFIG_PATH=str(prefix / 'lib/pkgconfig'))
    env['PATH'] = str(venv / 'bin') + ':' + str(prefix / 'bin') + ':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    def run(label, command, timeout, cwd=None):
        nonlocal stage_number
        stage_number += 1; file = logs / (str(stage_number).zfill(3) + '-' + re.sub('[^A-Za-z0-9._-]', '-', label) + '.log')
        with file.open('x') as f:
            child = subprocess.Popen(['/usr/bin/time', '-l', *command], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            row = {'label': label, 'pid': child.pid, 'command': command, 'cwd': str(cwd) if cwd else None, 'started': time.time(), 'log': str(file.relative_to(a.output))}; receipt['stages'].append(row)
            (a.output / 'native-build-receipt.json').write_text(json.dumps(receipt, indent=2))
            try: rc = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                try: child.wait(timeout=20)
                except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
                rc = 124
            row.update(exitcode=rc, finished=time.time()); (a.output / 'native-build-receipt.json').write_text(json.dumps(receipt, indent=2))
            require(rc == 0, label + ' failed; preserve logs and do not relax dependency/source guards')
    try:
        gnupg = Path(tempfile.mkdtemp(prefix='sduoj-native-gpg-', dir='/private/tmp')); gnupg.chmod(0o700); env['GNUPGHOME'] = str(gnupg)
        run('qemu-key-import', [lock['tools']['gpg']['path'], '--batch', '--import', str(a.sources / 'qemu-signing-key.asc')], 30)
        run('qemu-signature', [lock['tools']['gpg']['path'], '--batch', '--status-fd=1', '--verify', str(a.sources / 'qemu-10.0.13.tar.xz.sig'), str(a.sources / 'qemu-10.0.13.tar.xz')], 30)
        signature_log = (a.output / receipt['stages'][-1]['log']).read_text()
        require('VALIDSIG ' + lock['qemuSignatureFingerprint'] + ' ' in signature_log, 'Exact official QEMU signer required')
        qemu = extract(a.sources / 'qemu-10.0.13.tar.xz', work / 'qemu-source', 'qemu-10.0.13')
        ninja = extract(a.sources / 'ninja-v1.12.1.tar.gz', work / 'ninja-source', 'ninja-1.12.1')
        slirp = extract(a.sources / 'libslirp-v4.9.1.tar.gz', work / 'slirp-source', 'libslirp-v4.9.1')
        run('private-venv', [lock['tools']['python3']['path'], '-m', 'venv', str(venv)], 60)
        python = str(venv / 'bin/python3')
        run('offline-python-tools', [python, '-m', 'pip', 'install', '--no-index', '--find-links', str(qemu / 'python/wheels'), str(a.sources / 'meson-1.8.1-py3-none-any.whl'), 'pycotap==1.3.1'], 60)
        ninja_build = work / 'ninja-build'
        run('ninja-configure', [lock['tools']['cmake']['path'], '-S', str(ninja), '-B', str(ninja_build), '-G', 'Unix Makefiles', '-DBUILD_TESTING=OFF', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_OSX_DEPLOYMENT_TARGET=26.0'], 60)
        run('ninja-build-one-job', [lock['tools']['cmake']['path'], '--build', str(ninja_build), '--parallel', '1'], 600)
        (prefix / 'bin').mkdir(mode=0o700); shutil.copyfile(ninja_build / 'ninja', prefix / 'bin/ninja'); (prefix / 'bin/ninja').chmod(0o700)
        slirp_build = work / 'slirp-build'
        run('slirp-configure', [str(venv / 'bin/meson'), 'setup', str(slirp_build), str(slirp), '--prefix', str(prefix), '--buildtype', 'release', '--default-library', 'shared', '-Db_lto=false', '-Dc_link_args=-Wl,-headerpad_max_install_names'], 120)
        run('slirp-build-one-job', [str(prefix / 'bin/ninja'), '-C', str(slirp_build), '-j', '1'], 600)
        run('slirp-private-install', [str(venv / 'bin/meson'), 'install', '-C', str(slirp_build), '--no-rebuild'], 120)
        qemu_build = work / 'qemu-build'; qemu_build.mkdir(mode=0o700)
        command = [str(qemu / 'configure'), '--target-list=aarch64-softmmu', '--without-default-features', '--enable-hvf', '--disable-tcg', '--enable-slirp', '--enable-pixman', '--enable-tools', '--disable-gio', '--disable-modules', '--disable-cocoa', '--disable-sdl', '--disable-gtk', '--disable-vnc', '--disable-docs', '--disable-rust', '--disable-download', '--python=' + python, '--ninja=' + str(prefix / 'bin/ninja'), '--extra-ldflags=-Wl,-headerpad_max_install_names', '--prefix=' + str(prefix)]
        run('qemu-configure-offline', command, 300, qemu_build)
        run('qemu-build-one-job', [str(prefix / 'bin/ninja'), '-j', '1', 'qemu-system-aarch64', 'qemu-img'], 7200, qemu_build)
        bundle = a.output / 'bundle'; bundle.mkdir(mode=0o700)
        libraries = portable_bundle(qemu_build, bundle, firmware, lock, run)
        licenses = bundle / 'share/licenses'; licenses.mkdir(mode=0o700)
        for name, source in [('QEMU-COPYING', qemu / 'COPYING'), ('QEMU-COPYING.LIB', qemu / 'COPYING.LIB'), ('Ninja-COPYING', ninja / 'COPYING'), ('libslirp-COPYRIGHT', slirp / 'COPYRIGHT')]:
            require(source.is_file(), 'License input missing: ' + name)
            shutil.copyfile(source, licenses / name); (licenses / name).chmod(0o600)
        # Keep exact source license bytes and source provenance alongside copied existing dylibs.
        for archive_name in lock['sources']:
            if not archive_name.startswith('existing-dependency-sources/'):
                continue
            with tarfile.open(a.sources / archive_name) as tar:
                for row in tar.getmembers():
                    if row.isfile() and ((row.name.count('/') <= 1 and any(word in Path(row.name).name for word in ('COPYING', 'LICENCE', 'LICENSE'))) or '/LICENSES/' in row.name):
                        target = licenses / (Path(archive_name).name + '-' + row.name.replace('/', '_'))
                        target.write_bytes(tar.extractfile(row).read()); target.chmod(0o600)
        (licenses / 'dependency-source-provenance.json').write_text(json.dumps({name: value for name, value in lock['sources'].items() if name.startswith('existing-dependency-sources/')}, indent=2))
        (licenses / 'dependency-source-provenance.json').chmod(0o600)
        run('native-version', [str(bundle / 'bin/qemu-system-aarch64'), '--version'], 30)
        run('native-accelerators', [str(bundle / 'bin/qemu-system-aarch64'), '-accel', 'help'], 30)
        accel = (a.output / receipt['stages'][-1]['log']).read_text(); require(re.search(r'^hvf$', accel, re.M), 'HVF accelerator must be compiled')
        run('native-image-tools', [str(bundle / 'bin/qemu-img'), '--version'], 30)
        native_lock = {'schemaVersion': 1, 'status': 'INTERNAL_ARM64_HVF_BUNDLE_FROZEN', 'platform': 'darwin-arm64', 'qemuVersion': lock['qemuVersion'], 'sourceUrl': lock['sources']['qemu-10.0.13.tar.xz']['url'], 'sourceSha256': lock['sources']['qemu-10.0.13.tar.xz']['sha256'], 'sourceSignatureFingerprint': lock['qemuSignatureFingerprint'], 'sourceSignatureVerified': True, 'archiveSha256': '0' * 64, 'files': {str(p.relative_to(bundle)): sha(p) for p in bundle.rglob('*') if p.is_file()}, 'minimumMacOS': '26.0', 'guestStarted': False, 'mbpHvfValidated': False}
        output_lock = a.output / 'native-bundle.lock.json'; output_lock.write_text(json.dumps(native_lock, indent=2))
        run('portable-signature-and-loader-audit', [python, str(HERE / 'native-bundle.py'), 'verify', '--lock', str(output_lock), '--directory', str(bundle), '--runtime-checks'], 120)
        archive = a.output / 'native-hvf-tools.tar'
        with tarfile.open(archive, 'w') as t:
            for p in sorted(bundle.rglob('*')):
                if p.is_file(): t.add(p, arcname=str(p.relative_to(bundle)), recursive=False)
        native_lock['archiveSha256'] = sha(archive); output_lock.write_text(json.dumps(native_lock, indent=2) + '\n')
        verify_inputs(lock, a.sources)
        receipt.update(passed=True, complete=True, portableArchiveSha256=native_lock['archiveSha256'], portableLockSha256=sha(output_lock), copiedDylibSources=libraries, sourceUnchanged=sha(lock_path) == receipt['sourceLockSha256'], guestStarted=False, mbpHvfValidated=False)
    except Exception as error:
        receipt.update(passed=False, complete=False, failureType=type(error).__name__, failure=str(error)); raise
    finally:
        receipt['finished'] = time.time(); (a.output / 'native-build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': True, 'bundle': str(bundle), 'nativeToolingVerifiedOnMini': True, 'guestStarted': False, 'mbpHvfValidated': False}))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, tarfile.TarError):
        raise SystemExit('Native build guarded/failed; inspect owned receipts; no VM or system package install occurred')
