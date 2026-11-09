# ZTE W202DS Root + microG / Aurora Store 实战教程

> 真机实测记录，2026-11-07 ~ 11-08。设备：ZTE W202DS（紫光展锐 ums9620），Android 13 / SDK 33 / arm64-v8a。
> 本文所有结论均有实机日志或命令输出支撑，不臆测、不省略失败路径。

---

## 0. 结论速览

| 目标 | 结果 |
|---|---|
| 取得 root | ✅ 成功（patched trustos 禁用 AVB + Magisk 修补 `boot_a`） |
| 应用 + ADB 都有 root，且**可随时开关** | ✅ 成功（Magisk Superuser 的 Shell 开关，不写入数据库） |
| 官方 Google Play 商店 | ❌ 本机不可行，原因见第 5 章（四道硬件/签名级限制） |
| 替代：microG + Aurora Store | ✅ Aurora Store 4.8.4 与 FakeStore 已安装并验证可启动；GmsCore 已备好，接回设备一条命令装完 |
| 商店自行升级 | ⚠️ Aurora 4.8.4 自带自更新（更新日志明确 "self-updates now shown in the list"），但**国内网络必须给手机配代理**才能连上 Google 服务器 |

> **最重要的一条前置认知**：这台机器的系统分区是 **erofs**，root 也写不动；而 Aurora Store / microG 依赖的 Google 服务器在国内直连超时。这两点决定了整个方案的选择。

---

## 1. 设备与环境事实

| 项目 | 值 |
|---|---|
| 型号 / SoC | ZTE W202DS / Unisoc ums9620 |
| 系统 | Android 13 (SDK 33)，arm64-v8a |
| Bootloader | **locked / green**（未解锁） |
| 当前槽位 | `_a`；`veritymode=enforcing` |
| 动态分区 | `ro.boot.dynamic_partitions=true`；无 TWRP |
| 分区文件系统 | `/`、`/system`、`/system_ext`、`/vendor`、`/product`、`/odm` **全部 erofs (ro)** |
| 内核 overlayfs | **被锁死**（f2fs upper 报 `xattr` 不支持；tmpfs upper 报 `not supported`） |
| Magisk | v31.1.0（versionCode 31100） |
| 出厂 GMS | 预置在 `/data/app`（可卸载位置），默认 **disabled**，且**不完整** |

关键工具位置（本机）：

```
flash-tools/platform-tools/adb.exe
flash-tools/spd_dump/                 # BootROM / FDL 通道
flash-tools/stock_backup/             # 原厂分区备份（务必保留）
flash-tools/apks/                     # 下载好的 microG / Aurora APK
```

---

## 2. 第一部分：取得 Root（B 路线）

### 2.1 原理

BL 锁定且 verity 开启，直接刷改过的 `boot` 会因校验失败无法启动。本次采用两步：

1. 刷入 **patched trustos** —— 让校验链不再强制 AVB 失败即拒启（BL 仍显示 locked/green）。
2. 刷入 **Magisk 修补过的 `boot_a`** —— 提供 root 与 magiskd。

两者都通过 **BootROM / FDL 救援通道**写入，而不是 fastboot（该机 fastboot 能力受限）。这也是"变砖可救回"的前提：**先确认救援通道可用，再动任何写入**。

### 2.2 铁律：先备份，再验证救援，最后写入

顺序不可颠倒：

```bash
adb devices                                  # 确认设备在线
python3 flash-tools/stock_backup.py          # 全分区备份 → stock_backup/
python3 flash-tools/verify_partition.py      # 校验备份
python3 flash-tools/verify_rescue.py         # 验证 BootROM/FDL 能重新进入
python3 flash-tools/brom_session.py          # 建立一次 BROM 会话并留日志
```

`stock_backup/` 里的 `boot_a` / `boot_b` / `vendor_boot_*` 等是唯一退路，**不要删、不要移出工作目录**。

### 2.3 写入与验证

```bash
python3 flash-tools/flash_part.py            # 写入 patched trustos + magisk_boot_a.img
adb reboot
adb wait-for-device
adb shell getprop sys.boot_completed         # 应为 1
adb shell su -c 'id'                         # uid=0(root) ... u:r:magisk:s0
adb shell su -c 'magisk -v'                  # v31.1.0
```

刷写日志保存在 `logs/flash_boot_a.log`、`logs/flash_trustos.log`，可逐条核对写入分区与哈希。

### 2.4 踩过的坑

- 本机 `magisk` 二进制**只认 `-v` / `-c`**，不认 `--version`（传错会报 `Unrecognized argument`）。
- `magiskd` 把授权配置**缓存在内存**，直接 `magisk --sqlite` 插库不会重载；只有 Magisk Manager 自身的授权流程才实时生效。
- 系统分区是 erofs，`mount -o remount,rw` 必然失败——**root ≠ 系统可写**。

