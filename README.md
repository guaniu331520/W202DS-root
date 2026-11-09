# 中兴移动定制机ZTE W202DS Root + 安装谷歌商店（ microG / Aurora Store ）完全指南

> 从「插上 USB 线却连不上 adb」开始，到最后能装 App、能救砖。
> 真机实测记录：2026-11-07 ~ 11-09，所有结论都有命令输出或日志支撑。
> 本文是**单台具体设备的实战记录**，供参考，未确定是否通用刷机教程。

---

## 0. 先读这段

### 这台机器是什么

| 项目 | 值 |
|---|---|
| 型号 | 中兴云电脑 W202DS（中国移动定制机） |
| 平台 | Unisoc 紫光展锐 T760 / `ums9620_2h10` |
| 系统 | Android 13 (SDK 33)、arm64-v8a、MyOS，build `100240302` |
| Bootloader | **locked / green**，无官方解锁通道 |
| 启动校验 | AVB `enforcing`、动态分区、**无 TWRP** |
| 系统分区 | `/`、`/system`、`/system_ext`、`/vendor`、`/product`、`/odm` 全为 **erofs 只读** |
| GMS | 出厂预置在 `/data/app`，默认 disabled 且**不完整** |

它**不是**高通/联发科那种 `fastboot flashing unlock` 就能解的机器。展锐平台走 SPD / BootROM 下载模式，教程里那些"解锁 BL → 刷 TWRP → 卡刷 Magisk"的路径在这里全部不适用。

### 本次最终做到了什么

| 目标 | 结果 |
|---|---|
| 建立 adb 通道 | ✅ USB 修好后可用；中途靠**无线调试**绕过并反查 |
| 全分区备份 + 救援验证 | ✅ 21/21 分区、390.1 MB，已压缩分卷入库 |
| Root | ✅ patched trustos（关 AVB 强制）+ Magisk 修补 `boot_a` |
| 应用 + ADB root 且**可开关** | ✅ Magisk v31 的 Shell 开关，不写死数据库 |
| 官方 Google Play | ❌ 设备级限制，不可行（见第 7.1 节证据链） |
| 可用商店 | ✅ microG + Aurora Store 4.8.4，装在 `/data`、可自更新 |

### 风险与免责

刷写 `trustos` / `boot`、关闭 AVB 校验**有变砖风险**，会失去保修、降低系统安全等级，OTA 可能失效，银行类 App 可能拒绝运行。本文只是实测记录，照做造成的任何损失由操作者自行承担。**动手前必须完成第 4 章的备份与救援验证**。

### 建议阅读顺序

第 1 章（原理）→ 第 2 章（电脑准备）→ 第 3 章（**两条调试路径**）→ 第 4 章（备份）→ 第 5 章（Root）→ 第 6 章（root 开关）→ 第 7 章（商店）→ 第 8 章（救砖）。只想照着点命令的，直接看第 9 章命令速查，但**不要跳过原理和备份**。

---

## 1. 原理速览（先看懂再动手）

### 1.1 为什么普通教程不适用

- **展锐不是 fastboot 生态**：BootROM 里没有 `VID_18D1&PID_4EE0` 那样的 fastboot 端口；下载模式端口是 `VID_1782&PID_4D00`（`Sprd Gadget Serial`），要用 `spd_dump` 通过 BSL/FDL 协议读写分区。
- **BL 锁着但不等于不能 root**：我们没有解锁 BL（那会清空数据且这台机没有官方通道），而是走"**让校验链不再因 AVB 失败拒启**"的路线。
- **erofs 天生只读**：root（uid 0）也**不能** `mount -o remount,rw`。这是文件系统内核驱动的限制，跟权限无关。所以"root 后把 GMS 拷进 `/system/priv-app`"这类做法从根上就不成立。
- **动态分区 + 无 TWRP**：没有 recovery 卡刷通道，只能改 `boot_a` 这种启动镜像。

### 1.2 Root 的真实原理（B 路线）

启动链大致是：`BootROM → splloader → uboot/sml → trustos → boot_a(kernel+ramdisk) → Android`。

1. **patched trustos**：修改可信执行环境里负责校验策略的部分，让 AVB 校验失败不再强制拒启（BL 仍显示 locked/green，不改动 `bootloader` 分区本身）。
2. **Magisk 修补 `boot_a`**：Magisk 解包原厂 `boot_a`，往 ramdisk 注入 `magiskinit` / `magiskd`，重新打包成 `magisk_boot_a.img`。
3. 两者写回后，开机时 magiskd 取得 root 上下文，并通过 **magic mount** 把 `su`、`magisk` 等挂进 PATH。

> 为什么叫"B 路线"：当时对比过 A（解锁 BL + 第三方恢复）与 B（不打解锁、只改启动链），B 不需要清数据、可逆性更好。

### 1.3 为什么写入必须走 BootROM/FDL

