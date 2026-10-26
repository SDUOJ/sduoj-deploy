const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const https = require("node:https");
const { spawn, spawnSync } = require("node:child_process");
const script = path.resolve(__dirname, "../scripts/release-v2-artifact.sh");
const helpers = path.resolve(__dirname, "../scripts/frontend-release");
const { create } = require(path.join(helpers, "release-artifact.cjs"));
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const oldRef = "a".repeat(40),
  newRef = "b".repeat(40),
  olderRef = "c".repeat(40);
const realRsync = spawnSync("which", ["rsync"], {
  encoding: "utf8",
}).stdout.trim();
assert(realRsync, "Real rsync is required; these tests must not silently skip");
const reports = [];
process.on("exit", () => {
  if (process.env.RELEASE_V2_TEST_RECEIPTS)
    fs.writeFileSync(
      process.env.RELEASE_V2_TEST_RECEIPTS,
      JSON.stringify({ realRsync, tests: reports }, null, 2),
    );
});

function artifact(directory, ref, url, label) {
  fs.mkdirSync(directory, { recursive: true });
  const runtime = "static/js/runtime.abc.js",
    main = "static/js/main.abc.js";
  const vd = `/* vditor ${label} */`;
  const revision = hash(`index.min.js\0${hash(vd)}\n`);
  const deployment = {
    environment: "production",
    apiOrigin: new URL(url).origin,
    frontOrigin: new URL(url).origin,
    socketOrigin: new URL(url).origin.replace(/^https/, "wss"),
  };
  const files = {
    "index.html": `<html><head><meta name="sduoj-environment" content="${encodeURIComponent(JSON.stringify(deployment))}"></head><body><div id="root"></div><script src="/v2/${runtime}"></script><script src="/v2/${main}"></script>${label}</body></html>`,
    "asset-manifest.json": JSON.stringify({
      files: { runtime: `/v2/${runtime}`, main: `/v2/${main}` },
      entrypoints: [runtime, main],
    }),
    "manifest.json": JSON.stringify({ start_url: "/v2/home" }),
    [runtime]: `/* runtime ${label} */`,
    [main]: `/* main ${label} */`,
    [`vditor/${revision}/dist/index.min.js`]: vd,
  };
  for (const [name, content] of Object.entries(files)) {
    const destination = path.join(directory, name);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.writeFileSync(destination, content);
  }
  return create(directory, {
    sourceRef: ref,
    publicPath: "/v2/",
    releaseId: label,
    version: "test",
    createdAt: "2026-10-26T00:00:00.000Z",
    deployment,
  });
}
function inventory(root) {
  const result = {};
  function walk(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(file);
      else
        result[path.relative(root, file)] = entry.isSymbolicLink()
          ? `symlink:${fs.readlinkSync(file)}`
          : hash(fs.readFileSync(file));
    }
  }
  walk(root);
  return result;
}
async function fixture(context) {
  const directory = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "sduoj-v2-artifact-")),
  );
  const root = path.join(directory, "webroot"),
    candidate = path.join(directory, "artifact"),
    bin = path.join(directory, "bin");
  fs.mkdirSync(root);
  fs.mkdirSync(bin);
  const key = path.join(directory, "tls.key"),
    cert = path.join(directory, "tls.crt");
  const certificate = spawnSync(
    "openssl",
    [
      "req",
      "-x509",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-keyout",
      key,
      "-out",
      cert,
      "-days",
      "1",
      "-subj",
      "/CN=127.0.0.1",
      "-addext",
      "subjectAltName=IP:127.0.0.1",
    ],
    { encoding: "utf8" },
  );
  assert.equal(certificate.status, 0, certificate.stderr);
  let failAfterSmoke = false;
  const server = https.createServer(
    { key: fs.readFileSync(key), cert: fs.readFileSync(cert) },
    (request, response) => {
      const url = new URL(request.url, "https://127.0.0.1");
      const headers = {
        "content-security-policy": "default-src 'self'",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "permissions-policy": "camera=()",
        "strict-transport-security": "max-age=31536000",
        "cache-control": "no-store",
      };
      if (
        failAfterSmoke &&
        fs
          .readFileSync(path.join(root, "v2/release-manifest.json"), "utf8")
          .includes(newRef)
      )
        delete headers["strict-transport-security"];
      if (url.pathname === "/api/user/getProfile")
        return response
          .writeHead(401, { ...headers, "content-type": "application/json" })
          .end('{"code":401}');
      const name = decodeURIComponent(url.pathname).replace(/^\/v2\/?/, "");
      let file = path.resolve(root, "v2", name || "index.html");
      if (!file.startsWith(path.join(root, "v2") + path.sep))
        return response.writeHead(403, headers).end();
      if (!path.extname(file)) file = path.join(root, "v2/index.html");
      if (!fs.existsSync(file) || !fs.statSync(file).isFile())
        return response.writeHead(404, headers).end("missing");
      if (name.startsWith("static/") || name.startsWith("vditor/"))
        headers["cache-control"] = "public, max-age=31536000, immutable";
      const mime = {
        ".html": "text/html",
        ".json": "application/json",
        ".js": "application/javascript",
        ".css": "text/css",
      };
      response.writeHead(200, {
        ...headers,
        "content-type": mime[path.extname(file)] || "application/octet-stream",
      });
      fs.createReadStream(file).pipe(response);
    },
  );
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `https://127.0.0.1:${server.address().port}/v2/`;
  const current = artifact(path.join(root, "v2"), oldRef, url, "old");
  artifact(path.join(root, "v2-backup"), olderRef, url, "older");
  const release = artifact(candidate, newRef, url, "candidate");
  fs.mkdirSync(path.join(root, "v2-pre"));
  fs.writeFileSync(path.join(root, "v2-pre/index.html"), "pre-sentinel");
  fs.writeFileSync(path.join(root, "openresty.conf"), "server-config-sentinel");
  fs.writeFileSync(
    path.join(bin, "timeout"),
    `#!${process.execPath}\nif(process.argv[2]==='--version'){console.log('timeout (GNU coreutils) test shim');}else{require(${JSON.stringify(path.join(helpers, "timed-command.cjs"))}).run(process.argv[2],process.argv[3],process.argv.slice(4));}\n`,
    { mode: 0o755 },
  );
  fs.writeFileSync(
    path.join(bin, "ssh"),
    `#!${process.execPath}
const {spawnSync}=require('node:child_process');const fs=require('node:fs'),path=require('node:path');
const args=process.argv.slice(2),i=args.indexOf('fixture_user@fixture.invalid');if(i<0)process.exit(97);
const command=args.slice(i+1).join(' ');fs.appendFileSync(process.env.TEST_SSH_LOG,command+'\\n');
if(process.env.TEST_STAGED_DRIFT==='1'&&command.includes('remote-v2-transaction.sh apply'))fs.writeFileSync(path.join(process.env.TEST_REMOTE_ROOT,'.v2-release-case1/index.html'),'tampered stage');
if(process.env.TEST_CURRENT_DRIFT==='1'&&command.includes('remote-v2-transaction.sh apply'))fs.writeFileSync(path.join(process.env.TEST_REMOTE_ROOT,'v2/index.html'),'concurrent drift');
const r=spawnSync('bash',['-c',command],{stdio:'inherit',env:process.env});process.exit(r.status??1);
`,
    { mode: 0o755 },
  );
  fs.writeFileSync(
    path.join(bin, "rsync"),
    `#!${process.execPath}
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const args=process.argv.slice(2);if(args.includes('--version')){const r=spawnSync(${JSON.stringify(realRsync)},args,{stdio:'inherit'});process.exit(r.status??1);}const a=args.length-2,b=args.length-1;for(const i of [a,b])args[i]=args[i].replace(/^fixture_user@fixture.invalid:/,'');
const source=args[a],destination=args[b],mode=process.env.TEST_RSYNC_MODE;
let kind=source.includes('/artifact/')?'staging':destination.includes('/.v2-backup-new-')?'snapshot':source.includes('/.v2-release-case1/')?'apply':source.endsWith('/v2-backup/')?'restore':'other';
fs.appendFileSync(process.env.TEST_RSYNC_LOG,kind+'\\n');
const fail=mode===kind||(mode==='apply-and-restore'&&['apply','restore'].includes(kind))||(mode==='interrupt'&&kind==='apply');
if(fail){fs.mkdirSync(destination,{recursive:true});fs.writeFileSync(path.join(destination,'index.html'),'partial transfer');if(mode==='interrupt')process.kill(process.ppid,'SIGTERM');process.exit(23);}
const r=spawnSync(${JSON.stringify(realRsync)},args,{stdio:'inherit',env:process.env});process.exit(r.status??1);
`,
    { mode: 0o755 },
  );
  const environment = {
    ...process.env,
    PATH: `${bin}:${path.dirname(process.execPath)}:${process.env.PATH}`,
    NODE_EXTRA_CA_CERTS: cert,
    SDUOJ_RELEASE_URL: url,
    SDUOJ_DEPLOY_HOST: "fixture.invalid",
    SDUOJ_DEPLOY_USER: "fixture_user",
    SDUOJ_DEPLOY_ROOT: root,
    SDUOJ_RELEASE_EVIDENCE_DIR: path.join(directory, "evidence"),
    SDUOJ_RELEASE_COMMAND_TIMEOUT_SECONDS: "30",
    TEST_SSH_LOG: path.join(directory, "ssh.log"),
    TEST_RSYNC_LOG: path.join(directory, "rsync.log"),
    TEST_REMOTE_ROOT: root,
  };
  async function run(args, extra = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn("bash", [script, ...args], {
        env: { ...environment, ...extra },
      });
      let stdout = "",
        stderr = "";
      child.stdout.on("data", (data) => {
        stdout += data;
      });
      child.stderr.on("data", (data) => {
        stderr += data;
      });
      const timer = setTimeout(() => {
        child.kill("SIGTERM");
        reject(new Error("Bounded release test timed out"));
      }, 45000);
      child.once("error", reject);
      child.once("exit", (status, signal) => {
        clearTimeout(timer);
        resolve({ status, signal, stdout, stderr });
      });
    });
  }
  const ref = (name) =>
    JSON.parse(
      fs.readFileSync(path.join(root, name, "release-manifest.json"), "utf8"),
    ).sourceRef;
  const verifyCurrent = () => {
    const report = spawnSync(
      process.execPath,
      [
        path.join(helpers, "release-artifact.cjs"),
        "verify",
        path.join(root, "v2"),
        oldRef,
        "/v2/",
        url,
      ],
      { encoding: "utf8" },
    );
    assert.equal(report.status, 0, report.stdout + report.stderr);
  };
  context.after(async () => {
    assert.equal(
      fs.readFileSync(path.join(root, "v2-pre/index.html"), "utf8"),
      "pre-sentinel",
    );
    assert.equal(
      fs.readFileSync(path.join(root, "openresty.conf"), "utf8"),
      "server-config-sentinel",
    );
    reports.push({
      title: context.name,
      root,
      currentRef: ref("v2"),
      backupRef: ref("v2-backup"),
      preservedPreAndOpenResty: true,
      realRsyncInvocations: fs.existsSync(environment.TEST_RSYNC_LOG)
        ? fs.readFileSync(environment.TEST_RSYNC_LOG, "utf8").trim().split("\n")
        : [],
    });
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  });
  return {
    root,
    directory,
    candidate,
    url,
    current,
    release,
    run,
    ref,
    verifyCurrent,
    directRollback: (expectedBackup) =>
      spawnSync(
        "bash",
        [path.join(root, "rollback-v2.sh"), "", expectedBackup],
        { env: environment, encoding: "utf8" },
      ),
    failSmoke: () => {
      failAfterSmoke = true;
    },
    inventory: () => inventory(root),
    deploy: (extra = {}) => run(["deploy", candidate, newRef, "case1"], extra),
    rollback: (extra = {}) =>
      run(["rollback", current.manifestSha256, "rollback1"], {
        SDUOJ_RELEASE_EVIDENCE_DIR: path.join(directory, "rollback-evidence"),
        ...extra,
      }),
  };
}