---

## 3. 第二部分：让应用和 ADB 都有 root，且可开关

### 3.1 Magisk v31 的变化

v31 **取消了** "Apps and ADB" 总开关，改为**按 UID 授权**。Superuser 列表里的 `com.android.shell`（显示名 `Shell`）开关，就是 ADB root 的开关：

- 打开 → `adb shell su -c id` 返回 `uid=0(root)`
- 关闭 → 立即收回 ADB root，不影响已授权的其他 App

这个开关**不写死在 Magisk 数据库、不依赖任何模块**，删模块也不会留下孤儿权限，完全满足"不需要时关掉"的要求。

### 3.2 操作

Magisk Manager → **Superuser（超级用户）** 标签页 → 找到 `Shell` → 打开开关。
（v31 的右上角**没有**设置项，不用找。）

### 3.3 失败方案记录（别重试）

曾写过 `adbroot_module` 试图用模块在开机时写 sqlite 策略，结果：

- 探测参数用错（`--version` → 应为 `-c`）；
- 修正后仍失败：日志显示 `superuser_access=3` + `uid=2000 policy=1` 已正确写入，但 logcat 报 `su: request rejected (2000)` —— magiskd 不重读 sqlite。

**结论：ADB root 一律走 Manager 的 Shell 开关，不要用模块。**

---

## 4. 第三部分：安装 microG + Aurora Store

### 4.1 为什么是这个组合

官方 Play 在这台机器上无解（第 5 章），而：

- **Aurora Store**：开源 Play 客户端，装在 `/data`，**不需要任何特权权限**，能浏览/下载/更新 Play 目录里的 App，4.8.4 起自带自更新入口，且支持 root 安装器（静默升级，无需反复点确认）。
- **microG**：GMS 的开源平替（GmsCore + FakeStore），同样装在 `/data`，绕开 `signature|preinstalled` 权限问题。

### 4.2 组件清单与下载

| 组件 | 包名 | 版本 / 大小 | 来源 |
|---|---|---|---|
| Aurora Store | `com.aurora.store` | 4.8.4 / 9.4 MB | F-Droid repo（`com.aurora.store_76.apk`）或 GitLab release 4.8.4 |
| microG GmsCore | `com.google.android.gms` | 0.3.17.252432 / 108 MB | `github.com/microg/GmsCore/releases` |
| microG FakeStore | `com.android.vending` | 84022634 / 4.2 MB | 同上 release |

下载脚本：`scripts/download_apks.py`（已包含在归档中）。它做的事：

- 优先用国内 F-Droid 镜像拿 Aurora；
- 大文件走 `ghfast.top` 镜像 + **8 段 Range 并发**，每段落盘到 `.parts_*/pNN`，失败可单独重试、重跑可续传；
- 自动合并并校验总长度。

> 为什么这么绕：本机 curl(Windows schannel) 走 Clash 代理会 TLS 握手失败，Python(OpenSSL) 正常；GitHub 直连仅 ~20 KB/s，108 MB 单连接会超时。脚本把这些坑都处理掉了。

### 4.3 前置处理（关键，别跳过）

**① 卸载出厂 GMS**（它们占着同名包名，且是崩溃源）：

```bash
adb shell su -c 'pm uninstall --user 0 com.android.vending'
adb shell su -c 'pm uninstall --user 0 com.google.android.gms'
adb shell su -c 'pm uninstall --user 0 com.google.android.gsf'
# 三个都应返回 Success
adb shell pm list packages | grep -iE 'vending|gms|gsf'   # 应为空
```

**② 禁用 ZTE 的 GMS 禁用器**（否则新装的包会被立刻关掉）：

```bash
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.BootCompletedReceiver'
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.PackageChangeReceiver'
```

> 这两个接收器是开机反复禁用 GMS 的元凶：`.BootCompletedReceiver` 开机禁用，`.PackageChangeReceiver` 在每次 `pm enable` / 安装触发包变化广播时再次禁用（形成"开了又被关"的拉锯）。组件禁用状态存在 PackageManager 里，**重启后仍有效**，不依赖 Magisk 模块。

### 4.4 安装

```bash
adb install -r -d -t apks/AuroraStore-4.8.4.apk
adb install -r -d -t apks/microG-FakeStore.apk
adb install -r -d -t apks/microG-GmsCore.apk      # 108MB，streamed install 需 1~2 分钟
```

验证：

```bash
adb shell pm list packages | grep -iE 'aurora|vending|gms'
adb shell pm list packages -d | grep -iE 'aurora|vending|gms'   # 必须为空
adb shell monkey -p com.aurora.store -c android.intent.category.LAUNCHER 1
adb shell dumpsys window | grep mCurrentFocus                    # com.aurora.store/.ComposeActivity
```

