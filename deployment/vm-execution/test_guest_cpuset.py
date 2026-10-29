import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('guest_cgroup', HERE / 'guest-cgroup.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class GuestCpuSetTests(unittest.TestCase):
    def test_existing_debug_child_gains_interfaces_only_after_parent_enables_cpuset(self):
        # Model the kernel boundary: users cannot create absent cgroup control files.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / 'aggregate'
            debug = parent / 'debug'
            debug.mkdir(parents=True)
            original_write = Path.write_text
            for path, value in ((root / 'cpuset.mems.effective', '0'),
                                (parent / 'cgroup.subtree_control', 'cpu memory pids'),
                                (parent / 'cpuset.mems', ''), (parent / 'cpuset.cpus', ''),
                                (parent / 'cpuset.cpus.effective', '0-15')):
                path.write_text(value)
            def kernel_write(path, value, *args, **kwargs):
                if not path.exists():
                    raise FileNotFoundError('Controller interface not enabled in parent')
                result = original_write(path, value, *args, **kwargs)
                if path == parent / 'cgroup.subtree_control' and '+cpuset' in value:
                    for name in ('cpuset.mems', 'cpuset.cpus', 'cpuset.cpus.effective'):
                        original_write(debug / name, '')
                if path.name == 'cpuset.cpus':
                    original_write(path.parent / 'cpuset.cpus.effective', value)
                return result
            with patch.object(Path, 'write_text', kernel_write):
                guest.configure_cpu_sets(root, parent)
            self.assertEqual((debug / 'cpuset.cpus.effective').read_text(), '0-3')
            self.assertEqual((debug / 'cpuset.mems').read_text(), '0')
            self.assertEqual((parent / 'cpuset.cpus.effective').read_text(), '0-3')


if __name__ == '__main__':
    unittest.main()
