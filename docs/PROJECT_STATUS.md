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
  - 可走 GitHub connector（MCP）直接建仓/推文件，绕过本地认证
