# ios-sweet — iOS 16 on the Xiaomi Mi Note 10 Lite (`toco`)

**Apple's iOS 16 running on a Xiaomi Mi Note 10 Lite.**

This tree ports Apple's open-source XNU kernel (xnu-8796, the iOS 16 generation) to the Xiaomi Mi Note 10 Lite (`toco`, Qualcomm SM7150G / Snapdragon 730G, 6.47" 1080×2340). On top of it runs the **unmodified iOS 16.7.16 (20H392) userland of the iPhone X**: launchd, the system daemons, backboardd, SpringBoard and the stock apps.

It is a fork of [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet), the Redmi Note 10 Pro (`sweet`) port, and keeps its patch series. Patch 0082 adds the `toco` hardware: the 1080×2340 panel, the Focaltech FTM5 touch controller and its PM6150L LDO6 rail vote in the RPMh driver. The same kernel, shim and iOS root boot both phones.

As of **2026-11-26** the phone boots to iOS, and the touchscreen and hardware buttons work. GPU firmware staging, GMU/HFI startup, SMMU translation, ZAP authentication, SQE startup, and a CP fence have completed on the toco device. The strict patch series now defaults to the proven 267 MHz corner and publishes NativeAdreno only after clock and render-profile qualification; full kernel CI and on-device rendering are still pending, so the display may remain on the Apple loading logo while iOS starts.

> Experimental bring-up, not a usable phone OS. Many things are missing or stubbed (see below), and Apple's security model is mostly switched off. It installs into the `userdata` partition and so **erases Android's user data**.

## What works

| Area | State |
| --- | --- |
| Boot | Stock Xiaomi bootloader → `fastboot boot` of our shim → XNU → lock/home screen in about 90 seconds. Nothing is flashed to the boot partitions |
| CPU | All eight cores via PSCI (`cpus=8`; patch 0078), 16K pages, GICv3 interrupts, timers |
| Memory | About 3.95 GiB of the upper DDR bank |
| Storage | Own UFS host driver; the iOS root is a journaled HFS+ volume in `userdata`, read/write |
| iOS userland | Real iPhone X 16.7.16 root filesystem and shared cache; launchd and the system daemons run |
| Display | Kernel IOSurface + IOMobileFramebuffer (`AppleCLCD`) services; CoreAnimation renders in software; frames are copied into the bootloader's framebuffer. Presented to iOS as an iPhone X panel (1125×2436). Optional render scale (`sweetfb_w`/`sweetfb_h`) rasterises fewer pixels and stretches them to the panel |
| GUI | backboardd, SpringBoard, lock screen, home screen; the home gesture and app switcher work |
| GPU bring-up | Adreno 618 GMU firmware, HFI, SMMU, ZAP, SQE and CP fence verified on toco; UI rendering still needs qualification |
| Touch | Focaltech FTM5 (f521) over I²C, AVDD voted to 3.0 V through RPMh, delivered as HID digitizer events |
| Buttons | Power, volume up/down (PMIC through SPMI) as HID consumer keys; lock/wake works |
| Battery | IOPMPowerSource service (static 100 %, charging icon) |
| Device identity | iPhone X (`iPhone10,3` / `D22AP`): no Home button, gesture UI |
| Activation | Native "Hactivation" path of mobileactivationd, chosen through device-tree security status. No Apple servers involved |

## What does not work (yet)

- **Wi-Fi is integrated but not yet hardware-qualified.** The WCN3990 kernel transport, pinned iOS 16 `wland`/`netsvc` artifact, and verified installer are ready; on-phone installation and a scan/join test remain. Bluetooth, cellular, audio, camera, sensors, GPS and SEP / Face ID are still unavailable.
- **GPU UI rendering is not yet qualified.** The strict CI kernel was accepted for a temporary boot, and NativeAdreno is published only after strict clock and render-profile checks; a successful on-screen Metal draw and responsive UI have not yet been confirmed. Keep the GPU opt-in and preserve the working touch path while validating the matching userspace bundle.
- **Few apps.** The image has only what is on the system volume. There is no App Store, no Apple ID, and some Settings pages are empty. Several apps show a black window (Phone, Photos, Messages) because they need hardware we do not have.
- **Slow boot:** about 90 seconds on the Apple logo, against a few seconds on a real iPhone.
- **Security is off:** permissive code signing (AMFI) and sandbox policies, a stub AppleKeyStore, no data protection. Do not put anything personal on it.

