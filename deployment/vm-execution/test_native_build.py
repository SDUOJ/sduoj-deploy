"""Native preparation guards; no compilation, package installation or VM startup."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_build', HERE / 'native-build.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeBuildGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sduoj-native-test-')
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_plan_never_creates_build_output_or_compiler_process(self):
        output = self.root / 'build'
        args = ['native-build.py', '--sources', str(self.root), '--output', str(output)]
        with patch.object(sys, 'argv', args), patch.object(native, 'verify_inputs'), patch.object(native, 'pressure', return_value={'rawLevel': 2, 'query': 'fixture', 'freeInactiveSpeculativeBytes': 1000}), patch.object(native.subprocess, 'Popen') as process:
            native.main()
            process.assert_not_called()
        self.assertFalse(output.exists())

    def test_critical_pressure_rejects_explicit_build_before_writes(self):
        output = self.root / 'build'
        args = ['native-build.py', '--sources', str(self.root), '--output', str(output), '--owner', 'sduoj-native-build-fixture', '--execute-build', '--allow-warning-pressure']
        with patch.object(sys, 'argv', args), patch.object(native, 'verify_inputs'), patch.object(native, 'pressure', return_value={'rawLevel': 4, 'query': 'critical-fixture', 'freeInactiveSpeculativeBytes': 10**12}), patch.object(native.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(ValueError, 'pressure'):
                native.main()
            process.assert_not_called()
        self.assertFalse(output.exists())

    def test_warning_requires_owner_explicit_admission(self):
        output = self.root / 'build'
        args = ['native-build.py', '--sources', str(self.root), '--output', str(output), '--owner', 'sduoj-native-build-fixture', '--execute-build']
        with patch.object(sys, 'argv', args), patch.object(native, 'verify_inputs'), patch.object(native, 'pressure', return_value={'rawLevel': 2, 'query': 'warning-fixture', 'freeInactiveSpeculativeBytes': 10**12}):
            with self.assertRaisesRegex(ValueError, 'pressure'):
                native.main()
        self.assertFalse(output.exists())

    def test_failed_linux_builder_cannot_admit_native_compilation(self):
        linux = self.root / 'linux'; linux.mkdir()
        (linux / 'build-receipt.json').write_text(json.dumps({'owner': 'sduoj-vm-build-fixture', 'passed': False, 'vmStarted': False, 'stages': []}))
        output = self.root / 'build'
        args = ['native-build.py', '--sources', str(self.root), '--linux-artifacts', str(linux), '--output', str(output), '--owner', 'sduoj-native-build-fixture', '--execute-build']
        with patch.object(sys, 'argv', args), patch.object(native, 'verify_inputs'), patch.object(native, 'pressure', return_value={'rawLevel': 1, 'query': 'normal-fixture', 'freeInactiveSpeculativeBytes': 1}), patch.object(native.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(ValueError, 'Linux sole builder'):
                native.main()
            process.assert_not_called()
        self.assertFalse(output.exists())

    def test_composite_linux_resume_keeps_exact_failed_parent_and_source_hashes(self):
        linux = self.root / 'build-2'; source = linux / 'source'; source.mkdir(parents=True)
        original = self.root / 'build-1'; original.mkdir()
        parent = original / 'build-receipt.json'; parent.write_text(json.dumps({'passed': False}))
        names = ('manager-build.lock.json', 'build-inside.sh', 'source.lock.json', 'freeze-build.py', 'manager.py', 'vmctl.py')
        hashes = {}
        for name in names:
            file = source / name; file.write_text(name); hashes[name] = native.sha(file)
        value = dict(owner='sduoj-vm-build-fixture', passed=True, vmStarted=False, stages=[{'exitcode': 0}], sourceSha256=hashes, sourcePinsUnchanged=True, frozenOriginalSourceCommit='a'*40, permissionFixCommit='b'*40, parentFailedBuildReceiptSha256=native.sha(parent))
        (linux / 'build-receipt.json').write_text(json.dumps(value))
        native.verify_linux_build(linux)
        parent.write_text(json.dumps({'passed': True}))
        with self.assertRaisesRegex(ValueError, 'parent receipt'):
            native.verify_linux_build(linux)

    def test_source_checksum_mismatch_is_rejected(self):
        source = self.root / 'source'; source.write_bytes(b'drift')
        lock = {'status': 'MINI_FIXED_EXISTING_BUILD_DEPS_NOT_NATIVE_OUTPUT', 'sources': {'source': {'bytes': 5, 'sha256': '0' * 64}}}
        with patch.object(native.platform, 'system', return_value='Darwin'), patch.object(native.platform, 'machine', return_value='arm64'):
            with self.assertRaisesRegex(ValueError, 'source mismatch'):
                native.verify_inputs(lock, self.root)

    def test_external_archive_member_does_not_escape_owned_root(self):
        archive = self.root / 'bad.tar'
        with tarfile.open(archive, 'w') as tar:
            row = tarfile.TarInfo('expected/../../escaped'); row.size = 1
            tar.addfile(row, io.BytesIO(b'x'))
        with self.assertRaises(tarfile.TarError):
            native.extract(archive, self.root / 'extract', 'expected')
        self.assertFalse((self.root.parent / 'escaped').exists())

    def test_unexpected_archive_top_is_rejected(self):
        archive = self.root / 'bad.tar'
        with tarfile.open(archive, 'w') as tar:
            row = tarfile.TarInfo('other/file'); row.size = 1
            tar.addfile(row, io.BytesIO(b'x'))
        with self.assertRaisesRegex(ValueError, 'archive root'):
            native.extract(archive, self.root / 'extract', 'expected')

    def test_frozen_lock_pins_all_missing_tools_and_qemu_source(self):
        lock = json.loads((HERE / 'native-build.lock.json').read_text())
        self.assertEqual(lock['qemuVersion'], '10.0.13')
        self.assertTrue({'qemu-10.0.13.tar.xz', 'qemu-10.0.13.tar.xz.sig', 'qemu-signing-key.asc', 'ninja-v1.12.1.tar.gz', 'libslirp-v4.9.1.tar.gz', 'meson-1.8.1-py3-none-any.whl'} <= set(lock['sources']))
        self.assertLess(sum(x['bytes'] for x in lock['sources'].values()), 1024**3)
        self.assertEqual(lock['sources']['meson-1.8.1-py3-none-any.whl']['sha256'], '374bbf71247e629475fc10b0bd2ef66fc418c2d8f4890572f74de0f97d0d42da')
        self.assertGreater(len(lock['buildDependencyFiles']), 300)


if __name__ == '__main__':
    unittest.main()
