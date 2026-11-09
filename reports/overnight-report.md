# W202DS overnight read-only probe - final report

Generated: 2026-11-08 00:18 (session paused; no unattended run was left spinning)

## Safety statement

**No write, erase, repartition, unlock or AVB-disable command was issued.**
Bootloader is still `locked`, `verifiedbootstate=green`, no data wiped.
The tablet is back in normal Android with USB adb online. Battery was 64% and charging.

## Outcome: key combo CONFIRMED, unattended backup NOT completed

The user performed the boot-key combo once. A live 120-second USB monitor recorded:

```
00:13:21 | Error | Sprd Gadget Serial | USB\VID_1782&PID_4D00\5&3478949&0&1
... (present until about 00:13:52)
00:14:04 | OK | 中兴云电脑 | USB\VID_19D2&PID_1352\...
00:14:29 | OK | ADB Interface | USB\VID_19D2&PID_0306&MI_01\...
```

Conclusions:

1. **The combo is correct**: `Sprd Gadget Serial`, `VID_1782&PID_4D00` is exactly the
   Unisoc BootROM / SPD download-mode port. No `VID_18D1&PID_4EE0` (fastboot) device
   appeared, so it was NOT the wrong combo. Combination used:
   power off -> plug USB -> hold **Power + Volume Down ~8-10 s** -> release.
   Volume Up is NOT needed for this model.
2. **The window is short**: the download-mode port stayed for only ~30-40 s, then the
   tablet continued booting back into Android. BootROM gives up if no host connects.
3. **The host could not connect** because the port had no driver:
   - `ProblemCode 28` (driver not installed)
   - CompatibleIds: `USB\Class_FF&SubClass_00&Prot_00`, `USB\COMPAT_VID_1782&Class_FF`, ...
   - No `USB\MS_COMP_WINUSB`, so Windows never auto-binds WinUSB.
4. Fixing it needs a driver INF matching `USB\VID_1782&PID_4D00`. A local INF that
   references the signed built-in `winusb.inf` was created (`spd_winusb.inf`), but
   `pnputil` refused it: **"third-party INF does not contain digital signature
   information"**. Windows 11 driver signature enforcement blocks it.
   Installing it therefore requires temporarily enabling test-signing mode and a
   reboot - a system-level security change that was deliberately NOT performed
   while the user was asleep.

Because the tablet cannot re-enter download mode without a physical key press, an
unattended 4-hour loop would have produced nothing while keeping the PC awake and
the tablet idle. The scheduled task was therefore stopped instead of left spinning.

## What IS ready for tomorrow

- `flash-tools/spd_dump/spd_dump.exe` - open-source Unisoc dumper, x64 Release ver 251
  (2026-11-02 build), with its bundled `libusb-1.0.dll`. Verified runnable (`--help`).
- `flash-tools/spd_winusb.inf` - WinUSB binding INF (blocked only by signature policy).
- `flash-tools/usb_driver/` - official Google USB Driver r13 (already installed,
  this is what makes fastboot work).
- `flash-tools/Magisk.apk` - official Magisk v31.1, zip integrity verified, unused.
- `flash-tools/fastboot-getvar.txt` - earlier bootloader variables.
- `flash-tools/overnight.py` - read-only probe script (4 h cap, disconnect detection,
  report + S3 sleep). Kept for tomorrow.
- `flash-tools/usb-monitor.log` - full 120 s device timeline.

## Tomorrow's 10-minute plan (needs the user present)

1. Resolve the driver: either find a WHQL-signed SPD U2S Diag driver, or briefly
   enable test-signing mode with the user's explicit consent, then install
   `spd_winusb.inf` and verify the port becomes `OK`.
2. Start `spd_dump --wait 300 ...` FIRST so it is already waiting for the port.
3. User repeats the confirmed combo once (Power + Volume Down, plug USB, ~10 s).
   The host connects inside the 30-40 s window, which keeps BootROM waiting instead
   of booting Android.
4. Read-only commands only: `chip_uid`, `partition_list`, then `r all_lite` for a
   full partition backup into `flash-tools/backup/`.
5. Only after a verified backup exists, revisit the unlock / Magisk discussion.

## Notes

- The PC only supports S3 sleep (no S4 hibernate per `powercfg /a`).
- Black screen in download mode is normal; a charging animation means it did not work.
- Scheduled task name: `W202DS_Overnight_ReadOnly_Probe` (stopped after diagnosis;
  a separate one-shot task triggers the final sleep).
