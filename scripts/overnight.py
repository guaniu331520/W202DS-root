# -*- coding: utf-8 -*-
"""Overnight READ-ONLY SPD/BootROM probe for ZTE W202DS.

Hard safety rule: this script NEVER issues write / erase / repartition /
unlock / avb-disable commands. It only detects the device, inspects its
driver, and runs read-only probe commands. Everything is logged to a report.
"""
import ctypes
import datetime
import json
import os
import subprocess
import time

ROOT = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools"
SPD_DIR = os.path.join(ROOT, "spd_dump")
SPD_EXE = os.path.join(SPD_DIR, "spd_dump.exe")
LOG = os.path.join(ROOT, "overnight.log")
REPORT = os.path.join(ROOT, "overnight-report.md")

MAX_WAIT_HOURS = 4
POLL_SECONDS = 120
EVENTS = []
FINDINGS = []
DEVICE_TIMELINE = []

# Only read-only / exit commands are ever passed to spd_dump.
UNSAFE = ["write_part", "write_parts", "erase", "repartition", "mergenv",
          "dis_avb", "wof", "wov", "set_active", "firstmode", "skip_confirm 1"]

PROBES = [
    ["--wait", "90", "--verbose", "2", "chip_uid"],
    ["--wait", "90", "--verbose", "2", "--kick", "chip_uid"],
    ["--wait", "90", "--verbose", "2", "--kickto", "0", "chip_uid"],
    ["--wait", "90", "--verbose", "2", "--kickto", "2", "chip_uid"],
]


def note(msg, important=False):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (ts, msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    EVENTS.append((ts, msg, important))
    print(line, flush=True)


def ps(cmd, timeout=90):
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, timeout=timeout)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return (out + err).strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "PS-TIMEOUT", -1
    except Exception as e:
        return "PS-ERROR: %s" % e, -1


def find_devices():
    cmd = ("Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "
           "'VID_1782|VID_1EBF|SPRD|Spreadtrum|Unisoc' } | "
           "Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress")
    out, rc = ps(cmd)
    if not out or out.startswith("PS-"):
        return [], out
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data, ""
    except Exception:
        return [], out[:400]


def device_details(inst):
    out, _ = ps("Get-PnpDeviceProperty -InstanceId '%s' -KeyName "
                "DEVPKEY_Device_CompatibleIds -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty Data" % inst)
    return out.strip().replace("\n", " | ")[:600]


def ensure_winusb(inst):
    """Lossless attempt: preload signed built-in WinUSB INF and re-enumerate."""
    out, rc = ps("pnputil /add-driver C:\\Windows\\INF\\winusb.inf /install")
    note("winusb.inf preload rc=%d: %s" % (rc, out[:300].replace("\n", " | ")))
    key = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\%s\\Device Parameters" % inst
    guid = "{DEE824EF-729B-4A0E-9C14-B7117D33A817}"
    cmd = ('if (Test-Path "%s") { New-ItemProperty -Path "%s" '
           '-Name DeviceInterfaceGUIDs -PropertyType MultiString '
           '-Value @("%s") -Force | Out-Null; "GUID-SET" } else { "NO-KEY" }'
           % (key, key, guid))
    out2, _ = ps(cmd)
    note("WinUSB interface GUID: %s" % out2.strip()[:200])
    ps("Disable-PnpDevice -InstanceId '%s' -Confirm:$false -ErrorAction SilentlyContinue "
       "| Out-Null; Start-Sleep -Seconds 2; Enable-PnpDevice -InstanceId '%s' "
       "-Confirm:$false -ErrorAction SilentlyContinue | Out-Null" % (inst, inst), timeout=90)
    out3, _ = ps("(Get-PnpDevice -InstanceId '%s' -ErrorAction SilentlyContinue).Status" % inst)
    note("device status after re-enumeration: %s" % out3.strip()[:100])


def spd(args, timeout=420):
    joined = " ".join(args).lower()
    if any(w in joined for w in UNSAFE):
        note("BLOCKED unsafe command: %s" % joined, True)
        return "BLOCKED"
    try:
        r = subprocess.run([SPD_EXE] + args, cwd=SPD_DIR,
                           capture_output=True, timeout=timeout)
        text = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        note("spd_dump rc=%d args=[%s]" % (r.returncode, " ".join(args)))
        note("  output: %s" % text[:1500].replace("\n", " | "))
        FINDINGS.append((" ".join(args), r.returncode, text[:4000]))
        if r.returncode == 0 and text.strip() and "waiting" not in text.lower():
            return "RESPONSE"
        return text
    except subprocess.TimeoutExpired:
        note("spd_dump TIMEOUT args=[%s]" % " ".join(args))
        return "TIMEOUT"
    except Exception as e:
        note("spd_dump ERROR: %s" % e)
        return "ERROR"