`adb reboot autodloader` 让设备重启进展锐下载模式，再由 `spd_dump` 通过 **外部 FDL1/FDL2（仅载入 RAM，不写分区）** 读/写分区。这也是"变砖可救回"的兜底：即使 `boot`/`uboot` 全坏，BootROM 仍在，仍能通过同一条通道写回原厂镜像。本次救援验证的执行地址是 `0x65012f48`（ums9620 专用），实测 `MATCH`。

### 1.4 为什么官方 Play 装不了（一句话版）

GSF 需要的 `READ_DEVICE_CONFIG` 是 `signature|preinstalled` 权限，只有**平台密钥签名 + 特权路径**才会自动授予；出厂 GMS 在 `/data/app`（普通位置）、签名不是 ZTE 平台密钥、且缺登录组件；系统 erofs 只读、内核 overlayfs 被锁、Magisk 模块级 magic mount 不创建新文件 → 没有合法途径把它放进 `/system/priv-app`。详见 7.1。

### 1.5 术语表

| 词 | 含义 |
|---|---|
| AVB | Android Verified Boot，启动时逐级校验分区哈希 |
| erofs | 只读压缩文件系统，内核层面不支持写入 |
| magic mount | Magisk 用 bind mount 把模块文件"盖"到只读系统上 |
| FDL | 展锐下载模式下临时载入 RAM 的下载代理（FDL1/FDL2） |
| autodloader | `adb reboot autodloader`，让展锐设备重启进下载模式 |
| priv-app | `/system/priv-app` 等特权目录，系统会给其中的应用授予特权权限 |
| slot `_a` / `_b` | A/B 分区；本机当前在 `_a` |

---

## 2. 电脑端准备（一次性）

### 2.1 目录结构

```
<工作目录>/
├── flash-tools/
│   ├── platform-tools/        # adb.exe / fastboot.exe（Google 官方）
│   ├── spd_dump/              # 展锐下载模式工具及其 README
│   ├── stock_backup/          # 21 个原厂分区镜像（本地保管）
│   ├── stock_backup.tar.gz    # 未切分压缩包（由分卷可重建）
│   ├── magisk_boot_a.img      # Magisk 修补后的 boot
│   └── *.py / *.ps1           # 本次编写的全部脚本
└── zte-w202ds-guide/          # 本仓库（文档 + 开源脚本 + 镜像分卷）
```

### 2.2 安装工具

```bash
# 1) 官方 platform-tools（不要用来源不明的 adb 包）
#    https://developer.android.com/tools/releases/platform-tools
#    解压到 flash-tools/platform-tools/，确认版本：
flash-tools/platform-tools/adb.exe version

# 2) 确认支持 adb pair（Android 11+ 无线调试需要）
flash-tools/platform-tools/adb.exe help | grep pair

# 3) Python 3.10+（跑本仓库脚本）
python3 --version

# 4) 压缩/校验工具（还原镜像时用）
tar --version; sha256sum --version
```

### 2.3 驱动说明（重要）

Windows 会自动给这台机的 ADB 接口装**通用 WinUSB 驱动**。它能让设备管理器显示"ADB Interface"，但**没有登记 ADB 专用接口 GUID**，导致 adb 扫不到设备 —— 这正是第 3.2 节的故障根因。两种处理：

- 用本仓库 [`scripts/usb_guid_fix.ps1`](scripts/usb_guid_fix.ps1) 补 GUID（可逆、自动备份）；
- 或安装 Google USB Driver（在 INF 里加 `VID_19D2&PID_0306`）/ Universal ADB Driver / 用 Zadig。

> 展锐下载模式端口 `VID_1782&PID_4D00` 是**另一套驱动**。Windows 11 的驱动签名强制会拒绝未签名的第三方 INF（`pnputil` 报 "third-party INF does not contain digital signature information"）。本次改用 `adb reboot autodloader` 触发下载模式，避开了按键窗口与这个驱动问题。

### 2.4 网络说明

- 下载 Magisk / microG / Aurora 的 APK 需要能访问 GitHub、GitLab、F-Droid；本机实测 GitHub 直连很慢，用国内镜像或代理更稳（见 `scripts/download_apks.py`）。
- **Aurora Store 运行时**需要手机能访问 `android.clients.google.com`，国内网络直连会超时；手机侧代理请自行配置。
- 给 GitHub 推文件走的是 `api.github.com`；`uploads.github.com`（Release 附件）在本机不可达，所以大镜像用分卷走 Contents API（见第 4.4 节）。

### 2.5 自检

```bash
python3 scripts/probe_device.py          # 只读体检，插线后第一件事
```

---

## 3. 建立 ADB 调试通道（两条路径，必经）

> **这一步是全部工作的前提**。本次一开始在这里卡了最久：USB 线插上、USB 调试已打开、MTP 已选，但平板上**始终不弹「允许 USB 调试」**，电脑 `adb devices` 是空的。两条路径都要会。

### 3.1 平板端共同准备（两条路径都要先做）

