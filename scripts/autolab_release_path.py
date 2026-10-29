#!/usr/bin/env python3
"""Prepare an immutable local AutoLab code directory and change only unit paths.

No remote connections, environment dumps, service starts/stops, or data migration.
The two services must already be drained and inactive before apply or rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import grp
import json
import os
from pathlib import Path
import re
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile


UNITS = ("sduoj-autolab-web.service", "sduoj-autolab-worker.service")
MANIFEST = ".autolab-code-manifest.json"
PROPERTIES = ("ActiveState", "SubState", "WorkingDirectory", "User", "Group",
              "FragmentPath", "DropInPaths")
FORBIDDEN = {".git", ".env", "release.env", "runtime", "logs", "data", "workspaces",
             "__pycache__", ".pytest_cache", "node_modules", ".venv", "dev_config.py"}


class MigrationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise MigrationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


class Policy:
    """Tests inject an isolated trust anchor and owner; CLI never overrides these."""

    def __init__(self, owner=0, anchor=Path("/")):
        self.owner = owner
        self.anchor = Path(anchor)

    def mutation(self):
        require(os.geteuid() == self.owner, "Mutation requires the trusted owner")

    def path(self, path, protected=True):
        path = Path(path)
        require(path.is_absolute() and ".." not in path.parts, "An absolute physical path is required")
        require(path.is_relative_to(self.anchor), "Path outside trust anchor")
        parts = (self.anchor, *[self.anchor.joinpath(*path.relative_to(self.anchor).parts[:i])
                               for i in range(1, len(path.relative_to(self.anchor).parts) + 1)])
        for current in parts:
            info = current.lstat()
            require(not stat.S_ISLNK(info.st_mode), "Symlink in path: " + str(current))
            if protected:
                require(info.st_uid == self.owner and not info.st_mode & 0o022,
                        "Untrusted owner or writable ancestor: " + str(current))
        return path


def read_file(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Expected a single-link regular file")
        require(info.st_size <= 64 * 1024 * 1024, "Source file exceeds the 64 MiB bound")
        return stream.read()


def inventory(root, policy, protected=False):
    policy.path(root, protected)
    records = []
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(current) / name
            relative = path.relative_to(root)
            require(not any(part in FORBIDDEN or part.startswith(".env.") or
                            part.endswith((".pyc", ".key", ".pem")) for part in relative.parts),
                    "Runtime, private or generated entry in source bundle: " + str(relative))
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode), "Symlink in code bundle")
            require(not info.st_mode & 0o7000, "Special permission bits in code bundle")
            if protected:
                require(info.st_uid == policy.owner and not info.st_mode & 0o222,
                        "Installed code is writable or has the wrong owner")
            if stat.S_ISDIR(info.st_mode):
                continue
            require(stat.S_ISREG(info.st_mode), "Special file in code bundle")
            if relative.as_posix() == MANIFEST:
                continue
            require(relative.parts[0] == "autolab" or relative.as_posix() in
                    {"run-web.sh", "run-worker.sh"}, "Unexpected code bundle entry")
            data = read_file(path)
            require(b"-----BEGIN PRIVATE KEY-----" not in data and
                    b"-----BEGIN OPENSSH PRIVATE KEY-----" not in data,
                    "Private key marker in source bundle")
            records.append({"path": relative.as_posix(), "sha256": digest(data),
                            "size": len(data), "executable": bool(info.st_mode & 0o111)})
            require(len(records) <= 20000 and sum(row["size"] for row in records) <= 512 * 1024 * 1024,
                    "Code bundle exceeds size or entry bound")
    require(records, "Empty code bundle")
    return sorted(records, key=lambda row: row["path"])


def tree_sha(records):
    return digest(encode(records))


def validate_config(config):
    require(config.get("schemaVersion") == 1, "Unsupported configuration schema")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", config["releaseId"]) is not None,
            "Invalid release ID")
    require(config["releaseId"] not in {".", ".."}, "Invalid release ID")
    require(re.fullmatch(r"[0-9a-f]{40}", config["sourceRef"]) is not None, "Full source ref required")
    require(re.fullmatch(r"[0-9a-f]{64}", config["sourceTreeSha256"]) is not None,
            "Reviewed source tree digest required")
    require(set(config["dropins"]) == set(UNITS), "Exactly the existing two units are required")
    require(isinstance(config["serviceGid"], int) and config["serviceGid"] >= 0, "Service GID required")
    for key in ("serviceUser", "serviceGroup"):
        require(re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", config[key]) is not None,
                "Explicit service identity required")
    for unit in UNITS:
        require(re.fullmatch(r"[0-9a-f]{64}", config["dropins"][unit]["sha256"]) is not None,
                "Reviewed drop-in digest required")
        dropin = Path(config["dropins"][unit]["path"])
        require(dropin.name == "grade-review-release.conf" and dropin.parent.name == unit + ".d",
                "Only the existing release drop-in may be changed")
    for key in ("source", "oldRelease", "releaseRoot"):
        require(re.fullmatch(r"/[A-Za-z0-9_./-]+", config[key]) is not None and
                ".." not in Path(config[key]).parts, "Unsafe path in configuration")
    require(config["source"] != config["releaseRoot"], "Source and destination must differ")


def target(config):
    return Path(config["releaseRoot"]) / config["releaseId"]


def rewrite_launcher(data, config):
    old = (config["oldRelease"] + "/autolab").encode()
    require(old in data, "Launcher does not reference the expected old code path")
    return data.replace(old, (str(target(config)) + "/autolab").encode())


def rewrite_dropin(data, unit, config):
    role = "web" if unit == UNITS[0] else "worker"
    old = config["oldRelease"]
    new = str(target(config))
    substitutions = {"WorkingDirectory=" + old + "/autolab": "WorkingDirectory=" + new + "/autolab",
                     "ExecStart=/bin/bash " + old + "/run-" + role + ".sh":
                     "ExecStart=/bin/bash " + new + "/run-" + role + ".sh"}
    lines = data.decode("utf-8").splitlines(keepends=True)
    for before, after in substitutions.items():
        matching = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == before]
        require(len(matching) == 1, "Expected exactly one reviewed path directive")
        index = matching[0]
        lines[index] = after + lines[index][len(before):]
    result = "".join(lines).encode()
    require(old.encode() not in result, "Unexpected old code path in drop-in")
    return result


class Systemd:
    def identity(self):
        return digest(read_file(Path("/etc/machine-id")))

    def run(self, *args):
        result = subprocess.run(["/usr/bin/systemctl", *args], capture_output=True, timeout=30)
        require(result.returncode == 0, "systemctl operation failed: " + args[0])
        return result.stdout.decode()

    def show(self, unit):
        raw = self.run("show", unit, "--no-pager", *["--property=" + key for key in PROPERTIES])
        result = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        require(all(key in result for key in PROPERTIES), "Missing systemd metadata")
        return result

    def reload(self):
        self.run("daemon-reload")


def unit_files(metadata, policy):
    result = {}
    for path in sorted({metadata["FragmentPath"], *metadata["DropInPaths"].split()}):
        file = policy.path(Path(path))
        info = file.stat()
        result[path] = {"sha256": digest(read_file(file)), "uid": info.st_uid,
                        "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
    return result


def preflight(config, policy, system):
    validate_config(config)
    policy.path(Path(config["source"]), protected=False)
    rows = inventory(Path(config["source"]), policy)
    require(tree_sha(rows) == config["sourceTreeSha256"], "Source bundle drift")
    require({"run-web.sh", "run-worker.sh"}.issubset({row["path"] for row in rows}),
            "Both existing launchers must be supplied")
    policy.path(Path(config["releaseRoot"]))
    before, files = {}, {}
    for unit in UNITS:
        item = config["dropins"][unit]
        path = policy.path(Path(item["path"]))
        data = read_file(path)
        require(digest(data) == item["sha256"], "Unit drop-in drift: " + unit)
        rewrite_dropin(data, unit, config)
        metadata = system.show(unit)
        require(metadata["User"] == config["serviceUser"] and metadata["Group"] == config["serviceGroup"],
                "Service identity changed")
        files[unit] = unit_files(metadata, policy)
        require(metadata["WorkingDirectory"] == config["oldRelease"] + "/autolab",
                "Effective WorkingDirectory differs from reviewed old path")
        require(str(path) in metadata["DropInPaths"].split(), "Expected drop-in is not loaded")
        # Record only selected nonsecret metadata. Environment/ExecStart are never requested.
        before[unit] = metadata
    return {"schemaVersion": 1, "configSha256": digest(encode(config)),
            "sourceTreeSha256": tree_sha(rows), "target": str(target(config)),
            "targetMachineSha256": system.identity(),
            "units": before, "unitFiles": files, "productionQualified": False}


def atomic_write(path, data, mode=0o600, uid=None, gid=None):
    descriptor, temporary = tempfile.mkstemp(prefix=".autolab-path-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if uid is not None:
            os.chown(temporary, uid, gid)
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare(config, policy, system):
    policy.mutation()
    preflight(config, policy, system)
    destination = target(config)
    require(not destination.exists() and not destination.is_symlink(), "Release ID already exists")
    stage = Path(tempfile.mkdtemp(prefix=".autolab-stage-", dir=config["releaseRoot"]))
    try:
        rows = inventory(Path(config["source"]), policy)
        require(tree_sha(rows) == config["sourceTreeSha256"], "Source drift before copy")
        for row in rows:
            data = read_file(Path(config["source"]) / row["path"])
            require(digest(data) == row["sha256"], "Source drift during copy")
            if row["path"] in {"run-web.sh", "run-worker.sh"}:
                data = rewrite_launcher(data, config)
            output = stage / row["path"]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            os.chown(output, policy.owner, config["serviceGid"])
            os.chmod(output, 0o550 if row["executable"] else 0o440)
        installed = inventory(stage, policy)
        manifest = {"schemaVersion": 1, "sourceRef": config["sourceRef"],
                    "sourceTreeSha256": config["sourceTreeSha256"],
                    "configSha256": digest(encode(config)), "files": installed,
                    "installedTreeSha256": tree_sha(installed)}
        (stage / MANIFEST).write_bytes(encode(manifest))
        for path in [stage / MANIFEST, *[item for item in stage.rglob("*") if item.is_dir()], stage]:
            os.chown(path, policy.owner, config["serviceGid"])
            os.chmod(path, 0o550 if path.is_dir() else 0o440)
        os.rename(stage, destination)
        verify_installed(config, policy)
        return {"status": "prepared", "sourceRef": config["sourceRef"],
                "target": str(destination), "installedTreeSha256": tree_sha(installed),
                "productionQualified": False}
    finally:
        if stage.exists():
            for path in [stage, *[item for item in stage.rglob("*") if item.is_dir()]]:
                os.chmod(path, 0o700)
            shutil.rmtree(stage)


def verify_installed(config, policy):
    destination = policy.path(target(config))
    root_info = destination.stat()
    require(not root_info.st_mode & 0o222 and root_info.st_gid == config["serviceGid"],
            "Installed code root permissions differ")
    manifest = json.loads(read_file(destination / MANIFEST))
    require(manifest["configSha256"] == digest(encode(config)), "Installed configuration mismatch")
    require(manifest["sourceRef"] == config["sourceRef"], "Installed source mismatch")
    rows = inventory(destination, policy, protected=True)
    require(all(path.stat().st_gid == config["serviceGid"] for path in destination.rglob("*")),
            "Installed service group differs")
    for path in [destination, *destination.rglob("*")]:
        executable = path.is_dir() or bool(path.stat().st_mode & 0o111)
        require(stat.S_IMODE(path.stat().st_mode) == (0o550 if executable else 0o440),
                "Installed mode differs from immutable code policy")
    require(rows == manifest["files"] and tree_sha(rows) == manifest["installedTreeSha256"],
            "Installed source drift")
    return manifest


def plan(config, policy, system):
    result = preflight(config, policy, system)
    result["installedTreeSha256"] = verify_installed(config, policy)["installedTreeSha256"]
    result["dropins"] = {}
    for unit in UNITS:
        item = config["dropins"][unit]
        data = read_file(Path(item["path"]))
        result["dropins"][unit] = {"path": item["path"], "beforeSha256": digest(data),
                                   "afterSha256": digest(rewrite_dropin(data, unit, config))}
    return result


def require_inactive(metadata):
    require(all(value["ActiveState"] == "inactive" and value["SubState"] == "dead"
                for value in metadata.values()), "Drain and stop both units before the transaction")


def restore(config, state, state_dir, policy, system):
    validate_config(config)
    require(system.identity() == state["targetMachineSha256"], "Rollback state belongs to another host")
    require_inactive({unit: system.show(unit) for unit in UNITS})
    validated = []
    for unit in UNITS:
        entry = state["backups"][unit]
        path = policy.path(Path(entry["path"]))
        require(digest(read_file(path)) in {entry["beforeSha256"], entry["afterSha256"]},
                "Unit drift prevents automatic rollback")
        data = read_file(policy.path(state_dir / (unit + ".before")))
        require(digest(data) == entry["beforeSha256"], "Rollback backup drift")
        current_files = unit_files(system.show(unit), policy)
        require(set(current_files) == set(state["beforeFiles"][unit]),
                "Loaded unit file set changed; manual recovery required")
        for filename, details in state["beforeFiles"][unit].items():
            if filename != str(path):
                require(current_files.get(filename) == details,
                        "Another unit file changed; manual recovery required")
        validated.append((path, data, entry))
    for path, data, entry in validated:
        atomic_write(path, data, entry["mode"], entry["uid"], entry["gid"])
    system.reload()
    for unit in UNITS:
        require(system.show(unit) == state["beforeUnits"][unit], "Restored effective unit differs")
    state["status"] = "rolled-back"
    atomic_write(state_dir / "state.json", encode(state))
    return {"status": "rolled-back", "servicesStarted": False, "productionQualified": False}


def apply(config, expected_plan, gates, state_dir, policy, system):
    policy.mutation()
    actual = plan(config, policy, system)
    def configuration_only(value):
        return {**value, "units": {unit: {key: item for key, item in metadata.items()
                                         if key not in {"ActiveState", "SubState"}}
                                   for unit, metadata in value["units"].items()}}
    require(configuration_only(actual) == configuration_only(expected_plan),
            "Plan or effective unit drift")
    require_inactive(actual["units"])
    staging = gates.get("environment") == "staging" and gates.get("isolatedTarget") is True
    production = gates.get("environment") == "production" and gates.get("stagingStatus") == "passed"
    require((staging or production) and gates.get("drained") is True and
            gates.get("windowAuthorized") is True and
            gates.get("targetMachineSha256") == actual["targetMachineSha256"] and
            gates.get("configSha256") == actual["configSha256"] and
            gates.get("installedTreeSha256") == actual["installedTreeSha256"],
            "Matching staging, drain and maintenance-window receipts are required")
    policy.path(state_dir.parent)
    require(not state_dir.is_relative_to(Path(config["releaseRoot"])) and
            not state_dir.is_relative_to(Path(config["source"])),
            "Private state must stay outside code and source directories")
    require(not state_dir.exists() and not state_dir.is_symlink(), "State directory must be new")
    state_dir.mkdir(mode=0o700)
    state = {"schemaVersion": 1, "config": config, "beforeUnits": actual["units"],
             "beforeFiles": actual["unitFiles"],
             "targetMachineSha256": actual["targetMachineSha256"],
             "status": "prepared", "backups": {}}
    for unit in UNITS:
        item = config["dropins"][unit]
        path = policy.path(Path(item["path"]))
        info = path.stat()
        data = read_file(path)
        atomic_write(state_dir / (unit + ".before"), data)
        state["backups"][unit] = {**actual["dropins"][unit], "mode": stat.S_IMODE(info.st_mode),
                                   "uid": info.st_uid, "gid": info.st_gid}
    atomic_write(state_dir / "state.json", encode(state))
    try:
        for unit in UNITS:
            entry = state["backups"][unit]
            path = policy.path(Path(entry["path"]))
            data = read_file(path)
            require(digest(data) == entry["beforeSha256"], "Unit drift before replacement")
            atomic_write(path, rewrite_dropin(data, unit, config), entry["mode"], entry["uid"], entry["gid"])
        system.reload()
        for unit in UNITS:
            expected = {**actual["units"][unit], "WorkingDirectory": str(target(config) / "autolab")}
            require(system.show(unit) == expected, "Unexpected effective unit change")
            expected_files = json.loads(json.dumps(actual["unitFiles"][unit]))
            expected_files[config["dropins"][unit]["path"]]["sha256"] = actual["dropins"][unit]["afterSha256"]
            require(unit_files(system.show(unit), policy) == expected_files,
                    "Unexpected unit file change")
        verify_installed(config, policy)
        state["status"] = "applied"
        atomic_write(state_dir / "state.json", encode(state))
    except BaseException:
        try:
            restore(config, state, state_dir, policy, system)
        except BaseException:
            state["status"] = "rollback-required"
            atomic_write(state_dir / "state.json", encode(state))
        raise
    return {"status": "applied", "installedTreeSha256": actual["installedTreeSha256"],
            "servicesStarted": False, "productionQualified": False, "state": str(state_dir)}


def rollback(state_dir, policy, system):
    policy.mutation()
    policy.path(state_dir)
    state = json.loads(read_file(state_dir / "state.json"))
    require(state["status"] in {"prepared", "applied", "rollback-required"},
            "Transaction is not rollback eligible")
    try:
        return restore(state["config"], state, state_dir, policy, system)
    except BaseException:
        state["status"] = "rollback-required"
        atomic_write(state_dir / "state.json", encode(state))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inventory", "preflight", "prepare", "plan", "apply", "rollback"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--gates", type=Path)
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    policy, system = Policy(), Systemd()
    if args.phase == "inventory":
        rows = inventory(args.source, policy)
        result = {"sourceTreeSha256": tree_sha(rows), "files": rows}
    elif args.phase == "rollback":
        result = rollback(args.state, policy, system)
    else:
        policy.path(args.config)
        config = json.loads(read_file(args.config))
        require(config["releaseRoot"] == "/opt/sduoj/releases", "CLI release root must be /opt/sduoj/releases")
        require(pwd.getpwnam(config["serviceUser"]).pw_uid != 0 and
                grp.getgrnam(config["serviceGroup"]).gr_gid == config["serviceGid"],
                "Non-root service identity or group mapping mismatch")
        for unit in UNITS:
            require(config["dropins"][unit]["path"] ==
                    "/etc/systemd/system/" + unit + ".d/grade-review-release.conf",
                    "CLI may change only the existing two release drop-ins")
        if args.phase == "apply":
            policy.path(args.plan)
            policy.path(args.gates)
            result = apply(config, json.loads(read_file(args.plan)), json.loads(read_file(args.gates)),
                           args.state, policy, system)
        else:
            result = globals()[args.phase](config, policy, system)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (MigrationError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("AutoLab path migration refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
