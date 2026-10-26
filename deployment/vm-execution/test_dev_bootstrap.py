import base64
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('dev_bootstrap', HERE / 'dev-bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)


class DevBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sduoj-bootstrap-', dir='/tmp')
        self.root = Path(self.tmp.name).resolve()
        self.c = json.loads((HERE / 'dev-bootstrap.example.json').read_text())
        for k, n in [('stateDirectory', 'state'), ('sourceImage', 'source.qcow2'), ('nativeLock', 'native.json'), ('nativeDirectory', 'bundle')]:
            self.c[k] = str(self.root / n)
        self.c['guestSshPublicKey'] = 'ssh-ed25519 ' + base64.b64encode(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))).decode()
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(self.c)); self.config.chmod(0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_no_config_is_read_only_and_does_not_spawn(self):
        before = set(self.root.iterdir())
        result = subprocess.run([sys.executable, str(HERE / 'dev-bootstrap.py')], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['writes']); self.assertEqual(set(self.root.iterdir()), before)

    def test_plan_does_not_require_future_prepared_guest_or_tools(self):
        with patch.object(sys, 'argv', ['dev-bootstrap.py', 'plan', '--config', str(self.config)]), patch.object(subprocess, 'run') as run, patch.object(subprocess, 'check_output') as check:
            bootstrap.main(); run.assert_not_called(); check.assert_not_called()

    def test_prepare_and_start_require_exact_execution_confirmation(self):
        for operation in ['prepare', 'start']:
            for flags in [[], ['--execute', '--confirm-instance', 'wrong-instance']]:
                with patch.object(sys, 'argv', ['dev-bootstrap.py', operation, '--config', str(self.config), *flags]), patch.object(bootstrap, 'prepare') as prepare, patch.object(bootstrap, 'start') as start:
                    with self.assertRaises(ValueError): bootstrap.main()
                    prepare.assert_not_called(); start.assert_not_called()

    def test_production_and_unexpected_private_values_rejected(self):
        self.c['stage'] = 'production-staging'
        with self.assertRaises(ValueError): bootstrap.validate(self.c)
        self.c['stage'] = 'dev-bootstrap'; self.c['rabbitPassword'] = 'fixture'
        with self.assertRaises(ValueError): bootstrap.validate(self.c)

    def test_zero_key_and_noncanonical_path_rejected(self):
        self.c['guestSshPublicKey'] = 'ssh-ed25519 ' + base64.b64encode(struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(32)).decode()
        with self.assertRaises(ValueError): bootstrap.validate(self.c)
        with self.assertRaises(ValueError): bootstrap.real_path(str(self.root / 'nested/../state'))
        self.c['guestSshPublicKey'] = json.loads(self.config.read_text())['guestSshPublicKey']
        self.c['stateDirectory'] = str(self.root / ('x' * 100))
        with self.assertRaises(ValueError): bootstrap.validate(self.c)

    def test_host_envelope_rejects_mini_and_no_hvf(self):
        with patch.object(bootstrap.platform, 'system', return_value='Darwin'), patch.object(bootstrap.platform, 'machine', return_value='arm64'), patch.object(subprocess, 'check_output', side_effect=['1', '12']):
            with self.assertRaises(ValueError): bootstrap.host_capacity()
        with patch.object(bootstrap.platform, 'system', return_value='Darwin'), patch.object(bootstrap.platform, 'machine', return_value='arm64'), patch.object(subprocess, 'check_output', return_value='0'):
            with self.assertRaises(ValueError): bootstrap.host_capacity()

    def test_initial_guest_has_only_loopback_ssh_and_native_hvf(self):
        args = bootstrap.argv(self.c, self.root / 'state', self.root / 'bundle')
        net = args[args.index('-netdev') + 1]
        self.assertEqual(net, 'user,id=net0,ipv6=off,hostfwd=tcp:127.0.0.1:40222-:22')
        self.assertEqual(args[args.index('-accel') + 1], 'hvf')
        self.assertNotIn('tcg', args); self.assertNotIn('docker', ' '.join(args))

    def test_refuses_retained_runtime_before_spawning(self):
        self.assertNotIn('preparedGuest', self.c)
        bootstrap.validate(self.c)
        with patch.object(bootstrap, 'host_capacity'), patch.object(bootstrap, 'tools', return_value=({}, self.root)), patch.object(bootstrap, 'verify_state', side_effect=ValueError('runtime retained')), patch.object(subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError): bootstrap.start(self.c)
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
