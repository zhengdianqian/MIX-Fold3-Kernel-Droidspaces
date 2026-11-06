# MIX Fold 3（babylon）内核改造 · 收尾说明（2026-11-04）

## ① 最终运行的内核

| 项 | 内容 |
|---|---|
| 设备当前内核 | `5.15.220-ASB-2026-11-02_13-5.15-dirty`（GKI 5.15.220，THIN LTO + CFI） |
| 来源 | 本地 `~/aegis/src/kernel-common` 自建（5.15.220 + 厂商基线 + SusFS 兼容），未改版本号 |
| 设备 boot_b 内核段 sha256 | `24129d7d9ba6e3764d35a0a10102163afde53eef1df506e8b1f14fbd089b5460` |
| 原厂内核 | `5.15.194`，kernel 段 sha256 `89762cce5bae8c653fabd878ad1f8991b8a63379abbfb3496fd5a7cfd069605e` |
| root | KernelSU（LKM 模式，装在 `init_boot`）；SusFS 以 LKM（`susfs_guard_lkm.ko`）由 `ksud insmod` 加载，开机由模块脚本重新加载 |

## ② 交付物清单

| 文件 | 大小 | sha256 |
|---|---|---|
| `AnyKernel3-babylon-5.15.220-20261104.zip` | 22,462,895 B | `20b0140520f4645ca07ff651c39d8c6b7ed781ffdd0ead8334327d86990eec58` |
| `AnyKernel3-babylon-stock-5.15.194-20261104.zip` | 24,643,465 B | `d241f4ccec6c318c14cbacf9a5ae4b1dea703ec461721d93889889c4d8cd3a5d` |
| `images/Image_lto`（自建内核段） | 42,908,160 B | `24129d7d…b5460` |
| `images/Image_stock`（原厂内核段） | 47,577,600 B | `89762cce…605e` |
| `images/boot_new2.img`（当前设备 boot 镜像） | 42,913,792 B | — |
| `images/boot_b.img` / `init_boot_b.img` / `vendor_boot_b.img` / `vbmeta_b.img`（原机分区转储） | — | — |
| `apk/HorizonKernelFlasher-v1.3.apk`（AK3 zip 刷写工具） | 49,260 B | `442adca287bc74d6bf02f1593edd7da0a194ec5df0c3c2dbe6e43a49f73a1138` |
| `logs/`、`diag_*.sh`、`measure.sh`、`sched_probe.sh` 等 | — | 诊断/实测脚本与输出（调度诊断数据已采集，报告未落盘） |

两个 AK3 zip 的 `anykernel.sh` 完全相同（sha256 `983c515453a3d0d1687da94ec8aa490039f7d566312d55ac65bfcbdc88a70109`）：`device.name1=babylon`、`BLOCK=/dev/block/bootdevice/by-name/boot`、`IS_SLOT_DEVICE=1`、`do.modules=0`、`NO_MAGISK_CHECK=1`，用 `split_boot` + `flash_boot` 只替换 kernel。

## ③ 回退路径

1. 手机端（推荐）：用 Horizon Kernel Flasher / TWRP 刷 `AnyKernel3-babylon-stock-5.15.194-20261104.zip` → 回到原厂内核。
2. PC 端兜底：`fastboot flash boot D:\babylon_images_OS3.0.304.0.WMVCNXM_16.0\images\boot.img`
3. 以上操作只动 `boot` 分区，`init_boot`（KSU）不受影响，无需重装 root。

## ④ 已知限制

- **THIN LTO vs 官方 FULL LTO**：本内核为 THIN LTO + CFI 构建，与小米官方 FULL LTO 在体积与跨模块优化上存在差异；未做完整性能基准对比。
- **缺小米私有补丁**：厂商私有改动未全量移植，个别 vendor 侧特性可能表现与官方内核不同，建议仅作实验用途。
- **无待机耗电实测数据**：采样期间 `stay_on_while_plugged_in=2`（屏幕常亮），空闲采样作废，耗电结论暂无数据支撑。
- **SusFS 为外挂 LKM**：依赖 `ksud insmod` 与 KMI 匹配；系统/vendor 升级后需重新匹配，否则开机加载失败（`/proc/susfs_*` 不出现）。
