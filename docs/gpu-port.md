# GPU/Metal port from DC28088/ios-sweet

The Adreno 618 stack in this tree is ported from `DC28088/ios-sweet`, the
Redmi Note 10 Pro (sweet, SM7150-AC) port whose native Metal path renders at
~37-40 fps. toco (Mi Note 10 Lite, SM7150G) is the same SoC family and the same
A618 GPU, and both trees descend from the same 0001-0080 xnu patch prefix, so
the driver and userspace sources carry over.

## Series layout

| range | content |
| --- | --- |
| 0001-0080 | previous prefix. 0046/0056/0079 are now DC28088's versions because every later framebuffer patch is generated against them; the toco-only deltas live in 0166. 0031/0041 (sweet_hfs) are unchanged. |
| 0081-0165 | DC28088 Adreno/GMU/HFI/SMMU/CP bring-up, NativeAdreno kernel driver, Metal/GLES userspace integration, GPU clocks/OPP, DDR and BCM votes, present/page-flip path, scheduler tweaks. Renumbered continuously; the table below maps each back to its DC28088 number. |
| 0166 | toco adaptations: USB link-state, toco touch driver (from the old 0082), 1080x2340 panel geometry and touch edges. |

Superseded toco work (kept in git history, removed from the series): the
independent GPU bring-up 0083-0147 (power/clock/GMU/HFI/SMMU/CP ring and the
0147 shader dispatch) and the CPU-framebuffer present experiments 0127-0130.
DC28088's stack reaches the same hardware milestones and continues through a
userspace client, so keeping both would have meant reconciling two divergent
`sweet_gpu.c` bodies.

## Not ported (unrelated subsystems)

Baseband/IPA, audio/haptics/battery, WiFi/PMEM, Bluetooth, sensors, panel power
sequences (0200-0242) and the sweet-specific display-size experiments
(0163/0165 ARE ported; panel vci/k6/reset are not). Also skipped: 0138/0141/
0151-0153 (PMEM/WLAN votes) and 0168 (USB file server); the GPU patches that
needed their symbols were adapted instead (0147/0149/0169/0180 -> 0120-0122,
0125, 0160, 0161 in this tree).

## Userspace

`userspace/{metal,metal2,native-metal,gles}`, `third_party/unixnu` (PM4,
SMMU-4K and NativeAdreno references), the build scripts in `tools/` and the
`metal.yml`, `metal2.yml`, `native-metal.yml`, `gles.yml` workflows are copied
from DC28088. They build the Metal plugin / AIR translator bundles that pair
with patches 0099 (native Metal plugin), 0115-0121 (GLES) and 0173+; install
them into the iOS rootfs when the kernel driver is up.

## Number mapping (this tree -> DC28088)

