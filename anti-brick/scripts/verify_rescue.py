# -*- coding: utf-8 -*-
"""READ-ONLY verification of the external-FDL rescue path.

Goal: prove that even if splloader/uboot/sml/trustos were bricked, we can
still reach FDL2 from BootROM using EXTERNAL fdl1/fdl2 (loaded into RAM only)
and therefore write the stock backup back.

This does NOT write any partition. It only:
  1. reboots to autodloader,
  2. uses exec_addr + external FDL1/FDL2 to establish a FDL2 session,
  3. reads back one small partition (misc) into a local file,
  4. compares its SHA256 with our stock backup,
  5. sends reset (plain reboot) and verifies Android returns.

If step 3/4 succeed, the rescue channel is proven usable on THIS device.
"""
import hashlib
import os
import subprocess
import threading
import time

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
PKG = os.path.join(ROOT, "unlock_ums9620")
# Use the NEW libusb-capable spd_dump (ver 251). The 80KB spd_dump bundled in
# the official unlock package uses Channel9.dll and cannot see our WinUSB/libwdi
# bound port ("find port failed"). Files are referenced by absolute path so the
# new binary can still load the package's ums9620 payload + external FDLs.
SPD = os.path.join(ROOT, "spd_dump", "spd_dump.exe")
ADB = os.path.join(ROOT, "platform-tools", "adb.exe")
SERIAL = "<DEVICE_SERIAL>"
LOG = os.path.join(ROOT, "verify_rescue.log")
REPORT = os.path.join(ROOT, "verify_rescue_report.md")
OUT = os.path.join(ROOT, "rescue_readback")
STOCK = os.path.join(ROOT, "stock_backup")
os.makedirs(OUT, exist_ok=True)

EXEC_ADDR = "0x65012f48"
FDL1 = "fdl1-dl.bin"
FDL1_ADDR = "0x65000800"
FDL2 = "fdl2-dl.bin"
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
    return any(SERIAL in ln and "device" in ln
               and "offline" not in ln and "unauthorized" not in ln
               for ln in out.splitlines())


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


note("=== READ-ONLY RESCUE-PATH VERIFICATION ===")
try:
    subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
except Exception:
    pass
time.sleep(1)
if not adb_online():
    note("FATAL: device not in Android. Nothing touched.")
    logf.close()
    raise SystemExit(2)
note("baseline: " + adb(["shell", "getprop ro.build.display.id; getprop ro.boot.flash.locked"], 10).replace("\n", " | "))

# external FDL session + one read-only partition read
cmdline = [SPD, "--wait", "300", "--verbose", "1",
           "exec_addr", EXEC_ADDR,
           "fdl", os.path.join(PKG, FDL1), FDL1_ADDR,
           "fdl", os.path.join(PKG, FDL2), FDL2_ADDR,
           "exec",
           "path", OUT,
           "r", "misc",
           "reset"]
note("spd_dump cmd: " + " ".join(os.path.basename(x) if "\\" in x else x for x in cmdline[1:]))

# cwd=PKG so spd_dump finds custom_exec_no_verify_65012f48.bin for exec_addr.
# The exe's own directory still supplies libusb-1.0.dll via normal DLL search.
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
        for m in (b"BSL_REP_VER", b"CMD_CONNECT", b"EXEC FDL1", b"EXEC FDL2",
                  b"FDL1 >", b"FDL2 >", b"Read Part Done", b"LIBUSB_ERROR",
                  b"FAILED", b"not found"):
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

# compare read-back with stock backup
readback = None
for fn in os.listdir(OUT):
    fp = os.path.join(OUT, fn)
    if os.path.isfile(fp) and os.path.getsize(fp) > 0:
        readback = fp
        break

verdict = "UNKNOWN"
if readback:
    h1 = sha(readback)
    h2 = sha(os.path.join(STOCK, "misc"))
    note("readback file: %s (%d bytes)" % (os.path.basename(readback), os.path.getsize(readback)))
    note("readback sha256: " + h1)
    note("stock    sha256: " + h2)
    verdict = "MATCH - external FDL can read partitions correctly" if h1 == h2 else "MISMATCH"
else:
    verdict = "NO_READBACK - external FDL session failed"
note("VERDICT: " + verdict)

final_state = {}
if back:
    final_state["boot"] = adb(["shell", "getprop sys.boot_completed"], 10)
    final_state["BL"] = adb(["shell", "getprop ro.boot.flash.locked"], 10)
    final_state["verified"] = adb(["shell", "getprop ro.boot.verifiedbootstate"], 10)
    note("FINAL: " + str(final_state))

lines = [
    "# Rescue-path verification (READ-ONLY)",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Purpose: prove that bricked splloader/uboot/sml/trustos can still be",
    "  recovered via BootROM + EXTERNAL fdl1/fdl2 (RAM only, no partition write).",
    "- exec_addr: `%s` (ums9620-specific payload)" % EXEC_ADDR,
    "- Connection markers: " + (", ".join(markers) or "(none)"),
    "- spd_dump finished naturally: **" + ("YES" if natural else "NO") + "**",
    "- Device back in Android: **" + ("YES" if back else "NO - hold POWER 10-15s") + "**",
    "- Verdict: **" + verdict + "**",
    "",
    "## Final device state",
    "",
]
for k, v in final_state.items():
    lines.append("- %s: `%s`" % (k, v))
if not final_state:
    lines.append("(unavailable)")
lines += [
    "",
    "NOTE: strictly read-only. No partition was written, erased or modified.",
    "Only `r misc` (read) and `reset` (plain reboot) were sent.",
    "",
    "Full log: `verify_rescue.log`",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
note("REPORT: " + REPORT)
logf.close()
