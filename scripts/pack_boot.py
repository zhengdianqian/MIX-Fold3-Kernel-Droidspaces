#!/usr/bin/env python3
import struct, hashlib, os, sys

SRC_IMG = "/mnt/d/babylon_images_OS3.0.304.0.WMVCNXM_16.0/images/boot.img"
KERNEL = os.path.expanduser("~/aegis/src/kernel-common/arch/arm64/boot/Image")
OUTDIR = "/mnt/c/Users/Administrator/Documents/Trae-CN/temp_20261103_05/images"
OUT = os.path.join(OUTDIR, "boot_new.img")
PAGE = 4096
HDR = 1584

def main():
    k = open(KERNEL, "rb").read()
    ks = len(k)
    print("kernel Image size", ks, "sha256", hashlib.sha256(k).hexdigest())
    hdr = bytearray(HDR)
    struct.pack_into("<8s", hdr, 0, b"ANDROID!")
    struct.pack_into("<I", hdr, 8, ks)       # kernel_size
    struct.pack_into("<I", hdr, 12, 0)       # ramdisk_size
    struct.pack_into("<I", hdr, 16, 0)       # os_version
    struct.pack_into("<I", hdr, 20, HDR)     # header_size
    struct.pack_into("<I", hdr, 40, 4)       # header_version
    # cmdline 44..1580 empty
    struct.pack_into("<I", hdr, 1580, 0)     # boot_signature_size
    img = bytes(hdr) + k
    pad = (-len(img)) % PAGE
    img += b"\x00" * pad
    os.makedirs(OUTDIR, exist_ok=True)
    open(OUT, "wb").write(img)
    print("boot_new.img size", len(img), "pad", pad, "sha256", hashlib.sha256(img).hexdigest())

    # verify
    d = open(OUT, "rb").read()
    assert d[:8] == b"ANDROID!", "magic bad"
    ksz, rsz = struct.unpack_from("<II", d, 8)
    hv, hs = struct.unpack_from("<I", d, 40)[0], struct.unpack_from("<I", d, 20)[0]
    print("verify magic=ANDROID! kernel_size=%d ramdisk_size=%d header_version=%d header_size=%d" % (ksz, rsz, hv, hs))
    assert ksz == ks and rsz == 0 and hv == 4 and hs == HDR
    print("OK ->", OUT)

main()
