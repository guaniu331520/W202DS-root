#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pack the factory partition backup into a compressed + split archive.

Why split: GitHub's Contents API (api.github.com) is the only reachable write
endpoint here (uploads.github.com for Release assets is blocked). A single
80 MB blob becomes ~107 MB of base64 JSON, which is both over the practical
limit and unreliable. 5 MB parts -> ~6.7 MB JSON each, safely uploadable.

Outputs (all under zte-w202ds-guide/anti-brick/stock-images/):
  stock_backup.tar.gz.partNN   split parts (uploaded to the repo)
  SHA256SUMS.txt               checksums for parts, archive and raw partitions
  manifest.json                sizes, hashes, part list
  restore.py                   reassemble + verify + extract
  README.md                    what this is and how to use it
The unsplit archive is kept locally at flash-tools/stock_backup.tar.gz
(excluded from the repo; it is reproducible from the parts).
"""
import hashlib, io, json, pathlib, tarfile, datetime

# Run from the workspace root (the directory that contains both
# flash-tools/ and zte-w202ds-guide/).
ROOT = pathlib.Path.cwd()
SRC = ROOT / 'flash-tools' / 'stock_backup'
OUT = ROOT / 'zte-w202ds-guide' / 'anti-brick' / 'stock-images'
FULL = ROOT / 'flash-tools' / 'stock_backup.tar.gz'
OUT.mkdir(parents=True, exist_ok=True)

ARCHIVE = 'stock_backup.tar.gz'
PART_SIZE = 5 * 1024 * 1024


def sha(b):
    return hashlib.sha256(b).hexdigest()


files = sorted((p for p in SRC.iterdir() if p.is_file()), key=lambda p: p.name)
if not files:
    raise SystemExit('ERROR: no partition images in flash-tools/stock_backup/')

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz', compresslevel=6) as tf:
    for f in files:
        tf.add(f, arcname=f.name)
blob = buf.getvalue()
FULL.write_bytes(blob)

parts_meta = []
sums = []
for i in range(0, len(blob), PART_SIZE):
    chunk = blob[i:i + PART_SIZE]
    name = '%s.part%02d' % (ARCHIVE, len(parts_meta) + 1)
    (OUT / name).write_bytes(chunk)
    h = sha(chunk)
    parts_meta.append({'name': name, 'bytes': len(chunk), 'sha256': h})
    sums.append('%s  %s' % (h, name))
    print('  %-34s %6.2f MB' % (name, len(chunk) / 1024 / 1024), flush=True)

sums.append('%s  %s' % (sha(blob), ARCHIVE))
for f in files:
    sums.append('%s  original/%s' % (sha(f.read_bytes()), f.name))
(OUT / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n', encoding='utf-8')

manifest = {
    'device': 'ZTE W202DS (Unisoc ums9620, Android 13)',
    'created': datetime.datetime.now().isoformat(timespec='seconds'),
    'source': 'flash-tools/stock_backup/ (21 factory partition images)',
    'partition_count': len(files),
    'uncompressed_bytes': sum(f.stat().st_size for f in files),
    'compression': 'tar.gz (gzip level 6)',
    'compressed_bytes': len(blob),
    'archive': ARCHIVE,
    'archive_sha256': sha(blob),
    'part_size_bytes': PART_SIZE,
    'part_count': len(parts_meta),
    'parts': parts_meta,
}
(OUT / 'manifest.json').write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

print('original   : %.1f MB' % (manifest['uncompressed_bytes'] / 1024 / 1024))
print('compressed : %.1f MB' % (len(blob) / 1024 / 1024))
print('parts      : %d x %d MB' % (len(parts_meta), PART_SIZE // 1024 // 1024))
print('full copy  :', FULL)
