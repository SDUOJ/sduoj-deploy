import copy
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import tarfile
import io
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vmctl
import manager
spec = importlib.util.spec_from_file_location('fetch_source', HERE / 'fetch-source.py')
fetch = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetch)
spec = importlib.util.spec_from_file_location('guest_install', HERE / 'guest-install.py')
install = importlib.util.module_from_spec(spec); spec.loader.exec_module(install)
spec = importlib.util.spec_from_file_location('native_bundle', HERE / 'native-bundle.py')
native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)


class VmPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sduoj-vm-package-')
        self.root = Path(self.tmp.name).resolve()
        self.c = json.loads((HERE / 'deployment.example.json').read_text())
        self.c.update(stateDirectory=str(self.root / 'vm'), managerImage='registry.invalid/manager@sha256:' + '1' * 64,
                      qemuVersion='10.0.9', managerUid=os.getuid() or 1000, managerGid=os.getgid(), guestSshPublicKey='ssh-ed25519 ' + base64.b64encode(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))).decode())
        self.c['boot']['kernelSha256'] = 'd' * 64
        self.c['boot']['initrdSha256'] = 'e' * 64
        for key in ('sha256', 'preparationReceiptSha256'):
            self.c['preparedGuest'][key] = '2' * 64
        self.c['execution'].update(ideImage='registry.invalid/ide@sha256:' + '3' * 64, judgerImage='registry.invalid/judger@sha256:' + '4' * 64,
                                  environment='vm-owned-fixture', nacosNamespace='vm-owned-fixture', nacosHost='10.23.45.67', redisHost='10.23.45.67', rabbitHost='10.23.45.67', rabbitVirtualHost='/owned-vm-fixture',
                                  filesysUrl='http://10.23.45.67:8081', problemRpcUrl='http://10.23.45.67:8082', runRpcUrl='http://10.23.45.67:8082', advertiseAddress='')

    def tearDown(self):
        self.tmp.cleanup()

    def config_file(self):
        p = self.root / 'private.json'; p.write_text(json.dumps(self.c)); p.chmod(0o600); return p

    def test_artifact_builder_defaults_to_no_docker_network_or_write(self):
        before = set(self.root.iterdir())
        result = subprocess.run([sys.executable, str(HERE / 'build-artifacts.py')], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report['writes']); self.assertFalse(report['network']); self.assertFalse(report['guestStarted'])
        self.assertEqual(report['builderMemoryMiB'], 768); self.assertEqual(set(self.root.iterdir()), before)

    def test_default_is_help_without_process_or_files(self):
        before = set(self.root.iterdir())
        result = subprocess.run([sys.executable, str(HERE / 'vmctl.py')], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0); self.assertEqual(set(self.root.iterdir()), before)

    def test_readonly_plan_reports_unresolved_template(self):
        self.c = json.loads((HERE / 'deployment.example.json').read_text()); self.c['stateDirectory'] = str(self.root / 'vm')
        p = self.config_file(); before = set(self.root.iterdir())
        result = subprocess.run([sys.executable, str(HERE / 'vmctl.py'), 'plan', '--config', str(p)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0); self.assertFalse(json.loads(result.stdout)['fullyPinned']); self.assertEqual(set(self.root.iterdir()), before)

    def staged_fixture(self):
        state = Path(self.c['stateDirectory'])
        data = b'guard-test-only-not-a-VM-image'
        self.c['preparedGuest']['sha256'] = hashlib.sha256(data).hexdigest()
        p = self.c['preparedGuest']
        kernel = bytearray(64); kernel[56:60] = b'ARMd'
        self.c['boot']['kernelSha256'] = hashlib.sha256(kernel).hexdigest()
        self.c['boot']['initrdSha256'] = hashlib.sha256(b'fixture-initrd').hexdigest()
        receipt = dict(schemaVersion=1, status='PREPARED_NOT_GUEST_QUALIFIED', upstreamSha512=p['upstreamSha512'], diskSha256=p['sha256'], kernelRelease=p['kernelRelease'], dockerVersion=p['dockerVersion'], architecture='aarch64', cgroupVersion='2', cgroupDriver='cgroupfs', packageLockSha256='a'*64, kernelConfigSha256='b'*64, dockerDaemonConfigSha256='c'*64, bootMode='direct-kernel', boot=copy.deepcopy(self.c['boot']), kernelPackageVersion='6.12.113-1')
        text = json.dumps(receipt)
        self.c['preparedGuest']['preparationReceiptSha256'] = hashlib.sha256(text.encode()).hexdigest()
        vmctl.render(self.c, state)
        (state / 'prepared-guest.qcow2').write_bytes(data)
        for filename, content in (('kernel.Image', kernel), ('initrd.img', b'fixture-initrd')):
            (state / filename).write_bytes(content); (state / filename).chmod(0o400)
        (state / 'preparation-receipt.json').write_text(text)
        (state / 'preparation-receipt.json').chmod(0o600)
        return self.config_file()

    def test_explicit_start_guard_never_spawns_without_confirmation(self):
        config = self.staged_fixture()
        for flags in ([], ['--execute', '--confirm-instance', 'another-instance']):
            with patch.object(sys, 'argv', ['vmctl.py', 'start', '--config', str(config), *flags]), patch.object(subprocess, 'run') as run:
                with self.assertRaises(ValueError): vmctl.main()
                run.assert_not_called()

    def test_production_staging_requires_separate_bound_dispatch(self):
        self.c['stage'] = 'production-staging'; config = self.staged_fixture()
        with patch.object(sys, 'argv', ['vmctl.py', 'start', '--config', str(config), '--execute', '--confirm-instance', self.c['name']]), patch.object(subprocess, 'run') as run:
            with self.assertRaises(ValueError): vmctl.main()
            run.assert_not_called()

    def test_direct_boot_pins_cmdline_and_accelerator_are_exact(self):
        for backend in ('kvm', 'hvf'):
            args = manager.argv(self.c, self.root, backend)
            self.assertEqual(args[args.index('-accel') + 1], backend)
            self.assertEqual(args[args.index('-append') + 1], vmctl.KERNEL_COMMAND_LINE)
            self.assertIn('virt-10.0,gic-version=3', args)
            self.assertNotIn('pflash', ' '.join(args))
            self.assertNotIn('vars.fd', ' '.join(args))
        for key, value in (('commandLine', vmctl.KERNEL_COMMAND_LINE + ' init=/bin/sh'), ('rootPartuuid', 'unreviewed'), ('kernelSha256', '')):
            c = copy.deepcopy(self.c); c['boot'][key] = value
            with self.assertRaises(ValueError): vmctl.validate(c)
        c = copy.deepcopy(self.c); c['bootMode'] = 'uefi'
        with self.assertRaises(ValueError): vmctl.validate(c)

    def test_boot_asset_inventory_rejects_writable_symlink_and_hash_drift(self):
        state = self.root / 'boot-assets'; state.mkdir()
        kernel = bytearray(64); kernel[56:60] = b'ARMd'
        (state / 'kernel.Image').write_bytes(kernel); (state / 'initrd.img').write_bytes(b'initrd')
        for filename, key in (('kernel.Image', 'kernelSha256'), ('initrd.img', 'initrdSha256')):
            file = state / filename; self.c['boot'][key] = vmctl.sha(file); file.chmod(0o400)
        vmctl.verify_boot_assets(self.c, state)
        (state / 'initrd.img').chmod(0o600)
        with self.assertRaises(ValueError): vmctl.verify_boot_assets(self.c, state)
        (state / 'initrd.img').write_bytes(b'drift'); (state / 'initrd.img').chmod(0o400)
        with self.assertRaises(ValueError): vmctl.verify_boot_assets(self.c, state)
        (state / 'initrd.img').unlink(); (state / 'initrd.img').symlink_to(state / 'kernel.Image')
        with self.assertRaises(ValueError): vmctl.verify_boot_assets(self.c, state)

    def test_missing_image_and_package_pins_fail_closed(self):
        vmctl.validate(self.c)
        self.c['managerImage'] = 'manager:latest'
        with self.assertRaises(ValueError): vmctl.validate(self.c)
        with self.assertRaises(ValueError): install.packages(json.loads((HERE / 'guest-packages.example.json').read_text()), self.root)

    def test_offline_installer_does_not_fetch_optional_packages_or_remove_existing(self):
        command = install.install_command([{'file': 'frozen.deb'}], self.root)
        self.assertIn('--no-download', command)
        self.assertIn('--no-remove', command)
        self.assertIn('--no-install-recommends', command)
        self.assertEqual(command[-1], str(self.root / 'frozen.deb'))

    def test_apt_epoch_filename_token_is_accepted_without_url_decoding(self):
        rows = []
        for n in ('docker-ce', 'docker-ce-cli', 'containerd.io', 'docker-buildx-plugin', 'docker-compose-plugin'):
            file = n + '_5%3a29.2.1_arm64.deb'; data = n.encode(); (self.root / file).write_bytes(data)
            rows.append(dict(name=n, version='5:29.2.1', file=file, sha256=hashlib.sha256(data).hexdigest()))
        lock = dict(schemaVersion=1, architecture='arm64', status='OFFICIAL_APT_DEPENDENCY_CLOSURE_FROZEN', packages=rows)
        self.assertEqual(install.packages(lock, self.root), rows)
        for value in ('../escape.deb', 'docker%2fescape.deb', 'docker%00.deb', 'docker%253a.deb'):
            bad = copy.deepcopy(lock); bad['packages'][0]['file'] = value
            with self.assertRaises(ValueError): install.packages(bad, self.root)

    def test_apt_cache_staging_keeps_exact_bytes_and_refuses_existing_drift(self):
        source = self.root / 'source-debs'; source.mkdir(); cache = self.root / 'cache'
        file = 'docker-ce_5%3a29.2.1_arm64.deb'; data = b'verified deb'
        (source / file).write_bytes(data)
        rows = [dict(file=file, sha256=hashlib.sha256(data).hexdigest())]
        install.stage_archives(rows, source, cache)
        self.assertEqual((cache / file).read_bytes(), data)
        (cache / file).write_bytes(b'drift')
        with self.assertRaises(ValueError): install.stage_archives(rows, source, cache)

    def test_local_image_id_is_dev_only_and_never_registry_identity(self):
        self.c['execution']['ideImage'] = 'sha256:' + '5' * 64
        vmctl.validate(self.c)
        self.assertEqual(vmctl.image_reference_kinds(self.c)['ide-worker'], 'dev-local-image-config-id')
        self.c['stage'] = 'production-staging'
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_dev_local_images_preserve_permissions_and_production_rejects_each(self):
        original = vmctl.compose_executors(self.c)
        self.c['managerImage'] = 'sha256:' + '6' * 64
        self.c['execution']['ideImage'] = 'sha256:' + '7' * 64
        self.c['execution']['judgerImage'] = 'sha256:' + '8' * 64
        vmctl.validate(self.c)
        rendered = vmctl.compose_executors(self.c)
        for role, service in rendered['services'].items():
            self.assertEqual({k: v for k, v in service.items() if k != 'image'}, {k: v for k, v in original['services'][role].items() if k != 'image'})
            self.assertEqual(service['pull_policy'], 'never')
        vmctl.render(self.c, self.root / 'dev-local-render')
        vmctl.verify_render(self.c, self.root / 'dev-local-render')
        self.assertTrue(all(k == 'dev-local-image-config-id' for k in vmctl.image_reference_kinds(self.c).values()))
        for ref in ('mutable:latest', 'sha256:123', 'sha256:' + 'g' * 64):
            with self.assertRaises(ValueError): vmctl.image_reference_kind(ref, 'dev')
        for value in ('sha256:' + '6' * 64, 'sha256:' + '7' * 64, 'sha256:' + '8' * 64):
            with self.assertRaises(ValueError): vmctl.image_reference_kind(value, 'production-staging')

    def test_renderer_has_no_database_or_business_services(self):
        data = vmctl.compose_executors(self.c)
        self.assertEqual(set(data['services']), {'ide-worker', 'judger', 'run-worker'})
        self.assertTrue(all(x['profiles'] == ['explicit-executor-start'] for x in data['services'].values()))

    def test_manager_has_only_kvm_and_owned_storage(self):
        s = vmctl.compose_manager(self.c)['services']['manager']
        self.assertEqual(s['devices'], ['/dev/kvm:/dev/kvm:rw']); self.assertEqual(len(s['volumes']), 1)
        self.assertEqual(s['volumes'][0]['source'], self.c['stateDirectory']); self.assertFalse(s['privileged'])
        self.assertEqual(s['cap_drop'], ['ALL']); self.assertNotEqual(s['user'].split(':')[0], '0'); self.assertEqual(s['command'], ['plan'])
        self.assertNotIn('docker.sock', json.dumps(s)); self.assertNotIn('/dev/net/tun', json.dumps(s))

    def test_executor_quotas_and_cpu_sets_do_not_overlap(self):
        services = vmctl.compose_executors(self.c)['services']
        self.assertEqual([(x['cpus'], x['mem_limit'], x['cpuset']) for x in services.values()], [(4, '6g', '0-3'), (2, '2560m', '4-5'), (2, '2560m', '6-7')])
        self.assertTrue(all(x['memswap_limit'] == x['mem_limit'] for x in services.values()))
        self.assertEqual(services['ide-worker']['user'], '10001:10001'); self.assertEqual(services['judger']['cgroup'], 'private')
        self.assertEqual(services['judger']['entrypoint'][:3], ['/usr/bin/tini', '--', '/usr/local/bin/sduoj-judge-entrypoint'])
        self.c['execution']['runCpuset'] = '3-4'
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_bootstrap_forwards_only_loopback_no_80_443(self):
        args = manager.argv(self.c, self.root, 'kvm')
        net = args[args.index('-netdev') + 1]
        self.assertIn('tcp:127.0.0.1:40222-:22', net); self.assertIn('tcp:127.0.0.1:39086-:39086', net)
        self.assertNotIn('0.0.0.0', net); self.assertNotIn(':443-', net); self.assertNotIn(':80-', net)
        self.assertNotIn('tcg', args)

    def test_integrated_nacos_requires_real_private_host_binding(self):
        self.c['networkPhase'] = 'integrated'
        for value in ('', '10.0.2.15', '127.0.0.1', '8.8.8.8'):
            self.c['execution']['advertiseAddress'] = value
            with self.assertRaises(ValueError): vmctl.validate(self.c)
        self.c['healthBindAddress'] = '10.23.45.67'; self.c['execution']['advertiseAddress'] = '10.23.45.67'
        vmctl.validate(self.c)
        self.assertEqual(vmctl.compose_executors(self.c)['services']['ide-worker']['environment']['NACOS_IP'], '10.23.45.67')

    def test_integrated_java_ports_and_advertisements_are_distinct(self):
        self.c['networkPhase'] = 'integrated'
        self.c['healthBindAddress'] = '10.23.45.67'
        self.c['execution']['advertiseAddress'] = '10.23.45.67'
        vmctl.validate(self.c)
        services = vmctl.compose_executors(self.c)['services']
        for name, port in [('judger', 39087), ('run-worker', 39088)]:
            command = services[name]['command']
            self.assertIn('--server.port=' + str(port), command)
            self.assertIn('--spring.cloud.nacos.discovery.port=' + str(port), command)
            self.assertIn('--spring.cloud.nacos.discovery.ip=10.23.45.67', command)
        args = manager.argv(self.c, self.root, 'kvm')
        net = args[args.index('-netdev') + 1]
        for port in (39086, 39087, 39088): self.assertIn(f'hostfwd=tcp:10.23.45.67:{port}-:{port}', net)
        self.c['execution']['runPort'] = 39087
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_service_endpoint_rejects_guest_alias_and_public_ip(self):
        for value in ('10.0.2.2', '10.0.2.15', '127.0.0.1', '8.8.8.8', 'host.docker.internal', '169.254.1.1'):
            c = copy.deepcopy(self.c); c['execution']['redisHost'] = value
            with self.assertRaises(ValueError): vmctl.validate(c)

    def test_readonly_render_creates_private_bundle_only_when_explicit(self):
        output = self.root / 'render'; vmctl.render(self.c, output)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir()))
        vmctl.verify_render(self.c, output)
        self.assertEqual(json.loads((output / 'compose.executors.json').read_text())['services'], {})
        with self.assertRaises(ValueError): vmctl.render(self.c, output)
        (output / 'user-data').write_text('drift')
        with self.assertRaises(ValueError): vmctl.verify_render(self.c, output)

    def test_invalid_public_key_cannot_render_unreachable_guest_identity(self):
        self.c['guestSshPublicKey'] = 'ssh-ed25519 ' + 'A' * 68
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_private_config_permissions_and_symlinks_rejected(self):
        p = self.config_file(); p.chmod(0o644)
        with self.assertRaises(ValueError): vmctl.read_config(p)
        p.chmod(0o600); link = self.root / 'link'; link.symlink_to(p)
        with self.assertRaises(ValueError): vmctl.read_config(link)

    def test_production_activation_stage_is_not_supported(self):
        self.c['stage'] = 'production'
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_parent_directory_and_public_bind_injection_rejected(self):
        for value in ('/', str(self.root / '..' / 'escape'), '/private/path,invalid'):
            c = copy.deepcopy(self.c); c['stateDirectory'] = value
            with self.assertRaises(ValueError): vmctl.validate(c)
        self.c['healthBindAddress'] = '0.0.0.0'
        with self.assertRaises(ValueError): vmctl.validate(self.c)

    def test_preparation_receipt_does_not_accept_old_docker_or_missing_inventory(self):
        p = self.c['preparedGuest']
        receipt = dict(schemaVersion=1, status='PREPARED_NOT_GUEST_QUALIFIED', upstreamSha512=p['upstreamSha512'], diskSha256=p['sha256'], kernelRelease=p['kernelRelease'], dockerVersion=p['dockerVersion'], architecture='aarch64', cgroupVersion='2', cgroupDriver='cgroupfs', packageLockSha256='a'*64, kernelConfigSha256='b'*64, dockerDaemonConfigSha256='c'*64, bootMode='direct-kernel', boot=copy.deepcopy(self.c['boot']), kernelPackageVersion='6.12.113-1')
        vmctl.validate_preparation(self.c, receipt)
        receipt['dockerVersion'] = '27.1.1'
        with self.assertRaises(ValueError): vmctl.validate_preparation(self.c, receipt)
        receipt['dockerVersion'] = p['dockerVersion']; receipt['kernelConfigSha256'] = ''
        with self.assertRaises(ValueError): vmctl.validate_preparation(self.c, receipt)

    def test_source_lock_is_fixed_not_latest_and_requires_both_hashes(self):
        lock = json.loads((HERE / 'source.lock.json').read_text()); fetch.validate(lock)
        lock['url'] = lock['url'].replace('20261021-2638/', 'latest/')
        with self.assertRaises(ValueError): fetch.validate(lock)

    def test_native_unbuilt_bundle_is_not_ready(self):
        with self.assertRaises(ValueError): native.validate(json.loads((HERE / 'native-bundle.example.json').read_text()))
        for value in ('../host', '/root/host', 'lib/../../escape', 'bin/x;command'):
            self.assertFalse(native.valid_path(value))

    def test_native_bundle_requires_exact_archive_and_regular_payload(self):
        payload = {name: ('test-payload-' + name).encode() for name in native.REQUIRED}
        archive = self.root / 'native.tar'
        with tarfile.open(archive, 'w') as tar:
            for name, data in payload.items():
                row = tarfile.TarInfo(name); row.size = len(data); tar.addfile(row, io.BytesIO(data))
        lock = dict(schemaVersion=1, status='INTERNAL_ARM64_HVF_BUNDLE_FROZEN', platform='darwin-arm64', qemuVersion='10.0.9', sourceUrl='https://download.qemu.org/qemu-10.0.9.tar.xz', sourceSignatureVerified=True, sourceSignatureFingerprint='CEACC9E15534EBABB82D3FA03353C9CEF108B584', sourceSha256='a'*64, archiveSha256=vmctl.sha(archive), files={name: hashlib.sha256(data).hexdigest() for name, data in payload.items()})
        destination = self.root / 'bundle'
        native.stage(lock, archive, destination); self.assertFalse(native.verify(lock, destination)['vmStarted'])
        with self.assertRaises(ValueError): native.stage(lock, archive, destination)
        (destination / 'bin/qemu-img').write_bytes(b'drift')
        with self.assertRaises(ValueError): native.verify(lock, destination)
        bad = self.root / 'symlink.tar'
        with tarfile.open(bad, 'w') as tar:
            row = tarfile.TarInfo('bin/qemu-img'); row.type = tarfile.SYMTYPE; row.linkname = '/bin/sh'; tar.addfile(row)
        lock['archiveSha256'] = vmctl.sha(bad)
        with self.assertRaises(ValueError): native.stage(lock, bad, self.root / 'rejected')
        self.assertFalse((self.root / 'rejected').exists())

    def test_qcow_audit_rejects_corrupt_bytes_and_external_backing(self):
        data = struct.pack('>IIQIIQ', 0x514649fb, 3, 0, 0, 16, 3221225472) + bytes(72)
        file = self.root / 'small-test.qcow2'; file.write_bytes(data)
        lock = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'sha512': hashlib.sha512(data).hexdigest()}
        self.assertFalse(fetch.audit(file, lock)['guestBooted'])
        file.write_bytes(data + b'drift')
        with self.assertRaises(ValueError): fetch.audit(file, lock)
        data = struct.pack('>IIQIIQ', 0x514649fb, 3, 1024, 10, 16, 3221225472) + bytes(72); file.write_bytes(data)
        lock.update(sha256=hashlib.sha256(data).hexdigest(), sha512=hashlib.sha512(data).hexdigest())
        with self.assertRaises(ValueError): fetch.audit(file, lock)

if __name__ == '__main__':
    unittest.main()
