#!/usr/bin/env bash
# Runs only in the explicitly created owned builder, not on any physical host.
set -Eeuo pipefail
umask 077
[[ "${VM_BUILD_SCOPE:-}" == 'SDUOJ_ISOLATED_VM_ARTIFACTS_ONLY' && -f /src/manager-build.lock.json && -d /output ]]
mkdir -p /output/apt-evidence /output/guest-debs /output/manager-debs /output/firmware /opt/sduoj-vm
rm -f /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources
snapshot=$(cat /src/debian-snapshot)
printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s/ trixie main\n' "$snapshot" > /etc/apt/sources.list
apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=60 -o Debug::Acquire::gpgv=true update > /output/apt-evidence/debian-update.log 2>&1
# Exact Debian snapshot versions are passed by the local frozen renderer.
mapfile -t packages < /src/manager-packages
DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends -o Acquire::Retries=2 install "${packages[@]}" ca-certificates curl gnupg > /output/apt-evidence/manager-install.log 2>&1
# Retain an independently resolvable full manager dependency closure, not only dpkg versions.
: > /output/empty-status
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -delete
apt-get -o Dir::State::status=/output/empty-status -o Debug::NoLocking=1 -y --download-only --no-install-recommends -o Acquire::Retries=2 install "${packages[@]}" ca-certificates curl gnupg > /output/apt-evidence/manager-closure.log 2>&1
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -exec cp -- '{}' /output/manager-debs/ \;
cp -a /var/lib/apt/lists /output/apt-evidence/debian-lists
mkdir -p /etc/apt/keyrings
chmod 0755 /etc/apt/keyrings
curl --proto '=https' --tlsv1.2 --fail --retry 2 --connect-timeout 15 --max-time 60 https://download.docker.com/linux/debian/gpg -o /output/apt-evidence/docker.asc
gpg --batch --show-keys --with-colons /output/apt-evidence/docker.asc > /output/apt-evidence/docker-key.txt
fingerprint=$(awk -F: '$1=="fpr" {print $10;exit}' /output/apt-evidence/docker-key.txt)
[[ "$fingerprint" == '9DC858229FC7DD38854AE2D88D81803C0EBFCD88' ]] || { echo 'Docker signing key mismatch' >&2; exit 1; }
gpg --batch --dearmor < /output/apt-evidence/docker.asc > /etc/apt/keyrings/docker.gpg
chmod 0644 /etc/apt/keyrings/docker.gpg
printf 'deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian trixie stable\n' > /etc/apt/sources.list.d/docker.list
apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=60 -o Debug::Acquire::gpgv=true update > /output/apt-evidence/docker-update.log 2>&1
cp -a /var/lib/apt/lists /output/apt-evidence/all-lists
# Empty status resolves a self-contained ARM64 dependency closure without relying on builder-installed packages.
: > /output/empty-status
mapfile -t docker_packages < /src/docker-packages
# Purge only builder-local apt package cache so offline closure cannot include old bootstrap versions.
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -delete
apt-get -o Dir::State::status=/output/empty-status -o Debug::NoLocking=1 -y --download-only --no-install-recommends -o Acquire::Retries=2 install "${docker_packages[@]}" > /output/apt-evidence/docker-closure.log 2>&1
find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -exec cp -- '{}' /output/guest-debs/ \;
python3 /src/freeze-build.py
cp /src/manager.py /src/vmctl.py /src/source.lock.json /opt/sduoj-vm/
chmod 0755 /opt/sduoj-vm
chmod 0644 /opt/sduoj-vm/manager.py /opt/sduoj-vm/vmctl.py /opt/sduoj-vm/source.lock.json
dpkg-query -W > /opt/sduoj-vm/packages.lock
qemu-system-aarch64 --version > /output/qemu-version.txt
qemu-img --version > /output/qemu-img-version.txt
cp /usr/share/AAVMF/AAVMF_CODE.fd /usr/share/AAVMF/AAVMF_VARS.fd /output/firmware/
sha256sum /output/firmware/* > /output/firmware.sha256
cp /opt/sduoj-vm/packages.lock /output/manager-packages.lock
printf 'builder complete; no guest or Docker daemon started\n'
