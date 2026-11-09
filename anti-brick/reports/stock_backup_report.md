# W202DS STOCK PARTITION BACKUP (read-only) - build 100240302

- Time: 2026-11-08 16:16:14
- Method: `adb reboot autodloader` + `spd_dump ... r <part> reset`
- spd_dump finished naturally: **YES**
- Connection markers: BSL_REP_VER, CMD_CONNECT, Read Part Done
- Device back in Android: **YES**
- Files with data: **21 / 21** | total **390.1 MB**

## Backed-up partitions (original images, restore-ready)

- `boot_a` - 64.0 MB
- `boot_b` - 64.0 MB
- `dtb_a` - 8.0 MB
- `dtb_b` - 8.0 MB
- `dtbo_a` - 8.0 MB
- `dtbo_b` - 8.0 MB
- `init_boot_a` - 8.0 MB
- `init_boot_b` - 8.0 MB
- `misc` - 1.0 MB
- `persist` - 2.0 MB
- `sml_a` - 0.1 MB
- `splloader` - 0.1 MB
- `trustos_a` - 4.8 MB
- `uboot_a` - 1.1 MB
- `uboot_b` - 1.1 MB
- `vbmeta_a` - 1.0 MB
- `vbmeta_b` - 1.0 MB
- `vbmeta_system_a` - 1.0 MB
- `vbmeta_vendor_a` - 1.0 MB
- `vendor_boot_a` - 100.0 MB
- `vendor_boot_b` - 100.0 MB

## Final device state

- boot: ``
- BL: `1`
- verified: `green`
- battery: `level: 100`

## Next steps / cautions

Non-empty `boot_a` / `init_boot_a` / `vendor_boot_a` / `vbmeta_a` / `uboot_a`
are the ORIGINAL restore images for build `100240302`. The anti-brick
prerequisite is now satisfied: any failed flash can be rolled back with
`spd_dump ... w <part> <file>`.

Magisk patch target MUST be decided by inspecting dumped image headers
(Android 13 GKI: ramdisk usually in `init_boot`, but this Unisoc platform
marks `boot_a` as LK type - verify from the bytes, do NOT guess).

NOTE: strictly read-only. No unlock, no wipe, no partition write, no BL change.
Only `reset` (plain reboot) was sent; it writes nothing.

Full log: `stock_backup.log`
