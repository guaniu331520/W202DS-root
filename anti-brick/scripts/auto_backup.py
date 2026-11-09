# -*- coding: utf-8 -*-
"""Automatic READ-ONLY stock-partition backup for ZTE W202DS (Unisoc T760).

Breakthrough (verified 2026-11-08 12:48):
  `adb reboot autodloader` makes the device boot its OWN splloader/FDL and reach
  FDL2 automatically - NO external FDL binaries and NO key pressing needed.
  spd_dump then reads the full GPT (76 partitions) and enters `FDL2 >`.

Two bugs fixed vs auto_probe.py:
  1. Wrong command stage: `read_flash` / `read_mem` are BROM-stage commands and
     produce 0-byte files in FDL2. Correct commands are `r <part_name>`.
  2. Bad teardown: terminating spd_dump left the device stuck in FDL2. Now we
     send `reset` (BSL_CMD_NORMAL_RESET = plain reboot, writes nothing) and
     verify Android comes back.

SAFETY: strictly read-only. No w/write_part/erase/repartition/unlock/exec.
        `reset` is a normal reboot. BL stays locked / green.
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
LOG = os.path.join(ROOT, "auto_backup.log")
REPORT = os.path.join(ROOT, "auto_backup_report.md")
BACKUP = os.path.join(ROOT, "stock_backup")
os.makedirs(BACKUP, exist_ok=True)

# Only the partitions needed to restore the device / patch Magisk.
# Deliberately excludes userdata(109GB), cache, blackbox, super(6.3GB).
PARTS = [
    "splloader", "uboot_a", "uboot_b",
    "boot_a", "boot_b", "init_boot_a", "init_boot_b",
    "vendor_boot_a", "vendor_boot_b",
    "dtb_a", "dtbo_a",
    "vbmeta_a", "vbmeta_system_a", "vbmeta_vendor_a",
    "sml_a", "trustos_a", "misc", "persist",
]

CMDS = ["verbose 2", "path " + BACKUP, "p"] + ["r " + p for p in PARTS] + ["reset"]

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


def start_server():
    try:
        subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
    except Exception:
        pass
    time.sleep(1)


note("=== BASELINE ===")
start_server()
for i in range(5):
    if adb_online():
        break
    note("adb not ready (%d/5)" % (i + 1))
    start_server()
    time.sleep(2)
if not adb_online():
    note("FATAL: tablet not in Android. Power it on first (hold POWER 10-15s). Nothing touched.")
    logf.close()
    raise SystemExit(2)
note("model: " + adb(["shell", "getprop ro.product.model"], 10))
note("build: " + adb(["shell", "getprop ro.build.display.id"], 10))
note("battery: " + adb(["shell", "dumpsys battery | grep -i level:"], 10))
note("BL: " + adb(["shell", "getprop ro.boot.flash.locked; getprop ro.boot.verifiedbootstate"], 10).replace("\n", " | "))

proc = subprocess.Popen(
    [SPD_EXE, "--wait", "600", "--verbose", "1"],
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
        for m in (b"BSL_REP_VER", b"CMD_CONNECT", b"FDL1 >", b"FDL2 >", b"BROM >"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s)
                note("MARKER: " + s)
        if b"FDL2 >" in cur or b"FDL1 >" in cur or b"BROM >" in cur:
            ready.set()


threading.Thread(target=reader, daemon=True).start()
time.sleep(2)
note("spd_dump waiter started (pid %d)" % proc.pid)

note("TRIGGER: adb reboot autodloader (no key press needed)")
adb(["reboot", "autodloader"], 15)
for _ in range(30):
    if ready.is_set():
        break
    time.sleep(2)
note("connected=%s markers=%s" % (ready.is_set(), ",".join(markers) or "none"))

status = "NO_CONNECTION"
if ready.is_set():
    status = "CONNECTED"
    note("=== FDL2 SESSION: READ-ONLY partition backup ===")
    for cmd in CMDS:
        try:
            proc.stdin.write((cmd + "\n").encode())
            proc.stdin.flush()
            note("SENT: " + cmd)
        except Exception as e:
            note("stdin write failed: %s" % e)
            break
        # partition reads take much longer than setup commands
        time.sleep(3 if cmd.split()[0] in ("verbose", "path", "p", "reset") else 10)
    note("all commands sent; waiting 90s for large transfers to finish")
    time.sleep(90)
else:
    note("no FDL2 session - no backup performed")

# `reset` was sent above; give the device time to reboot cleanly
note("=== WAITING FOR ANDROID (up to 180s) ===")
back = False
for i in range(36):
    time.sleep(5)
    if adb_online():
        back = True
        note("Android is back after %ds" % ((i + 1) * 5))
        break

try:
    proc.terminate()
except Exception:
    pass

state = {}
if back:
    state["boot"] = adb(["shell", "getprop sys.boot_completed"], 10)
    state["BL"] = adb(["shell", "getprop ro.boot.flash.locked"], 10)
    state["verified"] = adb(["shell", "getprop ro.boot.verifiedbootstate"], 10)
    state["battery"] = adb(["shell", "dumpsys battery | grep -i level:"], 10)
    note("FINAL: " + str(state))
else:
    note("WARNING: Android not back. Hold POWER 10-15s. No data was modified.")

produced = []
for fn in sorted(os.listdir(BACKUP)):
    fp = os.path.join(BACKUP, fn)
    if os.path.isfile(fp):
        produced.append((fn, os.path.getsize(fp)))
total = sum(sz for _, sz in produced)
ok = [fn for fn, sz in produced if sz > 0]

lines = [
    "# W202DS STOCK PARTITION BACKUP (read-only)",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Status: **" + status + "**",
    "- Trigger: `adb reboot autodloader` (device loads its own FDL, no key press)",
    "- Connection markers: " + (", ".join(markers) or "(none)"),
    "- Device back in Android: **" + ("YES" if back else "NO - hold POWER 10-15s") + "**",
    "- Files with data: **%d / %d** | total **%.1f MB**" % (len(ok), len(PARTS), total / 1048576.0),
    "",
    "## Backed-up partitions",
    "",
]
for fn, sz in produced:
    lines.append("- `%s` - %s" % (fn, ("%.1f MB" % (sz / 1048576.0)) if sz else "0 bytes (failed)"))
if not produced:
    lines.append("(none)")
lines += [
    "",
    "## Final device state",
    "",
]
for k, v in state.items():
    lines.append("- %s: `%s`" % (k, v))
if not state:
    lines.append("(unavailable - device not back via adb)")
lines += [
    "",
    "## Why this matters",
    "",
    "Non-empty `boot_a` / `init_boot_a` / `vendor_boot_a` / `vbmeta_a` / `uboot_a`",
    "are the ORIGINAL restore images for build `100240302`. With them, any later",
    "unlock / Magisk attempt has something to flash back - this is the anti-brick",
    "prerequisite that was missing for the whole project.",
    "",
    "Magisk patch target still must be decided by inspecting the dumped image",
    "headers (boot vs init_boot vs vendor_boot) - do NOT guess.",
    "",
    "NOTE: strictly read-only. No unlock, no wipe, no partition write, no BL change.",
    "Only `reset` (plain reboot) was sent, which writes nothing.",
    "",
    "Log: `auto_backup.log`",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
note("REPORT: " + REPORT)
note("FILES WITH DATA: %d, TOTAL %.1f MB" % (len(ok), total / 1048576.0))
logf.close()
