import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('guest_preflight', HERE / 'guest-preflight.py')
preflight = importlib.util.module_from_spec(spec); spec.loader.exec_module(preflight)


class GuestPreparationProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sduoj-preparation-probe-')
        self.c = json.loads((HERE / 'deployment.example.json').read_text())
        self.c['stateDirectory'] = str(Path(self.tmp.name).resolve() / 'state')

    def tearDown(self):
        self.tmp.cleanup()

    def test_preparation_does_not_require_future_disk_or_registry_identity(self):
        preflight.validate_probe_config(self.c, preparation=True)
        with self.assertRaises(ValueError): preflight.validate_probe_config(self.c)

    def test_preparation_never_admits_production_or_business_probes(self):
        with self.assertRaises(ValueError): preflight.validate_probe_config(self.c, network=True, preparation=True)
        self.c['stage'] = 'production-staging'
        with self.assertRaises(ValueError): preflight.validate_probe_config(self.c, preparation=True)

    def test_preparation_still_requires_frozen_kernel_and_docker_version(self):
        self.c['preparedGuest']['kernelRelease'] = 'unreviewed-kernel'
        with self.assertRaises(ValueError): preflight.validate_probe_config(self.c, preparation=True)
        self.c['preparedGuest']['kernelRelease'] = '6.12.113+deb13-cloud-arm64'
        self.c['preparedGuest']['dockerVersion'] = '29.2.2'
        with self.assertRaises(ValueError): preflight.validate_probe_config(self.c, preparation=True)


if __name__ == '__main__':
    unittest.main()
