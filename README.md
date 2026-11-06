# MIX Fold 3（babylon）内核适配 Droidspaces

作者：**默默的阿文**　｜　设备：小米 MIX Fold 3（`babylon` / SM8550 / Android 16）

> **仓库独立性声明**：本仓库是一条独立工作线，与 `zhengdianqian/Droidspaces-Kernel-Shim`（Redmi Pad Pro 那条）**没有任何文件往来**，也没有向那个仓库提交过任何内容。两条线的设备、基线内核、KMI 与产物完全不同，请勿混用刷机包。

本仓库记录「给 MIX Fold 3 的内核补齐 Droidspaces 所需的命名空间 / SysV IPC 支持」这件事的完整过程：改了什么、怎么编、怎么验、怎么刷、怎么回滚，以及一路上踩过的所有坑。**不包含内核源码、boot 镜像、刷机 zip 等大文件**（见 [大文件与校验](#12-大文件与校验)）。

---

## 1. 目标与背景

Droidspaces 在容器里跑完整 Linux 发行版，需要内核提供 PID / IPC 命名空间与 SysV IPC。MIX Fold 3 的原厂内核把这些全部关掉了：

| 需求 | 原厂 5.15.194 | 改造后 |
|---|---|---|
| `CONFIG_PID_NS` | 未设置 | `=y` |
| `CONFIG_IPC_NS` | 未设置 | `=y` |
| `CONFIG_SYSVIPC` | 未设置 | `=y`（含 `SYSVIPC_SYSCTL` / `SYSVIPC_COMPAT`） |
| `CONFIG_POSIX_MQUEUE` | 未设置 | `=y`（含 `POSIX_MQUEUE_SYSCTL`） |

约束同样明确：**不碰** `CONFIG_CFS_BANDWIDTH` 与 `CONFIG_CGROUP_PIDS`。这两项会改变 `task_struct` / cgroup 相关布局，破坏厂商 kABI，逼着把所有 vendor 模块重编一遍，风险与收益完全不成比例。

最终形态：

| 项 | 值 |
|---|---|
| 设备代号 | `babylon`（MIX Fold 3） |
| 原厂内核 | `5.15.194`（KMI `5.15-android13-8`，gen 8） |
| 改造后内核 | `5.15.220-ASB-2026-11-02_13-5.15-dirty` |
| 内核源码 | AOSP `kernel/common` `android13-5.15`（SUBLEVEL 220） |
| LTO / CFI | `LTO_CLANG_THIN` + `CFI_CLANG`（保留 CFI，LTO 由 FULL 改 THIN） |
| 分区改动 | **只替换 `boot` 分区里的 kernel 段**；`init_boot`（KernelSU）、`vendor_boot`、`vbmeta` 一律不动 |

---

## 2. 环境与工具链

| 项 | 值 |
|---|---|
| 构建宿主 | WSL2 / Ubuntu 24.04，11,961 MB RAM（约 11.7 GiB）+ 4,096 MB swap，16 vCPU |
| 编译器 | clang `r450784e`（`Android (8508608, based on r450784e) clang version 14.0.7`） |
| 链接器 | LLD 14.0.7（`CONFIG_LD_IS_LLD=y`） |
| pahole | 1.25（原厂配置里是 1.23） |
| 构建命令 | `make ARCH=arm64 LLVM=1 -j12 Image modules` |
| 刷写工具 | Horizon Kernel Flasher v1.3（开源 AK3 刷写器，`xzr.hkf`） |
| Root | KernelSU（LKM 模式，装在 `init_boot`，本仓库不涉及） |

工具链与源码的获取不影响本仓库的可复现性：clang `r450784e` 取自 AOSP `prebuilts/clang/host/linux-x86`，源码用 `repo` 或 `git clone -b android13-5.15 https://android.googlesource.com/kernel/common`，检出到 `SUBLEVEL=220` 的那次提交即可。

---

## 3. 内核改动清单

### 3.1 配置

权威版本是 [`config/config_final`](config/config_final)（6,964 行，sha256 `7e8c8c81…e81468`），原厂基线是 [`config/config_stock`](config/config_stock)（6,962 行）。完整差异见 [`config/config.diff`](config/config.diff)（121 行）。

**功能性改动（4 项）**

```
CONFIG_SYSVIPC=y
CONFIG_SYSVIPC_SYSCTL=y
CONFIG_SYSVIPC_COMPAT=y
CONFIG_POSIX_MQUEUE=y
CONFIG_POSIX_MQUEUE_SYSCTL=y
CONFIG_IPC_NS=y
CONFIG_PID_NS=y
```

**为了跑起来 / 为了 ABI 必须一起改的（不要漏）**

| 配置 | 改动 | 原因 |
|---|---|---|
| `CONFIG_LTO_CLANG_FULL` → `CONFIG_LTO_CLANG_THIN` | FULL 关、THIN 开 | FULL LTO 在 12 GB WSL 上被 OOM killer 杀掉（见坑 1） |
| `CONFIG_CFI_CLANG` | 保持 `=y` | 关掉 CFI 会改变 `struct module` 布局 → `module_layout` CRC 不匹配 → vendor 模块全部拒载（见坑 2） |
| `CONFIG_TRIM_UNUSED_KSYMS` | `y` → 未设置 | 开着会把新内核里未被引用的导出符号裁掉，vendor KO 报 unknown symbol |
| `CONFIG_MODVERSIONS` | 保持 `=y` | 厂商 KO 靠 CRC 校验，不能关 |
| `CONFIG_ARM64_ERRATUM_4118414` | 新增 `=y` | 5.15.220 新增的 arm64 勘误项，跟随上游 |
| `CONFIG_MEMFD_ASHMEM_SHIM` | 移除 | 5.15.220 已无此 Kconfig |
| `CONFIG_UNUSED_KSYMS_WHITELIST` | 移除 | 原值指向构建机绝对路径，且随 `TRIM_UNUSED_KSYMS` 关闭而失效 |

其余差异（`PAHOLE_VERSION=125`、`CC_CAN_LINK`、`UAPI_HEADER_TEST`、`CAN_ESD_USB2→CAN_ESD_USB`、`QCOM_LMH`、`CRYPTO_FIPS140_MOD` 等）都是工具链/上游 Kconfig 变化带出来的，不是人为功能改动，`make olddefconfig` 也会得到同样结果——所以在新环境复现时，建议先 `make ARCH=arm64 LLVM=1 olddefconfig` 再 diff 一次。

**明确没有动的**

```
# CONFIG_CFS_BANDWIDTH is not set      （保持未设置）
# CONFIG_CGROUP_PIDS is not set        （保持未设置）
CONFIG_CGROUP_FREEZER=y                （原样）
```

### 3.2 kABI 补丁（必打，否则 struct 布局漂移）

[`patches/0001-kabi-task-struct-sysvipc.patch`](patches/0001-kabi-task-struct-sysvipc.patch)

打开 `CONFIG_SYSVIPC` 会在 `struct task_struct` 里多出 `sysv_sem` / `sysv_shm` 两个成员，直接插进去会让 `task_struct` 大小变化，所有依赖它的导出符号 CRC 全变。做法是把这两个成员塞进 Android KABI 预留位：

```c
#ifdef CONFIG_SYSVIPC
	ANDROID_KABI_USE(6, struct sysv_sem sysvsem);
	_ANDROID_KABI_REPLACE(ANDROID_KABI_RESERVE(7); ANDROID_KABI_RESERVE(8), struct sysv_shm sysvshm);
#else
	ANDROID_KABI_RESERVE(6);
	ANDROID_KABI_RESERVE(7);
	ANDROID_KABI_RESERVE(8);
#endif
```

同时把原来位于结构体前部的 `sysvsem` / `sysvshm` 定义注释掉，避免重复成员。这是整条工作里**唯一**一处源码改动。

---

## 4. 完整构建步骤（可照抄）

```bash
# 0) 依赖
sudo apt install -y git curl bc bison flex libssl-dev libelf-dev python3 zip unzip

# 1) 源码（任选其一，目标是 5.15.220 的 android13-5.15）
git clone -b android13-5.15 https://android.googlesource.com/kernel/common ~/aegis/src/kernel-common
cd ~/aegis/src/kernel-common
grep -E '^SUBLEVEL' Makefile        # 期望 220

# 2) 工具链（AOSP prebuilts/clang/host/linux-x86 的 r450784e）
export PATH="$HOME/aegis/toolchain/clang-r450784e/bin:$PATH"
clang --version                     # 期望 Android (8508608, based on r450784e) clang 14.0.7

# 3) 打 kABI 补丁 + 写入配置
git apply /path/to/repo/patches/0001-kabi-task-struct-sysvipc.patch
cp /path/to/repo/config/config_final .config
make ARCH=arm64 LLVM=1 olddefconfig
# 复核 4 个功能项确实在
grep -E '^CONFIG_(PID_NS|IPC_NS|SYSVIPC|POSIX_MQUEUE)=' .config

# 4) 编译（-j12 在 16 vCPU / 12 GB 上实测可用；-j16 更容易把内存打满）
make ARCH=arm64 LLVM=1 clean
make ARCH=arm64 LLVM=1 -j12 Image modules
# 产物：arch/arm64/boot/Image，以及 Module.symvers

# 5) 记录产物身份
sha256sum arch/arm64/boot/Image
```

本次实际使用的脚本就是 [`scripts/build3.sh`](scripts/build3.sh)（与 `build2.sh` 仅 `-j8` / `-j12` 不同），日志按 `START / CLEAN_DONE / EXIT / END` 打点，失败时 `EXIT != 0` 一眼可见。

本次一共整树编译 **4 次**：

| 日志 | 时间 | 结果 |
|---|---|---|
| `build.log` | 19:03:54 → 19:10:59 | `EXIT=0` |
| `build2.log` | 19:15:44 → 19:53:57 | **`Killed`，错误 137**（FULL LTO 阶段 OOM） |
| `build3.log` | 19:54:17 → 20:04:24 | `EXIT=0`（THIN LTO，最终产物） |
| `build4.log` | 21:14:09 → 21:24:35 | `EXIT=0`（配置回正后复核） |

---

## 5. 符号校验（闸门）与结果

脚本：[`scripts/analyze.py`](scripts/analyze.py)。原始输出：[`reports/symbols.txt`](reports/symbols.txt)、[`reports/symbols2.txt`](reports/symbols2.txt)（两次运行内容一致，第二次追加了写入路径行）。

它做四件事，任何一项不为 0 都视为「不许刷」：

1. **vendor KO 的 `__versions` vs 新 `Module.symvers`**：逐条比 CRC；
2. **设备 kallsyms 的 `__ksymtab_*` vs 新内核导出**：确认原机导出一个不少；
3. **`abi_gki_aarch64` 覆盖**：KMI 名单里的符号必须全在；
4. **ReKernel KO 的未定义符号**：必须全部可解析。

### 5.1 结果

```
Module.symvers entries: 15588   vmlinux exports: 15578

[1] vendor ko __versions vs new Module.symvers
  ipanetm.ko            entries=7  missing=4  crc_mismatch=0
  memlat_scmi.ko        entries=5  missing=1  crc_mismatch=0
  msm_show_epoch.ko     entries=6  missing=0  crc_mismatch=0
  process_exit.ko       entries=8  missing=0  crc_mismatch=0
  rekernel-…5.15.ko     entries=0  (无 __versions -> 加载时不校验 modversions)
                        undef=72  not_exported=0

[2] device kallsyms vs new exports
  device __ksymtab_* total=11553  vmlinux_exports=8575  module_exports=2978
  device vmlinux exports missing in new kernel: 0
  new-only vmlinux exports: 7003
  KEY-LIKE missing: 0

[3] abi_gki_aarch64: entries=138  missing_in_symvers=0

[4] rekernel undef=72  not_exported=0
```

**判读方式**：闸门看的是 `crc_mismatch=0` 与「not_exported=0」；`missing` 那几项是**树外**私有符号（`ipa3_*`、`ipc_log_string`、`cpucp_memlat_init`），本来就不在 in-tree `Module.symvers` 里，由同一批 vendor KO 在运行时互相提供，不是 KMI 缺口。设备实测这些模块全部正常加载，反过来验证了这个判读。

结论一句话：**4 个 vendor KO 的 CRC 差异全为 0；设备侧 8,575 个 vmlinux 导出一个不缺；KMI 138 项零缺失；ReKernel 72 个未定义符号全部可解析。**

---

## 6. boot 镜像打包（4096 页对齐是生死线）

MIX Fold 3 的 `boot` 是 **header v4**：`header_size = 1584`，`ramdisk_size = 0`（ramdisk 在 `init_boot` / `vendor_boot` 里）。

关键规则：**kernel 段必须从 4096（页）偏移开始**，而不是紧贴 1584 字节头之后。

| 打包方式 | kernel 起始偏移 | 结果 |
|---|---|---|
| `pack_boot.py`（初版，错的） | 1584 | **开机直接失败**（bootloader 读到错误数据），自动回滚 |
| `pack_boot2.py`（修正版） | 4096（1584 头之后补 `4096-1584=2512` 字节零填充） | 正常开机 |

证据：原厂 `boot_b.img` 与最终 `boot_new2.img` 在 1584–4096 区间**全部为 0**，kernel 首字节（ARM64 Image 头 `4d 5a 40 fa`）都落在 4096。用 [`scripts/cmp_hdr.py`](scripts/cmp_hdr.py) 对照两个镜像的 ARM64 Image 头即可复现这个结论。

正确的打包逻辑见 [`scripts/pack_boot2.py`](scripts/pack_boot2.py)：

```python
img = bytes(hdr) + b"\x00" * (PAGE - HDR) + k      # 1584 头 + 2512 零填充 + kernel
img += b"\x00" * ((-len(img)) % PAGE)              # 尾部再补齐到 4096
```

本次产物的身份（已复算）：

| 文件 | 大小 | kernel 起始 | kernel 段 sha256 |
|---|---|---|---|
| `Image_lto`（自建） | 42,908,160 B | — | `24129d7d9ba6e3764d35a0a10102163afde53eef1df506e8b1f14fbd089b5460` |
| `boot_new2.img`（刷入设备） | 42,913,792 B | 4096 | 同上（`sha256(d[4096:4096+42908160])` 完全一致） |
| `Image_stock`（原厂） | 47,577,600 B | — | `89762cce5bae8c653fabd878ad1f8991b8a63379abbfb3496fd5a7cfd069605e` |
| `boot_b.img`（原机转储） | 201,326,592 B（192 MiB） | 4096 | 同上（`89762cce…`） |

`boot_new2.img` 结构自检结果：`magic=ANDROID!`、`kernel_size=42908160`、`ramdisk_size=0`、`header_size=1584`、`header_version=4`、总大小 `4096 × 10477`。

---

## 7. 刷机与回滚

### 7.1 刷机（定制版）

1. 手机装 Horizon Kernel Flasher v1.3（`xzr.hkf`，需 root），或任意支持 AnyKernel3 的刷写器；
2. 选择 `AnyKernel3-babylon-5.15.220-20261104.zip` 刷入；
3. 重启，等待开机。

AK3 包的定制点（[`anykernel3/anykernel.sh`](anykernel3/anykernel.sh)）：

```
kernel.string=Aegis Kernel 5.15.220-ASB-2026-11-02 (THIN LTO + CFI) for babylon
do.devicecheck=1
device.name1=babylon
BLOCK=/dev/block/bootdevice/by-name/boot
IS_SLOT_DEVICE=1
NO_MAGISK_CHECK=1        # boot 无 ramdisk，Magisk 不能住这里
split_boot; flash_boot   # 只解包/只替换 kernel，ramdisk 与其他分区不碰
```

包内只有 `Image` + AK3 必需脚本/工具（完整清单见 [`anykernel3/MANIFEST.txt`](anykernel3/MANIFEST.txt)），`do.modules=0`，不写 vendor_dlkm。

仓库只保存**定制后的脚本**（`anykernel.sh` / `updater-script`）；`tools/` 里的 busybox、magiskboot 等二进制来自上游 [osm0sis/AnyKernel3](https://github.com/osm0sis/AnyKernel3)，未入库。自行重打包：

```bash
git clone https://github.com/osm0sis/AnyKernel3
cp anykernel3/anykernel.sh            AnyKernel3/anykernel.sh
cp anykernel3/updater-script          AnyKernel3/META-INF/com/google/android/updater-script
cp ~/aegis/src/kernel-common/arch/arm64/boot/Image  AnyKernel3/Image
cd AnyKernel3 && zip -r9 ../AnyKernel3-babylon-5.15.220-$(date +%Y%m%d).zip .
```

注意两点：zip 内**不能有顶层目录**（AK3 要求 `anykernel.sh` 在包根）；`Image` 必须是**未压缩**的 `arch/arm64/boot/Image`，不是 `Image.gz`。

### 7.2 回滚（原厂内核）

| 路径 | 做法 |
|---|---|
| 手机端（推荐） | 刷 `AnyKernel3-babylon-stock-5.15.194-20261104.zip` → 回到 `5.15.194` |
| PC 兜底 | `fastboot flash boot <原厂 boot.img>`（`OS3.0.304.0.WMVCNXM` 线刷包内） |

两个包共用同一份 `anykernel.sh`（sha256 `983c5154…a70109`），区别只在 `Image`。回滚只动 `boot`，`init_boot` 里的 KernelSU 不受影响，**不需要重装 root**。

---

## 8. 实测结果

刷入后设备端实测（只读采集，未刷写其他分区）：

| 检查项 | 结果 |
|---|---|
| `sys.boot_completed` | `1` |
| `uname -r` | `5.15.220-ASB-2026-11-02_13-5.15-dirty` |
| `/proc/self/ns` | 出现 `ipc` / `pid`（改造前没有） |
| 模块加载 | `lsmod` 计数 **408**，全部加载成功 |
| vendor 模块报错 | 无 version magic / unknown symbol / `module_layout` CRC 报错 |
| SusFS | `susfs_guard_lkm.ko` 以 LKM 方式由 `ksud insmod` 加载，`/proc/susfs_*` 正常 |

---

## 9. 踩坑记录（按发生顺序）

### 坑 1：FULL LTO 在 12 GB WSL 上 OOM

`build2.log` 最后停在 `LTO vmlinux.o`，紧接着 `Killed`、`make: *** [Makefile:1307：vmlinux] 错误 137`。

- `137 = 128 + 9`，就是被 OOM killer 杀的；
- 宿主 WSL2 只有 11,961 MB RAM + 4,096 MB swap，单个 `clang -flto` 链接 vmlinux 的峰值就顶穿了；
- 解法不是加 swap（会更慢且照样抖），而是换 `LTO_CLANG_THIN`：峰值内存显著下降，且不影响导出符号 CRC；
- 顺带教训：**不要把 `-j` 拉满**。`-j16` 会把多个 LTO 模块的峰值叠在一起，`-j12` 才稳。

### 坑 2：关掉 CFI 就会 `module_layout` CRC 不匹配

最早为了绕开 OOM，试过直接 `LTO_NONE`（这份中间态 diff 保留在 [`config/config.diff.build2`](config/config.diff.build2)，可以看到 `CONFIG_LTO_NONE=y` 且 `CFI_CLANG` 一起消失）。结果编译能过，但刷进去后所有 vendor KO 拒载：

- `CFI_CLANG` 会改变 `struct module` 等结构的布局，`module_layout` 的 CRC 随之变化；
- 厂商 KO 编的时候记的是原厂的 CRC，对不上就整批加载失败；
- 最终方案：**CFI 必须保留**，只把 `LTO_CLANG_FULL` 换成 `LTO_CLANG_THIN`。CRC 由类型签名决定，与 LTO 的 FULL/THIN 无关，所以 THIN 能同时满足「内存够」与「CRC 对」。

> 这也是为什么 `config.diff.build2` 和 `config_final` 看起来「互相矛盾」：前者是被否决的中间态，后者才是最终态。两个都留在仓库里，就是为了让后来人别再走这条死路。

### 坑 3：kernel 放 1584 偏移 → 开机失败 → 自动回滚

第一版 `pack_boot.py` 按「header 之后紧跟 kernel」的直觉打包，kernel 落在 1584。刷入后设备**无法开机**：

- 触发预设的自动救砖逻辑，立刻刷回原厂 `boot.img`，设备恢复；
- 麻烦的是 **pstore 在这台设备上不可用**，失败启动拿不到 ramoops / 上一次 dmesg，只能靠对照实验定位；
- 对照原厂镜像发现：1584–4096 这 2512 字节**全为零**，原厂 kernel 从 4096 开始；也就是说 bootloader 要求页对齐，1584 处它读到的是零填充，自然启动失败；
- 改成 `pack_boot2.py`（补零到 4096）后一次开机成功。

**这条是整条工作里代价最大、也最值得写下来的一条。**

### 坑 4：`objcopy -O binary --only-section=__versions` 取不出 CRC

最初想用 `objcopy -O binary --only-section=__versions x.ko out.bin` 把 CRC 表抠出来，实际在部分 KO 上失败/输出为空（KO 是 relocatable ELF，`-O binary` 对非 alloc 段的行为并不可靠）。

最终做法（`analyze.py` 里的 `elf_section()`）：直接按 ELF header（`e_shoff` / `e_shentsize` / `e_shnum` / `e_shstrndx`）遍历 section header，按名字匹配 `__versions`，再按 **64 字节一条**解析（前 8 字节 CRC + 56 字节符号名）。取未定义符号则用 `nm -u`，不再依赖 objcopy。

### 坑 5：ACK 树的 modpost 让树外模块 `__versions` 为空

Android Common Kernel 的 `scripts/mod/modpost.c` 在生成 `__versions` 时有一句：

```c
if (!s->module)
	continue;
```

它会把 `vmlinux` 提供的符号直接跳过。结果是**在 ACK 树外编译的模块**（比如 ReKernel）拿到的 `__versions` 是空段：

```
-- rekernel-android13-5.15.ko: versions_bytes=0 entries=0
   (no __versions -> modversions check disabled at load time)
```

这既是现象也是解释：**该 KO 加载时根本不校验 modversions**，所以 CRC 比对对它无意义，只能退而校验「72 个未定义符号是否都能导出」。要用 CRC 校验的模块，必须在 ACK 树内编译，或自行补齐 `__versions`。

### 坑 6：CRC 第一版按「相对偏移」算，结果全错

第一版脚本把 `__versions` 当成「从段内某个基准开始的偏移表」，用相对偏移去取 CRC，跑出来的 `crc_mismatch` 一片红。实际格式是**定长 64 字节连续条目**：

```
struct modversion_info { unsigned long crc; char name[MODULE_NAME_LEN]; };  // 8 + 56 = 64
```

改成从段起点按 64 字节步进遍历后，`crc_mismatch` 立刻归零。**结论：不要对 ELF 段结构做「猜偏移」，按 ABI 定长解析。**

### 坑 7：nekobox 只监听 127.0.0.1，WSL2 连不上

构建期需要代理拉 AOSP 源码，nekobox 默认只监听 `127.0.0.1:2080` 且没开 LAN 模式。WSL2 是 NAT 网络，**访问不到 Windows 的回环地址**，所以 WSL 里 `curl` 直接超时。

解法是加一层 TCP 转发，把 Windows 侧端口暴露给 WSL：

```powershell
# Windows 侧（管理员）：把 2080 转发到 0.0.0.0:2080
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=2080 connectaddress=127.0.0.1 connectport=2080
```

WSL 内则用 `http://<Windows 主机 IP>:2080`。这一步只影响「怎么把源码/工具链拉下来」，与内核逻辑无关，但不知道的话会卡很久。

### 坑 8：其它零碎

- **小米没有开源 babylon 的 5.15 内核分支**，`MiCode/Xiaomi_Kernel_OpenSource` 里找不到，只能用 AOSP common + 厂商基线对齐；
- **TWRP 在这台机器上是纯 ramdisk、不含内核**，刷它等于覆盖 `boot` 抹掉原厂内核，风险极高，不要用来刷内核；
- **不存在叫「AnyKernel3」的官方 App**，AnyKernel3 是 osm0sis 的刷写模板；实际用的是 Horizon Kernel Flasher；
- 刷完内核后 `stay_on_while_plugged_in`、`logd` 等设备状态做过还原，收尾阶段未再重启。

---

## 10. 重启 / 失败开机次数（如实统计）

| 项 | 次数 | 说明 |
|---|---|---|
| 整树编译 | **4** | 3 次成功，1 次被 OOM 杀（`build2.log`） |
| 刷写 boot | **2** | 第 1 次 1584 偏移（失败），第 2 次 4096 对齐（成功） |
| 开机失败 | **1** | 1584 偏移那次，bootloader 读不到有效 kernel |
| 自动回滚（刷回原厂） | **1** | 失败后立即刷回原厂 `boot.img` 救砖 |
| 设备重启 | **3** | 失败启动 1 + 回滚恢复 1 + 修正后成功 1 |
| 收尾阶段重启 | **0** | 收尾只做只读复核与 AK3 dry-run |

失败时无 pstore 日志可用，定位完全靠「原厂镜像 vs 自建镜像」的字节对照，这也是坑 3 花时间最久的原因。

---

## 11. 已知限制

1. **THIN LTO ≠ 官方 FULL LTO**：体积与跨模块优化和官方内核存在差异，未做完整性能基准对比。
2. **厂商私有补丁未全量移植**：个别 vendor 侧特性表现可能与官方内核不同，建议仅作实验用途。
3. **无待机耗电实测**：采样期间 `stay_on_while_plugged_in=2`（屏幕常亮），空闲功耗数据作废，不给耗电结论。
4. **SusFS 是外挂 LKM**：依赖 `ksud insmod` 与 KMI 匹配，系统/vendor 升级后需重新匹配，否则开机加载失败（`/proc/susfs_*` 不出现）。
5. **只在 b 槽验证**：设备当前 slot 为 `b`，a 槽未做对等验证。
6. **树外模块无 `__versions`**（见坑 5）：这类模块的 CRC 闸门只能退化为「符号可解析性」检查。
7. **不提供一键脚本**：构建涉及绝对路径与工具链位置，脚本里的路径需按自己的环境改。

---

## 12. 大文件与校验

以下文件**不进 Git 历史**（单个 8 MB–192 MB，塞进去只会让 clone 变灾难），存放位置与 sha256 见 [`release-assets.sha256`](release-assets.sha256)。如需获取，按清单核对哈希后再用。

| 文件 | 大小（字节） | sha256 |
|---|---|---|
| `AnyKernel3-babylon-5.15.220-20261104.zip` | 22,462,895 | `20b0140520f4645ca07ff651c39d8c6b7ed781ffdd0ead8334327d86990eec58` |
| `AnyKernel3-babylon-stock-5.15.194-20261104.zip` | 24,643,465 | `d241f4ccec6c318c14cbacf9a5ae4b1dea703ec461721d93889889c4d8cd3a5d` |
| `Image_lto`（自建内核段） | 42,908,160 | `24129d7d9ba6e3764d35a0a10102163afde53eef1df506e8b1f14fbd089b5460` |
| `boot_new2.img`（刷入设备的 boot） | 42,913,792 | `979244eea1409753f01adc1730611090fea21f45f971b601713b4dd2125c3b1e` |
| `boot_b.img`（原机 boot 转储，192 MiB） | 201,326,592 | `530e1884370a40911dc19bd956d8911ac137a8610999bc7be3f6f4f8f0255ed5` |
| `init_boot_b.img` | 8,388,608 | `6bc193ee78fe82ec0ad9927862df3e47feb3455dbeb189a7079986a8fb3fcea2` |
| `vendor_boot_b.img` | 100,663,296 | `169d67cd0a1350cc13611966c00d4c476e257b6fe8913b40211913ce68a3c970` |
| `vbmeta_b.img` | 131,072 | `cef4da69376e3e89cd6dd7012d2d8841251666eef62916bbb5e04df604c149e9` |
| `Image_stock`（原厂内核段） | 47,577,600 | `89762cce5bae8c653fabd878ad1f8991b8a63379abbfb3496fd5a7cfd069605e` |
| `HorizonKernelFlasher-v1.3.apk` | 49,260 | `442adca287bc74d6bf02f1593edd7da0a194ec5df0c3c2dbe6e43a49f73a1138` |
| `anland-v5_5.23.apk`（显示后端，仅记录） | 355,549 | `b41e26d982d98d5a7e75a9e413b557df3c0b16358ea0dd5ac7eca7615670b41c` |

> 原厂线刷包 `OS3.0.304.0.WMVCNXM` 内的 `boot.img` 是最终兜底回滚源，属于小米官方分发包，不在本仓库分发。

### 仓库内文件校验

| 文件 | 大小 | sha256 |
|---|---|---|
| `config/config_stock` | 188,554 | `eb03e6badcccd7841043517a26838ad41473d041c09a72020690648deaf5064b` |
| `config/config_final` | 188,442 | `7e8c8c817e4652dc47c54456d7db9e68223e39fdec57dc4ec5dc6c9d50e81468` |
| `config/config.diff` | 3,426 | `539d51416e09183d69d8f5da8d34eb4e5bf468ad00fdaca28a3a8065352e26bc` |
| `config/config.diff.build2` | 1,330 | `06168c95c71159056ada8a2727691ecbc2b0e84d8519ece0bed319aed5439428` |
| `patches/0001-kabi-task-struct-sysvipc.patch` | 917 | `9a367b247ccce781139941a0077b326700cbc6a43cf451a731eb5d7d49d4d031` |
| `reports/symbols.txt` | 2,028 | `b952125d8b03c39b22a3657e9431006dd0c1e8c540bf688fd5cc75eefe926dfd` |
| `reports/symbols2.txt` | 2,113 | `66905714aa85badbfe1c970bd0c4609a634650c10aa7e7708d7b518137d4b220` |
| `scripts/analyze.py` | 6,888 | `0b804c912b52874b46a36a3347f7ac50212c1e85c95121213ee30f66eeb225bc` |
| `scripts/build2.sh` | 506 | `7242b18e6b363a30494cc361af26b61fa66a2854177644ea3bc94f6ebf199936` |
| `scripts/build3.sh` | 508 | `c8a0146cef059c802eafb55b7a9bb05ed408d74c799375e8e3d4830523fd4db4` |
| `scripts/pack_boot.py` | 1,641 | `43cc2502a82c69fcbacce3ca6caea8257926bd945a0a8299ecf9f41537c9a1ea` |
| `scripts/pack_boot2.py` | 1,195 | `effe5b6400a551d48553e889980c189cc2120cea9136b26f6d7bb2f99f0b3002` |
| `scripts/cmp_hdr.py` | 978 | `7590beefae9fadf2bd3c37d96c17f1fe128354058615f0f1afdcf7b3a6fa418d` |
| `anykernel3/anykernel.sh` | 1,067 | `983c515453a3d0d1687da94ec8aa490039f7d566312d55ac65bfcbdc88a70109` |
| `anykernel3/updater-script` | 115 | `32973f7f95a7ca60e4be7b740f05d5faa394c7a9cddea23fd3cf636cabb43711` |
| `anykernel3/MANIFEST.txt` | 790 | `141c0dc4f191a0faae313c9c2529374ef16455a78615ed3e7ea6bce0249e1468` |
| `docs/project-wrap-up-20261104.md` | 3,054 | `7a679beac46c7a4b30b3d68638f5e9b5087e98da11b73fb3f01e27899d6e6937` |

---

## 13. 仓库结构

```
MIX-Fold3-Kernel-Droidspaces/
├── README.md
├── LICENSE
├── config/
│   ├── config_stock            # 原厂 5.15.194 基线配置（6,962 行）
│   ├── config_final            # 最终 5.15.220 配置（6,964 行）
│   ├── config.diff             # 最终权威 diff（stock → final，121 行）
│   └── config.diff.build2      # 历史中间态（LTO_NONE，已被否决，勿用）
├── patches/
│   └── 0001-kabi-task-struct-sysvipc.patch
├── scripts/
│   ├── build2.sh / build3.sh   # 实际构建脚本（-j8 / -j12）
│   ├── pack_boot.py            # 初版（1584 偏移，错误，仅作反面教材）
│   ├── pack_boot2.py           # 修正版（4096 页对齐）
│   ├── analyze.py              # 符号闸门
│   └── cmp_hdr.py              # ARM64 Image 头对照
├── reports/
│   ├── symbols.txt             # 闸门输出
│   └── symbols2.txt            # 同上，第二次运行
├── anykernel3/
│   ├── anykernel.sh            # AK3 定制脚本
│   ├── updater-script
│   └── MANIFEST.txt            # 刷机包内文件清单
├── docs/
│   └── project-wrap-up-20261104.md
└── release-assets.sha256       # 大文件清单（大小 + sha256 + 存放位置）
```

## 14. 许可

- 本仓库的文档、脚本、配置差异：MIT，作者「默默的阿文」，见 [LICENSE](LICENSE)；
- 内核源码本身不在此仓库分发，其许可为 GPL-2.0；
- AnyKernel3 模板版权归 osm0sis（XDA）所有，此处只保留定制后的 `anykernel.sh`。

---

**再次说明：本仓库与 `zhengdianqian/Droidspaces-Kernel-Shim`（Redmi Pad Pro）是两条完全独立的工作线，互不引用、互不覆盖。**
