#!/usr/bin/env python3
"""Builder-local receipts only. Official apt has already verified Release signatures and download hashes."""
from pathlib import Path
import hashlib
import json
import subprocess

out = Path('/output')
rows = []
for file in sorted((out / 'guest-debs').glob('*.deb')):
    fields = subprocess.check_output(['dpkg-deb', '-f', str(file), 'Package', 'Version', 'Architecture'], text=True)
    data = dict(x.split(': ', 1) for x in fields.splitlines())
    if data['Architecture'] not in ('arm64', 'all'):
        raise SystemExit('Wrong dependency architecture')
    rows.append({'name': data['Package'], 'version': data['Version'], 'architecture': data['Architecture'], 'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
required = json.loads(Path('/src/manager-build.lock.json').read_text())['dockerPackages']
versions = {r['name']: r['version'] for r in rows}
if any(versions.get(k) != v for k, v in required.items()):
    raise SystemExit('Pinned Docker package/closure missing')
(out / 'guest-packages.lock.json').write_text(json.dumps({'schemaVersion': 1, 'status': 'OFFICIAL_APT_DEPENDENCY_CLOSURE_FROZEN', 'architecture': 'arm64', 'dockerEngineVersion': '29.2.1', 'required': sorted(required), 'packages': rows}, indent=2) + '\n')
(out / 'apt-evidence/verification-scope.json').write_text(json.dumps({'repositoryChecks': 'apt default trusted Debian archive keyring + exact Docker primary fingerprint + signed-by scoped keyring; signed InRelease and package hashes verified by apt', 'snapshotCheckValidUntilDisabled': True, 'dockerIndexFrozenAfterSignedFetch': True, 'guestBooted': False, 'offlineGuestInstallTested': False}, indent=2))
