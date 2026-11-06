import struct, hashlib

def hdr(name, d, off):
    b = d[off:off+64]
    code0, code1 = struct.unpack_from("<II", b, 0)
    text_off, image_size, flags = struct.unpack_from("<QQQ", b, 8)
    magic = b[56:60]
    pe = struct.unpack_from("<I", b, 60)[0]
    print(f"{name}: code0={code0:08x} code1={code1:08x} text_offset={text_off:#x} image_size={image_size:#x} ({image_size}) flags={flags:#x} magic={magic} pe_off={pe}")

stock = open(r"D:\babylon_images_OS3.0.304.0.WMVCNXM_16.0\images\boot.img", "rb").read()
ks = struct.unpack_from("<I", stock, 8)[0]
hdr("STOCK ", stock, 1584)
print("stock kernel end bytes", stock[1584+ks-16:1584+ks].hex())

new = open(r"C:\Users\Administrator\Documents\Trae-CN\temp_20261103_05\images\boot_new.img", "rb").read()
ksn = struct.unpack_from("<I", new, 8)[0]
hdr("NEW   ", new, 1584)
print("new kernel head 64", new[1584:1584+64].hex())
print("stock kernel head 64", stock[1584:1584+64].hex())
print("new size", len(new), "kernel size", ksn)
