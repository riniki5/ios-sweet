# Xiaomi Mi Note 10 Lite (`toco`)

This fork of ios-sweet also carries a port to the **Xiaomi Mi Note 10 Lite** (`toco`, Qualcomm SM7150G / Snapdragon 730G, 6.47" 1080×2340). It shares the SoC family with `sweet` (Redmi Note 10 Pro), so the XNU patch series, the boot shim, the UFS root and the iOS 16.7.16 iPhone X userland are the same. What differs is the panel geometry, the touch controller, and the rails that feed it.

Everything else in the [README](../README.md) applies: this is an experimental bring-up, it installs into the `userdata` partition, and **Android's user data is erased** by the one flashing step.

## Status

Facts below were verified on a Mi Note 10 Lite running the stock MIUI firmware and TWRP:

| Area | State |
| --- | --- |
| Boot | Unlocked bootloader → `fastboot boot` of the shim → XNU. `boot`, `dtbo` and `recovery` stay untouched |
| CPU | All eight cores via PSCI (`cpus=8`; patch 0078 raises the SMP cap past the six A55s) |
| Memory | ~3.95 GiB, upper DDR bank, 16K pages |
| Storage | UFS host driver, journaled HFS+ root in `userdata`, read/write |
| iOS userland | iPhone X iOS 16.7.16 root filesystem and shared cache; launchd, backboardd and SpringBoard run |
| Display | 1080×2340 panel presented as the iPhone X's 1125×2436; CoreAnimation renders in software and the kernel copies frames (`SWEET FB`), no GPU driver |
| Touch | Focaltech FTM5 (f521) over I²C, single-touch and multi-touch, HID digitizer events |
| Buttons | Power and volume up/down (PMIC / SPMI) |
| Battery | Static 100 % IOPMPowerSource |
| Device identity | iPhone X (`iPhone10,3` / `D22AP`) |

Not working (same gaps as `sweet`): Wi-Fi, Bluetooth, cellular, audio, camera, sensors, GPS, SEP / Face ID, GPU acceleration, home gesture. Boot takes about 4–5 minutes.

## Hardware differences from `sweet`

| | `sweet` (Redmi Note 10 Pro) | `toco` (Mi Note 10 Lite) |
| --- | --- | --- |
| Panel | 1080×2400 | **1080×2340** |
| Touch IC | Goodix GT9896 at I²C `0x5d` | **Focaltech FTM5 (f521) at I²C `0x49`** |
| Touch protocol | Goodix register reads, 1 event per poll | FTI/FTM5: `0x86` event FIFO, `0xa6` framebuffer, `0xfa` hw registers |
| Touch AVDD | PM6150L LDO11 (L11C), 3.2 V | **PM6150L LDO6 (L6), 3.0 V** |
| Touch VDDIO | GPIO 90 | **GPIO 72** |
| Touch reset / IRQ | GPIO 8 / GPIO 9 | GPIO 8 / GPIO 9 (same) |
| I²C | QUP SE7 at `0xa84000` | QUP SE7 at `0xa84000` (same) |

The driver decides which board it is on from the panel height the device tree reports (2340 vs 2400): it picks LDO6 + GPIO 72 for `toco`, LDO11 + GPIO 90 for `sweet`. No build-time device switch is needed in the kernel. The two places you do pick the device at build time are `tools/mkadt.py` and `shim/build.sh`, both through `SWEET_DEVICE=toco`.

### Touch power is the part that matters

The Focaltech digital core runs from VDDIO (GPIO 72), but its analog front end is fed by **AVDD = PM6150L LDO6 at 3.0 V**. With 1.648 V (the value the vendor DTS initialises L6 to) the IC answers I²C and reports events but every node reads back the same saturated negative value ("mutual negative detect"). The kernel therefore votes 3.0 V through RPMh (`bsd/dev/sweet_rpmh.c`, patch 0062/0082). Note that the RPMh VRM voltage data word is in **millivolts**, not microvolts — the kernel logs the successful vote as:

```
SWEET RPMH: TCS0 ACTIVE 3000 mV mode=7 enable=1
```

If the log shows `L6 RPMh vote failed`, firmware left the rail in the state Android had it; touch may still work but the AFE supply is not guaranteed.

## Building and flashing

The steps mirror the README's, with `SWEET_DEVICE=toco` where the tool needs the panel height. You need: a `toco` with an **unlocked bootloader**, a Linux host (or WSL2), `aarch64-linux-gnu-gcc`, `mkbootimg`, `img2simg`, `hfsprogs`, `apfs-fuse`, and a GitHub account for the kernel build.

### 0. Back up first

Boot TWRP (temporary `fastboot boot twrp.img`) and pull at least `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `boot`, `dtbo` and `vbmeta`. They hold per-device calibration data. Keep them out of git (`backup/`, `dtb/` and `recovery/` are already ignored).

### 1. Your own stock DTB

Unpack **your phone's** stock boot image; the shim packs its DTB into the Android boot header:

```sh
python3 tools/unpack_bootv2.py backup/boot.img dtb/boot_unpacked   # -> dtb/boot_unpacked/dtb
```

Do not reuse another device's or another firmware's DTB.

### 2. Kernel

CI applies `xnu/patches/` in order, and patch 0082 (the `toco` port) also touches `sweet_touch.c`, `sweet_rpmh.c` and `SweetHID.cpp`, so the same kernel boots both devices.

```sh
gh workflow run xnu.yml -R YOU/ios-sweet
gh run download RUN_ID -R YOU/ios-sweet -n xnu-kernel -D xnu/out
```

### 3. iOS root image

Same as the README: an iPhone X (iPhone10,3) iOS 16.7.16 (20H392) IPSW, then

```sh
tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root.img 16G
sudo fsck.hfsplus -fy ios16-root.img
sudo mount -t hfsplus -o loop,force ios16-root.img /mnt/iosroot
sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot
sudo umount /mnt/iosroot
img2simg ios16-root.img ios16-root.simg
```

The Mi Note 10 Lite ships with 64 or 128 GB of `userdata`, so the 16 GB image fits; adjust the size in `mkiosroot.sh` if you want more.

### 4. Boot image

```sh
SWEET_DEVICE=toco python3 tools/mkadt.py shim/out/sweet.adt --highmem
python3 tools/mkpayload.py xnu/out/kernel.development.sweet shim/out/sweet.adt shim/out/payload.bin \
    --cmdline 'debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1 wdt=-1 sweetfb_noconsole=1 sweetfb_hz=60'
SWEET_DEVICE=toco shim/build.sh ../shim/out/payload.bin      # -> shim/out/shim-boot.img
```

`SWEET_DEVICE` only changes the advertised panel height (the ADT and the framebuffer stride the shim sets up). The touch driver detects the board from that height by itself.

There is a one-liner for the whole step:

```sh
tools/toco-shim.sh xnu/out/kernel.development.sweet     # -> shim/out/shim-boot.img
```

### 5. Flash the root, boot the shim

```sh
fastboot -S 512M flash userdata ios16-root.simg   # WIPES Android's user data; ~7 minutes
fastboot boot shim/out/shim-boot.img
```

Xiaomi's fastboot sometimes hangs right after a large flash; hold Power + Volume down to get back to the bootloader. **Only `userdata` is ever flashed.** `fastboot boot` loads the shim into RAM for one boot: nothing is written to `boot`, `dtbo` or `recovery`, so Android still starts normally if no shim is booted.

### 6. Read the log

There is no wired serial console. The kernel keeps a 4 MiB ring at the end of `userdata`.

```sh
fastboot boot recovery/recovery.img      # TWRP, temporary
tools/sweet-log-pull.sh logs/toco.txt
adb reboot bootloader
```

Useful greps:

```sh
grep 'SWEET TOUCH' logs/toco.txt     # bring-up: ic detect, ier, sense, poll counters, events
grep 'SWEET RPMH'  logs/toco.txt     # the AVDD vote (3000 mV mode=7)
grep 'SWEET FB'    logs/toco.txt     # swaps/presents, vsync ticks, skipped layers
grep 'SWEET HID'   logs/toco.txt     # touch registered, panel presented as 1125x2436
```

A healthy touch log ends up like this, with counts that keep rising while you drag a finger:

```
SWEET TOUCH: panel 1080x2340 ... vddio=0x...; voting touch AVDD through RPMh
SWEET RPMH: TCS0 ACTIVE 3000 mV mode=7 enable=1
SWEET TOUCH: fti polls=12000 ... edges=270 enter=49 motion=442 leave=43 status=15 err=0
```

## Boot arguments that matter on `toco`

| Boot-arg | Effect |
| --- | --- |
| `cpus=8` | All eight cores. If a unit resets during bring-up of the A76 pair, fall back to `cpus=6` (the six A55s) or `cpus=1` |
| `sweetfb_hz=60` | Copy a new frame every vsync tick; lower (`30`, default `10`) to trade smoothness for CPU time |
| `sweetfb_noconsole=1` | Never draw kernel text over the GUI (panics are still drawn) |
| `sweettouch=0` | Disable the touch driver |
| `sweettouchdelay=N` | Start the touch thread N seconds after boot (default 45) |
| `wdt=-1` | No hardware watchdog |

## Troubleshooting

- **Stuck on the Apple logo past ~6 minutes.** Pull the log. If the last lines are `SWEET FB` vsync ticks, the GUI is alive and the copy is just slow; if they are `launchd`/dyld errors, the root image is incomplete. Reboot with Power + Volume down.
- **Fastboot hang after flashing `userdata`.** Expected on Xiaomi; re-enter fastboot manually with Power + Volume down.
- **No touch.** Check `SWEET TOUCH: panel 1080x2340` first (wrong geometry means the ADT came from `sweet`), then the RPMh vote, then the poll counters. `status=... err=0` with rising `enter`/`motion` counts means the IC is fine and the problem is above it.
- **Touch coordinates offset or compressed.** The ADT and the shim must both be built with `SWEET_DEVICE=toco`; mixing them shifts or crops the digitizer area.
- **Back to Android.** `fastboot flash userdata` a stock fastboot image (or your own `userdata` backup). The boot partitions were never modified, so nothing else needs restoring.

## Notes and attribution

- The Focaltech FTM5 command set was taken from Xiaomi's published `sdmmagpie` kernel sources (`st,fts`: `fts_lib`, `f521_ftsCore.c`, `f521_ftsHardware.h`) and cross-checked against the stock firmware's touch driver through live I²C reads on the device.
- The RPMh regulator encoding follows the mainline `qcom-rpmh-regulator` driver: the VRM voltage data word is millivolts, mode `7` is HPM.
- The port builds on `dipa-studio/ios-sweet` (the `sweet` port) and keeps its patch series unchanged apart from patch 0082.
