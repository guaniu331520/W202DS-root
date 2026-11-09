# W202DS BootROM read-only probe report

- Time: 2026-11-08 12:42:40
- Status: **NO_CONNECTION**
- Connection markers seen: (none)
- Commands attempted: verbose, timeout, path, p, read_mem, read_flash, read_flash, read_flash, read_flash, partition_list, p

## Files produced (raw dumps, READ-ONLY)

(none - BROM rejected the read commands or no session)

## Interpretation

- If `flash_head_*.bin` is non-empty: BROM allowed raw flash reads. This is
  the breakthrough - GPT and stock partitions can be dumped WITHOUT any FDL,
  which gives us the restore images needed before any unlock.
- If no files: BROM blocks flash reads on this secure-boot device. Then the
  only remaining route to a partition dump needs FDL1/FDL2 from a stock .pac
  firmware, which we do not have - option 2 has reached its technical limit.

Raw log: `brom_session.log`

NOTE: Nothing was written to the device. No unlock, no wipe, no partition
modification. The tablet is safe regardless of this result.
