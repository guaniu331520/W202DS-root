#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download microG (GmsCore + FakeStore) and Aurora Store APKs.

The build machine sits behind a WorkBuddy hook proxy (127.0.0.1:14734) that
is slow and breaks TLS for large GitHub downloads. Clash Verge Rev listens on
127.0.0.1:7897; Python's OpenSSL stack works with it (Windows curl/schannel
does not). Big APKs are fetched in parallel byte ranges for speed.
"""
import os, sys, time, urllib.request, concurrent.futures

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apks')
os.makedirs(OUT, exist_ok=True)
CLASH = 'http://127.0.0.1:7897'
UA = {'User-Agent': 'Mozilla/5.0'}
TAG = 'v0.3.17.252432'
GH = 'https://github.com/microg/GmsCore/releases/download/' + TAG + '/'

GMSCORE = GH + 'com.google.android.gms-252432034.apk'
GMSCORE_SIZE = 108113833
# ghfast.top mirrors GitHub release assets and is ~5x faster than direct here.
GMSCORE_MIRROR = 'https://ghfast.top/' + GMSCORE
FAKESTORE = GH + 'com.android.vending-84022634.apk'

# Aurora Store 4.8.4 == F-Droid versionCode 76. Try CN mirrors first (no proxy),
# then F-Droid main repo via Clash.
AURORA = [
    ('https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo/com.aurora.store_76.apk', False),
    ('https://mirrors.bfsu.edu.cn/fdroid/repo/com.aurora.store_76.apk', False),
    ('https://mirrors.ustc.edu.cn/fdroid/repo/com.aurora.store_76.apk', False),
    ('https://f-droid.org/repo/com.aurora.store_76.apk', False),
    ('https://f-droid.org/repo/com.aurora.store_76.apk', True),
]


def opener(proxy):
    ph = urllib.request.ProxyHandler({'http': CLASH, 'https': CLASH}) if proxy \
        else urllib.request.ProxyHandler({})
    return urllib.request.build_opener(ph)


def get(url, rng=None, proxy=True, timeout=60, retries=3):
    h = dict(UA)
    if rng:
        h['Range'] = 'bytes=%d-%d' % rng
    err = None
    for _ in range(retries):
        try:
            return opener(proxy).open(urllib.request.Request(url, headers=h),
                                      timeout=timeout).read()
        except Exception as e:
            err = e
            time.sleep(1.5)
    raise err


def dl_single(name, sources):
    path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 100000:
        print('SKIP %-26s already present (%d bytes)' % (name, os.path.getsize(path)))
        return True
    for url, proxy in sources:
        try:
            d = get(url, proxy=proxy, timeout=90, retries=2)
            if d[:2] == b'PK' and len(d) > 100000:
                open(path, 'wb').write(d)
                print('OK   %-26s %9d bytes  <- %s' % (name, len(d), url.split('/')[2]))
                return True
            print('BAD  %-26s not an APK (%d bytes)' % (name, len(d)))
        except Exception as e:
            print('FAIL %-26s %-16s %s' % (name, type(e).__name__, url.split('/')[2]))
    return False


def dl_parallel(name, url, total, parts=8, proxy=True, workers=4):
    """Range-download a big APK with each chunk persisted to disk.

    Persisting chunks means a failed chunk can be retried alone, and rerunning
    the script resumes instead of starting over.
    """
    path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) == total:
        print('SKIP %-26s already complete' % name)
        return True
    step = (total + parts - 1) // parts
    ranges = [(i * step, min((i + 1) * step, total) - 1) for i in range(parts)]
    pdir = os.path.join(OUT, '.parts_' + name)
    os.makedirs(pdir, exist_ok=True)

    def work(i):
        pf = os.path.join(pdir, 'p%02d' % i)
        want = ranges[i][1] - ranges[i][0] + 1
        if os.path.exists(pf) and os.path.getsize(pf) == want:
            return i, True
        for attempt in range(5):
            try:
                b = get(url, ranges[i], proxy=proxy, timeout=90, retries=1)
                if len(b) == want:
                    open(pf, 'wb').write(b)
                    print('  part %02d ok (%d bytes)' % (i, want), flush=True)
                    return i, True
            except Exception as e:
                print('  part %02d retry %d (%s)' % (i, attempt + 1,
                                                     type(e).__name__), flush=True)
            time.sleep(2)
        return i, False

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(work, range(parts)))
    missing = [i for i, ok in res if not ok]
    still = []
    for i in missing:
        _, ok = work(i)
        if not ok:
            still.append(i)
    if still:
        print('FAIL %-26s missing parts %s (rerun to resume)' % (name, still))
        return False
    with open(path, 'wb') as f:
        for i in range(parts):
            with open(os.path.join(pdir, 'p%02d' % i), 'rb') as p:
                f.write(p.read())
    dt = time.time() - t0
    print('OK   %-26s %9d bytes  %d parts  %.0f KB/s'
          % (name, os.path.getsize(path), parts, total / dt / 1024))
    return True


if __name__ == '__main__':
    r1 = dl_single('AuroraStore-4.8.4.apk', AURORA)
    r2 = dl_single('microG-FakeStore.apk', [(FAKESTORE, False), (FAKESTORE, True)])
    r3 = dl_parallel('microG-GmsCore.apk', GMSCORE_MIRROR, GMSCORE_SIZE,
                     parts=8, proxy=False, workers=4)
    if not r3:
        r3 = dl_parallel('microG-GmsCore.apk', GMSCORE, GMSCORE_SIZE,
                         parts=8, proxy=True, workers=4)
    print('-----')
    for f in sorted(os.listdir(OUT)):
        print('  %-30s %10d' % (f, os.path.getsize(os.path.join(OUT, f))))
    sys.exit(0 if (r1 and r2 and r3) else 1)
