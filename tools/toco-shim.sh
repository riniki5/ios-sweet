#!/bin/sh
# Package a built XNU kernel into a bootable Mi Note 10 Lite (toco) shim.
# usage: tools/toco-shim.sh xnu/out/kernel.development.sweet
# Needs the stock DTB at dtb/boot_unpacked/dtb (tools/unpack_bootv2.py) and
# aarch64-linux-gnu-gcc, mkbootimg on PATH.
# Locally obtained, checksum-verified GPU firmware belongs in research/gpu/fw/;
# the ignored firmware blobs are packaged into the boot ADT and never committed.
set -eu
cd "$(dirname "$0")/.."
K=${1:?usage: tools/toco-shim.sh KERNEL}
[ -f "$K" ] || { echo "error: no kernel at $K" >&2; exit 1; }
[ -f dtb/boot_unpacked/dtb ] || { echo "error: unpack your stock boot.img first: tools/unpack_bootv2.py backup/boot.img dtb/boot_unpacked" >&2; exit 1; }
FW_DIR=${SWEET_GPU_FW_DIR:-research/gpu/fw}
for f in a618_gmu.bin a630_sqe.fw a615_zap.mdt a615_zap.b02; do
	[ -f "$FW_DIR/$f" ] || { echo "error: missing local GPU firmware $FW_DIR/$f" >&2; exit 1; }
done
GPU_STAGE=${SWEET_GPU_STAGE:-9}
case "$GPU_STAGE" in 1|2|3|4|5|6|7|8|9) ;; *) echo "error: SWEET_GPU_STAGE must be 1 through 9" >&2; exit 1 ;; esac
GPU_KHZ=${SWEET_GPU_KHZ:-267000}
case "$GPU_KHZ" in 180000|267000|355000|430000|565000|650000|800000) ;; *) echo "error: SWEET_GPU_KHZ must be a supported A618 OPP" >&2; exit 1 ;; esac
NATIVE_METAL=${SWEET_NATIVE_METAL:-0}
case "$NATIVE_METAL" in 0) RENDER_ARGS="sweetnative=0" ;; 1) RENDER_ARGS="sweetnative=1 sweetmtl=2 sweetgles=0" ;; *) echo "error: SWEET_NATIVE_METAL must be 0 or 1" >&2; exit 1 ;; esac
FILE_SERVER=${SWEET_FILE_SERVER:-0}
case "$FILE_SERVER" in 0|1) ;; *) echo "error: SWEET_FILE_SERVER must be 0 or 1" >&2; exit 1 ;; esac
WIFI=${SWEET_WIFI:-0}
case "$WIFI" in 0) WIFI_ARGS="sweetwifid=0" ;; 1) WIFI_ARGS="sweetwifid=1 sweetpmem=1 sweetsmmuprobe=1 sweetsmmuwlan=1 sweetcell=0" ;; *) echo "error: SWEET_WIFI must be 0 or 1" >&2; exit 1 ;; esac
FB_W=${SWEET_FB_W:-828}
FB_H=${SWEET_FB_H:-1792}
FB_SCALE=${SWEET_FB_SCALE:-2}
case "$FB_W:$FB_H:$FB_SCALE" in *[!0-9:]*|:*|*::*|*:) echo "error: framebuffer dimensions and scale must be integers" >&2; exit 1 ;; esac
if [ "${#FB_W}" -gt 4 ] || [ "${#FB_H}" -gt 4 ] || [ "${#FB_SCALE}" -gt 4 ] || \
   [ "$FB_W" -le 0 ] || [ "$FB_W" -ge 1080 ] || [ "$FB_H" -le 0 ] || [ "$FB_H" -ge 2340 ] || [ "$FB_SCALE" -le 0 ]; then
    echo "error: require 0 < SWEET_FB_W < 1080, 0 < SWEET_FB_H < 2340 and SWEET_FB_SCALE > 0" >&2
    exit 1
fi
mkdir -p shim/out
TMP=$(mktemp -d "${TMPDIR:-/tmp}/sweet-toco-adt.XXXXXX")
trap 'rm -f "$TMP/base.adt" "$TMP/gpu.adt"; rmdir "$TMP"' EXIT HUP INT TERM
SWEET_DEVICE=toco SWEET_FB_W="$FB_W" SWEET_FB_H="$FB_H" SWEET_FB_SCALE="$FB_SCALE" \
    python3 tools/mkadt.py "$TMP/base.adt" --highmem
python3 tools/sweet-adreno-firmware.py "$TMP/base.adt" "$FW_DIR/a618_gmu.bin" "$TMP/gpu.adt" \
    --sha256 9ef10b2b179054fb57af25008e29feb24300c2eaaeabf907bd741786bbacbf2e \
    --sqe-firmware "$FW_DIR/a630_sqe.fw" \
    --sqe-sha256 36298bd53ea3666413d288a3a3f5266f67fcb6db038a0a481af5869d1c17859c \
    --zap-metadata "$FW_DIR/a615_zap.mdt" \
    --zap-metadata-sha256 73e46f7698c9ca4bfc0dbbdbde39aa5b4b9367ac7c932ffd39b9ca9bcd11c503 \
    --zap-code "$FW_DIR/a615_zap.b02" \
    --zap-code-sha256 61be42f041eb6051eb9f56beb1f98ed97ab21faf2ef2df6b9151ba1a46aae878
python3 tools/mkpayload.py "$K" "$TMP/gpu.adt" shim/out/payload.bin \
    --cmdline "debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=60 sweetfb_w=$FB_W sweetfb_h=$FB_H sweetusb=2 sweetgpu=$GPU_STAGE sweetgpukhz=$GPU_KHZ $RENDER_ARGS sweetfiles=$FILE_SERVER $WIFI_ARGS"
SWEET_DEVICE=toco shim/build.sh ../shim/out/payload.bin
echo "shim/out/shim-boot.img ready (toco ADT + Adreno firmware, ${FB_W}x${FB_H}@${FB_SCALE}, sweetgpu=$GPU_STAGE, sweetgpukhz=$GPU_KHZ, sweetnative=$NATIVE_METAL, sweetfiles=$FILE_SERVER, sweetwifi=$WIFI): fastboot boot shim/out/shim-boot.img"
