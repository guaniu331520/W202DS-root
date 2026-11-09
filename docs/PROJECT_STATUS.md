# ZTE W202DS Root 项目 · 交接状态卡

> 唯一事实来源。后续继续工作只需读本文件，不必回溯长对话。

## 设备与环境
- ZTE W202DS / SN `<DEVICE_SERIAL>` / Android 13 (SDK 33) / arm64-v8a / ums9620
- BL locked、green；slot `_a`；`veritymode=enforcing`
- `/ /system /system_ext /vendor /product /odm` 全为 **erofs 只读**，root 也不能 remount rw
- 内核 **overlayfs 被锁死**：tmpfs upper 报 `not supported`，f2fs upper 报 `xattr` 不支持
- Magisk v31.1.0 (31100)：`magisk` 只认 `-v`/`-c`；magiskd 授权缓存于内存，直写 sqlite 不生效
- Magisk **模块级 magic mount 不创建新文件**；`mount --bind` 实测可用
- adb：`C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools\platform-tools\adb.exe`
- root 备用入口（安全模式时 su 不在 PATH）：`/debug_ramdisk/su -c 'id'`

## 已完成
1. **Root（B 路线）**：patched trustos（禁 AVB）+ Magisk 修补的 `boot_a` 已刷入并验证启动。
2. **应用 + ADB root 可开关**：Magisk Manager → Superuser 打开 `com.android.shell`(Shell)。
   v31 无 "Apps and ADB" 总开关；关掉即收回 ADB root，**不写入 Magisk 数据库**。
3. **设备恢复（11-08 20:29）**：删除 `gms_priv` / `gms-enable` 模块及全部测试残留，重启退出 Magisk 安全模式。
   现状：`su` = `/system_ext/bin/su`；`su -c id` → `uid=0(root)`；模块列表为空；`boot_completed=1`。

## 已证伪，不要重试
- **官方 Play 商店在本机不可行**：
  - 出厂 GMS 在 `/data/app`（非特权），GSF 需要 `READ_DEVICE_CONFIG`（`signature|preinstalled`），`pm grant` 无效 → 必崩
  - erofs 只读 + overlay 锁定 + 模块 magic mount 不建新文件 → 无法注入 `/system/priv-app`
  - `mount --bind` 强挂 `/product/priv-app` 方案：权限目录复制失败、`service.sh` 跑太早（PM 未就绪）、触发 Magisk bootloop 保护禁用全部模块 → **已回滚**
  - 出厂 GMS 不完整（缺 GoogleLoginService），且无配套 privapp-permissions 白名单
- ZTE 开机禁用 GMS 的元凶：`com.zte.heartyservice.strategy` 的 `BootCompletedReceiver` + `PackageChangeReceiver`（`pm enable` 会触发后者反复禁用）
- 出厂 GMS 现状：三个包仍在 `/data/app`，全部 **disabled**（回到初始状态，无数据损失）

## 剩余工作
- **A. 装 microG + Aurora Store**：先卸载出厂 GMS 三包（`com.android.vending` / `com.google.android.gms` / `com.google.android.gsf`，均在 `/data/app` 可卸载）以腾出同名包名；再装 microG GmsCore + GsfProxy + Aurora Store，配置自更新并验证。
  - 网络：`github.com` / `api.github.com` **通**；`f-droid.org` / `gitlab.com` **不通**（APK 需走 GitHub releases 或 F-Droid 镜像）
- **B. 整理教程推 GitHub**：仓库内容 = 本次 root 全过程 + microG/Aurora 安装说明教程（中文）。
  - `git` 2.55 有；`gh` CLI **无**；git 全局 user.name/email **未配置**
  - `flash-tools/` 下有 >100MB 大文件（MindTheGapps 385MB、`gms_module.zip` 384MB、`part.0~6` 各 48MB、`magisk_boot_a.img` 67MB）→ **推 GitHub 必须排除**
  - **实测结论（11-08 22:00）**：GitHub 集成**全局只读**——`create_repository` 403、`push_files` / `create_or_update_file` 均 `internal_error`，对已有仓库 `Tools` 写入也返回 `403 Resource not accessible by integration`。**无法通过集成自动推送**。
  - 用户已手动建好目标仓库 `guaniu331520/W202DS-root`（public，默认分支 main，内含 GitHub 自动生成的 README.md 与 .gitignore）。
  - 备选推送通道：`flash-tools/push_guide.py`（读环境变量 `GITHUB_PAT`，git clone → 覆盖 → commit → push，token 不落盘）；或用户在网页手动上传 `zte-w202ds-guide/README.md`。

## 已产出成果（11-08 22:00）
- `zte-w202ds-guide/`：本地归档，71 个文本文件 / 1.1 MB（已排除所有 >2MB 二进制与镜像），含 `docs/`、`scripts/`、`logs/`、`reports/`、`modules/`、`.gitignore`。
- `zte-w202ds-guide/README.md`：**完整中文教程**（root 全过程、可开关 ADB root、官方 Play 不可行的证据链、microG/Aurora 安装与自更新、恢复回滚、命令速查、免责声明）。
- `flash-tools/download_apks.py`：多线程分段落盘下载脚本（国内镜像 + Clash 兼容）。
- `flash-tools/push_guide.py`：待 PAT 的一键推送脚本。
- 未入库大文件仍留在 `flash-tools/`：`apks/`（3 个 APK）、`magisk_boot_a.img`、`stock_backup/`、`part.0~7`、`MindTheGapps-13-arm64.zip`、`gms_module.zip`。

