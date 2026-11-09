# Write-back verification (content-identical)

- Time: 2026-11-08 17:00:33
- Purpose: prove partitions can be WRITTEN back via the rescue channel.
- What was written: original `misc` image -> same `misc` partition (byte-identical).
- Connection markers: EXEC FDL1, EXEC FDL2, Read Part Done, write, Write Part Done
- spd_dump finished naturally: **YES**
- Device back in Android: **YES**
- Verdict: **MATCH - write-back works, content unchanged**

## Final device state

- boot: ``
- BL: `1`
- verified: `green`
- battery: `Can't find service: battery`

This completes the anti-brick proof: the external-FDL channel can BOTH
read and write partitions, so any bricked partition covered by the backup
can be restored. No unlock, no wipe, no AVB change, no content modification.

Log: `verify_writeback.log`