## How it boots

```
ABL (stock Xiaomi bootloader, unlocked)
  -> fastboot boot shim-boot.img              (temporary; nothing is flashed to boot)
     -> shim: own MMU setup, reads the live FDT, loads the payload from the ramdisk
        -> XNU Mach-O + generated Apple Device Tree (ADT) + boot-args
           -> XNU -> UFS driver -> HFS+ root in the userdata partition
              -> dyld + shared cache -> launchd -> daemons -> backboardd + SpringBoard
```

There is no serial port. The kernel draws its console into the framebuffer that ABL leaves at `0x9c000000`, and keeps a persistent 4 MiB log ring at the end of `userdata`. You read that log from TWRP with `tools/sweet-log-pull.sh`, so you don't have to film the screen.

## How to do it yourself

You need a Mi Note 10 Lite with an **unlocked bootloader**, a Linux PC (or WSL2), `aarch64-linux-gnu-gcc`, `mkbootimg`, `img2simg`, `hfsprogs`, `apfs-fuse`, and a GitHub account for the kernel build. **Everything on `userdata` is lost.** Bootloaders, recovery, modem and persist partitions are never touched.

### 0. Back up the phone

Boot TWRP (temporary `fastboot boot twrp.img`) and pull at least `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `boot`, `dtbo` and `vbmeta`. They contain per-device calibration data. Keep them off git; `.gitignore` already excludes `backup/`, `dtb/` and `recovery/`.

The shim packs your stock DTB into the boot image. Unpack **your own** `boot.img`:

```sh
python3 tools/unpack_bootv2.py backup/boot.img dtb/boot_unpacked   # -> dtb/boot_unpacked/dtb
```

### 1. Build the kernel

The kernel builds on GitHub's macOS runners with [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build). The workflow fetches xnu-8796, applies `xnu/patches/` in order, and also stages the pinned open-source libpthread, HFS and BearSSL sources it needs. Every repository-owned patch is required: CI fails if one is skipped, while incompatible upstream-only patches may still be skipped. Fork the repo (public repos get free macOS minutes) and run:

```sh
gh workflow run xnu.yml -R YOU/ios-sweet
gh run download RUN_ID -R YOU/ios-sweet -n xnu-kernel -D xnu/out
```

To check a patch locally before spending a CI run, `tools/xnu-cc.py` replays the compile commands of a previous CI log for single files.

### 2. Build the iOS root image

Download the iPhone X (iPhone10,3) iOS 16.7.16 (20H392) IPSW from Apple. Then, on Linux, with `apfs-fuse`, `hfsprogs` and sudo:

```sh
# OS, SystemOS and AppOS disk images from the IPSW (see BuildManifest.plist for their names)
tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root.img 16G
sudo fsck.hfsplus -fy ios16-root.img
sudo mount -t hfsplus -o loop,force ios16-root.img /mnt/iosroot
sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot
sudo umount /mnt/iosroot
img2simg ios16-root.img ios16-root.simg
```

`mkiosroot.sh` copies the OS volume and both cryptexes into one case-sensitive journaled HFS+ volume. It adds the dyld cache links, the plain system keybag and the log directories the daemons expect. `sweet-root-tweaks.py` applies the bring-up changes: it skips Setup, seeds the activation state, removes the baseband daemon, disables the watchdogs that kill slow apps and the crash-looping media paths, and so on. The script's header explains each change.

The device tree builder copies `/product` from the real iPhone X device tree, which MobileGestalt needs. Extract it once, without downloading the whole IPSW:

```sh
python3 tools/remotezip.py IPSW_URL DeviceTree.d22ap.im4p research/ipsw-x/dt
ipsw img4 im4p extract research/ipsw-x/dt/Firmware/all_flash/DeviceTree.d22ap.im4p -o research/ipsw-x/d22ap.adt
```

### 3. Build the boot image

Needs `aarch64-linux-gnu-gcc` and `mkbootimg`. `SWEET_DEVICE=toco` tells `mkadt.py` and the shim to advertise the 1080×2340 panel; the kernel's touch driver detects the board from that height by itself. For GPU stage 9, put locally obtained, checksum-verified blobs in `research/gpu/fw/`: `a618_gmu.bin`, `a630_sqe.fw`, `a615_zap.mdt`, and `a615_zap.b02`. The build helper checks the pinned SHA-256 values and packages them into `/sweet-adreno` in the boot ADT. Firmware blobs stay local and are not committed.

```sh
tools/toco-shim.sh xnu/out/kernel.development.sweet     # -> shim/out/shim-boot.img; defaults to sweetgpu=9
```

The helper writes only under `shim/out` in the repository. The local firmware
blobs are checksum-checked by `tools/sweet-adreno-firmware.py`, embedded into
the boot ADT, then consumed by XNU when `sweetgpu=9` is enabled. Use
`SWEET_GPU_STAGE=1` through `9` to select a diagnostic stage. The shim defaults
to the proven `sweetgpukhz=267000` corner; set `SWEET_GPU_KHZ` to another
supported A618 OPP only for testing, and NativeAdreno publication still requires
a nonzero measured GX clock plus exact render-profile readback. To opt into the
new `SweetNativeMetal.bundle` and the USB-only live file service, build with
`SWEET_NATIVE_METAL=1 SWEET_FILE_SERVER=1`; this selects `sweetnative=1`
and `sweetmtl=2` and enables `sweetfiles=1` for that boot.
Download the `sweet-native-metal-ios16` workflow artifact, then install its
bundle while that USB file service is running and before GPU discovery
restarts `backboardd`:

```sh
python3 tools/sweet-install-native-metal.py install \
    userspace/out/SweetNativeMetal.bundle work/native-metal-backup
