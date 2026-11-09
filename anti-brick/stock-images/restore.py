#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reassemble the split factory-image archive, verify it, and extract it.

Usage:
    python3 restore.py

Reads manifest.json + stock_backup.tar.gz.partNN from this directory,
verifies every part's SHA-256, rebuilds stock_backup.tar.gz, verifies the
whole archive, then extracts the 21 partition images into
./restored_stock_backup/. No network access and no root required.
"""
import hashlib, json, pathlib, tarfile, sys

HERE = pathlib.Path(__file__).resolve().parent


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    m = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    buf = bytearray()
    for p in m['parts']:
        f = HERE / p['name']
        if not f.exists():
            sys.exit('MISSING PART: %s' % p['name'])
        data = f.read_bytes()
        if len(data) != p['bytes'] or sha(data) != p['sha256']:
            sys.exit('CHECKSUM MISMATCH: %s (re-download this part)' % p['name'])
        buf.extend(data)
        print('ok  %-32s %8d bytes' % (p['name'], len(data)))
    if len(buf) != m['compressed_bytes'] or sha(bytes(buf)) != m['archive_sha256']:
        sys.exit('ARCHIVE CHECKSUM MISMATCH - do NOT use these images')

    full = HERE / m['archive']
    full.write_bytes(buf)
    dest = HERE / 'restored_stock_backup'
    dest.mkdir(exist_ok=True)
    with tarfile.open(full, 'r:gz') as tf:
        try:
            tf.extractall(dest, filter='data')   # Python 3.12+
        except TypeError:
            tf.extractall(dest)                   # older Python
    print('\nOK  archive: %s (%.1f MB)' % (full.name, len(buf) / 1024 / 1024))
    print('OK  extracted %d partition images -> %s' % (m['partition_count'], dest))
    print('\nNext: verify the raw images against SHA256SUMS.txt, then use')
    print('anti-brick/scripts/flash_part.py to write them back if needed.')


if __name__ == '__main__':
    main()
