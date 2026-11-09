"""Extract a single APK from a remote ZIP using HTTP Range requests.

Avoids downloading the whole 241 MB MindTheGapps archive just to get GSF.apk.
Usage: python extract_remote_zip.py <url> <size> <name-substring> <output.apk>
"""
import sys
import struct
import zlib
import zipfile
import subprocess

UA = '-A', 'Mozilla/5.0'


def range_get(url, start, end):
    cmd = ['curl', '-sL', '-A', 'Mozilla/5.0', '--retry', '3',
           '--retry-all-errors', '--retry-delay', '2', '--max-time', '180',
           '-r', '%d-%d' % (start, end), url]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise SystemExit('curl failed: ' + r.stderr.decode('utf-8', 'replace'))
    return r.stdout


def main():
    url, size, needle, out = sys.argv[1], int(sys.argv[2]), sys.argv[3].lower(), sys.argv[4]

    tail_len = 70000
    tail = range_get(url, max(0, size - tail_len), size - 1)
    pos = tail.rfind(b'PK\x05\x06')
    if pos < 0:
        raise SystemExit('EOCD not found in tail')
    e = struct.unpack('<IHHHHIIH', tail[pos:pos + 22])
    cd_size, cd_offset = e[5], e[6]
    print('EOCD: entries=%d cd_size=%d cd_offset=%d' % (e[4], cd_size, cd_offset))

    cd = range_get(url, cd_offset, cd_offset + cd_size - 1)
    p = 0
    found = None
    while p + 46 <= len(cd) and cd[p:p + 4] == b'PK\x01\x02':
        f = struct.unpack('<IHHHHHHIIIHHHHHII', cd[p:p + 46])
        method, csize, usize = f[4], f[8], f[9]
        fnlen, extralen, comlen, lho = f[10], f[11], f[12], f[16]
        name = cd[p + 46:p + 46 + fnlen].decode('utf-8', 'replace')
        if needle in name.lower() and name.lower().endswith('.apk'):
            found = (name, method, csize, usize, lho)
            break
        p += 46 + fnlen + extralen + comlen
    if not found:
        raise SystemExit('target entry not found')
    name, method, csize, usize, lho = found
    print('FOUND: %s  method=%d  compressed=%d  raw=%d  offset=%d' % (name, method, csize, usize, lho))

    hdr = range_get(url, lho, lho + 29)
    lfnlen, lextralen = struct.unpack('<HH', hdr[26:30])
    data_start = lho + 30 + lfnlen + lextralen
    raw = range_get(url, data_start, data_start + csize - 1)
    payload = zlib.decompress(raw, -15) if method == 8 else raw
    if len(payload) != usize:
        raise SystemExit('size mismatch: %d vs %d' % (len(payload), usize))
    with open(out, 'wb') as fh:
        fh.write(payload)
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
    print('WROTE: %s  bytes=%d  zip_test=%s' % (out, len(payload), 'OK' if bad is None else bad))


if __name__ == '__main__':
    main()