1. **保持在安卓模式**，不要切到「云电脑 / Windows 云桌面」模式（云模式下 adb 不通）。
2. 设置 → 关于平板 → 连点「版本号」**7 次** → 输锁屏密码 → 出现"您已处于开发者模式"。
3. 设置 → 系统（或「更多设置」，可在设置里搜"开发者选项"）→ 开发者选项：
   - 打开 **USB 调试**
   - 如有 **OEM 解锁** 就打开（本机大概率没有，运营商定制机常隐藏）
   - 关掉「通过 USB 验证应用」（会拦截 `adb install`）
   - 如存在「USB 调试（安全设置）」，注意它可能需要登录中兴账号联网验证
4. 用**能传数据的线**插电脑**后置 USB 口**，不要经 Hub。
5. 通知栏把 USB 用途从「仅充电」改成「**传输文件 (MTP)**」。
6. **保持屏幕解锁、亮屏**；电量 > 60%。
7. 走无线调试时，平板与电脑必须连**同一个 WiFi**（本机是 `192.168.1.x` 网段）。

### 3.2 路径 A：USB 调试（标准路径）

标准流程：插线 → 屏幕弹出「允许 USB 调试？」→ 勾「一律允许使用这台计算机进行调试」→ 确定 → 电脑验证：

```bash
adb devices -l
# 期望：<序列号>  device
```

#### 故障专题：连上了，但**不弹授权框**

**现象**：Windows 设备管理器显示 `ADB Interface`，MTP 显示"中兴云电脑"，但 `adb devices` **完全为空**（连 `unauthorized` 都没有），平板上不弹任何授权框；切安卓模式、MTP/仅充电来回切、重新插拔都无效。

**逐项排除**（本次实测）：

| 检查项 | 结果 | 结论 |
|---|---|---|
| 数据线 / USB 口 | Windows 认到 `VID_19D2&PID_0306`（中兴） | ✅ 线没问题 |
| USB 模式 | MTP 已建立 | ✅ 不是「仅充电」 |
| ADB 驱动 | `Class_ff/SubClass_42/Prot_01` + WinUSB，状态 OK | ✅ 驱动装上了 |
| adb 版本 | 换官方 34.0.5 / 33.0.3 交叉验证，仍为空 | ✅ 不是工具版本 |
| 重新枚举 | 禁用/启用 ADB 接口后再看，仍为空 | ✅ 不是枚举缓存 |
| 设备端状态 | `sys.usb.config=mtp,adb`、`adb_enabled=1`、`ro.adb.secure=1`、`init.svc.adbd=running`、USB configured=true | ✅ **平板端完全正常** |
| Windows 注册表 | 该接口 `Device Parameters\DeviceInterfaceGUIDs` = **`(NOT SET)`** | ❌ **根因** |

**根因**：`adb.exe` 的 Windows 后端（`AdbWinUsbApi.dll`）靠接口 GUID `{F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}` 枚举设备。Windows 自动装的通用 WinUSB 驱动没登记这个 GUID，于是 adb "看不见"这个接口 → 根本没发起握手 → **设备端自然不会弹授权框**。所以"不弹框"不是平板设置问题，也不是线的问题。

**诊断命令**：

```bash
# 设备端（此时可能只能靠无线 adb 连上，见 3.3）
adb shell "getprop sys.usb.config; getprop sys.usb.state; getprop ro.adb.secure; getprop init.svc.adbd; settings get global adb_enabled"
adb shell "dumpsys usb | head -60"
```

```powershell
# Windows 侧（管理员 PowerShell）
$base='HKLM:\SYSTEM\CurrentControlSet\Enum\USB\VID_19D2&PID_0306&MI_01'
Get-ChildItem $base | ForEach-Object {
  $v=(Get-ItemProperty (Join-Path $_.PSPath 'Device Parameters') -ErrorAction SilentlyContinue).DeviceInterfaceGUIDs
  "$($_.PSChildName) -> $(if($v){$v}else{'(NOT SET)'})"
}
```

**修复**（三选一，推荐第一个）：

```powershell
# 1) 本仓库脚本：备份原值 → 补 GUID → 重新枚举 → 重启 adb
#    以管理员身份运行
powershell -ExecutionPolicy Bypass -File scripts\usb_guid_fix.ps1

# 2) 装带该 VID/PID 的 Google USB Driver / Universal ADB Driver
# 3) Zadig 把该接口绑定为 WinUSB 并登记 ADB GUID
```

修好后的现象：`adb devices` 出现设备号（首次可能是 `unauthorized`），**此时平板上才会弹出授权框**，勾「一律允许」点确定，再 `adb devices` 变为 `device`。

> 手工写法：在 `HKLM:\SYSTEM\CurrentControlSet\Enum\USB\VID_19D2&PID_0306&MI_01\<实例>\Device Parameters` 新建 `REG_MULTI_SZ` 值 `DeviceInterfaceGUIDs` = `{F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}`，然后禁用/启用设备、重新插线、`adb kill-server && adb devices`。

