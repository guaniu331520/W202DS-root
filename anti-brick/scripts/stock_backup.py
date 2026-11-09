# -*- coding: utf-8 -*-
"""READ-ONLY stock partition backup for ZTE W202DS (build 100240302).

Uses the verified `adb reboot autodloader` path: the device boots its OWN
splloader -> FDL1 -> FDL2, no external FDL binary, no key press, no firmware
package. spd_dump is invoked in COMMAND-LINE mode so it executes each command
sequentially and naturally waits for every large partition transfer to finish.

CRITICAL (learned from the failed auto_probe.py run):
  - `read_flash` / `read_mem` are BROM-stage commands. In FDL2 they return
    `Partition not found (0x00fe)` and can hang USB with LIBUSB_ERROR_TIMEOUT.
    NEVER send them here. Only `r <part_name>` is valid in FDL2.
  - Terminating spd_dump mid-session leaves the device stuck in FDL2. Always
    finish with `reset` (BSL_CMD_NORMAL_RESET = plain reboot, writes nothing).

SAFETY: strictly read-only. No write_part/erase/repartition/unlock/exec/fdl.
        BL stays locked / green; no data is modified.
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
LOG = os.path.join(ROOT, "stock_backup.log")
REPORT = os.path.join(ROOT, "stock_backup_report.md")
BACKUP = os.path.join(ROOT, "stock_backup")
os.makedirs(BACKUP, exist_ok=True)

# Ordered by importance: if anything fails mid-way, core images are already on disk.
# Both slots are kept so either slot can be restored. Excludes userdata(109GB),
# cache, blackbox, super(6.3GB). Total ~400MB.
PARTS = [
    "boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "uboot_a",
    "splloader", "boot_b", "init_boot_b", "vendor_boot_b", "vbmeta_b",
    "uboot_b", "dtb_a", "dtbo_a", "dtb_b", "dtbo_b",
    "vbmeta_system_a", "vbmeta_vendor_a", "sml_a", "trustos_a",
    "misc", "persist",
]

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


def start_server():
    try:
        subprocess.run([ADB, "start-server"], capture_output=True, timeout=25)
    except Exception:
        pass
    time.sleep(1)


# ---------------- baseline ----------------
note("=== BASELINE (before anything touches the device) ===")
start_server()
for i in range(5):
    if adb_online():
        break
    note("adb not ready (%d/5)" % (i + 1))
    start_server()
    time.sleep(2)
if not adb_online():
    note("FATAL: tablet not in Android. Power it on (hold POWER 10-15s). Nothing touched.")
    logf.close()
    raise SystemExit(2)
note("model: " + adb(["shell", "getprop ro.product.model"], 10))
note("build: " + adb(["shell", "getprop ro.build.display.id"], 10))
note("battery: " + adb(["shell", "dumpsys battery | grep -i level:"], 10))
note("BL: " + adb(["shell", "getprop ro.boot.flash.locked; getprop ro.boot.verifiedbootstate"], 10).replace("\n", " | "))

# ---------------- build the command line ----------------
# spd_dump options first, then runtime commands. `reset` MUST be last.
cmdline = [SPD_EXE, "--wait", "300", "--verbose", "1",
           "path", BACKUP, "timeout", "30000"]
for p in PARTS:
    cmdline += ["r", p]
cmdline += ["reset"]

note("spd_dump command line: %d args, %d partitions" % (len(cmdline), len(PARTS)))

proc = subprocess.Popen(cmdline, cwd=SPD_DIR, stdout=subprocess.PIPE,
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
        for m in (b"BSL_REP_VER", b"CMD_CONNECT", b"FDL2 >", b"Read Part Done",
                  b"part not exist", b"LIBUSB_ERROR_TIMEOUT"):
            s = m.decode()
            if m in cur and s not in markers:
                markers.append(s)
                note("MARKER: " + s)


threading.Thread(target=reader, daemon=True).start()
time.sleep(2)

# ---------------- trigger download mode ----------------
note("TRIGGER: adb reboot autodloader (no button press needed)")
adb(["reboot", "autodloader"], 15)

# ---------------- wait for spd_dump to finish naturally ----------------
# Do NOT kill it early. `reset` at the end reboots the device normally.
deadline = time.time() + 1500  # 25 min for ~400MB over SPD USB
last_count = -1
while proc.poll() is None and time.time() < deadline:
    time.sleep(10)
    try:
        files = [f for f in os.listdir(BACKUP) if os.path.isfile(os.path.join(BACKUP, f))]
    except Exception:
        files = []
    if len(files) != last_count:
        note("partition files on disk: %d / %d" % (len(files), len(PARTS)))
        last_count = len(files)

finished_naturally = proc.poll() is not None
note("spd_dump %s" % ("finished naturally" if finished_naturally else "still running at timeout"))
if not finished_naturally:
    note("WARNING: terminating spd_dump after timeout; device may need POWER 10-15s")
    try:
        proc.terminate()
    except Exception:
        pass

# ---------------- verify Android returns ----------------
note("=== WAITING FOR ANDROID (up to 180s) ===")
back = False
for i in range(36):
    time.sleep(5)
    if adb_online():
        back = True
        note("Android is back after %ds" % ((i + 1) * 5))
        break

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
ok = [(fn, sz) for fn, sz in produced if sz > 0]

lines = [
    "# W202DS STOCK PARTITION BACKUP (read-only) - build 100240302",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Method: `adb reboot autodloader` + `spd_dump ... r <part> reset`",
    "- spd_dump finished naturally: **" + ("YES" if finished_naturally else "NO") + "**",
    "- Connection markers: " + (", ".join(markers) or "(none)"),
    "- Device back in Android: **" + ("YES" if back else "NO - hold POWER 10-15s") + "**",
    "- Files with data: **%d / %d** | total **%.1f MB**" % (len(ok), len(PARTS), total / 1048576.0),
    "",
    "## Backed-up partitions (original images, restore-ready)",
    "",
]
for fn, sz in produced:
    lines.append("- `%s` - %s" % (fn, ("%.1f MB" % (sz / 1048576.0)) if sz else "0 bytes (FAILED)"))
if not produced:
    lines.append("(none)")
lines += ["", "## Final device state", ""]
for k, v in state.items():
    lines.append("- %s: `%s`" % (k, v))
if not state:
    lines.append("(unavailable - device not back via adb)")
lines += [
    "",
    "## Next steps / cautions",
    "",
    "Non-empty `boot_a` / `init_boot_a` / `vendor_boot_a` / `vbmeta_a` / `uboot_a`",
    "are the ORIGINAL restore images for build `100240302`. The anti-brick",
    "prerequisite is now satisfied: any failed flash can be rolled back with",
    "`spd_dump ... w <part> <file>`.",
    "",
    "Magisk patch target MUST be decided by inspecting dumped image headers",
    "(Android 13 GKI: ramdisk usually in `init_boot`, but this Unisoc platform",
    "marks `boot_a` as LK type - verify from the bytes, do NOT guess).",
    "",
    "NOTE: strictly read-only. No unlock, no wipe, no partition write, no BL change.",
    "Only `reset` (plain reboot) was sent; it writes nothing.",
    "",
    "Full log: `stock_backup.log`",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
note("REPORT: " + REPORT)
note("FILES WITH DATA: %d / %d, TOTAL %.1f MB" % (len(ok), len(PARTS), total / 1048576.0))
logf.close()
