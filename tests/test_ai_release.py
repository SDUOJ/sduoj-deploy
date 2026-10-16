import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
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


def commit_source(root: Path) -> str:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments], env=environment, text=True).strip()
    git("init", "--quiet")
    git("add", ".")
    git("-c", "user.name=Release test", "-c", "user.email=release-test@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
    return git("rev-parse", "HEAD")


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
        ".gitignore": "node_modules/\nbuild/\n",
        "package.json": '{"packageManager":"yarn@1.22.22"}',
        "yarn.lock": "lock\n",
        "src/index.tsx": "export {};\n",
        "public/index.html": "<div id=root></div>\n",
        "node_modules/pkg/index.js": "module.exports = 1;\n",
        "scripts/release-artifact.cjs": "// orchestration-only fixture\n",
    })
    commit_source(web)
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


def real_web_source(tmp_path: Path):
    node = Path(os.environ.get("SDUOJ_RELEASE_TEST_NODE") or shutil.which("node") or "")
    yarn = Path(shutil.which("yarn") or "")
    if not node.is_file() or not yarn.is_file():
        pytest.skip("Real release identity regression requires Node 24 and Yarn 1.22.22")
    if subprocess.check_output([str(node), "-p", "process.versions.node"], text=True).split(".")[0] != "24":
        pytest.skip("Real release identity regression requires Node 24")
    artifact_script = SCRIPT.parents[2] / "sduoj-web2/scripts/release-artifact.cjs"
    assert artifact_script.is_file(), "Web2 checkout with the artifact creator is required"
    package = {
        "version": "1.0.0", "packageManager": "yarn@1.22.22", "private": True,
        "scripts": {"typecheck": "node check.cjs", "lint": "node check.cjs", "test:unit": "node check.cjs",
                    "build": "node fixture-build.cjs && node scripts/release-artifact.cjs create build"},
    }
    web = tree(tmp_path / "real-web", {
        ".gitignore": "node_modules/\nbuild/\n.env.local\n",
        "package.json": json.dumps(package), "yarn.lock": "# yarn lockfile v1\n",
        "src/index.tsx": "committed source", "public/index.html": "source template",
        "scripts/release-artifact.cjs": artifact_script.read_text(),
        "node_modules/offline-dependencies.txt": "No external dependencies are required by this fixture.",
        "check.cjs": "process.exit(0);\n",
        "fixture-build.cjs": r'''
const fs = require('node:fs');
const crypto = require('node:crypto');
const content = 'window.Vditor={};';
const checksum = crypto.createHash('sha256').update(content).digest('hex');
const revision = crypto.createHash('sha256').update(`index.min.js\0${checksum}\n`).digest('hex');
const directory = `build/vditor/${revision}/dist`;
fs.mkdirSync(directory, { recursive: true });
fs.mkdirSync('build/static/js', { recursive: true });
fs.writeFileSync(`${directory}/index.min.js`, content);
const entries = ['static/js/runtime-main.123abc.js', 'static/js/main.456def.js'];
for (const entry of entries) fs.writeFileSync(`build/${entry}`, fs.readFileSync('src/index.tsx'));
const deployment = { environment: 'production', apiOrigin: 'https://oj.qd.sdu.edu.cn', frontOrigin: 'https://oj.qd.sdu.edu.cn', socketOrigin: 'wss://oj.qd.sdu.edu.cn' };
fs.writeFileSync('build/index.html', `<meta name="sduoj-environment" content="${encodeURIComponent(JSON.stringify(deployment))}"><div id="root"></div>${entries.map(entry => `<script src="/v2/${entry}"></script>`).join('')}`);
fs.writeFileSync('build/asset-manifest.json', JSON.stringify({ files: Object.fromEntries(entries.map(entry => [entry, '/v2/' + entry])), entrypoints: entries }));
fs.writeFileSync('build/manifest.json', JSON.stringify({ start_url: '/v2/home' }));
''',
    })
    ref = commit_source(web)
    tree(web, {".env.local": "IGNORED_LOCAL_SECRET=not-a-build-input\n"})
    autolab = tree(tmp_path / "real-autolab", {
        "main.py": "app = 1\n", "requirements.txt": "fastapi\n", "auto_task/migrate.py": "",
        "auto_task/worker.py": "", "scripts/export_ai_contracts.py": "", "docs/sql/20260905_auto_task_ai.sql": "-- fixture\n",
    })
    python = tmp_path / "fixture-python"
    python.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then echo 'Python fixture'; else exit 0; fi\n")
    python.chmod(0o700)
    return web, autolab, node, yarn, python, ref


