#!/usr/bin/env bash
# Promote a prebuilt, verified /v2/ artifact. No dependency install or build command exists here.
set -Eeuo pipefail
IFS=$'\n\t'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HELPERS="$SCRIPT_DIR/frontend-release"
COMMAND_TIMEOUT="${SDUOJ_RELEASE_COMMAND_TIMEOUT_SECONDS:-600}"

fail() { echo "release-v2-artifact: $*" >&2; exit 1; }
need() { command -v "$1" > /dev/null 2>&1 || fail "missing command: $1"; }
valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] || fail 'invalid explicit release id'; }
valid_ref() { [[ "$1" =~ ^[a-f0-9]{40}$ ]] || fail 'full 40-character source ref required'; }
valid_sha() { [[ "$1" =~ ^[a-f0-9]{64}$ ]] || fail 'full SHA256 required'; }
file_sha() { node -e 'const f=require("fs"),c=require("crypto");console.log(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$1"; }
local_requirements() {
  need node
  [[ "$(node -p 'process.versions.node.split(".")[0]')" == 24 ]] || fail 'Node 24 is required'
  [[ "$COMMAND_TIMEOUT" =~ ^[1-9][0-9]{0,3}$ && "$COMMAND_TIMEOUT" -le 3600 ]] || fail 'timeout must be 1..3600 seconds'
  url=${SDUOJ_RELEASE_URL:?Set explicit SDUOJ_RELEASE_URL=https://host/v2/}
  [[ "$url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/v2/$ ]] || fail 'target must be a shell-safe HTTPS host and /v2/ path'
  node -e 'const u=new URL(process.argv[1]);if(u.protocol!=="https:"||u.pathname!=="/v2/"||u.username||u.password||u.search||u.hash||u.origin+u.pathname!==process.argv[1])process.exit(1)' "$url" || fail 'canonical HTTPS /v2/ URL required'
}
artifact_inputs() {
  [[ "$#" == 3 ]] || fail 'expected artifact-directory full-source-ref release-id'
  artifact=$1; source_ref=$2; release_id=$3
  [[ "$artifact" == /* && -d "$artifact" && ! -L "$artifact" ]] || fail 'explicit absolute artifact directory required'
  valid_ref "$source_ref"; valid_id "$release_id"
  local_requirements
  node "$HELPERS/release-artifact.cjs" verify "$artifact" "$source_ref" /v2/ "$url"
  artifact_sha=$(file_sha "$artifact/release-manifest.json")
}
remote_inputs() {
  need ssh; need rsync
  host=${SDUOJ_DEPLOY_HOST:?Set explicit SDUOJ_DEPLOY_HOST}; user=${SDUOJ_DEPLOY_USER:?Set explicit SDUOJ_DEPLOY_USER}
  root=${SDUOJ_DEPLOY_ROOT:?Set explicit canonical SDUOJ_DEPLOY_ROOT}; port=${SDUOJ_DEPLOY_PORT:-22}
  [[ "$host" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ && "$user" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || fail 'invalid SSH host/user'
  [[ "$port" =~ ^[1-9][0-9]{0,4}$ && "$port" -le 65535 ]] || fail 'invalid SSH port'
  [[ "$root" =~ ^/[A-Za-z0-9_./-]+$ && "$root" != / && "$root" != */ && "$root" != *'//'* ]] || fail 'invalid explicit remote root'
  [[ "/${root#/}/" != *'/../'* && "/${root#/}/" != *'/./'* ]] || fail 'remote root must be canonical'
  remote="$user@$host"
  ssh_args=(-p "$port" -o BatchMode=yes -o ForwardAgent=no -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
  if [[ -n "${SDUOJ_DEPLOY_KEY:-}" ]]; then
    [[ "$SDUOJ_DEPLOY_KEY" == /* && -f "$SDUOJ_DEPLOY_KEY" && "$SDUOJ_DEPLOY_KEY" =~ ^/[A-Za-z0-9_./-]+$ ]] || fail 'key must be an existing absolute path without shell metacharacters'
    ssh_args+=(-i "$SDUOJ_DEPLOY_KEY")
  fi
  printf -v rsync_ssh '%q ' ssh "${ssh_args[@]}"
}
ssh_run() { node "$HELPERS/timed-command.cjs" "$COMMAND_TIMEOUT" ssh "${ssh_args[@]}" "$remote" "$@"; }
rsync_remote() { node "$HELPERS/timed-command.cjs" "$COMMAND_TIMEOUT" rsync -rlptDc --timeout=60 --delete --no-owner --no-group -e "$rsync_ssh" "$@"; }
remote_plan() {
  ssh_run timeout "$COMMAND_TIMEOUT" bash -s -- "$root" "${1:-deploy}" <<'REMOTE' || fail 'read-only remote prerequisites failed'
set -Eeuo pipefail
root=$1; mode=$2
[[ -d "$root" && ! -L "$root" && "$(cd -- "$root" && pwd -P)" == "$root" && -w "$root" ]] || exit 1
for directory in v2 v2-backup; do
  [[ -d "$root/$directory" && ! -L "$root/$directory" && -w "$root/$directory" ]] || exit 1
done
[[ ! -L "$root/rollback-v2.sh" ]] || exit 1
if [[ "$mode" == deploy ]]; then
  [[ -s "$root/v2/index.html" && -f "$root/v2/release-manifest.json" ]] || exit 1
else
  [[ -f "$root/rollback-v2.sh" && -s "$root/v2-backup/release-manifest.json" ]] || exit 1
fi
command -v node > /dev/null || exit 1
command -v rsync > /dev/null || exit 1
command -v timeout > /dev/null || exit 1
[[ "$(node -p 'process.versions.node.split(".")[0]')" == 24 ]] || exit 1
timeout --version | grep -q 'GNU coreutils' || exit 1
rsync --version > /dev/null || exit 1
[[ ! -e "$root/.v2-release-lock" && ! -L "$root/.v2-release-lock" ]] || exit 1
REMOTE
  echo 'read-only remote prerequisites verified; no directories created'
}
smoke() { node "$HELPERS/deployment-smoke.cjs" "$url" "$@"; }
evidence_directory() {
  evidence=${SDUOJ_RELEASE_EVIDENCE_DIR:?Set a new absolute SDUOJ_RELEASE_EVIDENCE_DIR}
  [[ "$evidence" == /* && ! -e "$evidence" && ! -L "$evidence" ]] || fail 'evidence directory must be a new absolute path'
  (umask 077; mkdir "$evidence")
}
deploy() {
  artifact_inputs "$@"; remote_inputs; remote_plan
  evidence_directory
  smoke > "$evidence/before.json" || fail 'known-good before smoke failed; remote releases untouched'
  old_sha=$(node -p 'require(process.argv[1]).manifestSha256' "$evidence/before.json"); valid_sha "$old_sha"
  old_ref=$(node -p 'require(process.argv[1]).sourceRef' "$evidence/before.json"); valid_ref "$old_ref"
  node "$HELPERS/release-artifact.cjs" verify "$artifact" "$source_ref" /v2/ "$url" > "$evidence/artifact.json"
  stage="$root/.v2-release-$release_id"; meta="$root/.v2-release-meta-$release_id"
  ssh_run timeout "$COMMAND_TIMEOUT" bash -s -- "$root" "$release_id" <<'REMOTE' || fail 'cannot create a new release staging directory'
set -Eeuo pipefail
root=$1; id=$2
for name in ".v2-release-$id" ".v2-release-meta-$id" ".v2-backup-new-$id" ".v2-backup-old-$id" ".rollback-v2-$id.sh"; do
  [[ ! -e "$root/$name" && ! -L "$root/$name" ]] || { echo 'release id already retained; use a new id' >&2; exit 1; }
done
mkdir -m 0755 "$root/.v2-release-$id" "$root/.v2-release-meta-$id"
REMOTE
  rsync_remote "$artifact/" "$remote:$stage/" > "$evidence/upload.log" 2>&1 || fail 'artifact staging failed; current/backup untouched; partial stage retained'
  for helper in release-artifact.cjs remote-v2-transaction.sh; do
    rsync_remote "$HELPERS/$helper" "$remote:$meta/$helper" >> "$evidence/upload.log" 2>&1 || fail 'helper staging failed; current/backup untouched; stage retained'
  done
  validator_sha=$(file_sha "$HELPERS/release-artifact.cjs")
  transaction_sha=$(file_sha "$HELPERS/remote-v2-transaction.sh")
  ssh_run timeout "$COMMAND_TIMEOUT" bash -s -- "$meta" "$transaction_sha" <<'REMOTE' || fail 'staged transaction helper SHA mismatch'
set -Eeuo pipefail
node -e 'const f=require("fs"),c=require("crypto");if(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex")!==process.argv[2])process.exit(1)' "$1/remote-v2-transaction.sh" "$2"
REMOTE
  if ! ssh_run timeout "$COMMAND_TIMEOUT" bash "$meta/remote-v2-transaction.sh" apply "$root" "$release_id" "$source_ref" "$artifact_sha" "$old_ref" "$old_sha" "$url" "$validator_sha" "$COMMAND_TIMEOUT" > "$evidence/apply.log" 2>&1; then
    fail 'remote apply failed; automatic recovery attempted where needed; stage and recovery copies retained'
  fi
  if ! smoke --expected-manifest "$artifact/release-manifest.json" > "$evidence/after.json"; then
    if ! ssh_run timeout "$COMMAND_TIMEOUT" bash "$root/rollback-v2.sh" "$artifact_sha" > "$evidence/rollback.log" 2>&1; then
      fail 'post-deploy smoke failed and rollback could not verify recovery; preserve all copies for manual recovery'
    fi
    smoke --expected-sha256 "$old_sha" > "$evidence/rollback.json" || fail 'post-rollback smoke failed; backup retained'
    fail 'post-deploy smoke failed; verified previous release restored'
  fi
  echo 'v2 artifact deploy verified; independent rollback-v2.sh and recovery copies retained'
}
rollback() {
  [[ "$#" == 2 ]] || fail 'rollback requires expected-backup-manifest-sha256 operation-id'
  expected_backup=$1; valid_sha "$expected_backup"; valid_id "$2"
  local_requirements; remote_inputs; remote_plan rollback; evidence_directory
  ssh_run timeout "$COMMAND_TIMEOUT" bash -s -- "$root" "$expected_backup" <<'REMOTE' > "$evidence/rollback.log" 2>&1 || fail 'rollback prerequisite or recovery failed; inspect retained evidence'
set -Eeuo pipefail
root=$1; expected=$2
[[ -f "$root/rollback-v2.sh" && ! -L "$root/rollback-v2.sh" ]] || exit 1
actual=$(node -e 'const f=require("fs"),c=require("crypto");console.log(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$root/v2-backup/release-manifest.json")
[[ "$actual" == "$expected" ]] || { echo 'backup manifest SHA mismatch; rollback refused' >&2; exit 1; }
bash "$root/rollback-v2.sh" "" "$expected"
REMOTE
  smoke --expected-sha256 "$expected_backup" > "$evidence/after.json"
  echo 'independent v2 rollback and HTTPS smoke verified'
}
usage() {
  cat <<'USAGE'
Usage (no command prints this help and performs no work):
  release-v2-artifact.sh verify ARTIFACT_DIRECTORY FULL_SOURCE_REF RELEASE_ID
  release-v2-artifact.sh plan   ARTIFACT_DIRECTORY FULL_SOURCE_REF RELEASE_ID
  release-v2-artifact.sh deploy ARTIFACT_DIRECTORY FULL_SOURCE_REF RELEASE_ID
  release-v2-artifact.sh rollback EXPECTED_BACKUP_MANIFEST_SHA256 OPERATION_ID

Required for verify: SDUOJ_RELEASE_URL (canonical HTTPS /v2/ target).
Required for plan/deploy/rollback: explicit SDUOJ_DEPLOY_HOST, SDUOJ_DEPLOY_USER,
  SDUOJ_DEPLOY_ROOT (physical canonical parent of existing v2 and v2-backup).
Required for writes: SDUOJ_RELEASE_EVIDENCE_DIR (new absolute local directory).
Optional: SDUOJ_DEPLOY_PORT=22, SDUOJ_DEPLOY_KEY, SDUOJ_RELEASE_COMMAND_TIMEOUT_SECONDS=600.
Node 24, rsync, strict SSH known-host verification; remote GNU timeout required.
Only explicit deploy/rollback write. No build, install, hosts or OpenResty changes.
USAGE
}
case "${1:-}" in
  verify) shift; artifact_inputs "$@" ;;
  plan) shift; artifact_inputs "$@"; remote_inputs; remote_plan ;;
  deploy) shift; deploy "$@" ;;
  rollback) shift; rollback "$@" ;;
  ''|help|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
