# -*- coding: utf-8 -*-
"""Fully automatic READ-ONLY BootROM probe for ZTE W202DS (Unisoc T760).

Key idea: instead of asking the user to hold POWER+VOL_DOWN (timing never
matched), reboot the device from Android into SPD download mode via a Unisoc
reboot reason (`adb reboot autodloader`). spd_dump waits concurrently and takes
over the BootROM session as soon as the USB port enumerates.

SAFETY:
 - No partition is ever written/erased/repartitioned; no unlock; no wipe.
 - `adb reboot <reason>` is a plain reboot, fully reversible. If the reason is
   unsupported the device just reboots back into Android.
 - BootROM auto-continues to Android ~30-40s after the host releases the port.
 - If it does not come back, holding POWER 10-15s forces a reboot. No data loss.
 - Baseline (battery / BL state) is recorded before anything happens.
"""
import os
import subprocess
import threading
import time

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
SPD_DIR = os.path.join(ROOT, "spd_dump")
SPD_EXE = os.path.join(SPD_DIR, "spd_dump.exe")
ADB = os.path.join(ROOT, "platform-tools", "adb.exe")
SERIAL = "<DEVICE_SERIAL>"
LOG = os.path.join(ROOT, "auto_probe.log")
REPORT = os.path.join(ROOT, "auto_probe_report.md")
BACKUP = os.path.join(ROOT, "backup")
os.makedirs(BACKUP, exist_ok=True)

# READ-ONLY ONLY. No w/write_part/erase/repartition/exec/fdl/poweroff.
CMDS = [
    "verbose 2",
    "timeout 20000",
    "path " + BACKUP,
    "p",
    "read_mem 0x0 0x100 brom_mem0.bin",
    "read_flash 0 0 0x1000 flash_a_4k.bin",
    "read_flash 0x80000001 0 0x1000 flash_b_4k.bin",
    "read_flash 0 0 0x20000 flash_c_128k.bin",
    "read_flash 0x80000001 0 0x20000 flash_d_128k.bin",
    "partition_list partitions.xml",
    "p",
]

REASONS = ["autodloader", "download", "dloader"]

logf = open(LOG, "wb", buffering=0)
events = []