| toco | DC28088 | name |
| --- | --- | --- |
| 81 | 0081 | sweet-adreno-readonly-gpucc.patch |
| 82 | 0082 | sweet-adreno-power-audit.patch |
| 83 | 0083 | sweet-adreno-arc-vote.patch |
| 84 | 0084 | sweet-adreno-arc-readback.patch |
| 85 | 0085 | sweet-fb-120hz-scheduler.patch |
| 86 | 0086 | sweet-adreno-gfx-raise.patch |
| 87 | 0087 | sweet-adreno-gpucc-power.patch |
| 88 | 0088 | sweet-adreno-core.patch |
| 89 | 0089 | sweet-adreno-gmu-clocks.patch |
| 90 | 0090 | sweet-adreno-required-clocks.patch |
| 91 | 0091 | sweet-adreno-gmu-smmu-clock-list.patch |
| 92 | 0092 | sweet-adreno-dma-smmu-hfi.patch |
| 93 | 0093 | sweet-highmem-cache-sync.patch |
| 94 | 0094 | sweet-adreno-gmu-hfi-startup.patch |
| 95 | 0095 | sweet-adreno-smmu-fault-status.patch |
| 96 | 0096 | sweet-adreno-sqe-cp-backend.patch |
| 97 | 0097 | sweet-adreno-hfi-deadline-diagnostics.patch |
| 98 | 0098 | sweet-adreno-cp-clock-fence-ordering.patch |
| 99 | 0099 | adreno-cp-fault-address.patch |
| 100 | 0100 | adreno-cp-rptr-shadow.patch |
| 101 | 0101 | adreno-cp-scm-aperture-and-state.patch |
| 102 | 0102 | adreno-cp-trusted-range-setup.patch |
| 103 | 0103 | adreno-sqe-stage-and-fetch-evidence.patch |
| 104 | 0104 | adreno-authenticate-zap-before-sqe.patch |
| 105 | 0105 | sweet-adreno-sqe-bootstrap-gate.patch |
| 106 | 0106 | sweet-adreno-cp-startup-snapshots.patch |
| 107 | 0107 | sweet-native-adreno-a618-ring.patch |
| 108 | 0108 | sweet-native-adreno-buffer-vm-submit.patch |
| 109 | 0109 | sweet-native-adreno-live-vm.patch |
| 110 | 0110 | sweet-native-adreno-render-client.patch |
| 111 | 0111 | sweet-qcom-smmu-fault-route.patch |
| 112 | 0112 | sweet-gmem-readback-usb-reset.patch |
| 113 | 0113 | sweet-a618-macrotile-register.patch |
| 114 | 0114 | sweet-rpmh-fresh-completion.patch |
| 115 | 0115 | sweet-gles-userspace-integration.patch |
| 116 | 0116 | sweet-a618-uche-perfsel.patch |
| 117 | 0117 | sweet-gles-residency-cache-and-surface-padding.patch |
| 118 | 0118 | sweet-compositor-buffer-budget.patch |
| 119 | 0119 | sweet-immutable-gles-residency.patch |
| 120 | 0120 | sweet-low-svs-clock-profile.patch |
| 121 | 0121 | sweet-extension-cache-trust-service.patch |
| 122 | 0122 | sweet-metal2-plugin-selection.patch |
| 123 | 0123 | sweet-metal2-restart-backboardd.patch |
| 124 | 0124 | sweet-metal-owned-surface-rows.patch |
| 125 | 0125 | sweet-metal-cpu-presentation-fence.patch |
| 126 | 0126 | sweet-cpufreq-hw.patch |
| 127 | 0127 | sweet-a618-measured-opp.patch |
| 128 | 0128 | sweet-pipelined-submit-present-thread.patch |
| 129 | 0129 | sweet-metal-extra-client-windows.patch |
| 130 | 0130 | sweet-dsi-dcs-backlight.patch |
| 131 | 0131 | sweet-extra-window-and-backlight-keys.patch |
| 132 | 0132 | sweet-unlocked-present-gate-publish-stats.patch |
| 133 | 0133 | sweet-client-maintained-imports.patch |
| 134 | 0134 | sweet-gpu-lost-fault-report.patch |
| 135 | 0135 | sweet-write-combined-owned-bos.patch |
| 136 | 0136 | sweet-report-quiesce-and-close-loss.patch |
| 137 | 0137 | sweet-gpucc-clock-readback.patch |
| 138 | 0139 | sweet-present-breakdown-swap-fence.patch |
| 139 | 0140 | sweet-kernel-syncs-small-imports.patch |
| 140 | 0142 | sweet-dense-sampler.patch |
| 141 | 0143 | sweet-a618-650-800mhz.patch |
| 142 | 0144 | sweet-unlocked-fence-wait-gpu-busy.patch |
| 143 | 0145 | sweet-beam-raced-copy.patch |
| 144 | 0146 | sweet-owned-bo-pool.patch |
| 145 | 0167 | sweet-prefer-a76-for-ui-threads.patch |
| 146 | 0170 | sweet-gpu-smmu-cacheable-walk.patch |
| 147 | 0171 | sweet-gpu-rbbm-status-profile.patch |
| 148 | 0172 | sweet-gpu-force-writeback-mappings.patch |
| 149 | 0173 | sweet-native-metal-plugin.patch |
| 150 | 0174 | sweet-scoped-submit-client-imports.patch |
| 151 | 0175 | sweet-beam-race-tear-fix.patch |
| 152 | 0176 | sweet-bind-render-threads-to-a76.patch |
| 153 | 0177 | sweet-keep-kernel-pollers-off-a76.patch |
| 154 | 0178 | sweet-pull-ui-threads-to-idle-a76.patch |
| 155 | 0179 | sweet-per-tap-latency-probe.patch |
| 156 | 0147 | sweet-early-bo-pool |
| 157 | 0148 | sweet-multi-block-bo-pool |
| 158 | 0149 | sweet-bcm-vote-apps-smmu-probe |
| 159 | 0150 | sweet-bcm-votes-at-init |
| 160 | 0169 | sweet-ddr-bandwidth-vote |
| 161 | 0180 | sweet-dump-display-pipeline |
| 162 | 0163 | sweet-display-iphone-mini-full-width |
| 163 | 0165 | sweet-display-iphone-x-scaled |
| 164 | 0181 | sweet-page-flip-present |
| 165 | 0244 | sweet-fb-flip-live-modes |
| 166 | (toco adaptation) | usb link-state, toco touch driver, 1080x2340 panel/touch edges |

DC28088 patches that had to be re-generated rather than copied (0147, 0149,
0169, 0180) were hand-merged into this tree because they touch files the toco
side has diverged on (`sweet_ufs.c`, BCM/DDR votes, `sweet_rpmh.c`); their
commit diffs are what `xnu/patches` contains. 0148 applied as-is. 0244, 0245
and 0246 landed as one commit (the later two were no-ops on top of 0244), so
they are a single patch, 0165.