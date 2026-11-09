# 原厂分区镜像（压缩分卷）

这里放的是**本机 21 个原厂分区的完整二进制备份**——也就是"变砖后能救回来的那份东西"本体。之前的版本只放了脚本和哈希清单，镜像本体留在本地；现在按压缩分卷的方式一并入库，仓库才算完整。

## 数据概览

| 项目 | 值 |
|---|---|
| 来源 | `flash-tools/stock_backup/`（root 之前从设备读出） |
| 分区数 | 21（`boot_a/b`、`vendor_boot_a/b`、`trustos_a`、`uboot_a/b`、`vbmeta_*`、`dtb*`、`init_boot*`、`misc`、`persist`、`sml_a`、`splloader`） |
| 原始体积 | 390.1 MB |
| 压缩后 | **80.4 MB**（`tar.gz`，gzip level 6，约 20.6%） |
| 分卷 | **17 个**：`stock_backup.tar.gz.part01` ~ `part17`，每卷 5 MB（最后一卷 0.39 MB） |

## 为什么要压缩 + 分卷

- GitHub 单文件上限 100 MB，且仓库体积不宜过大 → 390 MB 原样不能推。
- 本项目网络里只有 `api.github.com`（Contents API）可写，`uploads.github.com`（Release 附件端点）不可达 → 大二进制只能走 Contents API。
- Contents API 要求文件内容 base64 编进 JSON；80 MB 会变成约 107 MB 的单个请求，既超限又容易超时 → 切成 5 MB 一卷，每卷 base64 约 6.7 MB，稳定可传。
- 还原时按顺序拼接即可，**不需要任何额外软件**（`restore.py` 只用 Python 标准库）。

## 目录文件

| 文件 | 用途 |
|---|---|
| `stock_backup.tar.gz.part01` … `part17` | 压缩包的二进制分卷 |
| `manifest.json` | 卷数、每卷大小与 SHA-256、原始/压缩体积、压缩包整体哈希 |
| `SHA256SUMS.txt` | 分卷、压缩包、以及 21 个原始分区镜像的 SHA-256 |
| `restore.py` | 一键校验 + 合并 + 解压（只用标准库，无需 root / 联网） |
| `README.md` | 本说明 |

> 未切分的 `stock_backup.tar.gz`（80.4 MB）保留在本地 `flash-tools/`，**不入库**——它可以由分卷完整重建，重复放一份没有意义。

## 怎么还原（3 步）

```bash
# 1. 把整个 stock-images/ 目录下载到本地（保持 17 个分卷在同一目录）
cd stock-images

# 2. 校验 + 合并 + 解压
python3 restore.py
# 输出：ok part01 ... OK extracted 21 partition images -> restored_stock_backup/

# 3. 用清单再核对一次原始分区
sha256sum -c SHA256SUMS.txt       # Linux / Git Bash
```

`restore.py` 会逐卷校验 SHA-256，任何一个分卷损坏都会**直接中止**，不会生成错误的镜像。合并后的 `stock_backup.tar.gz` 也会再校验一次整体哈希。

## 救砖时怎么用

还原出来的 `restored_stock_backup/` 就是 `anti-brick/scripts/stock_backup.py` 当初产出的目录结构。配合：

- `anti-brick/scripts/brom_session.py` — 进入 BootROM / FDL 通道
- `anti-brick/scripts/verify_rescue.py` — 确认救援通道可重复进入
- `anti-brick/scripts/flash_part.py` — 写回 `trustos_a` + `boot_a`
- `anti-brick/scripts/verify_writeback.py` — 回读比对

完整流程见 [`../README.md`](../README.md) 的「救砖流程」章节。

## ⚠️ 隐私提醒

这些是**从一台具体设备读出的原厂镜像**，可能包含该设备的校准数据、序列号相关信息（`persist` 等分区）。本仓库是公开的，如果你不希望这类数据公开，请：

- 把本目录改为私有 / 从仓库移除，或
- 只保留 `SHA256SUMS.txt` 与脚本，镜像本体自行保管（这也是之前版本的做法）。

## 开源与许可

分卷是设备固件数据，**不是本项目的原创代码**，请勿二次分发到别处；`restore.py` / `make_stock_archive.py` 等脚本为本次编写，随仓库开源。生成脚本见仓库 `scripts/make_stock_archive.py`。