def test_prepare_release_executes_real_git_creator_and_verifier_and_reproduces_bytes(tmp_path, monkeypatch):
    web, autolab, node, yarn, python, ref = real_web_source(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "f" * 40)  # The outer deploy workflow has a different repository SHA.
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "unrelated"))
    first, second = tmp_path / "real-one.tar.gz", tmp_path / "real-two.tar.gz"
    manifest = release.prepare_release(web, autolab, first, "identity", 1_788_534_000, node, yarn, python)
    release.prepare_release(web, autolab, second, "identity", 1_788_534_000, node, yarn, python)
    assert first.read_bytes() == second.read_bytes()
    assert manifest["preflight"]["source_git_sha"]["web2"] == ref
    assert "web2-artifact-verification" in [check["name"] for check in manifest["preflight"]["checks"]]
    with tarfile.open(first) as archive:
        web_manifest = json.load(archive.extractfile("web2/release-manifest.json"))
        assert web_manifest["sourceRef"] == ref
        assert web_manifest["releaseId"] == "identity"
        assert web_manifest["createdAt"] == "2026-09-04T15:00:00.000Z"
        assert not any(".git/" in member.name or ".env.local" in member.name for member in archive.getmembers())
    assert not (web / "build").exists()


@pytest.mark.parametrize("dirty", ["tracked", "untracked", "hidden-by-index"])
def test_prepare_release_rejects_source_changes_before_packaging(tmp_path, monkeypatch, dirty):
    web, autolab, node, yarn, python, _ = real_web_source(tmp_path)
    if dirty == "hidden-by-index":
        subprocess.check_call(["git", "-C", str(web), "update-index", "--assume-unchanged", "src/index.tsx"])
    if dirty == "untracked":
        tree(web, {"src/extra.ts": "uncommitted"})
    else:
        (web / "src/index.tsx").write_text("uncommitted")
    output = tmp_path / "dirty.tar.gz"
    with pytest.raises(release.ReleaseError, match="clean|does not match"):
        release.prepare_release(web, autolab, output, "dirty", 1_788_534_000, node, yarn, python)
    assert not output.exists()


def test_prepare_release_rejects_a_real_creator_with_wrong_artifact_identity(tmp_path):
    web, autolab, node, yarn, python, _ = real_web_source(tmp_path)
    package = json.loads((web / "package.json").read_text())
    package["scripts"]["build"] += " && node -e \"const fs=require('fs');const p='build/release-manifest.json';const m=JSON.parse(fs.readFileSync(p));m.sourceRef='a'.repeat(40);fs.writeFileSync(p,JSON.stringify(m));\""
    (web / "package.json").write_text(json.dumps(package))
    commit_source(web)
    output = tmp_path / "wrong.tar.gz"
    with pytest.raises(release.ReleaseError, match="source ref mismatch"):
        release.prepare_release(web, autolab, output, "wrong", 1_788_534_000, node, yarn, python)
    assert not output.exists()


def test_prepare_release_rejects_source_changes_during_the_isolated_build(tmp_path, monkeypatch):
    web, autolab, node, yarn, python, _ = real_web_source(tmp_path)
    with (web / "fixture-build.cjs").open("a") as stream:
        stream.write("\nfs.writeFileSync(process.env.RELEASE_TEST_SOURCE, 'changed during build');\n")
    commit_source(web)
    monkeypatch.setenv("RELEASE_TEST_SOURCE", str(web / "src/index.tsx"))
    output = tmp_path / "changed.tar.gz"
    with pytest.raises(release.ReleaseError, match="clean|inputs changed"):
        release.prepare_release(web, autolab, output, "changed", 1_788_534_000, node, yarn, python)
    assert not output.exists()


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