### 3.3 路径 B：无线调试（绕开 USB）

适用：Android 11+（本机 13）、能进开发者选项、平板与电脑同一 WiFi。**完全不依赖 USB 线和那个授权弹窗**，是当时破局的关键。

**平板端傻瓜步骤**：

1. 设置 → 开发者选项 → 找到 **无线调试 (Wireless debugging)** → 打开。
2. 若提示"当前 WiFi 不可用/未连接"，先连好 WiFi。
3. 点进「无线调试」页面 —— 如果看不到配对码，**在页面上点一下「使用配对码配对设备」**（这一步很容易漏，本次就是"点一下才跳出来"）。
4. 弹窗会显示 **6 位 Wi-Fi 配对码** 和 **IP 地址:端口**（例如 `192.168.1.9:39583`）。**弹窗别关、保持亮屏**。
5. 把配对码和 `IP:端口` 给电脑端，执行：

```bash
adb pair 192.168.1.9:39583 087275      # 配对端口 + 6 位码
# Successfully paired to ...
```

6. **回到无线调试主页面**，上面显示的是**另一个** `IP:端口`（连接端口，例如 `192.168.1.9:36913`）。注意：**配对端口 ≠ 连接端口**，别混用。

```bash
adb connect 192.168.1.9:36913
adb devices
# 期望：192.168.1.9:36913  device
```

**常见坑**：

| 现象 | 处理 |
|---|---|
| 找不到配对码/IP | 点「使用配对码配对设备」才会展开；或先点一下「无线调试」标题 |
| `adb pair` 失败 | 确认同一 WiFi、屏幕解锁、配对码没过期（弹窗关掉就失效）、端口用配对端口 |
| `adb connect` 连不上 | 用**主页面**的连接端口，不是配对端口 |
| 锁屏 / 切 WiFi 后断开 | 重新 `adb connect`，必要时重新配对 |
| 无线慢 / 不稳定 | 大文件传输（108MB APK）建议修好 USB 后走 USB |

**无线能做到 / 不能做到**：

- ✅ 完整体检、`adb install` 装 APK、读属性、**反查 USB 调试为什么不弹**（上面 3.2 的诊断命令就是靠它跑的）。
- ❌ 刷 `boot` / `trustos` 仍需要 USB 数据线 + 展锐下载模式（BootROM/FDL 不走 adb 网络）。

### 3.4 两条路径对照与本次实际走法

| | 路径 A：USB 调试 | 路径 B：无线调试 |
|---|---|---|
| 依赖 | USB 线 + 正确的 ADB 接口驱动 | 同一 WiFi、Android 11+ |
| 授权框 | 需要（修好驱动后才会弹） | 不需要 |
| 速度 | 快，适合传大文件/刷机 | 慢且可能掉线 |
| 能刷分区 | ✅（BootROM/FDL 必经 USB） | ❌ |
| 失败时的作用 | — | 可作为**诊断 USB 的跳板** |

**本次实际顺序**：插线 → USB 授权框不弹（3.2 现象）→ 走路径 B 用无线调试连上 → 通过无线 adb 读到设备端 `adb_enabled=1`、`adbd running`，确认问题在 Windows 侧 → 查出 `DeviceInterfaceGUIDs` 为空 → 补 GUID 修好 USB → 后续刷机、装 APK 全部走 USB；无线调试保留备用。

### 3.5 通道验证清单

```bash
adb devices                              # 有设备且状态 device
adb shell getprop ro.product.model        # W202DS
adb shell getprop ro.boot.flash.locked    # 1（BL 锁定）
python3 scripts/probe_device.py           # 只读体检报告
```

---

## 4. 体检、备份与救援验证（动手前必做）

### 4.1 铁律

1. **先完整备份并校验哈希**，再动任何一个分区。
2. **先验证 BootROM / FDL 救援通道能重复进入**，不要只成功一次就开刷。
3. **一次只改一个分区，写完立刻回读比对**。

### 4.2 备份 21 个分区

本次实际方法（**不用按物理键**）：

```bash
adb reboot autodloader            # 重启进展锐下载模式
python3 anti-brick/scripts/stock_backup.py       # spd_dump 逐分区 r <part> reset
python3 anti-brick/scripts/verify_partition.py
sha256sum -c anti-brick/reports/stock_backup_SHA256.txt
```

实测结果：`21 / 21` 分区有数据、共 **390.1 MB**、build `100240302`，设备正常回到 Android，BL 仍 `locked/green`、电量 100%。

> 物理按键法（备用）：关机 → 插 USB → **按住「电源 + 音量下」8–10 秒** → 松开。设备管理器出现 `Sprd Gadget Serial` / `USB\VID_1782&PID_4D00` 即进入下载模式。**不需要音量上**。该端口**只出现约 30–40 秒**，超时平板会自动继续开机；且这个端口常缺驱动（ProblemCode 28），Windows 11 会拒绝未签名 INF。所以优先用 `adb reboot autodloader`。