## 收尾状态（11-08 22:59，用户休息，明天继续）

### 已完成
- **设备 100%**：root 正常；Aurora Store 4.8.4 + microG FakeStore + GmsCore 0.3.17.252432 全部安装、启用、可启动（microG 设置界面已实测打开）；出厂 GMS 已卸载；ZTE 两个禁用接收器已禁。手机侧网络代理由用户自行配置（Aurora 需能访问 Google 服务器）。
- **归档 100%**：`zte-w202ds-guide/` 93 文件 / 1.9MB，含 `anti-brick/`（防变砖专目录，21 文件）；全库脱敏，序列号与本机路径残留 0。
- 后台等待授权的进程已停止，未留下任何 token 文件；临时分段目录与 `__pycache__` 已清理。
- **唯一剩余待办**：把归档推到 GitHub `guaniu331520/W202DS-root`（public，默认分支 `main`）。

### GitHub 推送的已知障碍
- 内置 GitHub 集成**只读**：`create_repository` 403；`push_files` / `create_or_update_file` 返回 `internal_error`；对已有仓库 `Tools` 写入也 403 `Resource not accessible by integration`。
- 本机无 `gh` CLI、无 PAT、无 git 凭据。
- `github.com/login/*` 端点网络不稳：Bash curl / Python 全部 000；PowerShell `HttpWebRequest` 有时可用（成功申请过 device code，轮询返回过 `authorization_pending` / `slow_down`）。
- `api.github.com` **可达**（Python + `ProxyHandler({})`），所以**只要有 token，推送一定没问题**。
- 授权网页若额外要求输入验证码，那是 GitHub 账号自身的登录 / 两步验证 / 人机验证，不是脚本缺参数；必须点到 **Authorize** 成功页才算完成（否则轮询一直是 `authorization_pending`）。

### 明天三条路（按推荐顺序）
1. **设备授权（无需 PAT，推荐）**：用 **PowerShell 工具**运行 `flash-tools/github_device_flow.ps1`（或把内容粘进 PowerShell 工具，可 `run_in_background`）。它会打印 USER_CODE → 用户打开 `https://github.com/login/device` 输入码、完成账号验证并点 Authorize → 脚本自动兑换 token（仅内存）→ 调 `push_via_api.py` 把 93 个文件推到 `main`。**不要用 Bash 调 PowerShell**（安全策略会拦）。
2. **PAT**：用户给 `GITHUB_PAT`（repo 权限）→ `python3 flash-tools/push_guide.py`（git clone → commit → push）。
3. **网页上传**：仓库页 `Add file → Upload files` 拖入 `zte-w202ds-guide/` 文件夹，零凭据。

### 关键文件
| 文件 | 用途 |
|---|---|
| `zte-w202ds-guide/README.md` | 完整中文教程 |
| `zte-w202ds-guide/anti-brick/README.md` | 防变砖 / 救援说明 |
| `flash-tools/github_device_flow.ps1` | 设备授权全流程（推荐入口） |
| `flash-tools/push_via_api.py` | REST API 推送，读 env `WB_GH_TOKEN` |
| `flash-tools/push_guide.py` | PAT + git 推送 |
| `flash-tools/download_apks.py` | APK 分段下载 |
| `flash-tools/apks/` | 3 个 APK（不入库） |

### 安全
授权 token 只在内存环境变量里，不落盘、不打印；脚本结束会清除。用完可在 GitHub → Settings → Applications 撤销授权。

## ✅ 全部完成（11-09 12:37）

- **网络**：用户开启 V2rayN 后全局/TUN 接管流量，`curl --noproxy '*'` 直连通道稳定（`github.com/login/device/code` POST 5/5 成功、平均 0.59s），无需手动指定 10808。
- **推送方式**：GitHub OAuth Device Flow（`flash-tools/auto_device_push.py` 申请码 → 用户网页授权 → 兑换 token 仅内存 → `flash-tools/push_via_api.py` 经 `api.github.com` 推送）。
- **第一轮**：84/93 成功；9 个失败是脚本 bug（已存在文件缺 sha 导致 422、大文件走命令行超 Windows 32K 导致 WinError 206）。
- **修复**：`push_via_api.py` 改为正确取 sha + 用临时文件 `--data-binary @file` 传大内容，并新增 `WB_ONLY_PATHS` 只推指定文件。
- **补齐**：`PUSHED=9 FAILED=0`。
- **最终校验**：仓库 `main` 共 **93 个文件**（与本地归档一致），`README.md` 16661 字节、标题为「ZTE W202DS Root + microG / Aurora Store 实战教程」，含 `anti-brick/` 与 microG 章节；关键文件（防变砖脚本、哈希清单、日志、模块 XML）全部齐全。
- 仓库地址：**https://github.com/guaniu331520/W202DS-root**（public，默认分支 main）
- 注：仓库内 `docs/PROJECT_STATUS.md` 是推送时的过程记录快照，教程正文以根目录 `README.md` 为准；本文件为本地最新版。