# Restore the saved bundle or remove files that the install added:
python3 tools/sweet-install-native-metal.py restore work/native-metal-backup
```

The installer durably saves existing files and verifies each readback hash.
Restore preflights every backup and refuses missing or tampered backups, or
files modified after installation, before changing the phone. Keep the backup
directory so the bundle can be restored from a later boot with
`SWEET_FILE_SERVER=1`.

Wi-Fi uses the pinned iOS 16 `wland`/`netsvc` build from the
`sweet-wifi-0239` workflow and kernel patches `0157`–`0159`. Install the
binaries, launchd job, and locally obtained modem/WLAN firmware before building
with `SWEET_WIFI=1`; `SWEET_FILE_SERVER=1` can be used only while installing
them. This enables root-only `/dev/pmem` and the kernel-programmed WLAN SMMU
stream. `wland` refuses to boot the modem unless the kernel publishes verified
SMMU readiness. Protected-network credential persistence is not implemented;
use open or otherwise non-sensitive test networks during bring-up.

Boot once with `SWEET_FILE_SERVER=1`, then install the workflow artifact and
locally obtained toco firmware without reflashing `userdata`:

```sh
python3 tools/sweet-install-wifi.py install \
    --binaries userspace/out/sweet-wifi-ios16 \
    --firmware research/wifi/fw \
    --rmtfs research/wifi/rmtfs \
    --backup work/wifi-backup
