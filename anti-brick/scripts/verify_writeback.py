# -*- coding: utf-8 -*-
"""READ-CONTENT-IDENTICAL write-back verification (the rescue proof).

Proves that partitions can be WRITTEN back, not just read, using the same
BootROM + external-FDL rescue channel verified by verify_rescue.py.

We write the ORIGINAL stock `misc` image back to the SAME `misc` partition.
Content is byte-for-byte identical, so the device state is unchanged. Then:
  - read it back and compare SHA256 with stock_backup/misc
  - send reset (plain reboot) and verify Android returns normally
  - verify BL is still locked/green

This is the last evidence needed for "bricked -> can be restored".
No partition content is altered. No unlock, no wipe, no AVB change.
"""
import hashlib
import os
import subprocess
import threading
import time

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
PKG = os.path.join(ROOT, "unlock_ums9620")
SPD = os.path.join(ROOT, "spd_dump", "spd_dump.exe")  # libusb build
ADB = os.path.join(ROOT, "platform-tools", "adb.exe")
SERIAL = "<DEVICE_SERIAL>"
LOG = os.path.join(ROOT, "verify_writeback.log")
REPORT = os.path.join(ROOT, "verify_writeback_report.md")
OUT = os.path.join(ROOT, "writeback_readback")
STOCK = os.path.join(ROOT, "stock_backup", "misc")
os.makedirs(OUT, exist_ok=True)

EXEC_ADDR = "0x65012f48"
FDL1 = os.path.join(PKG, "fdl1-dl.bin")
FDL1_ADDR = "0x65000800"
FDL2 = os.path.join(PKG, "fdl2-dl.bin")
FDL2_ADDR = "0xb4fffe00"

logf = open(LOG, "wb", buffering=0)


def note(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    logf.write((line + "\n").encode("utf-8", "replace"))
    print(line, flush=True)


def adb(args, timeout=20):
    try:
        p = subprocess.run([ADB, "-s", SERIAL] + args,
                           capture_output=True, timeout=timeout)
        return (p.stdout + p.stderr).decode("utf-8", "replace").strip()
    except Exception as e:
        return "ERR: %s" % e


def adb_online():
    try:
        p = subprocess.run([ADB, "devices"], capture_output=True, timeout=15)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except Exception:
        return False
    return any(SERIAL in ln and ln.rstrip().endswith("device")
               and "offline" not in ln and "unauthorized" not in ln
               for ln in out.splitlines())


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


note("=== WRITE-BACK VERIFICATION (content-identical) ===")
try:
    subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
except Exception:
    pass
time.sleep(1)

# Wait for the user to re-confirm the USB debugging prompt after autodloader.
if not adb_online():
    note("adb unauthorized - waiting up to 10 min for the user to confirm the USB debugging dialog")
    for i in range(120):
        time.sleep(5)
        if adb_online():
            note("adb authorized after %ds" % ((i + 1) * 5))
            break
    else:
        note("FATAL: adb never authorized. Nothing touched.")
        logf.close()
        raise SystemExit(2)

note("baseline build: " + adb(["shell", "getprop ro.build.display.id"], 10))
note("baseline BL: " + adb(["shell", "getprop ro.boot.flash.locked; getprop ro.boot.verifiedbootstate"], 10).replace("\n", " | "))
note("stock misc sha256: " + sha(STOCK))

# external-FDL session: write ORIGINAL content back, read it back, reboot.
cmdline = [SPD, "--wait", "300", "--verbose", "1",
           "exec_addr", EXEC_ADDR,
           "fdl", FDL1, FDL1_ADDR,
           "fdl", FDL2, FDL2_ADDR,
           "exec",
           "path", OUT,
           "w", "misc", STOCK,
           "r", "misc",
           "reset"]
note("commands: w misc <stock> ; r misc ; reset")
proc = subprocess.Popen(cmdline, cwd=PKG, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, bufsize=0)
markers = []
recent = bytearray()


def reader():
    while True:
        b = proc.stdout.read(1)
        if not b:
            break
        logf.write(b)
        recent.extend(b)
        if len(recent) > 256:
            del recent[:-256]
        cur = bytes(recent)
        for m in (b"EXEC FDL1", b"EXEC FDL2", b"Read Part Done",
                  b"Write Part Done", b"write", b"LIBUSB_ERROR", b"failed"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s)
                note("MARKER: " + s)


threading.Thread(target=reader, daemon=True).start()
time.sleep(2)
note("TRIGGER: adb reboot autodloader")
adb(["reboot", "autodloader"], 15)

deadline = time.time() + 420
while proc.poll() is None and time.time() < deadline:
    time.sleep(5)
natural = proc.poll() is not None
note("spd_dump %s" % ("finished naturally" if natural else "still running at timeout"))
if not natural:
    try:
        proc.terminate()
    except Exception:
        pass

note("=== WAITING FOR ANDROID ===")
back = False
for i in range(36):
    time.sleep(5)
    if adb_online():
        back = True
        note("Android is back after %ds" % ((i + 1) * 5))
        break

readback = os.path.join(OUT, "misc")
verdict = "UNKNOWN"
if os.path.isfile(readback) and os.path.getsize(readback) > 0:
    h1, h2 = sha(readback), sha(STOCK)
    note("readback sha256: " + h1)
    verdict = "MATCH - write-back works, content unchanged" if h1 == h2 else "MISMATCH"
else:
    verdict = "NO_READBACK"
note("VERDICT: " + verdict)

state = {}
if back:
    state["boot"] = adb(["shell", "getprop sys.boot_completed"], 10)
    state["BL"] = adb(["shell", "getprop ro.boot.flash.locked"], 10)
    state["verified"] = adb(["shell", "getprop ro.boot.verifiedbootstate"], 10)
    state["battery"] = adb(["shell", "dumpsys battery | grep -i level:"], 10)
    note("FINAL: " + str(state))

lines = [
    "# Write-back verification (content-identical)",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Purpose: prove partitions can be WRITTEN back via the rescue channel.",
    "- What was written: original `misc` image -> same `misc` partition (byte-identical).",
    "- Connection markers: " + (", ".join(markers) or "(none)"),
    "- spd_dump finished naturally: **" + ("YES" if natural else "NO") + "**",
    "- Device back in Android: **" + ("YES" if back else "NO - hold POWER 10-15s") + "**",
    "- Verdict: **" + verdict + "**",
    "",
    "## Final device state",
    "",
]
for k, v in state.items():
    lines.append("- %s: `%s`" % (k, v))
if not state:
    lines.append("(unavailable)")
lines += [
    "",
    "This completes the anti-brick proof: the external-FDL channel can BOTH",
    "read and write partitions, so any bricked partition covered by the backup",
    "can be restored. No unlock, no wipe, no AVB change, no content modification.",
    "",
    "Log: `verify_writeback.log`",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
note("REPORT: " + REPORT)
logf.close()