### 4.3 验证救援通道

```bash
python3 anti-brick/scripts/brom_session.py       # 建立一次 BROM 会话
python3 anti-brick/scripts/verify_rescue.py      # 外部 FDL1/FDL2 只读读分区
```

本次结果：`BSL_REP_VER, CMD_CONNECT, EXEC FDL1, EXEC FDL2, Read Part Done`，`exec_addr=0x65012f48`，判定 **MATCH**，设备回到 Android，全程未写任何分区。

### 4.4 镜像本体入库（压缩分卷）

原厂镜像 390.1 MB → `tar.gz` 压缩到 **80.4 MB**（20.6%）→ 切成 **17 个 5 MB 分卷**，放在 [`anti-brick/stock-images/`](anti-brick/stock-images/)。

为什么分卷：`uploads.github.com`（Release 附件）不可达，只能走 `api.github.com` 的 Contents API；它要求 base64 编进 JSON，80 MB 会变成约 107 MB 单请求，既超限又易超时，5 MB 一卷（base64 约 6.7 MB）稳定。

```bash
python3 anti-brick/stock-images/restore.py       # 校验 + 合并 + 解压，只用标准库
sha256sum -c anti-brick/stock-images/SHA256SUMS.txt
```

⚠️ 这些镜像来自一台具体设备，可能含校准/设备相关数据，仓库是公开的；如介意请改为私有或只保留哈希清单。详见该目录的 README。

---

## 5. Root（B 路线）逐步

### 5.1 准备两个镜像

| 文件 | 怎么来 | 作用 |
|---|---|---|
| patched `trustos` | 离线补丁流程（见 `flash-tools/offline_patch/`、`logs/flash_trustos.log`） | 让 AVB 失败不再强制拒启 |
| `magisk_boot_a.img` | Magisk v31.1.0 对原厂 `boot_a` 修补（Magisk App 或 `magiskboot`） | 注入 magiskd 提供 root |

**必须先核对**：补丁与本机 build `100240302`、槽位 `_a` 匹配；写入前跑一次哈希校验，别拿错镜像。

### 5.2 写入

```bash
python3 flash-tools/flash_part.py        # 通过 spd_dump 写入（参数以脚本为准）
# 日志：logs/flash_trustos.log、logs/flash_boot_a.log
python3 anti-brick/scripts/verify_writeback.py   # 写完立即回读比对
adb reboot
adb wait-for-device
```

### 5.3 验证（逐条都要过）

```bash
adb shell getprop sys.boot_completed                 # 1
adb shell su -c 'id'                                # uid=0(root) ... u:r:magisk:s0
adb shell su -c 'magisk -v'                         # v31.1.0
adb shell getprop ro.boot.slot_suffix                # _a
adb shell getprop ro.boot.veritymode                 # enforcing（BL 仍 locked/green）
adb shell cat /proc/mounts | grep erofs              # 系统分区仍只读，符合预期
```

### 5.4 关键坑

- 本机 `magisk` 二进制**只认 `-v` / `-c`**，传 `--version` 会报 `Unrecognized argument`。
- `magiskd` 把授权配置**缓存在内存**，直接 `magisk --sqlite` 插库不会重载（见 6.3）。
- root ≠ 系统可写：erofs 无法 remount rw，别在这一点上浪费时间。

---

## 6. 应用 + ADB root，且可随时开关

### 6.1 Magisk v31 的变化

v31 **取消了** "Apps and ADB" 总开关，改成**按 UID 授权**。Superuser 列表里的 `com.android.shell`（显示名 `Shell`）开关就是 ADB root 开关：

- 打开 → `adb shell su -c id` 返回 `uid=0(root)`
- 关闭 → 立即收回 ADB root，不影响其他已授权 App

它**不写入 Magisk 数据库、不依赖任何模块**，删模块也不会留下孤儿权限 —— 这正是"不需要时能关掉"的要求。

### 6.2 操作与验证

Magisk Manager → **Superuser（超级用户）** 标签页 → 找到 `Shell` → 打开开关。（v31 右上角**没有**设置项，不用找。）

```bash
adb shell su -c 'id'      # 开：uid=0(root)；关：su 被拒绝
```

### 6.3 失败方案记录（别重试）

曾写过 `adbroot_module` 试图开机时写 sqlite 策略：探测参数先写错（`--version` → 应为 `-c`），修正后**仍失败**——日志显示 `superuser_access=3` + `uid=2000 policy=1` 已写入，但 logcat 报 `su: request rejected (2000)`，因为 magiskd 不重读 sqlite。**结论：ADB root 一律走 Manager 的 Shell 开关。**

---

## 7. microG + Aurora Store

### 7.1 为什么官方 Google Play 不可行（完整证据链）

