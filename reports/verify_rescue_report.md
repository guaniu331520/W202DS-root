# Rescue-path verification (READ-ONLY)

- Time: 2026-11-08 16:53:24
- Purpose: prove that bricked splloader/uboot/sml/trustos can still be
  recovered via BootROM + EXTERNAL fdl1/fdl2 (RAM only, no partition write).
- exec_addr: `0x65012f48` (ums9620-specific payload)
- Connection markers: BSL_REP_VER, CMD_CONNECT, EXEC FDL1, EXEC FDL2, Read Part Done
- spd_dump finished naturally: **YES**
- Device back in Android: **YES**
- Verdict: **MATCH - external FDL can read partitions correctly**

## Final device state

- boot: ``
- BL: `1`
- verified: `green`

NOTE: strictly read-only. No partition was written, erased or modified.
Only `r misc` (read) and `reset` (plain reboot) were sent.

Full log: `verify_rescue.log`