> **本机实测状态**：Aurora Store 4.8.4 与 FakeStore 已安装、可启动、未被禁用；GmsCore 的 108 MB APK 已完整下载并校验（108,113,833 字节），但最后一次 `adb install` 时 USB 断开，未执行。**设备接回后补跑上面第三条 `adb install` 即可。**

### 4.5 自更新配置（对应"以后别老连电脑调试"）

Aurora Store 4.8.4 的更新日志明确写了 `self-updates now shown in the list` 与 `microG installer support`。建议：

1. 设置 → **安装方式** 选 **Root / Session installer**（有 root 时可静默安装，不必每次点确认）。
2. 设置 → 更新 → 打开**自动检查更新 / 自更新提示**。
3. 授予 `REQUEST_INSTALL_PACKAGES`（"安装未知应用"）权限，或直接用 root 安装器。

之后 Aurora 自己会在更新页列出新版本并可一键/root 静默升级。

### 4.6 ⚠️ 网络代理（必读，否则商店是空壳）

Aurora 需要连接 `android.clients.google.com` / Play API。实测本机在国内 WiFi 直连时：

```
java.net.SocketTimeoutException: failed to connect to
android.clients.google.com/74.125.203.102 (port 443) after 25000ms
首屏：connection closed
```

**这不是 Aurora 或 root 的问题，是网络可达性问题。** 手机侧必须能访问 Google 服务器，三选一：

- 在手机上装代理客户端并导入你的节点（**最推荐**，出门也能用，一次性设置）；
- 手机 WiFi 代理指向局域网内开了"允许局域网连接"的 Clash（家里可用）；
- 临时验证可用 `adb reverse tcp:7897 tcp:7897` + `adb shell settings put global http_proxy 127.0.0.1:7897`，但**拔线即失效，且会导致设备整体网络半瘫**，测完务必清除：
  ```bash
  adb shell settings delete global http_proxy
  adb reverse --remove tcp:7897
  ```

> 本机网络方案由使用者自行配置，本文不预设具体节点。

---

## 5. 第四部分：为什么官方 Google Play 在本机不可行（完整证据链）

这一步耗了最久，结论不是"没试对方法"，而是**设备本身的限制**。逐条实锤：

| # | 限制 | 证据 |
|---|---|---|
| 1 | 系统分区 erofs 只读 | `/proc/mounts` 显示 `/ /system /system_ext /vendor /product /odm` 全为 `erofs (ro)`；`remount,rw` 必失败 |
| 2 | 内核 overlayfs 被锁 | dmesg：`overlayfs: filesystem on '.../work' not supported`（tmpfs upper）、`upper fs does not support xattr`（f2fs upper） |
| 3 | Magisk **模块级** magic mount 不创建新文件 | 测试模块往 `/system_ext/bin`、`/system_ext/priv-app` 新增文件，重启后均不出现；而 Magisk 自身二进制确实被挂上（`/system_ext/bin/magisk` 存在），说明机制活着但模块叠加受限 |
| 4 | GSF 需要的权限拿不到 | `com.google.process.gservices` 启动即崩：`SecurityException: Permission denial: reading from settings requires android.permission.READ_DEVICE_CONFIG`；该权限 `prot=signature|preinstalled`，`pm grant` 无效，只有平台密钥签名且位于特权路径才会自动授予 |
| 5 | 出厂 GMS 不完整 | 仅 `vending` / `gms` / `gsf` 三包，缺 GoogleLoginService；系统里也没有配套的 `privapp-permissions-google*.xml` |
| 6 | ZTE 主动禁用 | `com.zte.heartyservice.strategy` 的两个接收器在开机与包变化时反复禁用 GMS |
| 7 | bind 强挂方案失败并触发保护 | 把 GMS bind 进 `/product/priv-app` 后：`cp: omitting directory '/product/etc/permissions/.'`、`cmd: Can't find service: package`（service.sh 跑太早），随后 Magisk **bootloop 保护**给所有模块自动写了 `disable` 文件（20:02），系统回滚到干净状态 |

曾尝试过的路线（均已证伪，别再重试）：

1. MindTheGapps → Magisk 模块叠加（overlayfs 不可用）
2. 直接 `pm enable` 出厂 GMS（被 ZTE 接收器反复禁用）
3. `service.sh` 延时 / `setsid` 看门狗反复 `pm enable`（形成拉锯，GMS 闪烁）
4. bind-mount 进 `/product/priv-app` + 手搓 `privapp-permissions` 白名单（触发 Magisk 安全模式）

