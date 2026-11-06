#!/bin/bash
set -u
OUT=/mnt/c/Users/Administrator/Documents/Trae-CN/temp_20261103_05/logs
mkdir -p "$OUT"
LOG="$OUT/build2.log"
cd "$HOME/aegis/src/kernel-common" || exit 1
date '+START %F %T' > "$LOG"
export PATH="$HOME/aegis/toolchain/clang-r450784e/bin:$PATH"
echo "nproc=$(nproc) jobs=8" >> "$LOG"
make ARCH=arm64 LLVM=1 clean >> "$LOG" 2>&1
date '+CLEAN_DONE %F %T' >> "$LOG"
make ARCH=arm64 LLVM=1 -j8 Image modules >> "$LOG" 2>&1
rc=$?
echo "EXIT=$rc" >> "$LOG"
date '+END %F %T' >> "$LOG"
exit $rc