test("default usage and local verify perform no SSH or filesystem writes", async (context) => {
  const f = await fixture(context),
    before = f.inventory();
  assert.equal((await f.run([])).status, 0);
  assert.equal(
    (await f.run(["verify", f.candidate, newRef, "case1"])).status,
    0,
  );
  assert.deepEqual(f.inventory(), before);
  assert.equal(fs.existsSync(path.join(f.directory, "ssh.log")), false);
});
test("read-only plan uses existing directories and creates no stage or evidence", async (context) => {
  const f = await fixture(context),
    before = f.inventory();
  const r = await f.run(["plan", f.candidate, newRef, "case1"]);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(f.inventory(), before);
  assert.equal(fs.existsSync(path.join(f.directory, "evidence")), false);
});
test("plan fails closed for missing backup and held lock without creating any directory", async (context) => {
  const f = await fixture(context),
    backup = path.join(f.root, "v2-backup"),
    retained = path.join(f.root, "retained-backup");
  fs.renameSync(backup, retained);
  try {
    const before = f.inventory();
    assert.notEqual(
      (await f.run(["plan", f.candidate, newRef, "case1"])).status,
      0,
    );
    assert.deepEqual(f.inventory(), before);
    assert.equal(fs.existsSync(path.join(f.directory, "evidence")), false);
  } finally {
    fs.renameSync(retained, backup);
  }
  fs.mkdirSync(path.join(f.root, ".v2-release-lock"));
  const before = f.inventory();
  assert.notEqual(
    (await f.run(["plan", f.candidate, newRef, "case1"])).status,
    0,
  );
  assert.deepEqual(f.inventory(), before);
});
test("missing explicit host, invalid ref and traversal release id stop before remote writes", async (context) => {
  const f = await fixture(context),
    before = f.inventory();
  assert.notEqual(
    (
      await f.run(["deploy", f.candidate, newRef, "case1"], {
        SDUOJ_DEPLOY_HOST: "",
      })
    ).status,
    0,
  );
  assert.notEqual(
    (await f.run(["deploy", f.candidate, "short", "case1"])).status,
    0,
  );
  assert.notEqual(
    (await f.run(["deploy", f.candidate, newRef, "../v2-pre"])).status,
    0,
  );
  assert.notEqual(
    (
      await f.run(["deploy", f.candidate, newRef, "case1"], {
        SDUOJ_RELEASE_URL: "https://host;command/v2/",
      })
    ).status,
    0,
  );
  assert.deepEqual(f.inventory(), before);
  assert.equal(fs.existsSync(path.join(f.directory, "ssh.log")), false);
});
test("real rsync apply verifies exact artifact and installs independent verified rollback", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy();
  assert.equal(r.status, 0, r.stderr);
  assert.equal(f.ref("v2"), newRef);
  assert.equal(f.ref("v2-backup"), oldRef);
  assert.equal(f.ref(".v2-backup-old-case1"), olderRef);
  assert.equal((await f.rollback()).status, 0);
  f.verifyCurrent();
});
test("staging sync failure leaves current and older backup untouched", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_RSYNC_MODE: "staging" });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /staging failed/);
  f.verifyCurrent();
  assert.equal(f.ref("v2-backup"), olderRef);
});
test("staged content drift is rejected before backup rotation or current writes", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_STAGED_DRIFT: "1" });
  assert.notEqual(r.status, 0);
  f.verifyCurrent();
  assert.equal(f.ref("v2-backup"), olderRef);
});
test("current changed after before-smoke cannot be overwritten by a stale deploy", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_CURRENT_DRIFT: "1" });
  assert.notEqual(r.status, 0);
  assert.equal(
    fs.readFileSync(path.join(f.root, "v2/index.html"), "utf8"),
    "concurrent drift",
  );
  assert.equal(f.ref("v2-backup"), olderRef);
});
test("failed snapshot preserves current and original backup and retains partial evidence", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_RSYNC_MODE: "snapshot" });
  assert.notEqual(r.status, 0);
  f.verifyCurrent();
  assert.equal(f.ref("v2-backup"), olderRef);
  assert.equal(fs.existsSync(path.join(f.root, ".v2-backup-new-case1")), true);
});
test("apply sync failure automatically restores the exact previous manifest and bytes", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_RSYNC_MODE: "apply" });
  assert.notEqual(r.status, 0);
  assert.match(
    fs.readFileSync(path.join(f.directory, "evidence/apply.log"), "utf8"),
    /v2 restored/,
  );
  f.verifyCurrent();
  assert.equal(f.ref("v2-backup"), oldRef);
  assert.equal(f.ref(".v2-backup-old-case1"), olderRef);
});
test("TERM during apply recovers and retains an independently usable rollback", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_RSYNC_MODE: "interrupt" });
  assert.notEqual(r.status, 0);
  f.verifyCurrent();
  assert.equal(f.ref("v2-backup"), oldRef);
  assert.equal((await f.rollback()).status, 0);
  f.verifyCurrent();
});
test("apply and recovery failures retain both snapshots and allow later independent rollback", async (context) => {
  const f = await fixture(context);
  const r = await f.deploy({ TEST_RSYNC_MODE: "apply-and-restore" });
  assert.notEqual(r.status, 0);
  assert.equal(f.ref("v2-backup"), oldRef);
  assert.equal(f.ref(".v2-backup-old-case1"), olderRef);
  assert.equal(f.ref(".v2-release-case1"), newRef);
  assert.equal((await f.rollback()).status, 0);
  f.verifyCurrent();
});
test("HTTPS post-smoke failure restores known-good bytes and still fails deployment", async (context) => {
  const f = await fixture(context);
  f.failSmoke();
  const r = await f.deploy();
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /verified previous release restored/);
  f.verifyCurrent();
  assert.equal(
    JSON.parse(
      fs.readFileSync(path.join(f.directory, "evidence/rollback.json")),
    ).manifestSha256,
    f.current.manifestSha256,
  );
});
test("wrong backup SHA and modified verifier block rollback writes", async (context) => {
  const f = await fixture(context);
  assert.equal((await f.deploy()).status, 0);
  const wrong = await f.run(["rollback", "d".repeat(64), "rollback1"], {
    SDUOJ_RELEASE_EVIDENCE_DIR: path.join(f.directory, "wrong-evidence"),
  });
  assert.notEqual(wrong.status, 0);
  assert.equal(f.ref("v2"), newRef);
  assert.match(
    fs.readFileSync(
      path.join(f.directory, "wrong-evidence/rollback.log"),
      "utf8",
    ),
    /SHA mismatch; rollback refused/,
  );
  fs.appendFileSync(
    path.join(f.root, ".v2-release-meta-case1/release-artifact.cjs"),
    "\n// drift",
  );
  assert.notEqual((await f.rollback()).status, 0);
  assert.equal(f.ref("v2"), newRef);
});
test("independent rollback checks the requested backup identity inside its lock", async (context) => {
  const f = await fixture(context);
  assert.equal((await f.deploy()).status, 0);
  const before = f.inventory(),
    result = f.directRollback("d".repeat(64));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /expected backup SHA mismatch/);
  assert.deepEqual(f.inventory(), before);
  assert.equal(f.ref("v2"), newRef);
});
test("release-id reuse, existing evidence and active lock retain all previous recovery copies", async (context) => {
  const f = await fixture(context);
  assert.equal((await f.deploy()).status, 0);
  const before = f.inventory();
  assert.notEqual((await f.deploy()).status, 0);
  assert.deepEqual(f.inventory(), before);
  const repeated = await f.deploy({
    SDUOJ_RELEASE_EVIDENCE_DIR: path.join(f.directory, "second-evidence"),
  });
  assert.notEqual(repeated.status, 0);
  assert.deepEqual(f.inventory(), before);
  fs.mkdirSync(path.join(f.root, ".v2-release-lock"));
  assert.notEqual((await f.rollback()).status, 0);
  assert.deepEqual(f.inventory(), before);
});
