#!/usr/bin/env bash
# Uploaded with the reviewed artifact verifier; only fixed v2 paths are writable.
set -Eeuo pipefail
IFS=$'\n\t'

fail() { echo "release-v2: $*" >&2; exit 1; }
valid_root() {
  [[ "$1" =~ ^/[A-Za-z0-9_./-]+$ && "$1" != / && "$1" != */ && "$1" != *'//'* ]] || fail 'invalid root'
  [[ "/${1#/}/" != *'/../'* && "/${1#/}/" != *'/./'* ]] || fail 'noncanonical root'
  [[ -d "$1" && ! -L "$1" && "$(cd -- "$1" && pwd -P)" == "$1" ]] || fail 'root must be a real canonical directory'
}
valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] || fail 'invalid release id'; }
valid_ref() { [[ "$1" =~ ^[a-f0-9]{40}$ ]] || fail 'full source ref required'; }
valid_sha() { [[ "$1" =~ ^[a-f0-9]{64}$ ]] || fail 'full SHA256 required'; }
manifest_sha() { node -e 'const f=require("fs"),c=require("crypto");console.log(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$1/release-manifest.json"; }
check_file_sha() {
  [[ -f "$1" && ! -L "$1" ]] || fail 'missing regular helper'
  [[ "$(node -e 'const f=require("fs"),c=require("crypto");console.log(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$1")" == "$2" ]] || fail 'helper SHA mismatch'
}
verify_tree() {
  [[ -d "$1" && ! -L "$1" ]] || fail 'artifact must be a real directory'
  [[ "$(manifest_sha "$1")" == "$3" ]] || fail 'manifest SHA mismatch'
  node "$validator" verify "$1" "$2" /v2/ "$url" > /dev/null
}
sync_tree() { rsync -rlptDc --timeout=60 --delete --no-owner --no-group "$1/" "$2/"; }

operation=${1:?operation required}; root=${2:?root required}; release_id=${3:?release id required}
valid_root "$root"; valid_id "$release_id"
meta="$root/.v2-release-meta-$release_id"; validator="$meta/release-artifact.cjs"
[[ -d "$meta" && ! -L "$meta" ]] || fail 'missing owned release metadata'
current="$root/v2"; backup="$root/v2-backup"; lock="$root/.v2-release-lock"
[[ -d "$current" && ! -L "$current" && -d "$backup" && ! -L "$backup" ]] || fail 'existing v2 and backup directories required'

if [[ "$operation" == apply ]]; then
  candidate_ref=${4:?}; candidate_sha=${5:?}; old_ref=${6:?}; old_sha=${7:?}; url=${8:?}; validator_sha=${9:?}; seconds=${10:?}
  valid_ref "$candidate_ref"; valid_sha "$candidate_sha"; valid_ref "$old_ref"; valid_sha "$old_sha"; valid_sha "$validator_sha"
  [[ "$seconds" =~ ^[1-9][0-9]{0,3}$ && "$seconds" -le 3600 ]] || fail 'invalid timeout'
  check_file_sha "$validator" "$validator_sha"
  stage="$root/.v2-release-$release_id"; backup_new="$root/.v2-backup-new-$release_id"; backup_old="$root/.v2-backup-old-$release_id"
  [[ ! -e "$backup_new" && ! -L "$backup_new" && ! -e "$backup_old" && ! -L "$backup_old" ]] || fail 'retained backup paths exist; use a new release id'
  mkdir "$lock" || fail 'another release/rollback holds the v2 lock; inspect it, never remove an unknown lock'
  applying=0
  restore_current() {
    verify_tree "$backup" "$old_ref" "$old_sha" && sync_tree "$backup" "$current" && verify_tree "$current" "$old_ref" "$old_sha"
  }
  finish() {
    rc=$?; trap - EXIT INT TERM
    if [[ "$applying" == 1 ]]; then
      if restore_current; then
        echo 'apply interrupted or failed; v2 restored; all recovery evidence retained' >&2
      else
        echo 'apply and automatic recovery failed; backup, older backup and stage retained for independent rollback' >&2
      fi
    fi
    rmdir "$lock" || echo 'could not release v2 lock; inspect before further writes' >&2
    exit "$rc"
  }
  trap finish EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # Recheck under the lock: a different release may have completed after HTTP preflight.
  verify_tree "$current" "$old_ref" "$old_sha"
  verify_tree "$stage" "$candidate_ref" "$candidate_sha"
  sync_tree "$current" "$backup_new"
  verify_tree "$backup_new" "$old_ref" "$old_sha"
  mv "$backup" "$backup_old"
  if ! mv "$backup_new" "$backup"; then
    mv "$backup_old" "$backup" || echo 'backup rotation failed; older copy retained for manual recovery' >&2
    exit 1
  fi
  transaction_sha=$(node -e 'const f=require("fs"),c=require("crypto");console.log(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$meta/remote-v2-transaction.sh")
  rollback_new="$root/.rollback-v2-$release_id.sh"
  [[ ! -e "$rollback_new" && ! -L "$rollback_new" ]] || fail 'retained rollback installer exists'
  {
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
    printf 'node -e '\''const f=require("fs"),c=require("crypto");if(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex")!==process.argv[2])process.exit(1)'\'' %q %q\n' "$meta/remote-v2-transaction.sh" "$transaction_sha"
    # Keep the optional current-manifest argument literal in the installed script.
    # shellcheck disable=SC2016
    printf 'exec timeout %q bash %q rollback %q %q %q %q %q %q "${1:-}" "${2:-}"\n' "$seconds" "$meta/remote-v2-transaction.sh" "$root" "$release_id" "$old_ref" "$old_sha" "$url" "$validator_sha"
  } > "$rollback_new"
  chmod 0755 "$rollback_new"
  [[ ! -L "$root/rollback-v2.sh" ]] || fail 'rollback entrypoint must not be a symlink'
  mv "$rollback_new" "$root/rollback-v2.sh"
  applying=1
  sync_tree "$stage" "$current"
  verify_tree "$current" "$candidate_ref" "$candidate_sha"
  applying=0
  echo 'v2 filesystem apply verified; stage and previous backups retained for audit'
elif [[ "$operation" == rollback ]]; then
  old_ref=${4:?}; old_sha=${5:?}; url=${6:?}; validator_sha=${7:?}; expected_current=${8:-}; expected_backup=${9:-}
  valid_ref "$old_ref"; valid_sha "$old_sha"; valid_sha "$validator_sha"
  [[ -z "$expected_current" ]] || valid_sha "$expected_current"
  check_file_sha "$validator" "$validator_sha"
  mkdir "$lock" || fail 'another release/rollback holds the v2 lock; inspect it first'
  trap 'rmdir "$lock"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if [[ -n "$expected_backup" ]]; then
    valid_sha "$expected_backup"
    [[ "$old_sha" == "$expected_backup" ]] || fail 'rollback entrypoint changed; expected backup SHA mismatch'
  fi
  verify_tree "$backup" "$old_ref" "$old_sha"
  if [[ -n "$expected_current" ]]; then
    [[ "$(manifest_sha "$current")" == "$expected_current" ]] || fail 'current changed after deployment; refuse automatic rollback over another release'
  fi
  sync_tree "$backup" "$current"
  verify_tree "$current" "$old_ref" "$old_sha"
  echo 'v2 rollback verified; backup retained'
else
  fail 'unknown transaction'
fi
