# Xiaomi Mi Note 10 Lite (`toco`) — port notes

Build and flashing instructions live in the [README](../README.md). This page covers what is specific to the `toco` port: the hardware differences from `sweet`, the touch controller and its power rails, and the troubleshooting that came out of bring-up.

The port is **patch 0082** in the XNU series plus the `SWEET_DEVICE=toco` switch in `tools/mkadt.py` and `shim/build.sh`. Nothing else in the tree is device-conditional at runtime: the kernel detects the board from the panel height the device tree reports (2340 on `toco`, 2400 on `sweet`) and picks the matching touch rail and VDDIO pin.

## Hardware differences from `sweet`

| | `sweet` (Redmi Note 10 Pro) | `toco` (Mi Note 10 Lite) |
| --- | --- | --- |
| SoC | SM7150 / SD732G | SM7150G / SD730G |
| Panel | 1080×2400 | **1080×2340** |
| Touch IC | Goodix GT9896 at I²C `0x5d` | **Focaltech FTM5 (f521) at I²C `0x49`** |
| Touch protocol | Goodix register reads, one event per poll | FTI/FTM5: `0x86` event FIFO, `0xa6` framebuffer, `0xfa` hardware registers |
| Touch AVDD | PM6150L LDO11 (L11C), 3.2 V | **PM6150L LDO6 (L6), 3.0 V** |
| Touch VDDIO | GPIO 90 | **GPIO 72** |
| Touch reset / IRQ | GPIO 8 / GPIO 9 | GPIO 8 / GPIO 9 (same) |
| I²C | QUP SE7 at `0xa84000` | QUP SE7 at `0xa84000` (same) |

The panel height the ADT advertises (through `SWEET_DEVICE=toco`) is the same number the touch driver reads back, so the two must be built for the same device. A `sweet` ADT on a `toco` shifts the digitizer area and leaves the wrong rail voted.

## Touch protocol in one page

`toco`'s Focaltech speaks the vendor's FTI/FTM5 command set over the same SE7 FIFO I²C block the Goodix part uses. Every opcode is a one-byte write, then a read of the reply length:

| Opcode | Use |
| --- | --- |
| `0xfa` | hardware register read/write (`0x01` config, `0x04` digital id, `0x08` firmware) |
| `0xa6` | framebuffer read: 16-bit address, then exactly N bytes |
| `0x86` | read the event FIFO |
| `0xa0` | scan control: mode + scan bitmask (`0x01` is low power and takes no bitmask) |
| `0xa2` | feature/gesture programming |
| `0xa4` | system command (`0xa4 0x00 0x02` = panel init) or load-data request (`0xa4 0x06 dt`) |
| `0xa1` | flush the event FIFO |
| `0x85`, `0x92`, `0x93`, `0xb6` | the older `st,fts` register protocol: one event, sense off, sense on, register read |

Events are `0x03` controller ready, `0x13` finger enter, `0x23` motion, `0x33` leave, `0x43` status (subcode `0x01` is the "mutual negative detect" force-cal reason) and `0xf3` error. The driver enables the interrupt through IER `0x20000029 = 0x41`; bit 0 is not latched, so a readback of `0x40` is correct. Stock order on screen-on is: gesture feature, active scan, scan off, 50 ms, scan on — no panel init and no raw capture at boot. The driver follows that order.

## Touch power is the part that matters

The Focaltech digital core runs from VDDIO (GPIO 72), but its analog front end is fed by **AVDD = PM6150L LDO6 at 3.0 V**. With 1.648 V (the value the vendor DTS initialises L6 to) the IC answers I²C and echoes commands, but every node reads back the same saturated negative value and the IC reports `43 05 01` mutual negative detect. Touch is dead even though the bus is healthy.

The kernel therefore votes 3.0 V through RPMh (`bsd/dev/sweet_rpmh.c`, patch 0062/0082). Two details cost us a full debugging cycle:

- The RPMh VRM voltage data word is **millivolts**, not microvolts. Mainline Linux writes `DIV_ROUND_UP(uV, 1000)`; a vote of `3000000` is accepted by the RPM (command status `0x10101`) and silently leaves the rail low.
- The mode is HPM (`7`) and the enable bit goes in the same three-command TCS batch as the voltage.

The successful vote logs as:

```
SWEET RPMH: TCS0 ACTIVE 3000 mV mode=7 enable=1
```

If the log shows `L6 RPMh vote failed`, firmware left the rail in the state Android had it; touch may still work but the AFE supply is then whatever ABL programmed, not a guarantee.

## Autodetection

`touch_panel_geometry()` reads the `sweet-fbcon` node's `width`/`height` from the live device tree. `touch_panel_h == 2340` selects the Focaltech path, VDDIO GPIO 72 and LDO6; otherwise the Goodix path with GPIO 90 and LDO11 is used. There is no build-time device switch in the kernel.

## Troubleshooting

- **No touch.** Look at `SWEET TOUCH: panel 1080x2340` first: a wrong geometry means the ADT came from `sweet`. Then check the RPMh vote, then the poll counters. `err=0` with rising `enter`/`motion`/`leave` counts means the IC is fine and the problem is above the driver.
- **Touch coordinates offset or compressed.** The ADT and the shim must both be built with `SWEET_DEVICE=toco`.
- **Single frozen frame after display off/on.** Known open issue on both devices: display power is a software fade, the panel is never powered down, so the missing repaint is above the frame copy. Check the `SWEET FB` swap/present/skip counters.
- **Stuck on the Apple logo past ~10 minutes.** Pull the log. `SWEET FB` vsync ticks with no swap means the GUI is alive and only presenting is slow; launchd/dyld errors mean the root image is incomplete.
- **Fastboot hangs after flashing `userdata`.** Expected on Xiaomi; re-enter fastboot manually with Power + Volume down.
- **Back to Android.** `fastboot flash userdata` a stock fastboot image (or your own backup). The boot partitions were never modified.

## Attribution

- The Focaltech FTM5 command set was taken from Xiaomi's published `sdmmagpie` kernel sources (`st,fts`: `fts_lib`, `f521_ftsCore.c`, `f521_ftsHardware.h`) and cross-checked against the stock firmware's touch driver through live I²C reads on the device.
- The RPMh regulator encoding follows the mainline `qcom-rpmh-regulator` driver.
- The port builds on [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) and keeps its patch series unchanged apart from patch 0082.
