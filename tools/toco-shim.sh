#!/bin/sh
# Package a built XNU kernel into a bootable Mi Note 10 Lite (toco) shim.
# usage: tools/toco-shim.sh xnu/out/kernel.development.sweet
# Needs the stock DTB at dtb/boot_unpacked/dtb (tools/unpack_bootv2.py) and
# aarch64-linux-gnu-gcc, mkbootimg on PATH.
set -eu
cd "$(dirname "$0")/.."
K=${1:?usage: tools/toco-shim.sh KERNEL}
[ -f "$K" ] || { echo "error: no kernel at $K" >&2; exit 1; }
[ -f dtb/boot_unpacked/dtb ] || { echo "error: unpack your stock boot.img first: tools/unpack_bootv2.py backup/boot.img dtb/boot_unpacked" >&2; exit 1; }
mkdir -p shim/out
SWEET_DEVICE=toco python3 tools/mkadt.py shim/out/sweet.adt --highmem
python3 tools/mkpayload.py "$K" shim/out/sweet.adt shim/out/payload.bin \
    --cmdline 'debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=60'
SWEET_DEVICE=toco shim/build.sh ../shim/out/payload.bin
echo "shim/out/shim-boot.img ready: fastboot boot shim/out/shim-boot.img"
