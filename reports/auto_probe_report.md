# W202DS automatic BootROM read-only probe

- Time: 2026-11-08 12:52:31
- Status: **CONNECTED**
- Reboot reason used: autodloader
- Connection markers: BSL_REP_VER, CMD_CONNECT, FDL2 >
- Device returned to Android: **NO - hold POWER 10-15s**

## Final device state

(not available - device not back via adb)

## Raw dumps produced (READ-ONLY)

- `brom_mem0.bin` - 0 bytes
- `flash_b_4k.bin` - 0 bytes

## What the result means

If any `flash_*.bin` is non-empty, BootROM allowed raw flash reads WITHOUT
FDL. That is the breakthrough: GPT + stock partitions can be dumped, giving
us restore images before any unlock attempt.

If no dumps: this secure-boot BootROM blocks flash reads. A partition dump
would then require FDL1/FDL2 from a stock .pac firmware, which we do not
have - option 2 has reached its technical limit.

NOTE: Nothing was written to the device. No unlock, no wipe, no partition
modification, no bootloader change. BL remains locked / green.

Logs: `auto_probe.log` (full timeline), `brom_session.log` (older runs)