def note(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    events.append(line)
    logf.write((line + "\n").encode("utf-8", "replace"))
    print(line, flush=True)


def adb(args, timeout=20):
    try:
        p = subprocess.run([ADB, "-s", SERIAL] + args,
                           capture_output=True, timeout=timeout)
        out = (p.stdout + p.stderr).decode("utf-8", "replace").strip()
        return out
    except Exception as e:
        return "ERR: %s" % e


def adb_start_server():
    """Keep one adb server alive; repeated cold starts corrupt get-state output."""
    try:
        subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
    except Exception:
        pass
    time.sleep(1)


def adb_online():
    """Parse `adb devices` instead of get-state (cold-start banners break it)."""
    try:
        p = subprocess.run([ADB, "devices"], capture_output=True, timeout=15)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except Exception:
        return False
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(SERIAL) and line.endswith("\tdevice"):
            return True
    # tolerate whitespace variants, but reject offline/unauthorized
    for line in out.splitlines():
        if SERIAL in line and "device" in line and "offline" not in line and "unauthorized" not in line:
            return True
    return False


# ---------------- baseline ----------------
note("=== BASELINE ===")
adb_start_server()
for attempt in range(5):
    if adb_online():
        break
    note("adb not ready yet (attempt %d/5), retrying" % (attempt + 1))
    adb_start_server()
    time.sleep(2)
if not adb_online():
    note("FATAL: tablet not online via adb - aborting, nothing touched")
    logf.close()
    raise SystemExit(2)
note("adb connectivity confirmed")
note("adb online: " + adb(["shell", "getprop ro.product.model"], 10))
note("battery: " + adb(["shell", "dumpsys battery | grep -iE 'level:|status:'"], 10).replace("\n", " | "))
note("BL: " + adb(["shell", "getprop ro.boot.flash.locked; getprop ro.boot.verifiedbootstate"], 10).replace("\n", " | "))
note("boot_completed: " + adb(["shell", "getprop sys.boot_completed"], 10))

# ---------------- start spd_dump waiter ----------------
proc = subprocess.Popen(
    [SPD_EXE, "--wait", "600", "--verbose", "2"],
    cwd=SPD_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, bufsize=0)
ready = threading.Event()
recent = bytearray()
markers = []


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
        for m in (b"BROM >", b"FDL1 >", b"FDL2 >", b"BSL_REP_VER", b"CMD_CONNECT"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s)
                note("MARKER: " + s)
        if b"BROM >" in cur or b"FDL1 >" in cur or b"FDL2 >" in cur:
            ready.set()


threading.Thread(target=reader, daemon=True).start()
time.sleep(2)
note("spd_dump waiter started (pid %d), interactive mode" % proc.pid)

# ---------------- trigger reboot into download mode ----------------
used_reason = None
for reason in REASONS:
    if ready.is_set():
        break
    if not adb_online():
        note("adb offline before trying '%s'; waiting up to 45s for Android" % reason)
        for _ in range(9):
            time.sleep(5)
            if adb_online():
                break
        if not adb_online():
            note("still offline - skipping '%s'" % reason)
            continue
    note("TRIGGER: adb reboot %s" % reason)
    r = adb(["reboot", reason], timeout=15)
    note("  adb response: " + (r[:120] if r else "(ok, connection dropped as expected)"))
    used_reason = reason
    # give BootROM up to 40s to enumerate + handshake
    for _ in range(20):
        if ready.is_set():
            break
        time.sleep(2)
    note("  connected=%s markers=%s" % (ready.is_set(), ",".join(markers) or "none"))
    if ready.is_set():
        break
    # let it fall back to Android before trying next reason
    note("  no session; waiting 35s for device to return to Android")
    for _ in range(7):
        time.sleep(5)
        if adb_online():
            note("  Android is back")
            break

# ---------------- run read-only commands ----------------
status = "NO_CONNECTION"
if ready.is_set():
    status = "CONNECTED"
    note("=== BROM SESSION HELD, sending READ-ONLY commands ===")
    for cmd in CMDS:
        try:
            proc.stdin.write((cmd + "\n").encode())
            proc.stdin.flush()
            note("SENT: " + cmd)
        except Exception as e:
            note("stdin write failed: %s" % e)
            break
        time.sleep(6)
    note("commands done; holding 15s for transfers")
    time.sleep(15)

try:
    proc.terminate()
    note("spd_dump terminated (USB released -> BootROM will continue to Android)")
except Exception as e:
    note("terminate: %s" % e)

# ---------------- verify the device returns ----------------
note("=== WAITING FOR ANDROID (up to 150s) ===")
back = False
for i in range(30):
    time.sleep(5)
    if adb_online():
        back = True
        note("Android is back after %ds" % ((i + 1) * 5))
        break
if not back:
    note("WARNING: Android not back yet. Hold POWER 10-15s on the tablet to reboot. No data was modified.")

state = {}
if back:
    state["model"] = adb(["shell", "getprop ro.product.model"], 10)
    state["boot"] = adb(["shell", "getprop sys.boot_completed"], 10)
    state["bl"] = adb(["shell", "getprop ro.boot.flash.locked"], 10)
    state["vb"] = adb(["shell", "getprop ro.boot.verifiedbootstate"], 10)
    state["bat"] = adb(["shell", "dumpsys battery | grep -i level:"], 10)
    note("FINAL: " + str(state))

produced = []
for fn in sorted(os.listdir(BACKUP)):
    fp = os.path.join(BACKUP, fn)
    if os.path.isfile(fp):
        produced.append((fn, os.path.getsize(fp)))

lines = [
    "# W202DS automatic BootROM read-only probe",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Status: **" + status + "**",
    "- Reboot reason used: " + (used_reason or "(none)"),
    "- Connection markers: " + (", ".join(markers) or "(none)"),
    "- Device returned to Android: **" + ("YES" if back else "NO - hold POWER 10-15s") + "**",
    "",
    "## Final device state",
    "",
]
for k, v in state.items():
    lines.append("- %s: `%s`" % (k, v))
if not state:
    lines.append("(not available - device not back via adb)")
lines += [
    "",
    "## Raw dumps produced (READ-ONLY)",
    "",
]
if produced:
    for fn, sz in produced:
        lines.append("- `%s` - %d bytes" % (fn, sz))
else:
    lines.append("(none)")
lines += [
    "",
    "## What the result means",
    "",
    "If any `flash_*.bin` is non-empty, BootROM allowed raw flash reads WITHOUT",
    "FDL. That is the breakthrough: GPT + stock partitions can be dumped, giving",
    "us restore images before any unlock attempt.",
    "",
    "If no dumps: this secure-boot BootROM blocks flash reads. A partition dump",
    "would then require FDL1/FDL2 from a stock .pac firmware, which we do not",
    "have - option 2 has reached its technical limit.",
    "",
    "NOTE: Nothing was written to the device. No unlock, no wipe, no partition",
    "modification, no bootloader change. BL remains locked / green.",
    "",
    "Logs: `auto_probe.log` (full timeline), `brom_session.log` (older runs)",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
note("REPORT: " + REPORT)
logf.close()