| # | 限制 | 证据 |
|---|---|---|
| 1 | 系统分区 erofs 只读 | `/proc/mounts` 全 `erofs (ro)`；`remount,rw` 必失败 |
| 2 | 内核 overlayfs 被锁 | dmesg：`filesystem ... not supported`（tmpfs upper）、`upper fs does not support xattr`（f2fs upper） |
| 3 | 模块级 magic mount 不建新文件 | 测试模块往 `/system_ext/bin`、`/system_ext/priv-app` 新增文件，重启后均不出现；而 Magisk 自身二进制确实挂上了，说明机制活着但模块叠加受限 |
| 4 | GSF 权限拿不到 | `SecurityException: ... android.permission.READ_DEVICE_CONFIG`；该权限 `signature|preinstalled`，`pm grant` 无效 |
| 5 | 出厂 GMS 不完整 | 仅 `vending`/`gms`/`gsf` 三包，缺 GoogleLoginService，且无配套 privapp 白名单 |
| 6 | ZTE 主动禁用 | `com.zte.heartyservice.strategy` 的 `BootCompletedReceiver` + `PackageChangeReceiver` 反复禁用 GMS |
| 7 | bind 强挂失败并触发保护 | 把 GMS bind 进 `/product/priv-app` 后 `cp: omitting directory ...`、`cmd: Can't find service: package`，随后 Magisk bootloop 保护给所有模块写 `disable`，系统自动回滚 |

曾证伪的路线：MindTheGapps 模块叠加、直接 `pm enable`、`service.sh` 看门狗反复启用、bind-mount + 手搓白名单。**结论**：官方 Play 需要把 GMS 放进 `/system/priv-app` 且用平台密钥签名，本机做不到。

### 7.2 组件与下载

| 组件 | 包名 | 版本 / 大小 | 来源 |
|---|---|---|---|
| Aurora Store | `com.aurora.store` | 4.8.4 / 9.4 MB | F-Droid repo 或 GitLab release |
| microG GmsCore | `com.google.android.gms` | 0.3.17.252432 / 108 MB | `github.com/microg/GmsCore/releases` |
| microG FakeStore | `com.android.vending` | 84022634 / 4.2 MB | 同上 |

下载脚本 [`scripts/download_apks.py`](scripts/download_apks.py)：优先国内 F-Droid 镜像；大文件走 `ghfast.top` 镜像 + 8 段 Range 并发、分段落盘、失败可续传、自动合并校验。

### 7.3 前置处理（别跳过）

```bash
# 1) 卸载出厂 GMS（占着同名包名，且是崩溃源）
adb shell su -c 'pm uninstall --user 0 com.android.vending'   # Success
adb shell su -c 'pm uninstall --user 0 com.google.android.gms' # Success
adb shell su -c 'pm uninstall --user 0 com.google.android.gsf' # Success

# 2) 禁用 ZTE 的 GMS 禁用器（组件状态持久，重启仍有效）
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.BootCompletedReceiver'
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.PackageChangeReceiver'
```

### 7.4 安装与验证

```bash
adb install -r -d -t apks/AuroraStore-4.8.4.apk
adb install -r -d -t apks/microG-FakeStore.apk
adb install -r -d -t apks/microG-GmsCore.apk       # 108MB，streamed install 1~2 分钟

adb shell pm list packages -d | grep -iE 'aurora|vending|gms'   # 必须为空
adb shell monkey -p com.aurora.store -c android.intent.category.LAUNCHER 1
adb shell dumpsys window | grep mCurrentFocus                    # com.aurora.store/.ComposeActivity
adb shell monkey -p com.google.android.gms -c android.intent.category.LAUNCHER 1
adb shell dumpsys window | grep mCurrentFocus                    # org.microg.gms.ui.SettingsActivity
```

本机实测：三包全部安装、启用、可启动，microG 设置图标出现在桌面。

### 7.5 自更新

Aurora Store 4.8.4 更新日志明确写了 `self-updates now shown in the list` 与 `microG installer support`。在 App 设置里：

1. 安装方式选 **Root / Session installer**（有 root 可静默安装，不必每次点确认）
2. 打开**自动检查更新 / 自更新提示**
3. 授予 `REQUEST_INSTALL_PACKAGES`，或直接用 root 安装器

### 7.6 网络代理（必读）

Aurora 需连 `android.clients.google.com`。本机直连实测：

```
java.net.SocketTimeoutException: failed to connect to
android.clients.google.com/74.125.203.102 (port 443) after 25000ms
首屏：connection closed
```

这不是 root 或 App 的问题，是**手机侧网络可达性**。请在手机侧配置代理（代理客户端 / 同局域网代理），或在 WiFi 里设置代理。

临时验证可用（**拔线即失效，会导致设备网络半瘫，测完务必清除**）：

```bash
adb reverse tcp:端口 tcp:端口     #端口为PC代理开放的端口根据代理自行填入
adb shell settings put global http_proxy 127.0.0.1:端口
# ... 验证 ...
adb shell settings delete global http_proxy
adb reverse --remove tcp:端口
```

