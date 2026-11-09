# -*- coding: utf-8 -*-
"""Hold a BootROM interactive session and run READ-ONLY probe commands.

spd_dump with no command arguments enters "BROM >" interactive mode, which keeps
the device waiting instead of letting it boot Android after ~30-40 seconds.
Only read-only commands are sent; no write/erase/repartition/unlock/fdl/exec.

Findings that shaped this version:
 - The tool package ships NO FDL1/FDL2 binaries; `r all` / `read_part` need FDL2.
 - BROM-stage native commands (read_flash / read_mem) may read raw flash without
   any FDL. That is the only path that can bypass the "no stock firmware" loop.
 - `chip_uid` timed out on this device before, so it is removed (it hangs stdin).
"""
import os
import subprocess
import threading
import time

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
SPD_DIR = os.path.join(ROOT, "spd_dump")
EXE = os.path.join(SPD_DIR, "spd_dump.exe")
LOG = os.path.join(ROOT, "brom_session.log")
REPORT = os.path.join(ROOT, "brom_probe_report.md")
BACKUP = os.path.join(ROOT, "backup")
os.makedirs(BACKUP, exist_ok=True)

# READ-ONLY ONLY. No w/write_part/erase/repartition/exec/fdl/reset.
# BROM-stage BSL native read commands (read_flash/read_mem) need NO FDL - this
# is the only known way to get a stock partition dump without a .pac firmware.
# Try several addr/offset forms since Unisoc BSL variants differ.
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

proc = subprocess.Popen(
    [EXE, "--wait", "3600", "--verbose", "2"],
    cwd=SPD_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, bufsize=0)

logf = open(LOG, "wb", buffering=0)
ready = threading.Event()
recent = bytearray()
CONNECTED = []


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
        for marker in (b"BROM >", b"FDL1 >", b"FDL2 >", b"BSL_REP_VER", b"CMD_CONNECT"):
            if marker in cur and marker.decode() not in CONNECTED:
                CONNECTED.append(marker.decode())
        if b"BROM >" in cur or b"FDL1 >" in cur or b"FDL2 >" in cur:
            ready.set()


threading.Thread(target=reader, daemon=True).start()
print("spd_dump started, waiting for BootROM (3600s)", flush=True)

if not ready.wait(3600):
    print("TIMEOUT: no interactive prompt; device did not enter download mode", flush=True)
    status = "NO_CONNECTION"
else:
    print("Interactive prompt detected. Sending read-only commands.", flush=True)
    status = "CONNECTED"
    for cmd in CMDS:
        try:
            proc.stdin.write((cmd + "\n").encode())
            proc.stdin.flush()
            print("SENT: " + cmd, flush=True)
        except Exception as e:
            print("stdin write failed: %s" % e, flush=True)
            break
        time.sleep(6)
    time.sleep(20)

try:
    proc.terminate()
except Exception:
    pass
logf.close()

# ---- auto report, so no need to wait for the assistant ----
produced = []
for fn in sorted(os.listdir(BACKUP)):
    fp = os.path.join(BACKUP, fn)
    if os.path.isfile(fp):
        produced.append((fn, os.path.getsize(fp)))

lines = [
    "# W202DS BootROM read-only probe report",
    "",
    "- Time: " + time.strftime("%Y-%m-%d %H:%M:%S"),
    "- Status: **" + status + "**",
    "- Connection markers seen: " + (", ".join(CONNECTED) if CONNECTED else "(none)"),
    "- Commands attempted: " + ", ".join(c.split()[0] for c in CMDS),
    "",
    "## Files produced (raw dumps, READ-ONLY)",
    "",
]
if produced:
    for fn, sz in produced:
        lines.append("- `%s` - %d bytes" % (fn, sz))
else:
    lines.append("(none - BROM rejected the read commands or no session)")
lines += [
    "",
    "## Interpretation",
    "",
    "- If `flash_head_*.bin` is non-empty: BROM allowed raw flash reads. This is",
    "  the breakthrough - GPT and stock partitions can be dumped WITHOUT any FDL,",
    "  which gives us the restore images needed before any unlock.",
    "- If no files: BROM blocks flash reads on this secure-boot device. Then the",
    "  only remaining route to a partition dump needs FDL1/FDL2 from a stock .pac",
    "  firmware, which we do not have - option 2 has reached its technical limit.",
    "",
    "Raw log: `brom_session.log`",
    "",
    "NOTE: Nothing was written to the device. No unlock, no wipe, no partition",
    "modification. The tablet is safe regardless of this result.",
    "",
]
with open(REPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("report written: " + REPORT, flush=True)
print("session closed; log: " + LOG, flush=True)
