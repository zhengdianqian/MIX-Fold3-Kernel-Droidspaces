#!/usr/bin/env python3
import os, re, subprocess, sys, json

KSRC = os.path.expanduser("~/aegis/src/kernel-common")
ABI = os.path.expanduser("~/aegis/abi")
OUT = "/mnt/c/Users/Administrator/Documents/Trae-CN/temp_20261103_05/logs/symbols.txt"

def log(f, *a):
    s = " ".join(str(x) for x in a)
    print(s)
    f.write(s + "\n")

def read_symvers(path):
    d = {}
    for line in open(path):
        parts = line.split()
        if len(parts) < 3:
            continue
        crc, sym, mod = parts[0], parts[1], parts[2]
        d[sym] = (crc, mod)
    return d

def elf_section(path, wanted):
    d = open(path, "rb").read()
    e_shoff = int.from_bytes(d[0x28:0x30], "little")
    e_shentsize = int.from_bytes(d[0x3A:0x3C], "little")
    e_shnum = int.from_bytes(d[0x3C:0x3E], "little")
    e_shstrndx = int.from_bytes(d[0x3E:0x40], "little")
    def sh(i):
        o = e_shoff + i * e_shentsize
        name = int.from_bytes(d[o:o+4], "little")
        off = int.from_bytes(d[o+0x18:o+0x20], "little")
        size = int.from_bytes(d[o+0x20:o+0x28], "little")
        return name, off, size
    _, stroff, strsize = sh(e_shstrndx)
    for i in range(e_shnum):
        name, off, size = sh(i)
        nm = d[stroff+name:stroff+name+64].split(b"\x00")[0].decode("latin1")
        if nm == wanted:
            return d[off:off+size]
    return b""

def ko_versions(path):
    raw = elf_section(path, "__versions")
    n = len(raw) // 64
    ents = []
    for i in range(n):
        crc = int.from_bytes(raw[i*64:i*64+8], "little")
        name = raw[i*64+8:i*64+64].split(b"\x00")[0].decode("latin1")
        if name:
            ents.append((name, crc))
    return ents, len(raw)

def ko_undef(path):
    out = subprocess.run(["nm", "-u", path], capture_output=True, text=True).stdout
    syms = []
    for line in out.splitlines():
        p = line.split()
        if len(p) == 2:
            syms.append(p[1])
    return syms

def kallsyms_exports(path):
    vmlinux_exports = set()
    module_exports = set()
    total_ksymtab = 0
    for line in open(path, errors="ignore"):
        if "__ksymtab_" not in line:
            continue
        p = line.split()
        if len(p) < 3:
            continue
        name = p[2]
        if not name.startswith("__ksymtab_"):
            continue
        total_ksymtab += 1
        sym = name[len("__ksymtab_"):]
        if len(p) >= 4:
            module_exports.add(sym)
        else:
            vmlinux_exports.add(sym)
    return vmlinux_exports, module_exports, total_ksymtab

def abi_list(path):
    syms = set()
    if not os.path.exists(path):
        return None
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            continue
        # entries may have form "symbol" or "type ..." blocks
        if " " in line:
            continue
        syms.add(line)
    return syms

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    f = open(OUT, "w", encoding="utf-8")
    symvers_path = os.path.join(KSRC, "Module.symvers")
    if not os.path.exists(symvers_path):
        log(f, "FATAL Module.symvers missing")
        return 1
    newsv = read_symvers(symvers_path)
    vmlinux_exports = {s for s, (c, m) in newsv.items() if m == "vmlinux"}
    all_exports = set(newsv.keys())
    log(f, "Module.symvers entries:", len(newsv), "vmlinux exports:", len(vmlinux_exports))

    # 1. vendor ko __versions vs new crc
    log(f, "\n=== [1] vendor ko __versions vs new Module.symvers ===")
    kos = sorted(x for x in os.listdir(os.path.join(ABI, "ko")) if x.endswith(".ko"))
    for ko in kos:
        ents, rawlen = ko_versions(os.path.join(ABI, "ko", ko))
        log(f, "\n-- {0}: versions_bytes={1} entries={2}".format(ko, rawlen, len(ents)))
        if not ents:
            log(f, "   (no __versions -> modversions check disabled at load time)")
        missing = []
        mismatch = []
        for name, crc in ents:
            if name not in newsv:
                missing.append(name)
            else:
                ncrc = newsv[name][0]
                try:
                    if int(ncrc, 16) != crc:
                        mismatch.append((name, hex(crc), ncrc))
                except ValueError:
                    pass
        log(f, "   missing_symbols={0} crc_mismatch={1}".format(len(missing), len(mismatch)))
        for m in missing[:40]:
            log(f, "   MISSING {0}".format(m))
        for m in mismatch[:40]:
            log(f, "   MISMATCH {0} ko={1} kernel={2}".format(*m))
        # also undefined symbols
        und = ko_undef(os.path.join(ABI, "ko", ko))
        miss_u = [s for s in und if s not in all_exports]
        log(f, "   undef={0} not_exported={1}".format(len(und), len(miss_u)))
        for m in miss_u[:40]:
            log(f, "   UNDEF_NOT_EXPORTED {0}".format(m))

    # 2. device kallsyms exports diff
    log(f, "\n=== [2] device kallsyms vs new kernel exports ===")
    ks = os.path.join(ABI, "kallsyms.txt")
    dev_v, dev_m, total = kallsyms_exports(ks)
    log(f, "device __ksymtab_* total={0} vmlinux_exports={1} module_exports={2}".format(total, len(dev_v), len(dev_m)))
    missing_dev = sorted(s for s in dev_v if s not in all_exports)
    log(f, "device vmlinux exports missing in new kernel: {0}".format(len(missing_dev)))
    for s in missing_dev[:200]:
        log(f, "  DEV_ONLY {0}".format(s))
    extra = sorted(s for s in vmlinux_exports if s not in dev_v)
    log(f, "new-only vmlinux exports: {0} (first 20) {1}".format(len(extra), extra[:20]))
    key_pat = re.compile("freezer|netfilter|kprobe|binder|android_vh|task_freeze|freezing|nf_|ip_")
    keymissing = [s for s in missing_dev if key_pat.search(s)]
    log(f, "KEY-LIKE missing: {0} {1}".format(len(keymissing), keymissing[:60]))

    # 3. abi_gki_aarch64 coverage
    log(f, "\n=== [3] abi_gki_aarch64 coverage ===")
    for cand in ["android/abi_gki_aarch64", "android/abi_gki_aarch64_core"]:
        p = os.path.join(KSRC, cand)
        s = abi_list(p)
        if s is None:
            log(f, "{0}: NOT FOUND".format(cand))
            continue
        missing = sorted(x for x in s if x not in all_exports)
        log(f, "{0}: entries={1} missing_in_symvers={2}".format(cand, len(s), len(missing)))
        for m in missing[:60]:
            log(f, "   KMI_MISSING {0}".format(m))

    # 4. rekernel undef
    log(f, "\n=== [4] rekernel ko undefined vs exports ===")
    rk = os.path.join(ABI, "ko", "rekernel-android13-5.15.ko")
    if os.path.exists(rk):
        und = ko_undef(rk)
        miss = [s for s in und if s not in all_exports]
        log(f, "rekernel undef={0} not_exported={1}".format(len(und), len(miss)))
        for m in miss:
            log(f, "   RK_MISSING {0}".format(m))
    f.close()
    print("WROTE", OUT)
    return 0

sys.exit(main())
