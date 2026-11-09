# 防变砖 / 救援资料（Anti-Brick）

本目录汇总本次 root 过程中**用于防止变砖、以及变砖后救回**的全部可文本化资料：备份脚本、救援通道验证脚本、分区校验与回写验证脚本、原始日志、报告与哈希清单。

> 所有日志与报告均已脱敏：设备序列号 → `<DEVICE_SERIAL>`，本地绝对路径 → `<WORKDIR>`。

---

## 1. 三条铁律（动手前必读）

1. **先完整备份并校验哈希**，再动任何一个分区。
2. **先验证 BootROM / FDL 救援通道能重复进入**，不要只成功一次就开刷。这是 BL 锁定时唯一的退路。
3. **一次只改一个分区，写完立刻回读比对**，确认无误再进行下一步。

本次正是按这个顺序做的：`stock_backup.py` → `verify_partition.py` → `verify_rescue.py` → `brom_session.py` → `flash_part.py` → `verify_writeback.py`。

---

## 2. 目录结构

| 子目录 | 内容 |
|---|---|
| `scripts/` | `stock_backup.py`（全分区备份）、`auto_backup.py`、`brom_session.py`（BROM 会话）、`verify_rescue.py`（救援通道验证）、`verify_partition.py`（分区校验）、`flash_part.py`（写入）、`verify_writeback.py`（回读比对）、`W202DS-spd.cfg`（SPD 配置） |
| `reports/` | `stock_backup_report.md`、`brom_probe_report.md`、`verify_rescue_report.md`、`verify_writeback_report.md`、`stock_backup_SHA256.txt`（**原厂镜像哈希清单**） |
| `logs/` | 上述步骤的原始日志：`stock_backup.log`、`flash_trustos.log`、`flash_boot_a.log`、`verify_*.log`、`brom_session.log` |

---

## 3. 原厂镜像本体（不在本仓库，务必本地保管）

原厂分区备份保存在本地 `flash-tools/stock_backup/`，共 21 个文件、约 400 MB：

| 分区 | 大小 | 说明 |
|---|---|---|
| `boot_a` / `boot_b` | 各 64 MB | 内核 / ramdisk，**root 改动的就是 `boot_a`** |
| `vendor_boot_a` / `vendor_boot_b` | 各 100 MB | vendor 启动镜像 |
| `trustos_a` | 5 MB | **本次 patched 的目标**（禁用 AVB 强制校验） |
| `dtb_a/b`、`dtbo_a/b`、`init_boot_a/b` | 各 8 MB | 设备树 / init boot |
| `vbmeta_a/b`、`vbmeta_system_a`、`vbmeta_vendor_a` | 各 1 MB | AVB 校验元数据 |
| `uboot_a/b`、`sml_a`、`splloader` | 1.1 MB / 138 KB / 65 KB | 启动链 |
| `misc`、`persist` | 1 MB / 2 MB | 杂项与持久化数据 |

**为什么不入库**：单个文件 64~100 MB、含设备唯一数据与厂商镜像，公开分发不合适；GitHub 单文件上限 100 MB，仓库体积也不宜过大。哈希清单 `reports/stock_backup_SHA256.txt` 已入库，**回刷前用它校验本地镜像是否完好**：

```bash
cd flash-tools/stock_backup
sha256sum -c ../stock_backup_SHA256.txt
```

> 如果确实需要把镜像也放到云端，建议用私有存储或 GitHub Release 附件（不走仓库文件）。

---

## 4. 救砖流程（BL locked 下唯一可靠路径）

```bash
# 0) 确认电脑能识别设备的 BootROM / FDL 通道
python3 anti-brick/scripts/brom_session.py
python3 anti-brick/scripts/verify_rescue.py      # 必须能重复进入

# 1) 校验本地原厂镜像没坏
cd flash-tools/stock_backup && sha256sum -c ../stock_backup_SHA256.txt

# 2) 写回原厂 trustos_a 与 boot_a（先用脚本的 dry-run / 分区参数确认目标）
python3 anti-brick/scripts/flash_part.py

# 3) 回读比对，确认写入正确
python3 anti-brick/scripts/verify_writeback.py

# 4) 重启
adb reboot
adb wait-for-device
adb shell getprop sys.boot_completed
```

写入日志见 `logs/flash_trustos.log` 与 `logs/flash_boot_a.log`，可逐条核对分区、偏移与长度。

---

## 5. 软变砖：Magisk 安全模式（本次真实发生过）

模块导致启动异常时，Magisk 的 bootloop 保护会给每个模块目录自动创建 `disable` 文件并禁用全部模块，表现为：

- `which su` 为空、`/system_ext/bin/magisk` 消失；
- 但 `magiskd` 进程仍在、Magisk Manager 仍在 —— **root 没有丢**。

备用 root 入口（安全模式下依然可用）：

```bash
adb shell /debug_ramdisk/su -c 'id'
# uid=0(root) gid=0(root) context=u:r:magisk:s0
```

恢复干净状态：

```bash
adb shell /debug_ramdisk/su -c '
  rm -rf /data/adb/modules/<出问题的模块>
'
adb reboot
adb wait-for-device
adb shell su -c 'id'                 # su 回到 /system_ext/bin/su
adb shell su -c 'ls /data/adb/modules/'   # 应为空
```

本次触发原因：`gms_priv` 模块在 `post-fs-data` 阶段 bind 覆盖 `/product/etc/permissions` 且 `service.sh` 跑得比 PackageManager 早，导致启动异常；系统自动回滚，**数据与原厂分区均未受损**。

---

## 6. 本次实测记录

| 检查项 | 结果 |
|---|---|
| 全分区备份 | 21 个分区，SHA256 全部校验通过 |
| BootROM / FDL 救援通道 | 可重复进入（见 `reports/brom_probe_report.md`、`verify_rescue_report.md`） |
| patched trustos + Magisk boot_a 写入 | 成功，回读比对通过 |
| 启动与 root 验证 | `sys.boot_completed=1`，`su -c id` → `uid=0(root)` |
| 模块导致启动异常 | Magisk 自动禁用全部模块；删模块重启后完整恢复 |

---

## 7. 命令速查

```bash
# 备份与校验
python3 anti-brick/scripts/stock_backup.py
python3 anti-brick/scripts/verify_partition.py
sha256sum -c anti-brick/reports/stock_backup_SHA256.txt

# 救援通道
python3 anti-brick/scripts/brom_session.py
python3 anti-brick/scripts/verify_rescue.py

# 软变砖恢复
adb shell /debug_ramdisk/su -c 'id'
adb shell /debug_ramdisk/su -c 'rm -rf /data/adb/modules/<模块名>'
adb reboot
```

> 刷机与修改 AVB 校验均有变砖风险，本文仅为单台设备的实测记录。动手前务必完整备份并确认救援通道可用。
