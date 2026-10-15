import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai_release.py"
SPEC = importlib.util.spec_from_file_location("ai_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(release)


def tree(root: Path, files: dict):
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def artifact(tmp_path: Path, release_id: str, web_content: str = "web") -> Path:
    web = tree(tmp_path / ("web-" + release_id), {"index.html": web_content, "assets/app.js": "js"})
    autolab = tree(tmp_path / ("autolab-" + release_id), {"main.py": "app = 1\n", "requirements.txt": "fastapi\n"})
    output = tmp_path / (release_id + ".tar.gz")
    release.build_release(web, autolab, output, release_id)
    return output


def rewrite_member(source: Path, target: Path, member_name: str, replacement: bytes):
    with tarfile.open(source, "r:gz") as archive:
        rows = [(item, archive.extractfile(item).read()) for item in archive.getmembers()]
    with target.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for old, data in rows:
                    info = tarfile.TarInfo(old.name)
                    content = replacement if old.name == member_name else data
                    info.size, info.mode, info.mtime = len(content), old.mode, 0
                    archive.addfile(info, io.BytesIO(content))


def test_release_manifest_hashes_files_and_excludes_secrets_build_state_and_links(tmp_path):
    web = tree(tmp_path / "web", {
        "index.html": "web", "node_modules/pkg/index.js": "dependency", ".env": "TOKEN=secret",
        "data/session.json": "secret", ".env.example": "TOKEN=example",
    })
    autolab = tree(tmp_path / "autolab", {"main.py": "app = 1", "logs/app.log": "log"})
    tree(autolab, {".coverage": "local", "htmlcov/index.html": "local report"})
    os.symlink(web / "index.html", web / "linked.html")
    output = tmp_path / "release.tar.gz"
    manifest = release.build_release(web, autolab, output, "r1")
    names = {item["path"] for item in manifest["files"]}
    assert names == {"web2/index.html", "web2/.env.example", "autolab/main.py"}
    assert "node_modules/" in manifest["excluded"]["web2"]
    assert release.verify_artifact(output, "release")["release_id"] == "r1"
    assert output.with_name(output.name + ".sha256").is_file()


def test_release_excludes_local_development_configuration_and_test_fixtures(tmp_path):
    web = tree(tmp_path / "web", {"index.html": "web"})
    autolab = tree(tmp_path / "autolab", {
        "main.py": "app = 1\n",
        "dev_config.py": "PASSWORD = 'local-only'\n",
        "prepare_dev.py": "print('local setup')\n",
        "tests/credentials.json": "fixture-secret\n",
        ".github/workflows/check.yml": "name: check\n",
        "runtime/module.py": "VALUE = 1\n",
    })
    output = tmp_path / "release.tar.gz"
    manifest = release.build_release(web, autolab, output, "r1")
    names = {item["path"] for item in manifest["files"]}
    assert names == {"web2/index.html", "autolab/main.py", "autolab/runtime/module.py"}
    assert "dev_config.py" in manifest["excluded"]["autolab"]
    assert "tests/" in manifest["excluded"]["autolab"]


def test_private_key_content_is_rejected_even_with_an_innocent_name(tmp_path):
    web = tree(tmp_path / "web", {"index.html": "-----BEGIN PRIVATE KEY-----\nsecret"})
    autolab = tree(tmp_path / "autolab", {"main.py": "app = 1"})
    with pytest.raises(release.ReleaseError, match="Private key"):
        release.build_release(web, autolab, tmp_path / "release.tar.gz", "r1")


def test_tampered_and_traversal_archives_are_rejected(tmp_path):
    source = artifact(tmp_path, "r1")
    tampered = tmp_path / "tampered.tar.gz"
    rewrite_member(source, tampered, "web2/index.html", b"changed")
    release._write_sidecar(tampered)
    with pytest.raises(release.ReleaseError, match="integrity mismatch"):
        release.verify_artifact(tampered)

    malicious = tmp_path / "traversal.tar.gz"
    with tarfile.open(malicious, "w:gz") as archive:
        info = tarfile.TarInfo("../outside")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    release._write_sidecar(malicious)
    with pytest.raises(release.ReleaseError, match="Unsafe archive path"):
        release.verify_artifact(malicious)


def test_local_deploy_switch_drift_and_verified_rollback(tmp_path):
    first = artifact(tmp_path, "r1", "one")
    second = artifact(tmp_path, "r2", "two")
    target = (tmp_path / "install").resolve()
    result = release.deploy_release(first, target, create_target=True)
    assert result == {"current": "r1", "previous": None, "replay": False}
    assert json.loads((target / release.ROOT_MARKER).read_text())["purpose"] == "sduoj-ai-release-root"
    assert (target / "current/web2/index.html").read_text() == "one"

    result = release.deploy_release(second, target)
    assert result == {"current": "r2", "previous": "r1", "replay": False}
    assert os.readlink(target / "current") == "releases/r2"
    state_before = (target / release.STATE).read_bytes()
    assert release.drift_report(target)["clean"]
    assert (target / release.STATE).read_bytes() == state_before

    (target / "releases/r2/web2/index.html").write_text("tampered", encoding="utf-8")
    drift = release.drift_report(target, ["web2"])
    assert not drift["clean"] and drift["changed"] == ["web2/index.html"]

    rollback = release.rollback_release(target)
    assert rollback == {"current": "r1", "previous": "r2"}
    assert (target / "current/web2/index.html").read_text() == "one"


def test_rollback_rejects_a_tampered_release_without_switching(tmp_path):
    first = artifact(tmp_path, "r1", "one")
    second = artifact(tmp_path, "r2", "two")
    target = (tmp_path / "install").resolve()
    release.deploy_release(first, target, create_target=True)
    release.deploy_release(second, target)
    (target / "releases/r1/autolab/main.py").write_text("tampered", encoding="utf-8")
    with pytest.raises(release.ReleaseError, match="integrity"):
        release.rollback_release(target)
    assert os.readlink(target / "current") == "releases/r2"

    manifest = target / "releases/r2" / release.RELEASE_MANIFEST
    value = json.loads(manifest.read_text())
    value["release_id"] = "forged"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(release.ReleaseError, match="manifest integrity"):
        release.rollback_release(target, "r2")


def test_backup_verification_and_restore_only_to_empty_explicit_target(tmp_path):
    source = tree(tmp_path / "persistent", {"uploads/one.txt": "one", "db/snapshot.sql": "CREATE TABLE t();"})
    backup = tmp_path / "backup.tar.gz"
    manifest = release.build_backup(source, backup, "b1")
    assert release.verify_artifact(backup, "backup") == manifest

    target = (tmp_path / "restore").resolve()
    restored = release.restore_backup(backup, target, create_target=True)
    assert restored["files"] == 2
    assert (target / "payload/uploads/one.txt").read_text() == "one"
    assert release.compare_tree(
        target,
        {item["path"]: item for item in manifest["files"]},
        ignored={release.BACKUP_MANIFEST},
    )["clean"]
    with pytest.raises(release.ReleaseError, match="empty"):
        release.restore_backup(backup, target)

    linked_source = tree(tmp_path / "linked-source", {"file": "value"})
    os.symlink(linked_source / "file", linked_source / "link")
    with pytest.raises(release.ReleaseError, match="symbolic link"):
        release.build_backup(linked_source, tmp_path / "linked.tar.gz", "b2")


def test_targets_must_be_absolute_and_owned_directory_may_not_be_a_symlink(tmp_path):
    built = artifact(tmp_path, "r1")
    with pytest.raises(release.ReleaseError, match="absolute"):
        release.deploy_release(built, Path("relative"), create_target=True)
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    link = (tmp_path / "link").resolve()
    os.symlink(outside, link)
    with pytest.raises(release.ReleaseError, match="symlink"):
        release.deploy_release(built, link)
    nonempty = (tmp_path / "nonempty").resolve()
    tree(nonempty, {"unrelated": "keep"})
    with pytest.raises(release.ReleaseError, match="must be empty"):
        release.deploy_release(built, nonempty)
    assert (nonempty / "unrelated").read_text() == "keep"


def test_archive_sidecar_detects_whole_file_tampering(tmp_path):
    built = artifact(tmp_path, "r1")
    with built.open("ab") as stream:
        stream.write(b"trailing")
    with pytest.raises(release.ReleaseError, match="sidecar"):
        release.verify_artifact(built)

    clean = artifact(tmp_path, "r2")
    clean.with_name(clean.name + ".sha256").unlink()
    with pytest.raises(release.ReleaseError, match="missing"):
        release.verify_artifact(clean)


def test_configuration_drift_uses_a_read_only_local_baseline(tmp_path):
    current = tree(tmp_path / "exported-config", {
        "nginx/site.conf": "location /api {}\n",
        "nacos/problem-service.json": '{"port":8080}\n',
        ".env": "TOKEN=not-recorded",
    })
    baseline_path = tmp_path / "config-baseline.json"
    baseline = release.build_config_baseline(current, baseline_path, "config-r1")
    assert {item["path"] for item in baseline["files"]} == {
        "nginx/site.conf", "nacos/problem-service.json"
    }
    before = {path: path.stat().st_mtime_ns for path in current.rglob("*")}
    first = release.config_drift(baseline_path, current)
    after = {path: path.stat().st_mtime_ns for path in current.rglob("*")}
    assert not first["clean"] and first["added"] == [".env"]
    assert before == after
    (current / ".env").unlink()
    (current / "nginx/site.conf").write_text("location /api { deny all; }\n")
    drift = release.config_drift(baseline_path, current)
    assert not drift["clean"] and drift["changed"] == ["nginx/site.conf"]
    baseline_path.write_text("{}", encoding="utf-8")
    with pytest.raises(release.ReleaseError, match="sidecar"):
        release.config_drift(baseline_path, current)


def test_cli_deploy_rollback_and_restore_are_dry_run_without_apply(tmp_path, capsys):
    first = artifact(tmp_path, "r1", "one")
    second = artifact(tmp_path, "r2", "two")
    target = (tmp_path / "dry-run-install").resolve()
    assert release.main(["deploy-local", str(first), "--target", str(target), "--create-target"]) == 0
    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert release.main(["deploy-local", str(first), "--target", str(target), "--create-target", "--apply"]) == 0
    capsys.readouterr()
    assert release.main(["deploy-local", str(second), "--target", str(target), "--apply"]) == 0
    capsys.readouterr()
    assert os.readlink(target / "current") == "releases/r2"
    assert release.main(["rollback-local", "--target", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert os.readlink(target / "current") == "releases/r2"
    assert release.main(["rollback-local", "--target", str(target), "--apply"]) == 0
    capsys.readouterr()
    assert os.readlink(target / "current") == "releases/r1"

    backup_source = tree(tmp_path / "dry-source", {"db.sql": "select 1;"})
    backup = tmp_path / "dry-backup.tar.gz"
    release.build_backup(backup_source, backup, "b1")
    restore_target = (tmp_path / "dry-restore").resolve()
    assert release.main(["restore-backup", str(backup), "--target", str(restore_target), "--create-target"]) == 0
    assert not restore_target.exists()


def test_prepare_release_runs_locked_preflight_and_is_reproducible(tmp_path):
    web = tree(tmp_path / "web-source", {
        "package.json": '{"packageManager":"yarn@1.22.22"}',
        "yarn.lock": "lock\n",
        "src/index.tsx": "export {};\n",
        "public/index.html": "<div id=root></div>\n",
        "node_modules/pkg/index.js": "module.exports = 1;\n",
    })
    autolab = tree(tmp_path / "autolab-source", {
        "main.py": "app = 1\n",
        "requirements.txt": "fastapi\n",
        "auto_task/migrate.py": "print('migration plan')\n",
        "auto_task/worker.py": "print('worker')\n",
        "scripts/export_ai_contracts.py": "print('contracts ok')\n",
        "docs/sql/20260905_auto_task_ai.sql": "-- ddl\n",
    })
    tools = tmp_path / "tools"
    tools.mkdir()
    node = tools / "node"
    node.write_text("#!/bin/sh\necho 24.19.0\n", encoding="utf-8")
    yarn = tools / "yarn"
    yarn.write_text(
        "#!/bin/sh\n"
        "if echo \"$*\" | grep -q -- --version; then echo 1.22.22; exit 0; fi\n"
        "if echo \"$*\" | grep -q 'run build'; then mkdir -p build/static; echo web > build/index.html; echo js > build/static/app.js; fi\n"
        "echo check-ok\n",
        encoding="utf-8",
    )
    python = tools / "python"
    python.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then echo 'Python 3.9.23'; else echo check-ok; fi\n", encoding="utf-8")
    for executable in (node, yarn, python):
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    first = tmp_path / "prepared-one.tar.gz"
    second = tmp_path / "prepared-two.tar.gz"
    arguments = (web, autolab, "release-1", 1_788_534_000, node, yarn, python)
    manifest = release.prepare_release(arguments[0], arguments[1], first, *arguments[2:], migration_check=True)
    release.prepare_release(arguments[0], arguments[1], second, *arguments[2:], migration_check=True)
    assert first.read_bytes() == second.read_bytes()
    assert manifest["created_utc"] == release.utc_from_epoch(1_788_534_000)
    assert manifest["preflight"]["tools"] == {
        "node": "24.19.0", "yarn": "1.22.22", "python": "Python 3.9.23"
    }
    assert manifest["preflight"]["migration_check"] is True
    assert release.verify_artifact(first, "release")["preflight"] == manifest["preflight"]


def test_artifact_and_release_target_symlinks_are_rejected(tmp_path):
    built = artifact(tmp_path, "r1")
    linked_artifact = tmp_path / "linked-release.tar.gz"
    linked_artifact.symlink_to(built)
    with pytest.raises(release.ReleaseError, match="symbolic link"):
        release.verify_artifact(linked_artifact)
    target = (tmp_path / "marked").resolve()
    release.deploy_release(built, target, create_target=True)
    (target / release.ROOT_MARKER).unlink()
    with pytest.raises(release.ReleaseError, match="marker"):
        release.rollback_release(target)