**唯一能真正跑官方 Play 的前提**是把 GMS 放进 `/system/priv-app` 且用平台密钥签名 —— 本机 erofs + BL locked + 无可用叠加，做不到。

---

## 6. 第五部分：恢复 / 回滚（变砖可救）

### 6.1 Magisk 安全模式长什么样

模块导致启动异常时，Magisk 的 bootloop 保护会给每个模块目录自动创建 `disable` 文件，重启后**所有模块被禁用**，表现为：

- `su` 不在 PATH（`which su` 为空）
- `/system_ext/bin/magisk` 消失
- 但 `magiskd` 进程仍在、Magisk Manager 仍在

**root 并没有丢**，只是 magic mount 没做。

### 6.2 备用 root 入口

```bash
adb shell /debug_ramdisk/su -c 'id'
# uid=0(root) gid=0(root) context=u:r:magisk:s0
```

`/debug_ramdisk/su` 是指向 `./magisk` 的符号链接，安全模式下依然可用。

### 6.3 恢复干净状态（本次实操）

```bash
adb shell /debug_ramdisk/su -c '
  rm -rf /data/adb/modules/gms_priv /data/adb/modules/gms-enable
  rm -rf /data/adb/gms_up /data/adb/gms_wk /data/adb/lo
'
adb reboot
adb wait-for-device
adb shell su -c 'id'        # which su = /system_ext/bin/su，恢复
adb shell su -c 'ls -la /data/adb/modules/'   # 应为空
```

### 6.4 彻底回退

用 `stock_backup/` 里的原厂镜像，通过同一条 BootROM/FDL 通道写回 `trustos` + `boot_a`，重启即恢复未 root 状态。备份的 SHA256 见 `reports/stock_backup_SHA256.txt`。

---

## 7. 附录

### 7.1 本地归档结构

```
zte-w202ds-guide/
├── README.md                 本教程
├── anti-brick/               **防变砖 / 救援专目录**（备份、救援通道、回写校验、哈希清单、说明）
├── docs/PROJECT_STATUS.md    项目状态卡（唯一事实来源）
├── scripts/                  探测/备份/刷写/校验/下载脚本（.py/.cpp/.cfg）
├── logs/                     刷写、探测、验证日志
├── reports/                  设备报告、探针报告、哈希清单
├── modules/                  历史模块（含已废弃/失败方案，仅作记录）
└── .gitignore                排除大文件与二进制
```

**未入库的文件**（留在 `flash-tools/`，因 GitHub 单文件上限 100 MB 且含设备特定数据）：
`MindTheGapps-13-arm64.zip`(385 MB)、`gms_module.zip`(384 MB)、`part.0~7`(各 48 MB)、`magisk_boot_a.img` / `stock_backup/*`(各 64~100 MB)、`apks/*.apk`。APK 请按 4.2 的链接自行下载。

**防变砖资料**已单独整理在 `anti-brick/`：脚本、报告、日志和 `stock_backup_SHA256.txt` 哈希清单都会随本仓库一并上传；**原厂镜像本体（约 400 MB）不入库**，仍需本地保管在 `flash-tools/stock_backup/`，回刷前用哈希清单校验。详见 `anti-brick/README.md`。

> 仓库内所有日志、报告、脚本均已脱敏：设备序列号 → `<DEVICE_SERIAL>`，本地绝对路径 → `<WORKDIR>`。

### 7.2 命令速查

```bash
# root 验证
adb shell su -c 'id'
adb shell su -c 'magisk -v'                  # 不要用 --version

# ADB root 开关
# Magisk Manager → Superuser → Shell → 开/关

# GMS 状态
adb shell pm list packages -d | grep -iE 'vending|gms|gsf'   # 应为空

# 安全模式恢复
adb shell /debug_ramdisk/su -c 'id'
adb shell /debug_ramdisk/su -c 'rm -rf /data/adb/modules/<出问题的模块>'

# 临时代理清理（务必执行）
adb shell settings delete global http_proxy
adb reverse --remove tcp:7897
```

### 7.3 版本信息

| 组件 | 版本 |
|---|---|
| Magisk | v31.1.0 (31100) |
| Aurora Store | 4.8.4 (versionCode 76) |
| microG GmsCore | 0.3.17.252432 |
| microG FakeStore | 84022634 |
| Android | 13 / SDK 33 |

### 7.4 免责声明

刷机、修改 trustos、禁用 AVB 校验均有变砖风险，且会使设备失去保修、降低安全等级。本文只是**一台具体设备的实测记录**，不构成对其它设备的保证。动手前务必完整备份并确认救援通道可用；因照本文操作造成的任何损失由操作者自行承担。

---

*文档生成：2026-11-08 · 所有结论均基于本机真机的命令输出与日志*