# From a later file-server boot, roll back with:
python3 tools/sweet-install-wifi.py restore --backup work/wifi-backup
```

The firmware directory must contain the toco `modem.*`, `modemr.jsn`,
`wlanmdsp.mbn`, `modemuw.jsn`, and matching `bdwlan.*` files. The RMTFS directory
must contain `modemst1.img`, `modemst2.img`, `fsg.img`, and `fsc.img`. The
installer verifies the pinned donor commit, patch hashes, binary hashes and
`SHA256SUMS` before contacting the phone. It backs up every replaced file and
the launchd plist, verifies each readback hash, and installs
`org.ios-sweet.wland` to run `wland auto` at boot. Boot-stamp write failures
refuse startup. Launchd retries only failures from before modem PAS; it never
automatically boots the modem twice in one boot.

The CPU renderer is the frame-time limit on this panel, so `tools/toco-shim.sh` reports a smaller logical display by default: 828×1792 (iPhone XR class, 414×896 points at 2×). It passes the same dimensions to the ADT and the `sweetfb_w`/`sweetfb_h` boot args, and AppleCLCD stretches the frames to 1080×2340. Override both dimensions together with `SWEET_FB_W`/`SWEET_FB_H`; `SWEET_FB_SCALE` controls the ADT scale. The ADT and the boot args must agree.

What the less obvious boot-args do:

| Boot-arg | Effect |
| --- | --- |
| `rd=ufsroot0 ufsrw=1 rootrw=1` | Root on the `userdata` partition, writable |
| `cpus=8` | Start all eight cores (two A76 + six A55). Fall back to `cpus=6` or `cpus=1` if a unit resets during boot |
| `launchd_unsecure_cache=1` | launchd accepts its job cache without AMFI |
| `wdt=-1 wdt_test=no_user_checkin` | No hardware watchdog |
| `sweetfb_noconsole=1` | Stop drawing kernel text over the GUI. It still goes to the persistent log; panics are drawn |
| `sweetfb_hz=60` | Panel copy every vsync tick; lower (`30`, default `10`) to trade smoothness for CPU time |
| `sweetfb_w=N sweetfb_h=N` | Render at a smaller logical size and stretch it to the panel (see above) |
| `sweetusb=2` | USB device mode: CDC-ECM gadget plus the live kernel console as UDP to the host |
| `sweetgpu=9` | Opt-in Adreno 618 firmware, GMU/HFI, SMMU, ZAP and CP bring-up. Requires the local firmware set above; a completed fence does not by itself qualify UI rendering |
| `sweetgpukhz=267000` | GPU OPP ceiling; the toco default is the proven 267 MHz corner. Higher values are opt-in and must pass clock/profile qualification |
| `sweetnative=1 sweetmtl=2 sweetgles=0` | Select the direct AIR/freedreno `SweetNativeMetal` frontend. Install the matching iOS 16 bundle before selecting it |
| `sweetfiles=1` | Opt-in root file access over the USB Ethernet gadget at `192.168.7.2:2223`; keep it disabled except while installing or restoring a bundle |
| `sweetpmem=1 sweetsmmuprobe=1 sweetsmmuwlan=1` | Enable the root-only physical-memory device, apps-SMMU probe, and kernel-programmed WCN3990 stream for `wland`; selected by `SWEET_WIFI=1` |
| `sweettouch=0`, `sweetkeys=0` | Disable the touch or button driver |
| `sweettouchdelay=N` | Start the touch thread N seconds after boot (default 45) |

### 4. Flash the root and boot

```sh
fastboot -S 512M flash userdata ios16-root.simg   # WIPES Android's user data; ~7 minutes; do not unplug
# Xiaomi's fastboot often hangs after a large flash: re-enter fastboot with Power + Volume down
fastboot boot shim/out/shim-boot.img
```

The first boot takes about 90 seconds on the Apple logo, then the lock screen appears. Swipe up to unlock. To get back to fastboot, hold Power + Volume down.

### 5. Read the kernel log

```sh
fastboot boot recovery/recovery.img      # TWRP, temporary
tools/sweet-log-pull.sh logs/toco.txt    # 4 MiB console ring from the end of userdata
adb reboot bootloader
```

Useful greps:

```sh
grep 'SWEET TOUCH' logs/toco.txt     # IC detect, IER, sense, poll counters, events
grep 'SWEET RPMH'  logs/toco.txt     # regulator votes: touch AVDD (3000 mV mode=7), ARC GPU rails
grep 'SWEET FB'    logs/toco.txt     # swaps/presents, vsync ticks, skipped layers
grep 'SWEET HID'   logs/toco.txt     # touch registered, panel presented as 1125x2436
grep 'SWEET GPU'   logs/toco.txt     # GPUCC clocks, CX/GX GDSC, PLL0 lock, RBBM revision
```

A healthy touch log contains `SWEET TOUCH: panel 1080x2340 ... vddio=0x...`, `SWEET RPMH: TCS0 ACTIVE 3000 mV mode=7 enable=1`, and poll lines whose `enter`/`motion`/`leave` counters rise while you drag a finger. More detail, including the touch power story and troubleshooting, is in [`docs/TOCO.md`](docs/TOCO.md).

## Repository layout

| Path | What |
| --- | --- |
| `shim/` | Bare-metal boot shim (C + asm) packed as an Android boot.img v2 |
| `xnu/patches/` | The XNU patch series (applied in order by CI), plus staging scripts for libpthread, HFS and BearSSL |
| `.github/workflows/xnu.yml` | Kernel CI build |
| `tools/mkadt.py` | Generates the Apple Device Tree (`SWEET_DEVICE=toco` for the 1080×2340 panel) |
| `tools/mkpayload.py` | Packs kernel + ADT + boot-args into the shim payload |
| `tools/toco-shim.sh` | Builds a temporary-boot `shim-boot.img` with the toco ADT and local GPU firmware |
| `tools/sweet-adreno-firmware.py` | Verifies and embeds locally supplied A618 firmware in the boot ADT |
| `tools/sweet-files.py` | Transfers files through the opt-in USB-only live file service |
| `tools/sweet-install-native-metal.py` | Installs the native Metal bundle with readback verification and a restore path |
| `tools/sweet-install-wifi.py` | Installs `wland`, `netsvc`, toco firmware, RMTFS images and the launchd job with rollback |
| `userspace/wifi/wland-0239/`, `.github/workflows/wifi-0239.yml` | Validated iOS 16 WCN3990 userspace patch series and pinned build workflow |
| `tools/mkiosroot.sh` | Builds the HFS+ iOS root from the IPSW images |
| `tools/sweet-root-tweaks.py` | Bring-up changes to the root (Setup skip, activation, daemons) |
| `tools/sweet-log-pull.sh`, `sweet-log.py` | Read the persistent kernel log from recovery |
| `tools/sweet-crash.py` | Symbolicate console crash reports |
| `tools/xnu-cc.py` | Local single-file compile check from a CI log |
| `tools/qemu-sweet.py` | QEMU test boots with framebuffer text decoding |
| `tools/adt.py`, `remotezip.py`, `unpack_bootv2.py`, `sparsediff.py` | Helpers |
| `docs/TOCO.md` | Port notes: the `toco`/`sweet` hardware differences, touch rail, troubleshooting |
| `NOTES.md` | Detailed engineering log: every boot, crash and decision, plus hardware facts |

Not in git: partition backups, live device trees, recovery images, Apple firmware and root images, and downloaded or generated build trees. They contain device serials and calibration data, or Apple's copyrighted files.

## Kernel patches

| # | What |
| --- | --- |
| 0001–0009 | Toolchain compatibility, SWEET machine config, non-PAC arm64, stubs for Apple-internal pieces |
| 0010–0018 | Early framebuffer console, physmap fix, PRNG without corecrypto, device-tree platform expert, timer PPI, boot CPU driver |
| 0019–0020 | Apple open-source libpthread kernel provider; BearSSL AES |
| 0021–0027 | RAM-disk root, mockfs, SHA-256, minimal AMFI, Apple open-source HFS+, MD5 |
| 0028–0034 | UFS host driver and root device, read/write root, DMA above 4 GiB |
| 0035–0045 | Entitlements, bindfs, AppleKeyStore stub, IOWatchdog, console crash reports |
| 0046 | IOSurface (IOCoreSurfaceRoot) and IOMobileFramebuffer (AppleCLCD) services |
| 0047–0055 | Diagnostics: persistent log, /dev/null tee, IOKit trace, heap strings and user stack sampler on crash; permissive Sandbox policy; HFS rename-swap; AppleKeyStore selectors |
| 0056–0057 | Throttled panel copy; no external identity resolver |
| 0058 | HID event services. Apple's IOHIDFamily-1915.140.3 user client and event queue, matching the iOS 16.7 userland |
| 0059 | iPhone X identity (`hw.product` / `hw.target` from the device tree) |
| 0060 | Power and volume keys over SPMI; touch over GENI I²C |
| 0061 | Present the display as 1125×2436 |
| 0062 | RPMh regulator vote for the touch rail; battery power source |
| 0063 | GENI FIFO packing fix and the Goodix GT9896 protocol |
| 0064 | Grant PRIV_WORK_INTERVAL (UIKit's CoreAnimation work interval) |
| 0065 | SMP: secondary A55 cores via PSCI CPU_ON |
| 0066–0067 | Fault-region crash info; console mute |
| 0068 | IOSurface lookup semantics for already-mapped surfaces |
| 0069 | Batched persistent-log flushes |
| 0070–0081 | PID hibernate, touch edges, USB device mode and Ethernet, 8-core SMP, display power, network traces |
| 0082 | Xiaomi Mi Note 10 Lite (`toco`): Focaltech touch, PM6150L LDO6 vote in millivolts, 1080×2340 panel |
| 0083–0084 | Adreno 618 GPUCC: GCC/GPUCC branch clocks and the CX power domain, register dump (`gpu=1`) |
| 0085–0086 | RPMh ARC votes for `cx.lvl`/`mx.lvl`/`gfx.lvl`: cmd-db lookup plus a single level-index write on the ARC slave, so the GX domain powers up (`gpu_gx=1`) |
| 0087 | GPU PLL0 (Fabia) start and the GX_GFX3D root clock switched to `crc_div`, so the core is clocked before its registers are read |
| 0148–0155 | DC28088 NativeAdreno/Metal stack for A618, strict 267 MHz clock qualification, ring-adoption and render-readback checks, and submission-stall diagnostics |
| 0157–0159 | WCN3990 `/dev/pmem` + `/dev/wlan` transport, bounded RPMh Wi-Fi votes, and the kernel-programmed WLAN SMMU stream |

## Key hardware facts

- RAM: payloads use the upper bank, `0x100000000` + `0xfcc00000` (about 3.95 GiB), above Qualcomm's protected carve-outs.
- GICv3 with security extensions: the timer goes through Group 1 IRQ (virtual timer INTID 19), not FIQ as on Apple silicon.
- PSCI through `smc`, 19.2 MHz timer, ARMv8.2 without pointer authentication. MPIDR uses Aff1 for the core number.
- Panel: 1080×2340 continuous splash from ABL; the kernel presents it to iOS as 1125×2436.
- Touch: Focaltech FTM5 (f521) at I²C `0x49` on QUP SE7 (`0xa84000`), IRQ GPIO 9, reset GPIO 8, VDDIO GPIO 72, AVDD on PM6150L LDO6 at 3.0 V through RPMh.
- Buttons: power and volume keys on the PM6150 PON block through SPMI.
- GPU: Adreno 618 (`a615`, chipid `0x06010800`) at `0x05000000`, GPUCC at `0x05090000`, GMU at `0x0506a000`. CX is already up from the bootloader; GX needs a `gfx.lvl` vote through RPMh (ARC slave 3, vote by cmd-db index).
- Wi-Fi/Bluetooth: Qualcomm WCN3990 combo behind `icnss@18800000` (IPA at `0x01e00000`, BT on the QUP UART at `0x88c000`), not a discrete PCIe card.

More in [`docs/TOCO.md`](docs/TOCO.md) and [`NOTES.md`](NOTES.md).

## Credits

Built on Apple's open-source releases (xnu, IOHIDFamily, libpthread, hfs), [BearSSL](https://bearssl.org), [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build), [ipsw](https://github.com/blacktop/ipsw), Qualcomm/Xiaomi's published Linux kernel sources for the hardware details (including the Focaltech `st,fts` driver), and [TWRP](https://twrp.me). iOS itself is Apple's and is not distributed here.
