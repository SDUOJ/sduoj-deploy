#!/usr/bin/env python3
"""No network by default. Fetch only the already SHA-pinned official source on explicit request."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import urllib.request

LOCK = Path(__file__).with_name('source.lock.json')

def validate(d):
    expected = 'https://cloud.debian.org/images/cloud/trixie/20261021-2638/debian-13-genericcloud-arm64-20261021-2638.qcow2'
    if d.get('url') != expected or d.get('bytes') != 336265216 or not re.fullmatch('[a-f0-9]{128}', d.get('sha512', '')) or not re.fullmatch('[a-f0-9]{64}', d.get('sha256', '')):
        raise ValueError('Frozen official URL, SHA512/SHA256 and length must be present before download')

def audit(file, d):
    a = hashlib.sha256(); b = hashlib.sha512()
    with file.open('rb') as f:
        header = f.read(104); f.seek(0)
        for block in iter(lambda: f.read(1024 * 1024), b''):
            a.update(block); b.update(block)
    if file.stat().st_size != d['bytes'] or a.hexdigest() != d['sha256'] or b.hexdigest() != d['sha512']:
        raise ValueError('Frozen source image size/checksum mismatch')
    magic, version, backing, backing_length, cluster_bits, virtual_bytes = struct.unpack('>IIQIIQ', header[:32])
    if magic != 0x514649fb or version != 3 or backing or backing_length:
        raise ValueError('Standalone QCOW2v3 without backing required')
    return {'verified': True, 'sha256': a.hexdigest(), 'sha512': b.hexdigest(), 'virtualBytes': virtual_bytes, 'qcow2Version': version, 'guestBooted': False, 'kernelFeaturesTested': False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', nargs='?', default='plan', choices=('plan', 'verify', 'download'))
    p.add_argument('--file', type=Path)
    a = p.parse_args(); d = json.loads(LOCK.read_text()); validate(d)
    if a.command == 'plan':
        print(json.dumps({'writes': False, 'network': False, 'sourcePinned': True, 'bytes': d['bytes'], 'guestBooted': False})); return
    if not a.file or not a.file.is_absolute() or a.file.is_symlink():
        p.error('Explicit real absolute file path required')
    if a.command == 'download':
        if a.file.exists() or not a.file.parent.is_dir():
            p.error('Existing parent and new destination required; partial downloads are retained, not reused')
        os.umask(0o077)
        count = 0
        with urllib.request.urlopen(d['url'], timeout=60) as response, a.file.open('xb') as output:
            for block in iter(lambda: response.read(1024 * 1024), b''):
                count += len(block)
                if count > d['bytes']:
                    raise ValueError('Source exceeds pinned size')
                output.write(block)
    report = audit(a.file, d)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit('Source verification/download failed; retain partial file for inspection')
