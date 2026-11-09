# -*- coding: utf-8 -*-
"""Flash one partition via external-FDL rescue channel, then read it back and
verify the written bytes match the source image (write-integrity check).
After reset, waits for Android and reports boot state.

Usage: python flash_part.py <partition> <source_image_abs_path>
"""
import hashlib, os, subprocess, threading, time, sys

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
PKG = os.path.join(ROOT, "unlock_ums9620")
SPD = os.path.join(ROOT, "spd_dump", "spd_dump.exe")
ADB = os.path.join(ROOT, "platform-tools", "adb.exe")
SERIAL = "<DEVICE_SERIAL>"
OUT = os.path.join(ROOT, "flash_writeback")
os.makedirs(OUT, exist_ok=True)
EXEC_ADDR = "0x65012f48"
FDL1 = os.path.join(PKG, "fdl1-dl.bin"); FDL1_ADDR = "0x65000800"
FDL2 = os.path.join(PKG, "fdl2-dl.bin"); FDL2_ADDR = "0xb4fffe00"

PART = sys.argv[1]
SRC = sys.argv[2].replace("/", "\\")  # normalize to windows sep for spd_dump
LOG = os.path.join(ROOT, "flash_%s.log" % PART)

logf = open(LOG, "wb", buffering=0)
def note(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    logf.write((line + "\n").encode("utf-8", "replace")); print(line, flush=True)
def adb(args, t=25):
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

note("=== FLASH PARTITION: %s  <--  %s ===" % (PART, SRC))
if not os.path.exists(SRC):
    note("FATAL: source image missing: %s" % SRC); logf.close(); raise SystemExit(2)
note("source sha256: " + sha(SRC))

try: subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
except Exception: pass
time.sleep(1)
if not online():
    note("adb unauthorized - waiting up to 10 min for USB debugging dialog")
    for i in range(120):
        time.sleep(5)
        if online():
            note("adb authorized after %ds" % ((i+1)*5)); break
    else:
        note("FATAL: adb never authorized."); logf.close(); raise SystemExit(2)

cmd = [SPD, "--wait", "300", "--verbose", "1",
       "exec_addr", EXEC_ADDR,
       "fdl", FDL1, FDL1_ADDR,
       "fdl", FDL2, FDL2_ADDR,
       "exec", "path", OUT,
       "w", PART, SRC,
       "r", PART,
       "reset"]
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
        for m in (b"EXEC FDL1", b"EXEC FDL2", b"Read Part Done", b"Write Part Done",
                  b"LIBUSB_ERROR", b"FAILED", b"not found", b"unknown partition"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s); note("MARKER: " + s)
threading.Thread(target=reader, daemon=True).start()
time.sleep(2)
note("TRIGGER: adb reboot autodloader")
adb(["reboot", "autodloader"], 15)
deadline = time.time() + 480
while proc.poll() is None and time.time() < deadline: time.sleep(5)
note("spd_dump %s" % ("finished naturally" if proc.poll() is not None else "TIMEOUT"))
if proc.poll() is None:
    try: proc.terminate()
    except Exception: pass
note("markers: " + (", ".join(markers) or "(none)"))

note("=== WAITING FOR ANDROID ===")
back = False
for i in range(48):
    time.sleep(5)
    if online(): back = True; note("Android back after %ds" % ((i+1)*5)); break

rb = os.path.join(OUT, PART)
verdict = "UNKNOWN"
if os.path.exists(rb) and os.path.getsize(rb) > 0:
    h1, h2 = sha(rb), sha(SRC)
    note("readback %s: %d bytes  sha256:%s" % (PART, os.path.getsize(rb), h1[:16]))
    note("source   sha256:%s" % h2[:16])
    verdict = "MATCH - flash integrity OK" if h1 == h2 else "MISMATCH - flash did NOT match source!"
else:
    verdict = "NO_READBACK - write may have failed"
note("VERDICT: " + verdict)

state = {}
if back:
    for p in ("sys.boot_completed", "ro.boot.flash.locked", "ro.boot.verifiedbootstate"):
        state[p] = adb(["shell", "getprop " + p], 10)
    note("FINAL: " + str(state))
logf.close()
print("\nRESULT: PART=%s VERDICT=%s BOOTED=%s" % (PART, verdict, back))
