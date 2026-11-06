### AnyKernel3 Ramdisk Mod Script
## osm0sis @ xda-developers

### AnyKernel setup
# global properties
properties() { '
kernel.string=Aegis Kernel 5.15.220-ASB-2026-11-02 (THIN LTO + CFI) for babylon
do.devicecheck=1
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=babylon
device.name2=
device.name3=
device.name4=
device.name5=
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; } # end properties

# boot shell variables
BLOCK=/dev/block/bootdevice/by-name/boot;
IS_SLOT_DEVICE=1;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;
NO_MAGISK_CHECK=1; # boot.img has no ramdisk on this GKI device; Magisk cannot live in boot

# import functions/variables and setup patching - see for reference (DO NOT REMOVE)
. tools/ak3-core.sh;

# boot install
# babylon is GKI hdr v4 with ramdisk_size=0 in boot (ramdisk lives in init_boot/vendor_boot).
# split_boot only splits the image, flash_boot only repacks the kernel, so ramdisk,
# vendor_boot and init_boot are never touched.
split_boot;
flash_boot;
## end boot install