---

## 8. 恢复 / 救砖

### 8.1 Magisk 安全模式（软变砖）

模块导致启动异常时，Magisk 的 bootloop 保护会给每个模块目录自动创建 `disable` 文件并禁用全部模块：

- `which su` 为空、`/system_ext/bin/magisk` 消失
- 但 `magiskd` 进程仍在、Manager 仍在 —— **root 没有丢**

备用 root 入口：

```bash
adb shell /debug_ramdisk/su -c 'id'
# uid=0(root) gid=0(root) context=u:r:magisk:s0
```

恢复干净状态：

```bash
adb shell /debug_ramdisk/su -c 'rm -rf /data/adb/modules/<出问题的模块>'
adb reboot
adb wait-for-device
adb shell su -c 'id'                    # su 回到 /system_ext/bin/su
adb shell su -c 'ls /data/adb/modules/' # 应为空
```

### 8.2 完整回退（硬变砖）

```bash
python3 anti-brick/stock-images/restore.py          # 还原原厂镜像
sha256sum -c anti-brick/stock-images/SHA256SUMS.txt
python3 anti-brick/scripts/verify_rescue.py         # 确认 BootROM 通道可进入
python3 anti-brick/scripts/flash_part.py            # 写回原厂 trustos_a 与 boot_a
python3 anti-brick/scripts/verify_writeback.py      # 回读比对
adb reboot
```

详细流程见 [`anti-brick/README.md`](anti-brick/README.md)。

### 8.3 本次真实恢复案例

`gms_priv` 模块在 `post-fs-data` 阶段 bind 覆盖 `/product/etc/permissions` 且 `service.sh` 早于 PackageManager 执行，导致启动异常 → Magisk 自动禁用全部模块 → 删除模块重启后完整恢复，**数据与原厂分区均未受损**。

---

## 9. 完整命令速查（按阶段）

```bash
# ---- 阶段 0：通道 ----
adb devices -l
python3 scripts/probe_device.py
# USB 不弹授权框 → 管理员运行 scripts\usb_guid_fix.ps1
# 或无线：开发者选项 → 无线调试 → 使用配对码配对设备
adb pair <IP>:<配对端口> <6位码>
adb connect <IP>:<连接端口>
adb devices

# ---- 阶段 1：备份 ----
adb reboot autodloader
python3 anti-brick/scripts/stock_backup.py
python3 anti-brick/scripts/verify_partition.py
python3 anti-brick/scripts/verify_rescue.py
sha256sum -c anti-brick/reports/stock_backup_SHA256.txt

# ---- 阶段 2：root ----
python3 flash-tools/flash_part.py
python3 anti-brick/scripts/verify_writeback.py
adb reboot; adb wait-for-device
adb shell su -c 'id'; adb shell su -c 'magisk -v'
# Magisk Manager → Superuser → Shell 开/关

# ---- 阶段 3：商店 ----
adb shell su -c 'pm uninstall --user 0 com.android.vending'   # 另两个同理
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.BootCompletedReceiver'
adb shell su -c 'pm disable com.zte.heartyservice.strategy/.PackageChangeReceiver'
adb install -r -d -t apks/AuroraStore-4.8.4.apk
adb install -r -d -t apks/microG-FakeStore.apk
adb install -r -d -t apks/microG-GmsCore.apk

# ---- 阶段 4：救砖 ----
adb shell /debug_ramdisk/su -c 'id'
python3 anti-brick/stock-images/restore.py
```

---

## 10. 开源工具 / 软件清单

> 本项目**只使用开源或官方可获取的工具**，全部代码在本仓库可见。许可证以各官方仓库为准。

