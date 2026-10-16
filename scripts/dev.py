#!/usr/bin/env python3
"""Local development lifecycle using the existing application image build chains."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/dev"
SERVICES = ["gateway", "user-service", "problem-service", "contest-service", "filesys-service", "websocket"]
MIDDLEWARE = ["mysql", "redis", "rabbit", "nacos", "autolab-mysql", "autolab-redis"]
HTTP = build_opener(ProxyHandler({}))
DOCKER_CONTEXT = "desktop-linux" if sys.platform == "darwin" else "default"


def read_env(path):
    result = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        words = shlex.split(value, comments=True)
        result[key.strip()] = " ".join(words)
    return result


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
        stream.write(content)
    path.chmod(0o600)


def initialize():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / "compose.env"
    if not path.exists():
        private_write(path, "".join(f"{key}={secrets.token_hex(24)}\n" for key in (
            "DEV_RPC_TOKEN", "DEV_AUTOLAB_ROOT_PASSWORD", "DEV_AUTOLAB_MYSQL_PASSWORD", "DEV_AUTOLAB_REDIS_PASSWORD")))
    env = read_env(path)
    private_write(STATE / "autolab.env", "\n".join([
        "SDUOJ_MODE=debug", "SDUOJ_TOKEN=" + env["DEV_RPC_TOKEN"],
        "AUTOLAB_MYSQL_PASSWORD=" + env["DEV_AUTOLAB_MYSQL_PASSWORD"],
        "AUTOLAB_REDIS_PASSWORD=" + env["DEV_AUTOLAB_REDIS_PASSWORD"], "",
    ]))
    return env


def prepare_local_storage():
    # A Linux-initialized MySQL data dictionary needs a case-sensitive filesystem.
    # The image is stored on the project's disk; never create an empty data directory
    # in place of an unmounted image.
    image = STATE / "docker/autolab-mysql.sparsebundle"
    if sys.platform != "darwin" or not image.exists():
        return
    mount = Path("/Volumes/SDUOJ-Dev-MySQL")
    if not mount.is_mount():
        subprocess.run(["hdiutil", "attach", "-nobrowse", str(image)], check=True,
                       stdout=subprocess.DEVNULL)
    if not mount.is_mount() or not (mount / "data/mysql").is_dir():
        raise RuntimeError("The SSD MySQL data image is not mounted at " + str(mount))


def compose_command(*args):
    prepare_local_storage()
    return ["docker", "--context", DOCKER_CONTEXT, "compose", "--progress", "plain", "--env-file", str(STATE / "compose.env"), "-f", str(ROOT / "compose.dev.yaml"), *args]


def compose(*args, **kwargs):
    return subprocess.run(compose_command(*args), check=True, **kwargs)


def nacos(path, data=None, method=None):
    body = urlencode(data).encode() if data is not None else None
    request = Request("http://127.0.0.1:8848/nacos/v1/" + path, data=body, method=method)
    with HTTP.open(request, timeout=30) as response:
        return response.read().decode()


def configure(env):
    spaces = json.loads(nacos("console/namespaces"))["data"]
    if not any(item["namespace"] == "dev" for item in spaces):
        nacos("console/namespaces", {"customNamespaceId": "dev", "namespaceName": "dev", "namespaceDesc": "Local Docker development"})
    substitutions = dict(env)
    for path in ("env/mysql/mysql.env", "env/rabbitmq/rabbitmq.env"):
        substitutions.update(read_env(ROOT / path))

    def expand(value):
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            return substitutions[value[2:-1]]
        return value

    for path in sorted((ROOT / "dev-config/nacos").glob("*.json")):
        data_id = path.stem + ".yml"
        params = {"dataId": data_id, "group": "DEFAULT_GROUP", "tenant": "dev"}
        backup = STATE / "original-nacos" / data_id
        if not backup.exists():
            try:
                private_write(backup, nacos("cs/configs?" + urlencode(params)))
            except HTTPError as exc:
                if exc.code != 404:
                    raise
        content = json.dumps(expand(json.loads(path.read_text())), ensure_ascii=False)
        if nacos("cs/configs", dict(params, content=content, type="json")) != "true":
            raise RuntimeError("Nacos rejected " + data_id)
        print("Configured dev/" + data_id, flush=True)


def mysql(service, sql=None, **kwargs):
    command = 'export MYSQL_PWD="$MYSQL_PASSWORD"; exec mysql -u "$MYSQL_USER" --default-character-set=utf8mb4 "$MYSQL_DATABASE"'
    return compose("exec", "-T", service, "sh", "-c", command,
                   input=sql.encode() if sql is not None else None, **kwargs)


def check():
    ports = dict(zip(SERVICES, (8080, 18081, 18082, 18083, 18084, 18085)))
    for service, port in ports.items():
        with HTTP.open(f"http://127.0.0.1:{port}/actuator/health", timeout=10) as response:
            if json.load(response).get("status") != "UP":
                raise RuntimeError(service + " is not healthy")
        print(service + ": healthy", flush=True)
    with HTTP.open("http://127.0.0.1:8080/api/site/getCopyright", timeout=15) as response:
        if json.load(response).get("code") != 0:
            raise RuntimeError("Gateway -> user service check failed")
    rabbit = read_env(ROOT / "env/rabbitmq/rabbitmq.env")
    credentials = (rabbit["RABBITMQ_DEFAULT_USER"] + ":" + rabbit["RABBITMQ_DEFAULT_PASS"]).encode()
    request = Request("http://127.0.0.1:15672/api/queues/%2Fsduoj/sduoj.judger.submission",
                      headers={"Authorization": "Basic " + base64.b64encode(credentials).decode()})
    for attempt in range(60):
        try:
            with HTTP.open(request, timeout=10) as response:
                if json.load(response).get("consumers", 0) > 0:
                    print("judger: connected to local submission queue", flush=True)
                    return
        except HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(2)
    raise RuntimeError("Judger did not start consuming the local submission queue")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down", "status", "check", "logs", "build", "configure", "middleware"])
    parser.add_argument("target", nargs="?")
    parser.add_argument("--no-build", action="store_true", help="Start cached images without contacting build registries")
    args = parser.parse_args()
    env = initialize()
    os.chdir(ROOT)
    if args.action in ("up", "middleware"):
        compose("up", "-d", "--wait", "--wait-timeout", "600", *MIDDLEWARE)
        configure(env)
        if args.action == "up":
            from run_migrate import migrate_run
            migrate_run()
            if not args.no_build:
                compose("build", "gateway", "judger", "run-worker")

            compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "600", *SERVICES)
            compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "judger")
            compose("up", "-d", "--no-build", "run-worker")
            check()
            print("Docker dev environment is ready. Start web2 and Autolab manually.")
    elif args.action == "down":
        compose("down")
    elif args.action == "status":
        compose("ps")
    elif args.action == "check":
        check()
    elif args.action == "logs":
        compose("logs", "--tail", "150", *([args.target] if args.target else []))
    elif args.action == "build":
        compose("build", "gateway", "judger", "run-worker")

    elif args.action == "configure":
        configure(env)



if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
