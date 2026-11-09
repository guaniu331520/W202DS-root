# -*- coding: utf-8 -*-
"""READ-ONLY: read back a partition via external-FDL rescue path and compare
to our stock backup. Proves (a) the partition NAME is valid for spd_dump and
(b) the on-device partition currently matches stock (i.e. not yet patched)."""
import hashlib, os, subprocess, threading, time, sys

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
PKG = os.path.join(ROOT, "unlock_ums9620")
SPD = os.path.join(ROOT, "spd_dump", "spd_dump.exe")
ADB = os.path.join(ROOT, "platform-tools", "adb.exe")
SERIAL = "<DEVICE_SERIAL>"
STOCK = os.path.join(ROOT, "stock_backup")

PART = sys.argv[1] if len(sys.argv) > 1 else "trustos"
STOCK_FILE = sys.argv[2] if len(sys.argv) > 2 else os.path.join(STOCK, "trustos_a")
OUTDIR = os.path.join(ROOT, "part_readback")
os.makedirs(OUTDIR, exist_ok=True)
OUT = os.path.join(OUTDIR, PART + ".img")

EXEC_ADDR = "0x65012f48"
FDL1 = "fdl1-dl.bin"; FDL1_ADDR = "0x65000800"
FDL2 = "fdl2-dl.bin"; FDL2_ADDR = "0xb4fffe00"

logf = open(os.path.join(ROOT, "verify_partition.log"), "wb", buffering=0)
def note(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    logf.write((line + "\n").encode("utf-8", "replace")); print(line, flush=True)
def adb(args, t=20):
    try:
        p = subprocess.run([ADB, "-s", SERIAL] + args, capture_output=True, timeout=t)
        return (p.stdout + p.stderr).decode("utf-8", "replace").strip()
    except Exception as e:
        return "ERR: %s" % e
def online():
    try:
        p = subprocess.run([ADB, "devices"], capture_output=True, timeout=15)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except Exception:
        return False
    return any(SERIAL in l and "device" in l and "offline" not in l and "unauthorized" not in l for l in out.splitlines())
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

note("=== READ-ONLY PARTITION CHECK: %s ===" % PART)
try: subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
except Exception: pass
time.sleep(1)
if not online():
    note("FATAL: device not in Android."); logf.close(); raise SystemExit(2)
note("adb ok; rebooting to autodloader ...")
cmd = [SPD, "--wait", "300", "--verbose", "1",
       "exec_addr", EXEC_ADDR,
       "fdl", os.path.join(PKG, FDL1), FDL1_ADDR,
       "fdl", os.path.join(PKG, FDL2), FDL2_ADDR,
       "exec", "path", OUTDIR, "r", PART, "reset"]
note("cmd: " + " ".join((os.path.basename(x) if "\\" in x else x) for x in cmd[1:]))
proc = subprocess.Popen(cmd, cwd=PKG, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
markers = []; recent = bytearray()
def reader():
    while True:
        b = proc.stdout.read(1)
        if not b: break
        logf.write(b); recent.extend(b)
        if len(recent) > 256: del recent[:-256]
        cur = bytes(recent)
        for m in (b"Read Part Done", b"LIBUSB_ERROR", b"FAILED", b"not found", b"unknown partition"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s); note("MARKER: " + s)
threading.Thread(target=reader, daemon=True).start()
time.sleep(2)
adb(["reboot", "autodloader"], 15)
deadline = time.time() + 420
while proc.poll() is None and time.time() < deadline: time.sleep(5)
note("spd_dump finished naturally" if proc.poll() is not None else "spd_dump timeout")
if proc.poll() is None:
    try: proc.terminate()
    except Exception: pass
note("markers: " + (", ".join(markers) or "(none)"))

note("=== WAITING FOR ANDROID ===")
back = False
for i in range(36):
    time.sleep(5)
    if online(): back = True; note("Android back after %ds" % ((i+1)*5)); break

verdict = "UNKNOWN"
if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
    h1 = sha(OUT); h2 = sha(STOCK_FILE)
    note("readback %s: %d bytes  sha256:%s" % (PART, os.path.getsize(OUT), h1[:16]))
    note("stock    %s:           sha256:%s" % (os.path.basename(STOCK_FILE), h2[:16]))
    verdict = "MATCH - partition name valid + device still stock (not yet patched)" if h1 == h2 else "MISMATCH - on-device differs from stock backup!"
else:
    verdict = "NO_READBACK - partition name '%s' likely INVALID or read failed" % PART
note("VERDICT: " + verdict)
logf.close()
