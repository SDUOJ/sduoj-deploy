#!/usr/bin/env python3
"""Local release, rollback, drift, and backup tooling for Web2 + Autolab.

The tool never performs a remote deployment. Every deployment mutation requires
an explicit absolute local target and CLI --apply. The optional migration plan
connects only to the database selected by the caller's Autolab environment.
Java services remain outside this release unit.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FORMAT_VERSION = 1
RELEASE_MANIFEST = "release-manifest.json"
BACKUP_MANIFEST = "backup-manifest.json"
MARKER = ".artifact-sha256"
STATE = "release-state.json"
ROOT_MARKER = ".sduoj-ai-release-root"
COMPONENT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
MAX_FILE_SIZE = 512 * 1024 * 1024

EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".hg",
    ".svn",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "__pycache__",
    "node_modules",
    "build",
    "coverage",
    "data",
    "logs",
    "workspaces",
    "output",
    "test-results",
    "tests",
    "playwright-report",
}
EXCLUDED_NAMES = {
    ".env",
    ".coverage",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "auth.json",
    "autolab.env",
    "compose.env",
    "credentials",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
    "sessions.json",
    "test-user.json",
    "dev_config.py",
    "local_config.py",
    "config.local.py",
    "prepare_dev.py",
    "test_main.http",
}
EXCLUDED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
PRIVATE_MARKERS = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----")


class ReleaseError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_from_epoch(value: int) -> str:
    if value < 0:
        raise ReleaseError("SOURCE_DATE_EPOCH must not be negative")
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ReleaseError("Unsafe archive path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ReleaseError("Unsafe archive path: " + value)
    return path


def _excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in EXCLUDED_DIRS for part in parts[:-1]):
        return True
    name = relative.name
    lowered = name.lower()
    if lowered in EXCLUDED_NAMES or (lowered.startswith(".env.") and lowered != ".env.example"):
        return True
    if Path(lowered).suffix in EXCLUDED_SUFFIXES:
        return True
    return name in {".DS_Store"} or lowered.endswith((".pyc", ".pyo", ".swp", "~"))


def _file_record(path: Path, archive_path: str) -> dict:
    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ReleaseError("File exceeds 512 MiB: " + str(path))
    with path.open("rb") as stream:
        prefix = stream.read(4096)
    if any(marker in prefix for marker in PRIVATE_MARKERS):
        raise ReleaseError("Private key content is not allowed: " + str(path))
    return {
        "path": archive_path,
        "sha256": sha256_file(path),
        "size": size,
        "mode": stat.S_IMODE(path.stat().st_mode) & 0o755,
    }


def collect_tree(root: Path, prefix: str, release_policy: bool = True) -> Tuple[List[Tuple[Path, dict]], List[str]]:
    if root.expanduser().is_symlink():
        raise ReleaseError("Source directory may not be a symbolic link")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ReleaseError("Source is not a directory: " + str(root))
    if root in {Path("/"), Path.home().resolve()}:
        raise ReleaseError("Refusing a broad source directory")
    result: List[Tuple[Path, dict]] = []
    excluded: List[str] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept = []
        for name in sorted(directories):
            relative = (current_path / name).relative_to(root)
            candidate = current_path / name
            if candidate.is_symlink():
                if not release_policy:
                    raise ReleaseError("Backup source contains a symbolic link: " + relative.as_posix())
                excluded.append(relative.as_posix() + "/")
            elif release_policy and (name in EXCLUDED_DIRS or _excluded(relative)):
                excluded.append(relative.as_posix() + "/")
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            path = current_path / name
            relative = path.relative_to(root)
            if path.is_symlink():
                if not release_policy:
                    raise ReleaseError("Backup source contains a symbolic link: " + relative.as_posix())
                excluded.append(relative.as_posix())
                continue
            if not path.is_file() or (release_policy and _excluded(relative)):
                excluded.append(relative.as_posix())
                continue
            archive_path = ((PurePosixPath(prefix) / PurePosixPath(relative.as_posix())).as_posix()
                            if prefix else relative.as_posix())
            result.append((path, _file_record(path, archive_path)))
    if not result:
        raise ReleaseError("Source contains no packageable files: " + str(root))
    result.sort(key=lambda item: item[1]["path"])
    return result, sorted(excluded)


def _write_archive(output: Path, manifest_name: str, manifest: dict, files: Sequence[Tuple[Path, dict]]) -> Path:
    if output.expanduser().is_symlink():
        raise ReleaseError("Output may not be a symbolic link")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sidecar = output.with_name(output.name + ".sha256")
    if output.exists() or sidecar.exists():
        raise ReleaseError("Output already exists: " + str(output))
    temporary = output.with_name("." + output.name + ".partial-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    manifest_data = json_bytes(manifest)
                    info = tarfile.TarInfo(manifest_name)
                    info.size, info.mode, info.mtime = len(manifest_data), 0o644, 0
                    archive.addfile(info, io.BytesIO(manifest_data))
                    for source, record in files:
                        info = tarfile.TarInfo(record["path"])
                        info.size, info.mode, info.mtime = record["size"], record["mode"], 0
                        with source.open("rb") as stream:
                            archive.addfile(info, stream)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    digest = sha256_file(output)
    _write_sidecar(output, digest)
    return output


def build_release(web2: Path, autolab: Path, output: Path, release_id: Optional[str] = None,
                  created_utc: Optional[str] = None, preflight: Optional[dict] = None) -> dict:
    release_id = release_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not RELEASE_RE.fullmatch(release_id):
        raise ReleaseError("Invalid release ID")
    files: List[Tuple[Path, dict]] = []
    excluded: Dict[str, List[str]] = {}
    for name, root in (("web2", web2), ("autolab", autolab)):
        rows, skipped = collect_tree(root, name, release_policy=True)
        files.extend(rows)
        excluded[name] = skipped
    paths = [item[1]["path"] for item in files]
    if len(paths) != len(set(paths)):
        raise ReleaseError("Duplicate packaged path")
    manifest = {
        "format_version": FORMAT_VERSION,
        "kind": "release",
        "release_id": release_id,
        "created_utc": created_utc or utc_now(),
        "components": ["web2", "autolab"],
        "files": [record for _, record in sorted(files, key=lambda item: item[1]["path"])],
        "excluded": excluded,
        "java_backend": "unchanged",
    }
    if preflight is not None:
        manifest["preflight"] = preflight
    _write_archive(output, RELEASE_MANIFEST, manifest, files)
    return manifest


def _tree_digest(root: Path) -> str:
    rows, _ = collect_tree(root, "", release_policy=True)
    value = [{"path": record["path"], "sha256": record["sha256"],
              "size": record["size"], "mode": record["mode"]} for _, record in rows]
    return hashlib.sha256(json_bytes(value)).hexdigest()


def _copy_packageable_tree(source: Path, destination: Path) -> None:
    rows, _ = collect_tree(source, "", release_policy=True)
    destination.mkdir(parents=True, mode=0o750)
    for source_file, record in rows:
        target = destination.joinpath(*PurePosixPath(record["path"]).parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        shutil.copyfile(source_file, target)
        target.chmod(record["mode"])


def _run_preflight(command: Sequence[str], cwd: Path, environment: Mapping[str, str],
                   label: str, timeout: int = 1200) -> dict:
    try:
        result = subprocess.run(list(command), cwd=cwd, env=dict(environment), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseError(label + " could not complete: " + str(error)) from error
    output = result.stdout or ""
    if result.returncode != 0:
        raise ReleaseError("{} failed ({}):\n{}".format(label, result.returncode, output[-6000:]))
    return {"name": label, "status": "passed"}


def _tool_version(command: Sequence[str], cwd: Path, environment: Mapping[str, str], label: str) -> str:
    try:
        result = subprocess.run(list(command), cwd=cwd, env=dict(environment), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseError(label + " version check failed: " + str(error)) from error
    if result.returncode != 0 or not result.stdout.strip():
        raise ReleaseError(label + " version check failed: " + result.stdout[-2000:])
    return result.stdout.strip().splitlines()[-1]


def prepare_release(web2_source: Path, autolab_source: Path, output: Path, release_id: str,
                    source_date_epoch: int, node: Path, yarn: Path, python: Path,
                    migration_check: bool = False) -> dict:
    if not RELEASE_RE.fullmatch(release_id):
        raise ReleaseError("Invalid release ID")
    web2_source = web2_source.resolve(strict=True)
    autolab_source = autolab_source.resolve(strict=True)
    node = node.resolve(strict=True)
    yarn = yarn.resolve(strict=True)
    python = python.resolve(strict=True)
    for path, label in ((node, "Node"), (yarn, "Yarn"), (python, "Python")):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ReleaseError(label + " executable is unavailable: " + str(path))
    required_web = ["package.json", "yarn.lock", "src", "public"]
    required_autolab = ["main.py", "requirements.txt", "auto_task/migrate.py", "auto_task/worker.py",
                        "scripts/export_ai_contracts.py", "docs/sql/20260905_auto_task_ai.sql"]
    for relative in required_web:
        if not (web2_source / relative).exists():
            raise ReleaseError("Web2 release input is missing: " + relative)
    for relative in required_autolab:
        if not (autolab_source / relative).is_file():
            raise ReleaseError("Autolab release input is missing: " + relative)
    node_modules = web2_source / "node_modules"
    if node_modules.is_symlink() or not node_modules.is_dir():
        raise ReleaseError("Web2 node_modules must be a real, preinstalled offline dependency directory")

    created_utc = utc_from_epoch(source_date_epoch)
    environment = os.environ.copy()
    environment.update({
        "PATH": str(node.parent) + os.pathsep + environment.get("PATH", ""),
        "CI": "true",
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "npm_config_offline": "true",
        "YARN_ENABLE_NETWORK": "0",
        "SOURCE_DATE_EPOCH": str(source_date_epoch),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    node_version = _tool_version([str(node), "-p", "process.versions.node"], web2_source, environment, "Node")
    if node_version.split(".", 1)[0] != "24":
        raise ReleaseError("Web2 release build requires Node 24, found " + node_version)
    yarn_version = _tool_version([str(yarn), "--version"], web2_source, environment, "Yarn")
    package = json.loads((web2_source / "package.json").read_text(encoding="utf-8"))
    if package.get("packageManager") != "yarn@" + yarn_version:
        raise ReleaseError("Yarn version does not match Web2 packageManager")
    python_version = _tool_version([str(python), "--version"], autolab_source, environment, "Python")

    checks = []
    with tempfile.TemporaryDirectory(prefix="sduoj-ai-release-") as temporary_value:
        temporary = Path(temporary_value)
        web_build_tree = temporary / "web2"
        _copy_packageable_tree(web2_source, web_build_tree)
        os.symlink(node_modules, web_build_tree / "node_modules", target_is_directory=True)
        yarn_base = [str(yarn), "--offline", "--frozen-lockfile", "--non-interactive", "run"]
        checks.append(_run_preflight([*yarn_base, "typecheck"], web_build_tree, environment, "web2-typecheck"))
        checks.append(_run_preflight([*yarn_base, "lint"], web_build_tree, environment, "web2-lint"))
        test_environment = dict(environment)
        if "SDUOJ_TEST_NODE_OPTIONS" in environment:
            test_environment["NODE_OPTIONS"] = environment["SDUOJ_TEST_NODE_OPTIONS"]
        checks.append(_run_preflight([*yarn_base, "test:unit", "--watch=false"], web_build_tree, test_environment, "web2-unit-tests"))
        checks.append(_run_preflight([*yarn_base, "build"], web_build_tree, environment, "web2-production-build"))
        build_output = web_build_tree / "build"
        if not (build_output / "index.html").is_file():
            raise ReleaseError("Web2 build did not produce build/index.html")

        checks.append(_run_preflight([str(python), "-m", "pytest", "-q"], autolab_source,
                                     environment, "autolab-unit-tests"))
        checks.append(_run_preflight([str(python), "scripts/export_ai_contracts.py"], autolab_source,
                                     environment, "autolab-contract-and-ddl"))
        if migration_check:
            checks.append(_run_preflight([str(python), "-m", "auto_task.migrate"], autolab_source,
                                         environment, "autolab-migration-dry-run", timeout=120))
        preflight = {
            "source_date_epoch": source_date_epoch,
            "input_sha256": {"web2": _tree_digest(web2_source), "autolab": _tree_digest(autolab_source)},
            "tools": {"node": node_version, "yarn": yarn_version, "python": python_version},
            "node_options": environment.get("NODE_OPTIONS", ""),
            "test_node_options": test_environment.get("NODE_OPTIONS", ""),
            "checks": checks,
            "migration_check": migration_check,
            "network_policy": "yarn-offline",
        }
        manifest = build_release(build_output, autolab_source, output, release_id,
                                 created_utc=created_utc, preflight=preflight)
        if verify_artifact(output, "release") != manifest:
            raise ReleaseError("Finished release artifact did not verify against its manifest")
    return manifest


def build_backup(source: Path, output: Path, backup_id: Optional[str] = None) -> dict:
    backup_id = backup_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not RELEASE_RE.fullmatch(backup_id):
        raise ReleaseError("Invalid backup ID")
    files, _ = collect_tree(source, "payload", release_policy=False)
    manifest = {
        "format_version": FORMAT_VERSION,
        "kind": "backup",
        "backup_id": backup_id,
        "created_utc": utc_now(),
        "files": [record for _, record in files],
    }
    _write_archive(output, BACKUP_MANIFEST, manifest, files)
    return manifest


def _check_sidecar(artifact: Path) -> None:
    sidecar = artifact.with_name(artifact.name + ".sha256")
    if not sidecar.exists():
        raise ReleaseError("Artifact SHA-256 sidecar is missing")
    fields = sidecar.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != artifact.name or fields[0] != sha256_file(artifact):
        raise ReleaseError("Artifact SHA-256 sidecar mismatch")


def _write_sidecar(path: Path, digest: Optional[str] = None) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if sidecar.exists():
        raise ReleaseError("Output already exists: " + str(sidecar))
    temporary = sidecar.with_name("." + sidecar.name + ".partial-" + uuid.uuid4().hex)
    try:
        temporary.write_text((digest or sha256_file(path)) + "  " + path.name + "\n", encoding="ascii")
        os.replace(temporary, sidecar)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_artifact(artifact: Path, expected_kind: Optional[str] = None) -> Tuple[dict, Dict[str, tarfile.TarInfo]]:
    if artifact.expanduser().is_symlink():
        raise ReleaseError("Artifact may not be a symbolic link")
    artifact = artifact.resolve(strict=True)
    _check_sidecar(artifact)
    try:
        with tarfile.open(artifact, mode="r:gz") as archive:
            members: Dict[str, tarfile.TarInfo] = {}
            total = 0
            for member in archive.getmembers():
                path = _safe_relative(member.name).as_posix()
                if path in members:
                    raise ReleaseError("Duplicate archive member: " + path)
                if not member.isfile():
                    raise ReleaseError("Archive may contain regular files only: " + path)
                total += member.size
                if member.size > MAX_FILE_SIZE or total > 2 * 1024 * 1024 * 1024:
                    raise ReleaseError("Artifact expansion limit exceeded")
                members[path] = member
            manifest_name = RELEASE_MANIFEST if RELEASE_MANIFEST in members else BACKUP_MANIFEST if BACKUP_MANIFEST in members else None
            if manifest_name is None:
                raise ReleaseError("Artifact manifest is missing")
            manifest_stream = archive.extractfile(members[manifest_name])
            if manifest_stream is None:
                raise ReleaseError("Artifact manifest is unreadable")
            manifest = json.loads(manifest_stream.read())
            _validate_manifest(manifest, manifest_name, members)
            if expected_kind and manifest["kind"] != expected_kind:
                raise ReleaseError("Expected a {} artifact".format(expected_kind))
            for record in manifest["files"]:
                stream = archive.extractfile(members[record["path"]])
                if stream is None:
                    raise ReleaseError("Artifact member is unreadable")
                digest = hashlib.sha256()
                size = 0
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
                if size != record["size"] or digest.hexdigest() != record["sha256"]:
                    raise ReleaseError("Artifact member integrity mismatch: " + record["path"])
            return manifest, members
    except (tarfile.TarError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        if isinstance(error, ReleaseError):
            raise
        raise ReleaseError("Invalid artifact: " + type(error).__name__) from error


def _validate_manifest(manifest: object, manifest_name: str, members: Mapping[str, tarfile.TarInfo]) -> None:
    if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
        raise ReleaseError("Unsupported artifact manifest")
    if manifest.get("kind") not in ("release", "backup") or not isinstance(manifest.get("files"), list):
        raise ReleaseError("Invalid artifact manifest")
    expected_manifest = RELEASE_MANIFEST if manifest["kind"] == "release" else BACKUP_MANIFEST
    if manifest_name != expected_manifest:
        raise ReleaseError("Artifact kind and manifest disagree")
    records = {}
    for record in manifest["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "size", "mode"}:
            raise ReleaseError("Invalid file record")
        path = _safe_relative(record["path"]).as_posix()
        if path in (RELEASE_MANIFEST, BACKUP_MANIFEST, MARKER) or path in records:
            raise ReleaseError("Duplicate or reserved file record: " + path)
        if not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])):
            raise ReleaseError("Invalid file digest: " + path)
        if not isinstance(record["size"], int) or not 0 <= record["size"] <= MAX_FILE_SIZE:
            raise ReleaseError("Invalid file size: " + path)
        if not isinstance(record["mode"], int) or record["mode"] & ~0o755:
            raise ReleaseError("Invalid file mode: " + path)
        records[path] = record
    archive_files = set(members) - {manifest_name}
    if archive_files != set(records):
        raise ReleaseError("Manifest and archive members differ")
    if manifest["kind"] == "release":
        if not RELEASE_RE.fullmatch(str(manifest.get("release_id", ""))):
            raise ReleaseError("Invalid release ID")
        if set(manifest.get("components", [])) != {"web2", "autolab"}:
            raise ReleaseError("Release components are incomplete")
        if any(not (path.startswith("web2/") or path.startswith("autolab/")) for path in records):
            raise ReleaseError("Release file is outside a declared component")
        if "preflight" in manifest:
            preflight = manifest["preflight"]
            expected_keys = {"source_date_epoch", "input_sha256", "tools", "checks",
                             "migration_check", "network_policy"}
            if (not isinstance(preflight, dict) or not expected_keys.issubset(preflight)
                    or set(preflight) - expected_keys - {"node_options", "test_node_options"}
                    or not isinstance(preflight.get("node_options", ""), str)
                    or not isinstance(preflight.get("test_node_options", ""), str)):
                raise ReleaseError("Invalid release preflight record")
            if not isinstance(preflight["source_date_epoch"], int) or preflight["source_date_epoch"] < 0:
                raise ReleaseError("Invalid release preflight epoch")
            if manifest.get("created_utc") != utc_from_epoch(preflight["source_date_epoch"]):
                raise ReleaseError("Release timestamp does not match SOURCE_DATE_EPOCH")
            inputs = preflight["input_sha256"]
            tools = preflight["tools"]
            if not isinstance(inputs, dict) or set(inputs) != {"web2", "autolab"} or any(
                    not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in inputs.values()):
                raise ReleaseError("Invalid release input provenance")
            if not isinstance(tools, dict) or set(tools) != {"node", "yarn", "python"} or any(
                    not isinstance(value, str) or not value for value in tools.values()):
                raise ReleaseError("Invalid release tool provenance")
            checks = preflight["checks"]
            if not isinstance(checks, list) or any(
                    not isinstance(item, dict) or set(item) != {"name", "status"}
                    or not isinstance(item["name"], str)
                    or item["status"] != "passed" for item in checks):
                raise ReleaseError("Invalid release preflight check")
            expected_checks = {"web2-typecheck", "web2-lint", "web2-unit-tests",
                               "web2-production-build", "autolab-unit-tests",
                               "autolab-contract-and-ddl"}
            if not isinstance(preflight["migration_check"], bool):
                raise ReleaseError("Invalid migration preflight state")
            if preflight["migration_check"]:
                expected_checks.add("autolab-migration-dry-run")
            if {item["name"] for item in checks} != expected_checks or len(checks) != len(expected_checks):
                raise ReleaseError("Release preflight checks are incomplete")
            if preflight["network_policy"] != "yarn-offline":
                raise ReleaseError("Release build network policy is invalid")
            required = {"web2/index.html", "autolab/main.py", "autolab/requirements.txt",
                        "autolab/auto_task/migrate.py", "autolab/auto_task/worker.py",
                        "autolab/scripts/export_ai_contracts.py", "autolab/docs/sql/20260905_auto_task_ai.sql"}
            if not required.issubset(records):
                raise ReleaseError("Prepared release is missing a runtime or migration entrypoint")
    elif not RELEASE_RE.fullmatch(str(manifest.get("backup_id", ""))):
        raise ReleaseError("Invalid backup ID")


def verify_artifact(artifact: Path, expected_kind: Optional[str] = None) -> dict:
    manifest, _ = read_artifact(artifact, expected_kind)
    return manifest


def _normalized_target(path: Path) -> Path:
    if not path.is_absolute():
        raise ReleaseError("Target must be an explicit absolute local path")
    normalized = Path(os.path.abspath(str(path)))
    probe = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        probe /= part
        if probe.is_symlink():
            raise ReleaseError("Target path may not traverse a symlink: " + str(probe))
    forbidden = {Path("/"), Path.home().resolve(), Path("/etc"), Path("/usr"), Path("/var"), Path("/opt")}
    if normalized in forbidden:
        raise ReleaseError("Refusing a broad target directory")
    return normalized


def _explicit_target(path: Path, create: bool = False, require_empty: bool = False) -> Path:
    normalized = _normalized_target(path)
    if normalized.exists() and normalized.is_symlink():
        raise ReleaseError("Target directory may not be a symlink")
    if not normalized.exists():
        if not create:
            raise ReleaseError("Target does not exist; pass --create-target explicitly")
        normalized.mkdir(parents=True, mode=0o750)
    if not normalized.is_dir():
        raise ReleaseError("Target is not a directory")
    if require_empty and any(normalized.iterdir()):
        raise ReleaseError("Restore target must be empty")
    return normalized


def deployment_plan(artifact: Path, target: Path, create_target: bool = False) -> dict:
    manifest = verify_artifact(artifact, "release")
    normalized = _normalized_target(target)
    previous = None
    if normalized.exists():
        normalized = _explicit_target(normalized)
        initialized = (normalized / STATE).exists()
        marker_exists = _validate_root_marker(normalized, allow_missing=True)
        entries = {item.name for item in normalized.iterdir()}
        if not initialized and entries - ({ROOT_MARKER} if marker_exists else set()):
            raise ReleaseError("First deploy target must be empty")
        if initialized:
            if not marker_exists:
                raise ReleaseError("Release target marker is missing")
            previous = _read_state(normalized).get("current")
    elif not create_target:
        raise ReleaseError("Target does not exist; pass --create-target explicitly")
    return {"dry_run": True, "action": "deploy-local", "release_id": manifest["release_id"],
            "target": str(normalized), "previous": previous, "would_create_target": not normalized.exists()}


def rollback_plan(target: Path, release_id: Optional[str] = None) -> dict:
    normalized = _explicit_target(target)
    _validate_root_marker(normalized)
    state = _read_state(normalized)
    current = state.get("current")
    if release_id is None:
        candidates = [item for item in reversed(state.get("history", [])) if item != current]
        if not candidates:
            raise ReleaseError("No previous release is available")
        release_id = candidates[0]
    if not RELEASE_RE.fullmatch(str(release_id)):
        raise ReleaseError("Invalid rollback release ID")
    verify_release_directory(normalized / "releases" / release_id)
    return {"dry_run": True, "action": "rollback-local", "current": current,
            "target_release": release_id, "target": str(normalized)}


def restore_plan(artifact: Path, target: Path, create_target: bool = False) -> dict:
    manifest = verify_artifact(artifact, "backup")
    normalized = _normalized_target(target)
    if normalized.exists():
        _explicit_target(normalized, require_empty=True)
    elif not create_target:
        raise ReleaseError("Target does not exist; pass --create-target explicitly")
    return {"dry_run": True, "action": "restore-backup", "backup_id": manifest["backup_id"],
            "files": len(manifest["files"]), "target": str(normalized),
            "would_create_target": not normalized.exists()}


def _extract_verified(artifact: Path, destination: Path, expected_kind: str) -> dict:
    manifest, _ = read_artifact(artifact, expected_kind)
    with tarfile.open(artifact, mode="r:gz") as archive:
        members = {}
        for member in archive.getmembers():
            relative = _safe_relative(member.name).as_posix()
            if relative in members or not member.isfile():
                raise ReleaseError("Artifact changed after verification")
            members[relative] = member
        manifest_name = RELEASE_MANIFEST if expected_kind == "release" else BACKUP_MANIFEST
        expected_names = {manifest_name, *(record["path"] for record in manifest["files"])}
        if set(members) != expected_names:
            raise ReleaseError("Artifact changed after verification")
        for record in manifest["files"]:
            relative = _safe_relative(record["path"])
            target = destination.joinpath(*relative.parts)
            if destination.resolve(strict=True) not in target.resolve(strict=False).parents:
                raise ReleaseError("Extraction target escaped staging")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            member = members[record["path"]]
            if member.size != record["size"]:
                raise ReleaseError("Artifact changed after verification")
            stream = archive.extractfile(member)
            if stream is None:
                raise ReleaseError("Artifact member is unreadable")
            with target.open("xb") as output:
                shutil.copyfileobj(stream, output, length=1024 * 1024)
            target.chmod(record["mode"])
    manifest_name = RELEASE_MANIFEST if expected_kind == "release" else BACKUP_MANIFEST
    (destination / manifest_name).write_bytes(json_bytes(manifest))
    return manifest


def _atomic_current(target: Path, release_id: str) -> None:
    current = target / "current"
    if (current.exists() or current.is_symlink()) and not current.is_symlink():
        raise ReleaseError("Current release pointer is not a symbolic link")
    temporary = target / (".current-" + uuid.uuid4().hex)
    os.symlink((Path("releases") / release_id).as_posix(), temporary)
    try:
        os.replace(temporary, current)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _read_state(target: Path) -> dict:
    path = target / STATE
    if not path.exists():
        return {"current": None, "history": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("history"), list):
        raise ReleaseError("Release state is invalid")
    return value


def _write_state(target: Path, value: dict) -> None:
    temporary = target / ("." + STATE + "." + uuid.uuid4().hex)
    temporary.write_bytes(json_bytes(value))
    os.replace(temporary, target / STATE)


def _root_marker_value() -> dict:
    return {"format_version": FORMAT_VERSION, "purpose": "sduoj-ai-release-root"}


def _validate_root_marker(target: Path, allow_missing: bool = False) -> bool:
    marker = target / ROOT_MARKER
    if not marker.exists() and not marker.is_symlink():
        if allow_missing:
            return False
        raise ReleaseError("Release target marker is missing")
    if marker.is_symlink() or not marker.is_file():
        raise ReleaseError("Release target marker is unsafe")
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError("Release target marker is invalid") from error
    if value != _root_marker_value():
        raise ReleaseError("Release target marker belongs to another workflow")
    return True


def _write_root_marker(target: Path) -> None:
    marker = target / ROOT_MARKER
    if marker.exists() or marker.is_symlink():
        _validate_root_marker(target)
        return
    temporary = target / ("." + ROOT_MARKER + "." + uuid.uuid4().hex)
    try:
        temporary.write_bytes(json_bytes(_root_marker_value()))
        temporary.chmod(0o640)
        os.replace(temporary, marker)
    finally:
        if temporary.exists():
            temporary.unlink()


def _installed_manifest(release: Path) -> dict:
    manifest_path = release / RELEASE_MANIFEST
    if not manifest_path.is_file():
        raise ReleaseError("Installed release manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marker_path = release / MARKER
    if not marker_path.is_file():
        raise ReleaseError("Installed release integrity marker is missing")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ReleaseError("Installed release integrity marker is invalid") from error
    if marker.get("manifest_sha256") != hashlib.sha256(json_bytes(manifest)).hexdigest():
        raise ReleaseError("Installed release manifest integrity check failed")
    if manifest.get("kind") != "release" or manifest.get("format_version") != FORMAT_VERSION:
        raise ReleaseError("Installed release manifest is invalid")
    return manifest


def verify_release_directory(release: Path) -> dict:
    manifest = _installed_manifest(release)
    expected = {record["path"]: record for record in manifest.get("files", [])}
    report = compare_tree(release, expected, ignored={RELEASE_MANIFEST, MARKER})
    if any(report[key] for key in ("missing", "changed", "added", "unsafe")):
        raise ReleaseError("Installed release integrity check failed")
    return manifest


def deploy_release(artifact: Path, target: Path, create_target: bool = False) -> dict:
    manifest = verify_artifact(artifact, "release")
    target = _explicit_target(target, create=create_target)
    initialized = (target / STATE).exists()
    marker_exists = _validate_root_marker(target, allow_missing=True)
    entries = {item.name for item in target.iterdir()}
    if not initialized and entries - ({ROOT_MARKER} if marker_exists else set()):
        raise ReleaseError("First deploy target must be empty")
    if initialized and not marker_exists:
        raise ReleaseError("Release target marker is missing")
    if not marker_exists:
        _write_root_marker(target)
    releases = target / "releases"
    releases.mkdir(mode=0o750, exist_ok=True)
    release_id = manifest["release_id"]
    destination = releases / release_id
    if destination.exists():
        installed = verify_release_directory(destination)
        if installed != manifest:
            raise ReleaseError("Release ID already exists with different content")
    else:
        staging = releases / (".staging-" + uuid.uuid4().hex)
        staging.mkdir(mode=0o750)
        try:
            extracted = _extract_verified(artifact, staging, "release")
            (staging / MARKER).write_bytes(json_bytes({
                "artifact_sha256": sha256_file(artifact),
                "manifest_sha256": hashlib.sha256(json_bytes(extracted)).hexdigest(),
            }))
            verify_release_directory(staging)
            os.replace(staging, destination)
            if extracted != manifest:
                raise ReleaseError("Extracted release manifest mismatch")
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    state = _read_state(target)
    previous = state.get("current")
    _atomic_current(target, release_id)
    history = [item for item in state.get("history", []) if item != release_id]
    if previous and previous != release_id:
        history.append(previous)
    state = {"current": release_id, "history": history[-20:], "updated_utc": utc_now()}
    _write_state(target, state)
    return {"current": release_id, "previous": previous, "replay": previous == release_id}


def rollback_release(target: Path, release_id: Optional[str] = None) -> dict:
    target = _explicit_target(target)
    _validate_root_marker(target)
    state = _read_state(target)
    current = state.get("current")
    history = list(state.get("history", []))
    if release_id is None:
        candidates = [item for item in reversed(history) if item != current]
        if not candidates:
            raise ReleaseError("No previous release is available")
        release_id = candidates[0]
    if not RELEASE_RE.fullmatch(str(release_id)):
        raise ReleaseError("Invalid rollback release ID")
    destination = target / "releases" / release_id
    verify_release_directory(destination)
    _atomic_current(target, release_id)
    history = [item for item in history if item != release_id]
    if current and current != release_id:
        history.append(current)
    state = {"current": release_id, "history": history[-20:], "updated_utc": utc_now()}
    _write_state(target, state)
    return {"current": release_id, "previous": current}


def compare_tree(root: Path, expected: Mapping[str, dict], ignored: Iterable[str] = ()) -> dict:
    ignored = set(ignored)
    actual: Dict[str, Path] = {}
    unsafe: List[str] = []
    if not root.is_dir():
        raise ReleaseError("Comparison root is not a directory")
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        base = Path(current)
        kept = []
        for name in sorted(directories):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                unsafe.append(relative + "/")
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative in ignored:
                continue
            if path.is_symlink() or not path.is_file():
                unsafe.append(relative)
            else:
                actual[relative] = path
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    changed = sorted(path for path in set(expected) & set(actual)
                     if actual[path].stat().st_size != expected[path]["size"] or sha256_file(actual[path]) != expected[path]["sha256"])
    return {"clean": not (missing or added or changed or unsafe), "missing": missing,
            "changed": changed, "added": added, "unsafe": sorted(unsafe)}


def drift_report(target: Path, prefixes: Sequence[str] = ()) -> dict:
    target = _explicit_target(target)
    _validate_root_marker(target)
    state = _read_state(target)
    release_id = state.get("current")
    if not release_id:
        raise ReleaseError("No current release")
    release = target / "releases" / release_id
    manifest = _installed_manifest(release)
    normalized = []
    for prefix in prefixes:
        normalized.append(_safe_relative(prefix.rstrip("/")).as_posix() + "/")
    expected = {record["path"]: record for record in manifest["files"]
                if not normalized or any(record["path"].startswith(prefix) for prefix in normalized)}
    report = compare_tree(release, expected, ignored={RELEASE_MANIFEST, MARKER})
    if normalized:
        report["added"] = [path for path in report["added"] if any(path.startswith(prefix) for prefix in normalized)]
        report["unsafe"] = [path for path in report["unsafe"] if any(path.startswith(prefix) for prefix in normalized)]
        report["clean"] = not any(report[key] for key in ("missing", "changed", "added", "unsafe"))
    return {"release_id": release_id, "prefixes": list(prefixes), **report}


def build_config_baseline(source: Path, output: Path, baseline_id: Optional[str] = None) -> dict:
    baseline_id = baseline_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not RELEASE_RE.fullmatch(baseline_id):
        raise ReleaseError("Invalid configuration baseline ID")
    files, excluded = collect_tree(source, "", release_policy=True)
    baseline = {"format_version": FORMAT_VERSION, "kind": "config", "baseline_id": baseline_id,
                "created_utc": utc_now(), "files": [record for _, record in files], "excluded": excluded}
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_name(output.name + ".sha256").exists():
        raise ReleaseError("Output already exists: " + str(output))
    temporary = output.with_name("." + output.name + ".partial-" + uuid.uuid4().hex)
    try:
        temporary.write_bytes(json_bytes(baseline))
        os.replace(temporary, output)
        _write_sidecar(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return baseline


def read_config_baseline(path: Path) -> dict:
    try:
        path = path.resolve(strict=True)
        _check_sidecar(path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError("Invalid configuration baseline") from error
    if not isinstance(value, dict) or value.get("format_version") != FORMAT_VERSION or value.get("kind") != "config":
        raise ReleaseError("Invalid configuration baseline")
    if not RELEASE_RE.fullmatch(str(value.get("baseline_id", ""))) or not isinstance(value.get("files"), list):
        raise ReleaseError("Invalid configuration baseline")
    seen = set()
    for record in value["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "size", "mode"}:
            raise ReleaseError("Invalid configuration file record")
        relative = _safe_relative(record["path"]).as_posix()
        if relative in seen or not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])):
            raise ReleaseError("Invalid configuration file record")
        if not isinstance(record["size"], int) or record["size"] < 0:
            raise ReleaseError("Invalid configuration file record")
        seen.add(relative)
    return value


def config_drift(baseline_path: Path, current: Path) -> dict:
    baseline = read_config_baseline(baseline_path)
    current = current.resolve(strict=True)
    expected = {record["path"]: record for record in baseline["files"]}
    return {"baseline_id": baseline["baseline_id"], **compare_tree(current, expected)}


def restore_backup(artifact: Path, target: Path, create_target: bool = False) -> dict:
    manifest = verify_artifact(artifact, "backup")
    target = _explicit_target(target, create=create_target, require_empty=True)
    staging = target.parent / ("." + target.name + ".restore-" + uuid.uuid4().hex)
    staging.mkdir(mode=0o750)
    try:
        _extract_verified(artifact, staging, "backup")
        expected = {record["path"]: record for record in manifest["files"]}
        report = compare_tree(staging, expected, ignored={BACKUP_MANIFEST})
        if not report["clean"]:
            raise ReleaseError("Restored backup integrity check failed")
        target.rmdir()
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"backup_id": manifest["backup_id"], "files": len(manifest["files"]), "target": str(target)}


def _path(value: str) -> Path:
    return Path(value)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-release")
    build.add_argument("--web2", required=True, type=_path, help="Prepared Web2 deployable directory")
    build.add_argument("--autolab", required=True, type=_path, help="Prepared Autolab deployable directory")
    build.add_argument("--output", required=True, type=_path)
    build.add_argument("--release-id")

    prepare = sub.add_parser("prepare-release")
    prepare.add_argument("--web2-source", required=True, type=_path)
    prepare.add_argument("--autolab-source", required=True, type=_path)
    prepare.add_argument("--output", required=True, type=_path)
    prepare.add_argument("--release-id", required=True)
    prepare.add_argument("--source-date-epoch", required=True, type=int)
    prepare.add_argument("--node", required=True, type=_path)
    prepare.add_argument("--yarn", required=True, type=_path)
    prepare.add_argument("--python", required=True, type=_path)
    prepare.add_argument("--migration-check", action="store_true",
                         help="Run read-only auto_task.migrate against the configured database")

    verify = sub.add_parser("verify")
    verify.add_argument("artifact", type=_path)
    verify.add_argument("--kind", choices=["release", "backup"])

    deploy = sub.add_parser("deploy-local")
    deploy.add_argument("artifact", type=_path)
    deploy.add_argument("--target", required=True, type=_path)
    deploy.add_argument("--create-target", action="store_true")
    deploy.add_argument("--apply", action="store_true", help="Perform the planned local mutation")

    rollback = sub.add_parser("rollback-local")
    rollback.add_argument("--target", required=True, type=_path)
    rollback.add_argument("--to")
    rollback.add_argument("--apply", action="store_true", help="Perform the planned local mutation")

    drift = sub.add_parser("drift")
    drift.add_argument("--target", required=True, type=_path)
    drift.add_argument("--prefix", action="append", default=[])

    config_baseline = sub.add_parser("config-baseline")
    config_baseline.add_argument("--source", required=True, type=_path)
    config_baseline.add_argument("--output", required=True, type=_path)
    config_baseline.add_argument("--baseline-id")

    config_drift_parser = sub.add_parser("config-drift")
    config_drift_parser.add_argument("--baseline", required=True, type=_path)
    config_drift_parser.add_argument("--current", required=True, type=_path)

    backup = sub.add_parser("build-backup")
    backup.add_argument("--source", required=True, type=_path)
    backup.add_argument("--output", required=True, type=_path)
    backup.add_argument("--backup-id")

    restore = sub.add_parser("restore-backup")
    restore.add_argument("artifact", type=_path)
    restore.add_argument("--target", required=True, type=_path)
    restore.add_argument("--create-target", action="store_true")
    restore.add_argument("--apply", action="store_true", help="Perform the planned local mutation")

    args = parser.parse_args(argv)
    try:
        if args.command == "build-release":
            result = build_release(args.web2, args.autolab, args.output, args.release_id)
        elif args.command == "prepare-release":
            result = prepare_release(args.web2_source, args.autolab_source, args.output,
                                     args.release_id, args.source_date_epoch, args.node,
                                     args.yarn, args.python, args.migration_check)
        elif args.command == "verify":
            result = verify_artifact(args.artifact, args.kind)
        elif args.command == "deploy-local":
            result = (deploy_release(args.artifact, args.target, args.create_target) if args.apply
                      else deployment_plan(args.artifact, args.target, args.create_target))
        elif args.command == "rollback-local":
            result = rollback_release(args.target, args.to) if args.apply else rollback_plan(args.target, args.to)
        elif args.command == "drift":
            result = drift_report(args.target, args.prefix)
        elif args.command == "config-baseline":
            result = build_config_baseline(args.source, args.output, args.baseline_id)
        elif args.command == "config-drift":
            result = config_drift(args.baseline, args.current)
        elif args.command == "build-backup":
            result = build_backup(args.source, args.output, args.backup_id)
        else:
            result = (restore_backup(args.artifact, args.target, args.create_target) if args.apply
                      else restore_plan(args.artifact, args.target, args.create_target))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if args.command not in ("drift", "config-drift") or result["clean"] else 2
    except ReleaseError as error:
        print("error: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