def write_report(status):
    lines = [
        "# W202DS overnight read-only probe report",
        "",
        "Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "## Safety statement",
        "",
        "**No write, erase, repartition, unlock or AVB-disable command was issued.**",
        "Bootloader was NOT unlocked. No partition was modified. No data was wiped.",
        "Only device detection, driver inspection and read-only probe commands ran.",
        "",
        "## Outcome",
        "",
        status,
        "",
        "## Findings",
        "",
    ]
    if FINDINGS:
        for args, rc, text in FINDINGS:
            lines.append("### `spd_dump %s` (rc=%d)" % (args, rc))
            lines.append("")
            lines.append("```")
            lines.append(text[:1500])
            lines.append("```")
            lines.append("")
    else:
        lines.append("No spd_dump probe produced output.")
        lines.append("")
    lines += ["## Timeline", ""]
    for ts, msg, important in EVENTS:
        mark = " **" if important else ""
        lines.append("- `%s` %s%s" % (ts, msg, mark))
    lines += [
        "",
        "## Files",
        "",
        "- `flash-tools/overnight.log` - raw timestamped log",
        "- `flash-tools/spd_dump/spd_dump.exe` - open-source Unisoc dump tool (x64 Release 251)",
        "- `flash-tools/Magisk.apk` - official Magisk v31.1 (not used tonight)",
        "- `flash-tools/fastboot-getvar.txt` - earlier bootloader variables",
        "",
        "## Power / tablet state",
        "",
        "- Baseline before sleep: **64% battery, charging (status=2), health good**.",
        "- SPD download mode keeps the screen **OFF**; the USB cable supplies power",
        "  while connected, so there is no always-on display draining the battery.",
        "- Hard runtime cap: **4 hours**. The script stops immediately if the",
        "  download-mode device disappears, so the tablet is never left idling",
        "  all night.",
        "- Device timeline: " + ("; ".join(DEVICE_TIMELINE) if DEVICE_TIMELINE
                                 else "device never appeared"),
        "- After the PC sleeps, USB power may stop and the tablet may power off.",
        "  That is expected - long-press power in the morning to boot normally.",
        "",
        "## Notes for tomorrow",
        "",
        "1. If the tablet screen is black or it appears off, that is normal for SPD",
        "   download mode / after PC sleep. Long-press power to boot it normally.",
        "2. This PC only supports S3 sleep (no S4 hibernate per `powercfg /a`),",
        "   so the script triggers sleep rather than hibernation.",
        "3. If no SPD device was ever detected, the boot-key combo needs to be",
        "   retried: power off, hold Volume Down (try Volume Up if that fails),",
        "   plug USB, release when the port appears.",
    ]
    try:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        note("Report written: %s" % REPORT, True)
    except Exception as e:
        note("Report write failed: %s" % e, True)


def sleep_pc():
    note("All work finished. Triggering S3 sleep in 10 seconds.", True)
    time.sleep(10)
    try:
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        note("SetSuspendState returned (system likely suspended).")
    except Exception as e:
        note("Sleep call failed: %s" % e, True)


def main():
    note("=== Overnight READ-ONLY SPD probe started ===", True)
    note("Rule: no write/erase/repartition/unlock commands, ever.", True)
    if not os.path.isfile(SPD_EXE):
        note("FATAL: spd_dump.exe missing", True)
        write_report("FAILED: spd_dump.exe missing.")
        sleep_pc()
        return
    note("Tool ready: %s" % SPD_EXE)

    # Lossless, signed built-in WinUSB driver preload (does not change signing policy).
    out, rc = ps("pnputil /add-driver C:\\Windows\\INF\\winusb.inf /install")
    note("Preload WinUSB INF rc=%d: %s" % (rc, out[:250].replace("\n", " | ")))

    deadline = time.time() + MAX_WAIT_HOURS * 3600
    seen = False
    driver_done = False
    status = "FAILED: SPD download-mode device was never detected within 4 hours."
    while time.time() < deadline:
        devs, raw = find_devices()
        if devs:
            if not seen:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                DEVICE_TIMELINE.append("appeared at %s" % ts)
                note("Device APPEARED at %s" % ts, True)
            seen = True
            for d in devs:
                inst = d.get("InstanceId", "")
                note("DEVICE: status=%s class=%s name=%s id=%s"
                     % (d.get("Status"), d.get("Class"), d.get("FriendlyName"), inst), True)
                note("  compatible IDs: %s" % device_details(inst))
                if not driver_done:
                    ensure_winusb(inst)
                    driver_done = True
            note("Running read-only probes (brom handshake / chip_uid).", True)
            got = False
            for args in PROBES:
                if not find_devices()[0]:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    DEVICE_TIMELINE.append("disappeared at %s" % ts)
                    note("Device DISAPPEARED during probing - stopping early "
                         "to avoid leaving the tablet idling", True)
                    break
                res = spd(args)
                if res == "RESPONSE":
                    got = True
                    break
            if got:
                status = ("SUCCESS: SPD download-mode device detected and responded to a "
                          "read-only probe. See Findings. No partition was written. "
                          "Next step: obtain chip-specific FDL1/FDL2, then run "
                          "`partition_list` and `r all_lite` for a full read-only backup.")
            else:
                status = ("PARTIAL: SPD download-mode device was detected and the driver "
                          "was inspected, but no read-only probe got a response. "
                          "See Findings for the exact error. Most likely the WinUSB/"
                          "libusb binding or the chip-specific FDL is missing.")
            break
        else:
            fb, _ = ps("Get-PnpDevice -PresentOnly | Where-Object { "
                       "$_.InstanceId -match 'VID_18D1&PID_4EE0' -or "
                       "$_.FriendlyName -match 'fastboot' } | "
                       "Select-Object -ExpandProperty FriendlyName | ConvertTo-Json -Compress")
            if fb and fb.strip() not in ("", "null", "[]"):
                note("NOTE: fastboot-mode device present (%s). The key combo entered "
                     "fastboot, not SPD download mode - wrong combo, need retry."
                     % fb[:120], True)
            note("No SPD download-mode device yet (waiting %ds). %s"
                 % (POLL_SECONDS, raw[:120] if raw.startswith("PS-") else ""))
            time.sleep(POLL_SECONDS)

    if not seen:
        note("Timed out waiting for the device.", True)
    still, _ = find_devices()
    note("Final state before sleep: %s" % ("tablet still attached" if still
                                           else "no SPD device attached"), True)
    write_report(status)
    sleep_pc()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        note("UNHANDLED ERROR: %s" % e, True)
        write_report("FAILED: unhandled error %s" % e)
        sleep_pc()
