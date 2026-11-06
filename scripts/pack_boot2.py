import struct, hashlib, os

KERNEL = r"C:\Users\Administrator\Documents\Trae-CN\temp_20261103_05\images\Image_lto"
OUT = r"C:\Users\Administrator\Documents\Trae-CN\temp_20261103_05\images\boot_new2.img"
PAGE = 4096
HDR = 1584

k = open(KERNEL, "rb").read()
ks = len(k)
print("kernel Image size", ks, "sha256", hashlib.sha256(k).hexdigest())

hdr = bytearray(HDR)
struct.pack_into("<8s", hdr, 0, b"ANDROID!")
struct.pack_into("<I", hdr, 8, ks)
struct.pack_into("<I", hdr, 12, 0)
struct.pack_into("<I", hdr, 16, 0)
struct.pack_into("<I", hdr, 20, HDR)
struct.pack_into("<I", hdr, 40, 4)
struct.pack_into("<I", hdr, 1580, 0)

img = bytes(hdr) + b"\x00" * (PAGE - HDR) + k
img += b"\x00" * ((-len(img)) % PAGE)
open(OUT, "wb").write(img)
print("boot_new2.img size", len(img), "sha256", hashlib.sha256(img).hexdigest())

d = open(OUT, "rb").read()
assert d[:8] == b"ANDROID!"
ksz, rsz = struct.unpack_from("<II", d, 8)
hv, hs = struct.unpack_from("<I", d, 40)[0], struct.unpack_from("<I", d, 20)[0]
print("verify kernel_size=%d ramdisk=%d hv=%d hs=%d" % (ksz, rsz, hv, hs))
# kernel payload location sanity
print("bytes at 4096:", d[4096:4096+8].hex(), "ARM magic at", 4096 + 56, d[4096+56:4096+60])
