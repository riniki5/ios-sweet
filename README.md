# ios-sweet — iOS 16 on the Xiaomi Mi Note 10 Lite (`toco`)

**Experimental XNU/iOS bring-up for the Xiaomi Mi Note 10 Lite.**

This tree ports Apple's open-source XNU kernel (xnu-8796, the iOS 16 generation) to the Xiaomi Mi Note 10 Lite (`toco`, Qualcomm SM7150G / Snapdragon 730G, 6.47" 1080×2340). It runs the iPhone X's iOS 16.7.16 (20H392) userland with project-specific bring-up modifications: launchd, system daemons, backboardd, SpringBoard and the stock apps. It is not an unmodified or daily-driver iOS installation.

The project descends from [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) and [DC28088/ios-sweet](https://github.com/DC28088/ios-sweet), the Redmi Note 10 Pro (`sweet`) port. Patch 0082 adds the `toco` hardware: the 1080×2340 panel, the Focaltech FTM5 touch controller and its PM6150L LDO6 rail vote in the RPMh driver.

Active development is on [`codex/springboard-gpu-access`](https://github.com/riniki5/ios-sweet/tree/codex/springboard-gpu-access). The fork's default `main` branch retains the upstream `sweet` port; its hardware and feature claims are not `toco` results.

As of **2026-11-27**, known-good CPU-rendered configurations have reached the iOS lock/home screen with working touch and hardware buttons. WCN3990 scanning, WPA2 authentication and association work through the kernel `en0` bridge. The Layer-3 DHCP helper has passed arm64 iOS CI, but the new binary is not installed on the phone yet, so IPv4 routing, DNS and Safari web access remain unverified. GPU firmware staging, GMU/HFI startup, SMMU translation, ZAP authentication, SQE startup and a CP fence have completed on toco; a successful native-Metal UI draw and stable 60 FPS have not been confirmed, and GPU diagnostic boots may still stall at the Apple logo.

> Experimental bring-up, not a usable phone OS. Many things are missing or stubbed (see below), and Apple's security model is mostly switched off. It installs into `userdata` and **erases Android's user data**. Never flash `boot`, `dtbo` or `recovery`; test kernels only with `fastboot boot shim-boot.img`.

## Verified or implemented

| Area | State |
| --- | --- |
| Boot | Stock Xiaomi bootloader → temporary `fastboot boot` of our shim → XNU → lock/home screen in about 90 seconds in known-good CPU-rendered configurations. Current GPU diagnostics can stall before the UI |
| CPU | Eight-core arm64 configuration (`cpus=8`; patch 0078), 16K pages, GICv3 interrupts and timers; eight-core boot has been tested, but sustained stability is not established |
| Memory | About 3.95 GiB from the upper DDR bank, above Qualcomm's protected carve-outs |
| Storage | Own UFS host driver; the iOS root is a journaled HFS+ volume in `userdata`, read/write |
| iOS userland | iPhone X 16.7.16 root filesystem and shared cache with bring-up modifications; launchd and the system daemons run |
| Display | Kernel IOSurface + IOMobileFramebuffer (`AppleCLCD`) services; CoreAnimation renders in software and frames are copied into the bootloader's framebuffer. The physical panel is 1080×2340; the current default logical framebuffer is 828×1792 and is stretched to the panel |
| GUI | backboardd, SpringBoard, lock screen and home screen; the home gesture and app switcher work on the CPU path |
| GPU bring-up | Adreno 618 GMU firmware, HFI, SMMU, ZAP, SQE and CP fence verified on toco; native-Metal UI rendering still needs qualification |
| Touch | Focaltech FTM5 (f521) over I²C, AVDD voted to 3.0 V through RPMh, delivered as HID digitizer events |
| Buttons | Power and volume up/down (PMIC through SPMI) as HID consumer keys; lock/wake works |
| Wi-Fi link | WCN3990 firmware, scanning, WPA2 authentication, key installation and association work through the kernel `en0` bridge. Link stability and Layer 3 still need validation |
| Battery | Bring-up IOPMPowerSource service with a static 100% reading and charging icon; not real fuel-gauge telemetry |
| Device identity | Emulated iPhone X identity (`iPhone10,3` / `D22AP`) for userland compatibility and gesture UI; the physical device remains a Mi Note 10 Lite |
| Activation | Bring-up activation path in mobileactivationd, selected through device-tree security status; not a genuine Apple activation |

## What does not work (yet)

- **Wi-Fi associates but has no validated Layer 3 yet.** The installed `0001`–`0007` build scans and joins on `en0`, but does not configure an IPv4 service, default route or resolver, so Safari cannot load pages. Patch `0008` adds a supervised `en0` DHCP client and passed [arm64 iOS CI run 45959320701](https://github.com/riniki5/ios-sweet/actions/runs/45959320701); its artifact is verified but still needs a recovery-file-service reinstall and on-device DHCP/routing/DNS/Safari validation. Bluetooth, cellular, camera, GPS and SEP / Face ID are unavailable on toco; do not carry over the `sweet` branch's audio, haptics, sensor or SIM claims.
- **GPU UI rendering is not yet qualified.** The strict CI kernel and matching native Metal bundle are built and verified, but the first temporary boot produced no USB telemetry and the phone is no longer in fastboot. A newer stage-0 diagnostic adds `GETLOG` and disables the GPU audit for the safest log-recovery boot; boot it with `SWEET_LOG_PERSIST=0` to retrieve the preceding boot's log. Stage 1 can also disable the unconditional DDR vote and BO-pool reservation. NativeAdreno is published only after strict clock and render-profile checks; a successful on-screen Metal draw and responsive UI have not yet been confirmed. Raw MMIO and secure-monitor transactions remain outside same-CPU timeout protection, so keep the GPU opt-in and preserve the working touch path while validating the userspace bundle.
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

There is no serial port. The kernel draws its console into the framebuffer that ABL leaves at `0x9c000000`, and keeps a persistent 4 MiB log ring at the end of `userdata`. Read it from TWRP with `tools/sweet-log-pull.sh`, or from a file-server boot with `tools/sweet-log-usb.py`. Boot the reader with `SWEET_LOG_PERSIST=0` (`sweetlog=0`) so the current boot cannot overwrite the previous boot's log before you fetch it.

## How to do it yourself

You need a Mi Note 10 Lite with an **unlocked bootloader**, a Linux PC (or WSL2), `aarch64-linux-gnu-gcc`, `mkbootimg`, `img2simg`, `hfsprogs`, `apfs-fuse`, and a GitHub account for the kernel build. **Everything on `userdata` is lost.** Bootloaders, recovery, modem and persist partitions are never touched.

### 0. Back up the phone

Boot TWRP (temporary `fastboot boot twrp.img`) and pull at least `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `boot`, `dtbo` and `vbmeta`. They contain per-device calibration data. Keep them off git; `.gitignore` already excludes `backup/`, `dtb/`, `recovery/` and `logs/`.

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
and `sweetmtl=2` and enables `sweetfiles=1` for that boot. `SWEET_LOG_PERSIST=0`
disables only the on-disk logger for that boot; use it on a diagnostic/file-server
boot when you need `GETLOG` to return the preceding boot's log. Live console
output remains available.
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
`org.ios-sweet.wland` to run `wland auto` at boot. It also removes the stock
`wifid` device-tree launch restriction, which otherwise hides the direct `en0`
interface from Settings on toco. Boot-stamp write failures refuse startup.
Launchd retries only failures from before modem PAS; it never automatically
boots the modem twice in one boot.

With patch `0008`, `wland` supervises the `l3dhcp` helper after opening `/dev/wlan`.
The helper waits for asynchronous `en0` creation and interface-up state, uses a
temporary IPv4 link-local source for the first DHCP broadcast, then replaces it
with the leased address. It handles renewal, rebinding and expiry, rolls back
failed address/route changes, and cleans up on link loss or shutdown. DHCP DNS is
written atomically to `/etc/resolv.conf` only when no resolver file already
exists, and the lease is also published through `netsvc` for
SystemConfiguration. The installer sets `WLAND_EN0_DHCP=1`; set it to `0` to
disable this helper. Set `WLAND_FORCE_UTUN=1` to bypass the kernel bridge and use
the existing userland `ipnet`/utun DHCP path instead. These are `wland`
environment variables, not kernel boot arguments.

Validation must show `l3: waiting for en0 link`, a temporary link-local DHCP
source, DHCP DISCOVER/OFFER/REQUEST/ACK, an `en0` IPv4 address and netmask, a
default route through the offered router,
and successful `netsvc up` publication. Then compare ICMP to a public IP with
name resolution and test both HTTP and HTTPS in Safari; TLS clock and certificate
trust remain separate checks. The USB file service has no command-execution
primitive, so use the persisted `wland` log and Safari until a diagnostic shell
is available.

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
| `sweetlog=0` | Keep the current boot from overwriting the persistent log; use with `sweetfiles=1` and `GETLOG` to recover the preceding boot's log |
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

From a GPU-disabled file-server boot, fetch the preceding boot's log without recovery:

```sh
SWEET_GPU_STAGE=0 SWEET_DDR_VOTE=0 SWEET_BO_POOL_MIB=0 \
  SWEET_FILE_SERVER=1 SWEET_LOG_PERSIST=0 \
  tools/toco-shim.sh xnu/out/kernel.development.sweet
fastboot boot shim/out/shim-boot.img      # temporary; nothing is flashed
python3 tools/sweet-log-usb.py logs/toco.txt
```

The fetch saves `logs/toco.txt.bin` before decoding it. If the phone cannot
reach the file service, use recovery instead:

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
| `tools/sweet-log-usb.py` | Fetch and decode the persistent kernel log through `GETLOG` |
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
