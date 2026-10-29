"""Real temporary files; simulated systemd only. No service or network access."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "autolab_release_path", Path(__file__).parents[1] / "scripts/autolab_release_path.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeSystemd:
    def __init__(self, config):
        self.config = config
        self.active = False
        self.calls = []
        self.fail_reload_once = False

    def identity(self):
        return m.digest(b"isolated-test-machine")

    def show(self, unit):
        self.calls.append(("show", unit))
        path = Path(self.config["dropins"][unit]["path"])
        body = path.read_text()
        cwd = next(line.split("=", 1)[1] for line in body.splitlines()
                   if line.startswith("WorkingDirectory="))
        return {"ActiveState": "active" if self.active else "inactive",
                "SubState": "running" if self.active else "dead", "WorkingDirectory": cwd,
                "User": "service-test", "Group": "service-test",
                "FragmentPath": str(path.parent.parent / unit), "DropInPaths": str(path)}

    def reload(self):
        self.calls.append(("daemon-reload",))
        if self.fail_reload_once:
            self.fail_reload_once = False
            raise m.MigrationError("simulated daemon-reload failure")


class PathMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.policy = m.Policy(owner=os.getuid(), anchor=self.root)
        self.source = self.root / "frozen-input"
        self.releases = self.root / "releases"
        self.state_parent = self.root / "private-state"
        for path in (self.source / "autolab", self.releases, self.state_parent):
            path.mkdir(parents=True, mode=0o700)
        self.old = "/home/service/.releases/grade-review"
        self.runtime = "/home/service/.releases/rc2/runtime/release.env"
        self.python = "/home/service/.releases/rc1/runtime/py39/bin/python"
        self.logs = "/home/service/.releases/rc2/logs/error.log"
        (self.source / "autolab/main.py").write_text("app = object()\n")
        for role in ("web", "worker"):
            body = ("#!/bin/bash\nset -euo pipefail\nset -a\nsource " + self.runtime +
                    "\nset +a\ncd " + self.old + "/autolab\nexec " + self.python +
                    " -m " + ("gunicorn" if role == "web" else "auto_task.worker") +
                    " --log " + self.logs + "\n")
            path = self.source / ("run-" + role + ".sh")
            path.write_text(body)
            path.chmod(0o750)
        self.config = {"schemaVersion": 1, "releaseId": "path-stage-1", "sourceRef": "a" * 40,
                       "source": str(self.source), "oldRelease": self.old,
                       "releaseRoot": str(self.releases), "serviceGid": os.getgid(),
                       "serviceUser": "service-test", "serviceGroup": "service-test", "dropins": {}}
        self.original = {}
        self.base_units = {}
        for unit in m.UNITS:
            role = "web" if unit == m.UNITS[0] else "worker"
            path = self.root / "units" / (unit + ".d") / "grade-review-release.conf"
            path.parent.mkdir(parents=True)
            body = ("[Service]\n# preserve this comment\nWorkingDirectory=" + self.old +
                    "/autolab\nExecStart=\nExecStart=/bin/bash " + self.old + "/run-" + role +
                    ".sh\nEnvironment=TOKEN=do-not-print\nTimeoutStopSec=73\n")
            path.write_text(body)
            self.original[unit] = path.read_bytes()
            self.config["dropins"][unit] = {"path": str(path), "sha256": m.digest(path.read_bytes())}
            base = path.parent.parent / unit
            base.write_text("[Service]\nUser=service-test\nGroup=service-test\nEnvironmentFile=" +
                            self.runtime + "\nStandardOutput=journal\nRestart=on-failure\n")
            self.base_units[base] = base.read_bytes()
        self.config["sourceTreeSha256"] = m.tree_sha(m.inventory(self.source, self.policy))
        self.system = FakeSystemd(self.config)
        self.state = self.state_parent / "operation-1"

    def tearDown(self):
        for current, dirs, files in os.walk(self.root, followlinks=False):
            Path(current).chmod(0o700)
            for name in files:
                path = Path(current) / name
                if not path.is_symlink():
                    path.chmod(0o600)
        self.tmp.cleanup()

    def prepared(self):
        m.prepare(self.config, self.policy, self.system)
        return m.plan(self.config, self.policy, self.system)

    def gates(self, plan):
        return {"environment": "production", "stagingStatus": "passed", "drained": True, "windowAuthorized": True,
                "configSha256": plan["configSha256"],
                "targetMachineSha256": plan["targetMachineSha256"],
                "installedTreeSha256": plan["installedTreeSha256"]}

    def test_preflight_is_read_only_and_never_prints_unit_secrets(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = m.preflight(self.config, self.policy, self.system)
        self.assertNotIn("do-not-print", json.dumps(result))
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*")
                                  if path.is_file()})
        self.assertEqual(list(self.releases.iterdir()), [])
        self.assertTrue(all(call[0] == "show" for call in self.system.calls))

    def test_prepare_immutable_code_and_exact_unit_round_trip_preserve_runtime(self):
        plan = self.prepared()
        new = m.target(self.config)
        for role in ("web", "worker"):
            original = (self.source / ("run-" + role + ".sh")).read_bytes()
            actual = (new / ("run-" + role + ".sh")).read_bytes()
            self.assertEqual(actual, original.replace((self.old + "/autolab").encode(),
                                                      (str(new) + "/autolab").encode()))
            for persistent in (self.runtime, self.python, self.logs):
                self.assertIn(persistent.encode(), actual)
        for path in [new, *new.rglob("*")]:
            self.assertEqual(path.stat().st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o222, 0)
        result = m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        self.assertFalse(result["productionQualified"])
        self.assertFalse(result["servicesStarted"])
        for unit in m.UNITS:
            body = Path(self.config["dropins"][unit]["path"]).read_bytes()
            self.assertEqual(body, m.rewrite_dropin(self.original[unit], unit, self.config))
            self.assertEqual(stat.S_IMODE((self.state / (unit + ".before")).stat().st_mode), 0o600)
        for path, data in self.base_units.items():
            self.assertEqual(path.read_bytes(), data)
        m.rollback(self.state, self.policy, self.system)
        for unit in m.UNITS:
            self.assertEqual(Path(self.config["dropins"][unit]["path"]).read_bytes(), self.original[unit])
        self.assertTrue(all(call[0] in {"show", "daemon-reload"} for call in self.system.calls))

    def test_active_services_are_never_stopped_by_tool(self):
        plan = self.prepared()
        self.system.active = True
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        self.assertFalse(self.state.exists())

    def test_plan_before_external_stop_can_be_used_after_external_stop(self):
        self.system.active = True
        plan = self.prepared()
        self.system.active = False
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)

    def test_missing_staging_or_wrong_exact_bundle_gate_is_refused(self):
        plan = self.prepared()
        gates = self.gates(plan)
        gates["installedTreeSha256"] = "0" * 64
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, gates, self.state, self.policy, self.system)
        self.assertFalse(self.state.exists())

    def test_isolated_staging_can_prepare_its_own_first_acceptance(self):
        plan = self.prepared()
        gates = self.gates(plan)
        gates.update(environment="staging", isolatedTarget=True, stagingStatus="pending")
        result = m.apply(self.config, plan, gates, self.state, self.policy, self.system)
        self.assertFalse(result["productionQualified"])

    def test_production_cannot_use_pending_staging_gate(self):
        plan = self.prepared()
        gates = self.gates(plan)
        gates["stagingStatus"] = "pending"
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, gates, self.state, self.policy, self.system)

    def test_gate_and_rollback_are_bound_to_actual_host(self):
        plan = self.prepared()
        gates = self.gates(plan)
        gates["targetMachineSha256"] = "0" * 64
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, gates, self.state, self.policy, self.system)
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        with patch.object(self.system, "identity", return_value="0" * 64), self.assertRaises(m.MigrationError):
            m.rollback(self.state, self.policy, self.system)

    def test_private_state_cannot_be_written_inside_code(self):
        plan = self.prepared()
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, self.gates(plan), self.releases / "private-state",
                    self.policy, self.system)

    def test_systemd_adapter_never_requests_environment_or_execstart(self):
        raw = "\n".join(key + "=test" for key in m.PROPERTIES).encode()
        with patch.object(m.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=raw)) as run:
            m.Systemd().show(m.UNITS[0])
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[:3], ["/usr/bin/systemctl", "show", m.UNITS[0]])
        self.assertNotIn("--property=Environment", arguments)
        self.assertNotIn("--property=ExecStart", arguments)
        with patch.object(m.subprocess, "run", return_value=SimpleNamespace(
                returncode=1, stdout=b"secret", stderr=b"secret")):
            with self.assertRaisesRegex(m.MigrationError, "^systemctl operation failed: daemon-reload$"):
                m.Systemd().reload()

    def test_other_unit_field_drift_is_detected_by_file_hash(self):
        plan = self.prepared()
        base = next(iter(self.base_units))
        base.write_bytes(base.read_bytes() + b"Environment=OTHER=changed\n")
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        self.assertFalse(self.state.exists())

    def test_source_symlink_hardlink_generated_data_and_hash_drift_are_refused(self):
        path = self.source / "autolab/unsafe.py"
        path.symlink_to(self.source / "autolab/main.py")
        with self.assertRaises(m.MigrationError):
            m.inventory(self.source, self.policy)
        path.unlink()
        os.link(self.source / "autolab/main.py", path)
        with self.assertRaises(m.MigrationError):
            m.inventory(self.source, self.policy)
        path.unlink()
        path = self.source / "autolab/release.env"
        path.write_text("not a deployable source file")
        with self.assertRaises(m.MigrationError):
            m.inventory(self.source, self.policy)
        path.unlink()
        (self.source / "autolab/main.py").write_text("changed\n")
        with self.assertRaises(m.MigrationError):
            m.preflight(self.config, self.policy, self.system)

    def test_writable_ancestor_and_symlink_destination_are_refused(self):
        self.releases.chmod(0o775)
        with self.assertRaises(m.MigrationError):
            self.prepared()
        self.releases.chmod(0o700)
        self.releases.rmdir()
        self.releases.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(m.MigrationError):
            self.prepared()
        self.releases.unlink()

    def test_unit_and_installed_code_drift_are_refused(self):
        plan = self.prepared()
        code = m.target(self.config) / "autolab/main.py"
        code.chmod(0o640)
        code.write_text("changed")
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        self.assertFalse(self.state.exists())

    def test_reload_failure_restores_both_original_dropins(self):
        plan = self.prepared()
        self.system.fail_reload_once = True
        with self.assertRaises(m.MigrationError):
            m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        for unit in m.UNITS:
            self.assertEqual(Path(self.config["dropins"][unit]["path"]).read_bytes(), self.original[unit])
        self.assertEqual(json.loads((self.state / "state.json").read_text())["status"], "rolled-back")

    def test_rollback_refuses_changed_current_unit_or_backup(self):
        plan = self.prepared()
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        path = Path(self.config["dropins"][m.UNITS[0]]["path"])
        path.write_bytes(path.read_bytes() + b"# later operator change\n")
        with self.assertRaises(m.MigrationError):
            m.rollback(self.state, self.policy, self.system)

    def test_second_unit_drift_does_not_partially_restore_first_unit(self):
        plan = self.prepared()
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        first = Path(self.config["dropins"][m.UNITS[0]]["path"])
        first_before = first.read_bytes()
        second = Path(self.config["dropins"][m.UNITS[1]]["path"])
        second.write_bytes(second.read_bytes() + b"# independent change\n")
        with self.assertRaises(m.MigrationError):
            m.rollback(self.state, self.policy, self.system)
        self.assertEqual(first.read_bytes(), first_before)

    def test_backup_tamper_is_refused_before_any_rollback_write(self):
        plan = self.prepared()
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        first = Path(self.config["dropins"][m.UNITS[0]]["path"])
        before = first.read_bytes()
        (self.state / (m.UNITS[1] + ".before")).write_bytes(b"tampered\n")
        with self.assertRaises(m.MigrationError):
            m.rollback(self.state, self.policy, self.system)
        self.assertEqual(first.read_bytes(), before)

    def test_second_unit_write_failure_restores_first_unit(self):
        plan = self.prepared()
        original = m.atomic_write
        second = Path(self.config["dropins"][m.UNITS[1]]["path"])
        failed = False

        def fail_once(path, *args, **kwargs):
            nonlocal failed
            if path == second and not failed:
                failed = True
                raise OSError("simulated write failure")
            return original(path, *args, **kwargs)

        with patch.object(m, "atomic_write", fail_once), self.assertRaises(OSError):
            m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        for unit in m.UNITS:
            self.assertEqual(Path(self.config["dropins"][unit]["path"]).read_bytes(), self.original[unit])

    def test_prepared_crash_state_can_be_rolled_back(self):
        plan = self.prepared()
        m.apply(self.config, plan, self.gates(plan), self.state, self.policy, self.system)
        state = json.loads((self.state / "state.json").read_text())
        state["status"] = "prepared"
        (self.state / "state.json").write_bytes(m.encode(state))
        m.rollback(self.state, self.policy, self.system)
        self.assertEqual(Path(self.config["dropins"][m.UNITS[0]]["path"]).read_bytes(),
                         self.original[m.UNITS[0]])


if __name__ == "__main__":
    unittest.main()