| 工具 | 用途 | 来源 | 许可证 |
|---|---|---|---|
| Android SDK Platform-Tools (`adb`/`fastboot`) | 调试桥、`adb pair/connect/install` | [developer.android.com/tools/releases/platform-tools](https://developer.android.com/tools/releases/platform-tools) | Android SDK License |
| `spd_dump` | 展锐 BootROM / FDL 分区读写 | 展锐下载模式开源实现（随附 `README.md` / `README_zh.md`） | 见其仓库 |
| Magisk v31.1.0 | 修补 `boot_a`、root、模块 | [github.com/topjohnwu/Magisk](https://github.com/topjohnwu/Magisk) | GPL-3.0 |
| microG GmsCore 0.3.17.252432 | GMS 开源平替 | [github.com/microg/GmsCore](https://github.com/microg/GmsCore) | Apache-2.0 |
| Aurora Store 4.8.4 | 开源 Play 客户端、自更新 | [gitlab.com/AuroraOSS/AuroraStore](https://gitlab.com/AuroraOSS/AuroraStore) | GPL-3.0（以官方为准） |
| MindTheGapps 13 arm64 | **仅用于取证对比**，未刷入 | [github.com/MindTheGapps](https://github.com/MindTheGapps) | 见其仓库 |
| Google USB Driver / Universal ADB Driver / Zadig | 修 ADB 接口 GUID | 各自官网/仓库 | 各自许可证 |
| Python 3.10+ | 跑本仓库全部脚本 | python.org | PSF License |
| 7-Zip / GNU tar + gzip | 镜像压缩、分卷 | 各自官网 | 各自许可证 |
| Clash Verge / V2rayN | 网络代理（用户自备） | 各自开源仓库 | 各自许可证 |

**本次自写、随仓库开源的代码**（`scripts/`、`anti-brick/scripts/`）：见第 11 章索引，均为 Python / PowerShell / Shell，注释完整，可直接运行。

---

## 11. 仓库代码索引

| 路径 | 作用 |
|---|---|
| `scripts/probe_device.py` | 只读设备体检（通道建立后第一步） |
| `scripts/usb_guid_fix.ps1` | 修复 Windows ADB 接口 GUID（3.2 根因） |
| `scripts/download_apks.py` | 分段下载 microG / Aurora APK，支持镜像与断点续传 |
| `scripts/make_stock_archive.py` | 打包 `stock_backup/` 并切成 5 MB 分卷 + 生成哈希清单 |
| `scripts/probe_device.py`、`auto_backup.py` | 体检与自动备份 |
| `scripts/verify_partition.py`、`verify_rescue.py`、`verify_writeback.py` | 分区校验与救援验证链 |
| `scripts/stock_backup.py`、`brom_session.py`、`flash_part.py` | BROM 会话、分区读写 |
| `scripts/auto_probe.py`、`overnight.py` | 自动探针（早期只读探索） |
| `anti-brick/scripts/*` | 防变砖专用副本（同上，按目录归类） |
| `anti-brick/stock-images/restore.py` | 分卷校验 + 合并 + 解压 |
| `anti-brick/stock-images/manifest.json` | 分卷元数据与 SHA-256 |
| `modules/*` | 历史 Magisk 模块（含已废弃/失败方案，仅作记录） |
| `docs/`、`reports/`、`logs/` | 状态卡、探针报告、原始日志（均已脱敏） |

---

## 12. 哪些文件入库、哪些不入库

| 类别 | 是否入库 | 说明 |
|---|---|---|
| 文档、脚本、日志、报告 | ✅ | 全库脱敏：序列号 → `<DEVICE_SERIAL>`，本机绝对路径 → `<WORKDIR>` |
| 原厂镜像压缩分卷（17×5 MB） | ✅ | `anti-brick/stock-images/`，可由 `restore.py` 完整还原 |
| 未切分的 `stock_backup.tar.gz`（80 MB） | ❌ | 可由分卷重建，不重复放 |
| 单个 APK（Aurora / microG / FakeStore） | ❌ | 体积大且属第三方分发物，按 7.2 链接自行下载 |
| `magisk_boot_a.img`、patched trustos、`part.0~7`、原厂单分区镜像 | ❌ | 设备特定二进制，本地保管在 `flash-tools/` |

---

## 13. 排错速查表

| 症状 | 原因 | 处理 |
|---|---|---|
| `adb devices` 空、不弹授权框 | WinUSB 缺 ADB 接口 GUID | 3.2 + `scripts/usb_guid_fix.ps1` |
| 无线调试找不到配对码 | 没点「使用配对码配对设备」 | 3.3 |
| `adb connect` 失败 | 用了配对端口而非连接端口 | 3.3 |
| `INSTALL_FAILED_*` | 未卸载出厂 GMS / 签名冲突 | 7.3 |
| 装完 GMS 立刻变 disabled | ZTE strategy 两个接收器 | 7.3 `pm disable` |
| `su: inaccessible or not found` | Magisk 安全模式，模块被禁 | 8.1 用 `/debug_ramdisk/su` |
| `magisk: Unrecognized argument` | 用了 `--version` | 改用 `-v` / `-c` |
| 模块写了 sqlite 但授权不生效 | magiskd 缓存于内存 | 6.3，走 Manager 开关 |
| `mount -o remount,rw` 失败 | erofs 天生只读 | 见 1.1 |
| GSF 崩溃 / Play 打不开账号 | `READ_DEVICE_CONFIG` 不可授予 | 7.1，改用 microG + Aurora |
| Aurora 首屏 `connection closed` | 手机连不上 Google 服务器 | 7.6 配置手机侧代理 |

---

## 14. 免责声明

刷机、修改 `trustos`、关闭 AVB 校验均有变砖风险，会失去保修并降低系统安全等级。本文仅为**一台具体设备的实测记录**，不构成对其它设备的保证。动手前务必完整备份、验证救援通道，并自行评估隐私风险（原厂镜像含设备相关数据）。因照本文操作造成的任何损失由操作者自行承担。

---

*仓库：`guaniu331520/W202DS-root` · 文档生成：2026-11-09 · 全部结论基于真机命令输出与日志*
