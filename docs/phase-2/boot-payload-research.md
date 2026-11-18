# Phase 2 pre-write research: the GT-I9195 proof-of-execution payload

**Researched:** 2026-11-10, from public source code and public reports only. **No device was touched, no image was built, and nothing here has been confirmed on the owner's phone.**

**Measured on the phone, 2026-11-18.** The Phase 2 session of that day started `payload.img` from `RECOVERY` in 5 of 5 trials ([session record](../evidence/phase-2/2026-11-18-v5-session.md)). The values it measured are added beside the expected ones below, which are kept, with their label and the date.

**This document proposes and approves no flash command.** It is input to a later write-plan issue ([AGENTS.md](../../AGENTS.md#hardware-safety-contract), rule 1). Every device write still needs that approved plan.

It builds on [gt-i9195.md](../hardware/gt-i9195.md) and does not repeat it. Where that file already states a fact, this one cites it. The questions come from [ROADMAP Phase 2](../../ROADMAP.md#phase-2--first-bare-metal-boot) and the boot handoff contract in [ARCHITECTURE.md](../../ARCHITECTURE.md#contracts-to-define).

## Labels and sources

| Label | Meaning |
| --- | --- |
| **Source** | Stated in a cited file and line, or a cited URL. The citation says what kind of source it is; a community report weighs less than project source code. |
| **Inference** | Our conclusion from the cited sources. No source states it. |
| **Unknown** | No reliable information found. The entry says what would resolve it. |
| **Measured** | Read on the owner's phone from a log, a command's output or a photograph, with the date and a link to the record. |
| **Owner-confirmed** | Stated by the owner during a recorded session, with the date and a link to the record. |

Samsung does not publish its `aboot` source. Every statement about what the stock bootloader does internally is therefore an Inference or an Unknown, never a Source.

Source trees were read at these commits. A citation such as `[LK] arch/arm/crt0.S:41-51` means that file and those lines at the pinned commit.

| Tag | Tree | Commit |
| --- | --- | --- |
| **[LK]** | lk2nd, a fork of Qualcomm's reference LK bootloader: <https://github.com/msm8916-mainline/lk2nd> | [`cf45aefd22d7`](https://github.com/msm8916-mainline/lk2nd/tree/cf45aefd22d744b2bf9b39455afae697ce430063) (`main`, 2026-11-07) |
| **[SK]** | Stock-derived Samsung kernel, LineageOS: <https://github.com/LineageOS/android_kernel_samsung_msm8930-common> | [`94cbcc369124`](https://github.com/LineageOS/android_kernel_samsung_msm8930-common/tree/94cbcc3691247ded64f6c772ca37b5916f9f4b4a) (`lineage-18.1`) |
| **[FK]** | Community mainline fork: <https://github.com/msm8227-mainline/linux> | [`b51f999a8ab2`](https://github.com/msm8227-mainline/linux/tree/b51f999a8ab27982c2b5ea07f963cd226058ac04) (`msm8227-6.19`) |
| **[LKML]** | Pavel Machek, "mainline on Samsung S4 mini (seranoltexx), earlyfb patch?", 2026-01-02 and 2026-01-03: [first message](https://lkml.iu.edu/hypermail/linux/kernel/2601.0/00939.html), [follow-up](https://lkml.iu.edu/hypermail/linux/kernel/2601.0/01442.html). A hands-on report from one S4 Mini booted through lk2nd. | n/a |

The task brief names the installed bootloader as the `I9195XXSCQAN` family. The repository holds no recorded evidence of the installed build yet (checklist steps C5 and F2), so nothing below is tied to that exact build.

## Answers in brief

| # | Question | Answer | Label |
| --- | --- | --- | --- |
| 1 | Payload format | A version-0 Android boot image with a **raw, non-Linux binary** in the kernel slot is what lk2nd ships for this phone. No ramdisk content, ATAGS, QCDT or signature is needed in the image. Whether the zImage magic word and the `SEANDROIDENFORCE` trailer are *required* is not known; lk2nd carries both. Behaviour on a failed check is not known. **Measured, 2026-11-18:** `payload.img` (a raw binary, no signature, the zImage words, a 1-byte ramdisk, the trailer) was written to `RECOVERY` and started from it ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)); which fields are required is still not known. | Source (packaging); Unknown (which fields are checked, failure behaviour); Measured (this image starts) |
| 2 | Entry | Expected: load and entry at `0x80208000`, ARM state, `r0 = 0`, `r1 = 3727`, `r2` → ATAGS, SVC mode, IRQ masked, MMU and caches off. All of it is expected, none measured. FIQ is probably **not** masked. **Measured, 2026-11-18,** for `RECOVERY`: all as expected, with FIQ not masked and abort masked: entry `0x80208000`, `r0` = 0, `r1` = 3727, `r2` = `0x80200100` → ATAGS, CPSR `0x60000193` (SVC), SCTLR `0x00C5487A` (MMU and caches off) ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). | Inference; Unknown until measured; Measured |
| 3 | Framebuffer | The stock bootloader does leave a live 24-bit scan-out for the stock kernel. The address is **disputed**: `0x88300000` in the fork, `0x88100000` in a 2026 hands-on report. It must be read from the display controller, not hard-coded. Byte order is expected to be blue, green, red in memory. No cache flush is needed while the data cache is off. **Measured, 2026-11-18:** the panel is still scanning out when an image starts from `RECOVERY`; the buffer on screen is at `0x88100000`, byte 0 is blue, and the display controller's register names the same address ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). | Source (scan-out exists); Unknown (address on this unit, byte order, recovery path); Measured (all three, for `RECOVERY`) |
| 4 | Watchdog | Registers are known and agree across three trees. Whether it is running at handoff is not known; indirect evidence says probably not. 2026-11-18: no reset was seen in any trial, but the windows' lengths are not yet measured, so the state and timeout stay unknown ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). | Source (registers); Unknown (state and timeout); Owner-confirmed (no reset seen) |
| 5 | Halt and reset | `PS_HOLD` control is at `0x00800820`; writing 0 hands the decision to the PMIC. Whether that resets or powers off depends on PMIC state we cannot yet set. A watchdog-bite reset needs no PMIC. An interrupt-masked halt ended by removing the battery is the only route with no unverified register. | Source (registers); Unknown (outcome on this phone) |
| 6 | lk2nd option B | Build target `lk2nd-msm8960`. It is written to the start of `BOOT` and then treats `BOOT` + 512 KiB as the real boot partition. Its `fastboot boot` accepts a non-Linux payload on this phone through an ATAGS-copy path. It changes the entry state, so results under lk2nd are not the stock handoff. | Source (build, layout); Inference (payload path, state changes) |

## 1. Payload format

| Point | Finding | Label and evidence |
| --- | --- | --- |
| Container | Android boot image, header version 0, page size 2048, base `0x80200000`. | Source: [gt-i9195.md](../hardware/gt-i9195.md#boot-image-format-and-handoff). lk2nd builds the same container for this SoC: `[LK] lk2nd/device/2nd/rules.mk:54-70`, `[LK] target/msm8960/rules.mk:10-14`, defaults in `[LK] lk2nd/scripts/mkbootimg:519-543`. |
| Raw binary in the kernel slot | lk2nd's kernel is `lk.bin`, a flat `objcopy -O binary` output, not a zImage and not Linux. For `lk2nd-msm8960` nothing is appended to it. lk2nd lists the GT-I9195 as supported and states that the stock bootloader loads it "just like the original Android image". | Source: `[LK] make/build.mk:4-7`, `[LK] lk2nd/device/2nd/rules.mk:29-35`, `[LK] lk2nd/device/dts/msm8960/rules.mk:4-5` (only a bundled DTB, no appended one), `[LK] Documentation/devices.md:249`, `[LK] README.md:23-30`. Project claim, not tested on this unit. **Measured, 2026-11-18:** a raw binary in the kernel slot (`payload.img`) started from `RECOVERY` in 5 of 5 trials ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| zImage magic | lk2nd places the three zImage header words in its binary: magic `0x016f2818` at offset `0x24`, start `0` at `0x28`, image end at `0x2c`. Its commit message says Qualcomm's bootloader uses them to find an appended DTB. So every lk2nd image this bootloader is reported to accept carried the magic. | Source: `[LK] arch/arm/crt0.S:41-51`; lk2nd commit [`92d6f0f228`](https://github.com/msm8916-mainline/lk2nd/commit/92d6f0f228). **Unknown** whether Samsung's `aboot` rejects a kernel without it. Resolved only by a hardware test, or avoided by keeping the three words. |
| Ramdisk | lk2nd ships a 1-byte ramdisk containing a single zero. Its commit gives no reason. | Source: `[LK] lk2nd/device/2nd/rules.mk:48-51`; commit [`2c81fe6c9b`](https://github.com/msm8916-mainline/lk2nd/commit/2c81fe6c9b). **Unknown** whether a zero-length ramdisk is accepted. Hardware test, or keep the byte. |
| ATAGS, DTB, QCDT (`dt.img`) | None is carried in the image. LineageOS builds this device's boot image with plain `mkbootimg` arguments, postmarketOS's `deviceinfo` sets no QCDT or DTB field, and `lk2nd-msm8960` builds no QCDT. | Source: LineageOS [`BoardConfigCommon.mk`](https://github.com/LineageOS/android_device_samsung_serrano-common/blob/lineage-18.1/BoardConfigCommon.mk) lines 39-43 and no custom boot-image makefile in that tree; postmarketOS `deviceinfo` (cited in gt-i9195.md); `[LK] lk2nd/device/2nd/rules.mk:37-46`. ATAGS are produced by the bootloader at run time (Inference, section 2). |
| `SEANDROIDENFORCE` trailer | lk2nd appends these 16 bytes after every boot image it builds. LineageOS and postmarketOS do not append them for this device, and both were bootable, so the trailer is not needed to boot. | Source: `[LK] lk2nd/device/2nd/rules.mk:82`. Inference for "not needed". What this bootloader prints when the trailer is missing is **Unknown**. Community reports on Samsung phones of this era describe a `Set Warranty Bit: kernel` line at the top left with the boot continuing ([one Galaxy S4 report](https://forums.androidcentral.com/threads/set-warranty-bit-kernel-comes-up-on-samsung-galaxy-s4.685489)). 2026-11-18, with the trailer present: no `Set Warranty Bit` line was seen at the write or in the five trials (Owner-confirmed, [session record](../evidence/phase-2/2026-11-18-v5-session.md#5-the-writes)). |
| Signature | No check blocks an unsigned image on this variant. | Inference, already in [gt-i9195.md](../hardware/gt-i9195.md#bootloader-lock-and-knox). The Knox warranty bit is the cost. **Measured for `RECOVERY`, 2026-11-18:** `payload.img` carries no signature, and it was written and started from `RECOVERY` in 5 of 5 trials. Afterwards the Download-mode status lines read `KNOX WARRANTY VOID: 0x1` (before: `0x0`) and `CURRENT BINARY: Custom` (before: `Samsung Official`) ([session record](../evidence/phase-2/2026-11-18-v5-session.md#6-status-lines)). |
| Behaviour on a failed check | Not documented anywhere we found. One GT-I9195 owner reports the text "Could not do normal boot" with the phone staying in Odin (Download) mode, after a failed update rather than a custom image ([report](https://forums.androidcentral.com/threads/error-while-trying-to-do-update-s4-mini.647651)). Another GT-I9195 owner reports `Set Warranty Bit : Kernel` and no further boot after flashing a kernel package ([report](https://forums.androidcentral.com/threads/mistake-when-using-odin-and-not-selecting-usb-debugging-my-samsung-galaxy-s4-mini.769702)). | **Unknown.** Only the ROADMAP's negative test (a deliberately bad header) on the phone answers this. |

## 2. Entry address and handoff state

No public source records the state this bootloader hands over. lk2nd logs exactly these values when it starts (`[LK] lk2nd/device/2nd/parse-tags.c:163-164`), but we found no published log for a GT-I9195. The table gives what the code around the bootloader expects.

| Point | Expected value | Label and evidence |
| --- | --- | --- |
| Load address | `0x80208000`, the header's `kernel_addr` (base + `0x8000`). | Inference. Qualcomm's reference LK copies the kernel to the header address (`[LK] app/aboot/aboot.c:3459-3461`); Samsung's build may differ. lk2nd does not rely on it: it records its real address and relocates itself (`[LK] arch/arm/crt0.S:53-56`, `:110-129`). **Unknown** until measured. **Measured, 2026-11-18:** `0x80208000`; the image was not relocated ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Entry point | First byte of the kernel image, in ARM state. | Inference: `[LK] app/aboot/aboot.c:1212`, `:1316`; `[LK] project/msm8960.mk:18` (`ENABLE_THUMB := false`). **Measured, 2026-11-18:** entered at the image's first byte, `0x80208000`, in ARM state (CPSR T = 0) ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| `r0`, `r1`, `r2` | `r0 = 0`; `r1` = machine number, expected 3727; `r2` = physical address of an ATAGS list, expected `0x80200100`. | Inference. Reference LK calls `entry(0, machtype, tags)` (`[LK] app/aboot/aboot.c:1316`). The stock kernel registers machine `SERRANO` = 3727 (`[SK] arch/arm/tools/mach-types:1027`, `[SK] arch/arm/mach-msm/board-serrano.c:4727-4737`). lk2nd identifies this phone from the bootloader's command line, which it can only read when `r0 = 0` and `r2` points at valid tags (`[LK] lk2nd/device/2nd/parse-tags.c:166-186`, `[LK] lk2nd/device/dts/msm8960/bundle.dts:25-28`). **Measured, 2026-11-18:** `r0` = 0, `r1` = `0xE8F` (3727), `r2` = `0x80200100` ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| ATAGS or DTB | ATAGS. | Inference: [gt-i9195.md](../hardware/gt-i9195.md#boot-image-format-and-handoff) (board files), and [LKML] booted mainline only through lk2nd's "ATAGS from the previous bootloader" path. **Measured, 2026-11-18:** ATAGS. The first word at `r2` is `2`, the size word of an `ATAG_CORE` header; the second word was not read ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| CPU mode | SVC. HYP is not expected. | Inference: LK runs in SVC (`[LK] arch/arm/crt0.S:171-173`). HYP support on Krait remains Unknown in gt-i9195.md. **Measured, 2026-11-18:** SVC (CPSR `0x60000193`) ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Interrupt masks | IRQ masked. **FIQ probably not masked.** | Inference: reference LK's critical section sets only the I bit (`[LK] arch/arm/ops.S:37-41`, `[LK] include/kernel/thread.h:129-134`). The payload must mask FIQ itself. **Measured, 2026-11-18:** IRQ masked and FIQ not masked, as inferred; abort (A) also masked ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| MMU and caches | Off. | Inference: `[LK] app/aboot/aboot.c:1304-1308`; the ARM Linux boot protocol cited in gt-i9195.md. lk2nd does not trust this either and clears the MMU and cache bits first (`[LK] arch/arm/crt0.S:63-77`). **Measured, 2026-11-18:** MMU, data cache and instruction cache off (SCTLR `0x00C5487A`); alignment checking (A, bit 1) on ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Second core | **Unknown** (held in reset or parked). Not needed for Phase 2. | Measured later (Phase 3). |

**What lk2nd's entry code assumes** (Source: `[LK] arch/arm/crt0.S:31-204`): nothing about its load address until it has relocated; nothing about the stack; a privileged mode with CP15 access; RAM at its link address `0x88F00000` (`[LK] target/msm8960/rules.mk:7-8`). It saves `r0`–`r3` and its own address before touching anything. That is the pattern to copy.

## 3. Framebuffer

| Point | Finding | Label and evidence |
| --- | --- | --- |
| Does the stock bootloader leave the panel scanning out? | **Yes, when it boots the stock kernel.** The stock kernel for this board sets `cont_splash_enabled`, and at start-up reads the splash size and address back from the display controller and copies the image, assuming 3 bytes per pixel. That code only makes sense if the bootloader hands over a running display. | Source: `[SK] arch/arm/mach-msm/board-8930-display.c:1528`, `[SK] drivers/video/msm/mdp.c:3028-3080`. |
| Same for an image in `recovery`, and for a non-Samsung image? | Probably. lk2nd cannot initialise this display itself and only draws on a splash an earlier bootloader left running, and it lists the GT-I9195 without the display caveat it gives two neighbouring devices. [LKML] drew to the framebuffer on an S4 Mini under lk2nd. The bootloader tells the kernel about the display and the boot mode with `lcd_attached=` and `androidboot.boot_recovery=`. | Inference: `[LK] lk2nd/project/msm8x60-late.mk:13-20`, `[LK] Documentation/devices.md:242-250`, `[SK] drivers/video/msm/mipi_samsung_oled-8930.c:2257-2298`. **Unknown** for the recovery-key path specifically; the phone answers it. **Measured, 2026-11-18:** yes. `payload.img`, started from `RECOVERY` with the recovery keys, painted a buffer the panel was showing, in 5 of 5 trials ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Address | **Disputed.** The fork says `0x88300000`. [LKML] found that address wrong on the device tested and got output only at `0x88100000`. Qualcomm's reference value for this SoC family is `0x89000000`, so the address is Samsung's choice and may vary by bootloader build. | Source (conflicting): `[FK] arch/arm/boot/dts/qcom/qcom-msm8930-samsung-serranolte.dts:28-49`, `:145-150`; [LKML]; `[LK] target/msm8960/include/target/display.h:32`. **Unknown** for this unit. **Measured, 2026-11-18:** `0x88100000` on this unit, as [LKML] found, not `0x88300000`, when an image starts from `RECOVERY` ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| How to find the address without guessing | Read it from the MDP4 display controller (base `0x05100000`): DMA_P buffer address at `0x05190008`, size at `0x05190004`, stride at `0x0519000C`, config at `0x05190000`; or the RGB1 pipe source address at `0x05140010`. lk2nd and the stock kernel both do this. | Source: `[LK] include/dev/lcdc.h:36-40`, `[LK] platform/msm8960/include/platform/iomap.h:113-114`, `[LK] platform/msm_shared/include/mdp4.h:60-67`, `[LK] lk2nd/display/cont-splash/dma.c:16-24`, `[LK] lk2nd/display/cont-splash/pipe.c:58-69`, `[SK] drivers/video/msm/mdp.c:3046-3055`. Unverified on this phone. Reading a display register while its clock is off can hang (`[LK] lk2nd/display/cont-splash/target_display.c:42-52`). **Measured, 2026-11-18:** the read of the DMA_P buffer address at `0x05190008` returned, with `0x88100000`, the buffer on screen ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Geometry | 540×960, 24 bits per pixel, video-mode DSI panel. Stride 1620 bytes (540 × 3) is the fork's value; the stock kernel also assumes 3 bytes per pixel with no padding. | Source: `[SK] drivers/video/msm/mipi_samsung_oled_video_qhd_pt-8930.c:1954-1969`, `:2040-2042`; `[FK]` as above; `[SK] drivers/video/msm/mdp.c:3039-3052`. The real stride is in the register above. |
| Byte order | Expected **blue, green, red** in memory. The fork's `r8g8b8` means red in bits 23–16 of a little-endian 24-bit pixel, so byte 0 is blue. Reference LK writes `0xRRGGBB` low byte first, which is the same order. | Source for the naming: `[FK] Documentation/devicetree/bindings/display/simple-framebuffer.yaml:103`, `[LK] dev/fbcon/fbcon.c:67-75`, `:131-134`. Inference for this phone: lk2nd emits `r8g8b8` for any 24-bit splash without reading the pack pattern (`[LK] lk2nd/display/simplefb.c:152-154`). **Unknown** until seen; the payload must reveal it, not depend on it. **Measured, 2026-11-18:** blue, green, red. The `FF 00 00` fill at `0x88100000` showed blue ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Cache flush | Not needed while the data cache is off, as expected at entry: a store goes straight to RAM, and the controller reads RAM. lk2nd flushes only because it runs with caches on. A video-mode panel is refreshed continuously, so no "start" write is needed either. | Inference: section 2; `[LK] lk2nd/display/cont-splash/convert.c:22-24`; `[LK] lk2nd/display/cont-splash/refresh.c:76-110`. |

## 4. Watchdog

| Point | Finding | Label and evidence |
| --- | --- | --- |
| Registers | Watchdog 0 lives in the KPSS timer block: reset (pet) `+0x38`, enable `+0x40`, status `+0x44`, bark time `+0x4C`, bite time `+0x5C`. It counts the 32,768 Hz sleep clock. | Source, three trees agree: `[LK] platform/msm8960/include/platform/iomap.h:74-76`; `[SK] arch/arm/mach-msm/restart.c:38-41`, `[SK] arch/arm/mach-msm/msm_watchdog.c:42-48` with `[SK] arch/arm/mach-msm/msm_watchdog.h:17`; `[FK] drivers/watchdog/qcom-wdt.c:25-31` with `[FK] arch/arm/boot/dts/qcom/qcom-msm8227-common.dtsi:262-272`. |
| Block address | `0x0200A000` in lk2nd and the fork; the stock kernel uses `0x0208A000` for the watchdog. The fork gives the block a per-CPU offset of `0x80000`. So `0x0200A000` is most likely the current CPU's view and `0x0208A000` CPU 0's own frame, and on CPU 0 both reach the same watchdog. | Source for the two addresses: `[LK] platform/msm8960/include/platform/iomap.h:48`, `[SK] arch/arm/mach-msm/include/mach/msm_iomap-8930.h:35-39`, `[SK] arch/arm/mach-msm/devices-8960.c:1719-1724`. Inference for the aliasing. |
| Pet and disable | Pet: write 1 to reset (`0x0200A038`). Disable: write 0 to enable (`0x0200A040`). | Source: `[SK] arch/arm/mach-msm/msm_watchdog.c:128-143`, `[SK] arch/arm/mach-msm/restart.c:306`, `[FK] drivers/watchdog/qcom-wdt.c:87-101`. Unverified on this phone. The stock kernel marks this watchdog `has_secure`, so TrustZone may also be involved. |
| Is it running at handoff? | **Unknown.** Probably not: lk2nd's code for this SoC never pets or disables it outside its reboot routine, yet lk2nd idles in its menu on this phone; and the stock kernel programs the timeouts and enables the watchdog itself late in boot. | Inference: `[LK] target/msm8960/init.c:203-222` is the only watchdog code in `platform/msm8960` and `target/msm8960`; `[SK] arch/arm/mach-msm/msm_watchdog.c:419-440`. Resolved on the phone by reading enable and status at entry. 2026-11-18: no reset was seen in any trial's window (10 minutes asked in trial 1, 2 minutes in trials 2 to 5) (Owner-confirmed). The windows' actual lengths are not yet read from the videos, and no reset does not show that the watchdog is off ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)). |
| Time to reset, if it is running | **Unknown.** Reference points only: the stock kernel uses a 45-second bark with the bite 3 seconds later; the reboot fallback arms a bite of `0x31F3` ticks, about 0.39 seconds. | Source: `[SK] arch/arm/mach-msm/devices-8960.c:1719-1724`, `[SK] arch/arm/mach-msm/msm_watchdog.c:421-422`, `[SK] arch/arm/mach-msm/restart.c:314-317`. |

## 5. Deterministic halt and reset

| Route | Finding | Label and evidence |
| --- | --- | --- |
| `PS_HOLD` | Control register `PSHOLD_CTL_SU` at TLMM base `0x00800000` + `0x820` = **`0x00800820`**. Writing 0 drops `PS_HOLD` and the PMIC acts. | Source: `[LK] platform/msm8960/include/platform/iomap.h:71-77`, `[LK] target/msm8960/init.c:82-92`, `:203-209`; `[SK] arch/arm/mach-msm/restart.c:43`, `:135-149`, `:306-311`; `[SK] arch/arm/mach-msm/include/mach/msm_iomap-8930.h:89`. |
| Reset or power-off? | The PMIC decides, from two registers programmed just before `PS_HOLD` is dropped. Both lk2nd and the stock kernel program them every time. That needs an SSBI PMIC write, and this phone's PMIC is still unconfirmed (PM8917 or PM8038). What a bare `PS_HOLD` drop does in the state the bootloader leaves is **Unknown**. | Source: `[LK] dev/pmic/pm8921/pm8921.c:288-322`, `[SK] arch/arm/mach-msm/restart.c:141`, `:270`. Hardware test. |
| Watchdog bite | Needs no PMIC: reset = 1, bark and bite set short, enable = 1, and the SoC resets after about 0.39 seconds. lk2nd also writes 3 to `TCSR_WDOG_CFG` at `0x1A400030`. | Source: `[SK] arch/arm/mach-msm/restart.c:314-317`, `[LK] target/msm8960/init.c:212-218`, `[LK] platform/msm8960/include/platform/iomap.h:46`, `:73`. How Samsung's bootloader treats a watchdog reset is **Unknown**. |
| Restart reason | A word at `0x2A03F65C` tells the next boot what to do. The stock kernel writes `0x12345678` for a normal restart, `0x77665502` for recovery and `0x12345671` for Download mode. | Source: `[LK] platform/msm8960/include/platform/iomap.h:41-42`, `[SK] arch/arm/mach-msm/restart.c:45`, `:272-304`. **Unknown** what the bootloader does with a stale or missing value after a payload-triggered reset. |
| Halt | Mask IRQ and FIQ, then loop on `wfi`. Removing the battery ends it. This uses no unverified register, but it is deterministic only if the watchdog is not running. | Source for the battery: [gt-i9195.md](../hardware/gt-i9195.md#recovery-mechanisms). |

## 6. lk2nd, option B

| Point | Finding | Label and evidence |
| --- | --- | --- |
| Build | Project `lk2nd-msm8960`, output `lk2nd.img`; the prebuilt release asset is `lk2nd-msm8960.img` (release 23.1). The device entry matches bootloader versions `I9195*`. Not built or run for this research. | Source: `[LK] project/lk2nd-msm8960.mk:1-4`, `[LK] lk2nd/project/lk2nd.mk:38-40`, `[LK] lk2nd/device/dts/msm8960/bundle.dts:25-46`, `[LK] README.md:83-91`; [releases](https://github.com/msm8916-mainline/lk2nd/releases). |
| What it writes, and where | lk2nd is installed through the stock flashing interface at the **start of `BOOT`**. Running, it presents the first 512 KiB of `BOOT` as a virtual partition `lk2nd` and the rest as `boot`, so a later boot-image write through lk2nd lands at `BOOT` + 512 KiB. | Source: `[LK] README.md:43-47`, `:67-73`; `[LK] lk2nd/project/lk2nd.mk:14-18`; `[LK] lk2nd/device/2nd/partition.c:87-95`. |
| Consequences for Android | Installing lk2nd overwrites the start of the stock boot image, so Android no longer boots from `BOOT` until a boot image is written again through lk2nd. If lk2nd were placed in `recovery` instead, a release build would still split `BOOT`, and any lk2nd flash command aimed at `boot` or `lk2nd` would write inside the stock boot image. Only a RAM boot writes nothing. | Inference from the code above and `[LK] app/aboot/aboot.c:3459-3475`. A write plan must say which partition, and list the lk2nd commands allowed. |
| Does `fastboot boot` take a non-Linux payload? | lk2nd says so: "any kind of kernel can be packed into an Android boot image". The code path needs a valid header, RAM addresses that do not overlap lk2nd, and either a DTB in the image or ATAGS inherited from the stock bootloader. On this phone that should be the ATAGS path. There is no zImage check on that path. | Source: `[LK] README.md:28-30`, `[LK] app/aboot/aboot.c:3404-3411`, `:3442-3456`. Inference for "should work here". Caveats from [LKML]: a non-empty ramdisk was required, and an appended DTB needed an lk2nd patch. |
| Entry state compared with stock | Differs. `r1` comes from lk2nd's own board lookup. `r2` points at tags lk2nd rebuilt, at the header's tags address. lk2nd has run its own drivers (interrupt controller, clocks, PMIC, eMMC, USB, Samsung MUIC reset) and has drawn on the framebuffer. It masks IRQ, stops its timer and turns the MMU and caches off before jumping, and leaves the display on. | Source: `[LK] app/aboot/aboot.c:1202-1317`, `[LK] target/msm8960/init.c:171-174`, `[LK] lk2nd/device/2nd/parse-tags.c:94-106`, `:206-242`, `[LK] platform/msm8960/platform.c:99-106`, `[LK] platform/init.c:74`, `[LK] platform/msm_shared/timer.c:96-102`, `[LK] lk2nd/device/2nd/samsung-muic-reset.c:12-47`. Inference: a result under lk2nd is not the stock handoff state. |
| What it would measure for us | lk2nd logs the stock bootloader's `r0`–`r2` and load address, and the splash address, size, stride and format, and offers that log over USB. It can also read registers and read partitions back. | Source: `[LK] lk2nd/device/2nd/parse-tags.c:163-164`, `[LK] lk2nd/display/cont-splash/dma.c:26-31`, `[LK] lk2nd/fastboot/misc.c:13`, `[LK] lk2nd/fastboot/debug/register.c:61-68`, `[LK] lk2nd/fastboot/fetch.c:131-132`. |
| Risk it adds | The same interface offers flash, erase and register-write commands for every partition, protected ones included. | Source: `[LK] lk2nd/fastboot/debug/register.c:43-68`. A plan using lk2nd must name the only commands permitted. |

## Candidate payload specification

A proposal for review, not a build instruction. **Every value is unverified on the device** unless the row says otherwise; "expected" means "from the sections above".

**Image packaging** (copies lk2nd's known layout, section 1):

| Field | Value |
| --- | --- |
| Container | Android boot image, header version 0, page size 2048 |
| `kernel_addr` / `ramdisk_addr` / `second_addr` / `tags_addr` | `0x80208000` / `0x81200000` / `0x81100000` / `0x80200100` (lk2nd's values; LineageOS uses `0x82200000` for the ramdisk) |
| Kernel | Flat binary. Branch at offset 0; zImage words at `0x24`, `0x28`, `0x2c` (`0x016f2818`, `0`, image size) |
| Ramdisk | 1 byte, value 0 |
| Second stage, QCDT, appended DTB, signature | None |
| Command line, board name | A short fixed string; empty board name |
| Trailer | 16 bytes `SEANDROIDENFORCE` after the image |
| Recorded | SHA-256 of the final file, and of two clean builds, which must match |

**Entry code** (ARM Assembly):

1. Save `r0`–`r3`, the CPSR, SCTLR and its own run-time address before changing anything.
2. Mask IRQ and FIQ. Do not rely on the bootloader for FIQ.
3. Run position-independently until the run-time address has been compared with the link address `0x80208000`; record whether they match.
4. Set the stack inside the image's own reserved static region, zero `.bss`, call the Rust entry.

**The one observable signal:** a full-screen fill of the framebuffer, held for 10 seconds.

- The framebuffer address, size and stride are read from the display controller (section 3). The payload writes only if the address equals one of the two reported values (`0x88300000` or `0x88100000`) and the size is 540×960. Otherwise it writes nothing and goes straight to the end state, which is itself a recorded result.
- Top half: bytes `FF 00 00` per pixel. It shows blue if the order is blue-green-red, red if it is the reverse. Bottom half: white, which is correct in either order and cannot be mistaken for the Samsung splash.
- Across the middle, one row of 32 blocks per recorded word, most significant bit first, white for 1 and dark grey for 0, so that a photograph carries the handoff state.
- The hold is timed with the KPSS general-purpose timer at 32,768 Hz (`[LK] platform/msm_shared/timer.c:104-117`), with a bounded busy loop if the counter does not advance.

**End state:** halt. IRQ and FIQ masked, `wfi` loop; the owner removes the battery. The watchdog is neither petted nor disabled in this first payload, so if it is running the phone resets on its own and the elapsed time is the ROADMAP's watchdog measurement. A payload-triggered reset (`PS_HOLD` or watchdog bite) is a separate, later increment, because its outcome is unknown (section 5).

**What the entry code must record** (one 32-bit word each):

| Word | Why |
| --- | --- |
| `r0`, `r1`, `r2` | Boot handoff contract |
| CPSR | Mode, and the I, F, A and T bits |
| SCTLR | MMU and cache enable bits |
| Run-time entry address | Confirms the load address |
| First word at `r2`, if `r2` lies in RAM | ATAGS or DTB. An ATAGS list reads as the ATAG_CORE size word, `0x00000005` (or `0x00000002` for an empty core tag); the tag number `0x54410001` is the second word. A device tree reads as `0xEDFE0DD0`, its magic bytes `d0 0d fe ed` taken as a little-endian word. |
| Watchdog enable and status | Section 4 |
| Display buffer address, size, stride, config | Section 3 |
| A checksum computed in Rust | Proves Rust code ran, as in Phase 1 |

**Reuse from Phase 1** ([rust-foundation.md](../phase-1/rust-foundation.md)):

| Shared with the Phase 1 QEMU fixture | GT-I9195-specific, new |
| --- | --- |
| The entry-stub pattern: mask interrupts, set the stack, zero `.bss`, call Rust | Link address `0x80208000`, the position-independent prologue and the register capture |
| `#![no_std]` Rust, `panic=abort`, target `armv7a-none-eabi`, soft-float, no heap | Boot-image packing, the zImage words and the trailer |
| The static-table checksum and the panic handler's structure | Framebuffer output in place of the PL011 UART; the panic handler paints, it does not print |
| Build checks: no undefined symbols, ELF attributes, byte-identical rebuilds, hosted-dependency rejection, corrupted-image rejection | **No `svc` at all.** The semihosting exit must not exist in the device image |
| | Display-controller and watchdog register reads, the timer delay, the halt |

Device-specific logic that is pure computation (the header packer, the pattern generator) can be tested on the host. Nothing device-specific can be tested in QEMU, which has no MSM8930 machine ([TESTING.md](../TESTING.md#not-implemented-yet)).

## Questions only the phone can answer

Research cannot close these. They are not guessed here.

1. Whether the bootloader accepts a kernel without the zImage words, a zero-length ramdisk, or a missing trailer, and what it shows and does when it rejects an image.
2. The actual load address and entry state: `r0`–`r2`, mode, interrupt masks, MMU and caches.
3. Whether the display is still scanning out when a non-Samsung image is started from `recovery`, the framebuffer address on this unit, and the byte order.
4. Whether the watchdog is running at handoff, and its timeout.
5. What a `PS_HOLD` drop or a watchdog bite does in the state the bootloader leaves, and how the bootloader treats the next boot.

**Answers from the session of 2026-11-18** ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)):

- Question 1 was not tested: the image carried the zImage words, a 1-byte ramdisk and the trailer. An unsigned image was accepted into `RECOVERY` and started from it (Measured).
- Questions 2 and 3 are answered (Measured): see sections 2 and 3.
- Question 4 is open. No reset was seen (Owner-confirmed), but the windows' lengths are not yet measured.
- Question 5 is not answered: the payload triggers no reset.

## Blockers before any write

| # | Missing | Who resolves it |
| --- | --- | --- |
| 1 | Phase 0 passed, with its evidence reviewed (ROADMAP Phase 2 entry gate). | Owner (remaining checklist steps); orchestrator (review) |
| 2 | The installed build recorded as evidence: bootloader version, build, baseband, CSC (checklist C5, F2). | Owner |
| 3 | The Download-mode status lines photographed and transcribed: Knox warranty bit, secure boot, reactivation lock, write protection (F2). | Owner |
| 4 | Download mode shown reliable, Heimdall detection, and the PIT listing `BOOT` and `RECOVERY` with sizes (F1, F4, F5). | Hardware test, by the owner |
| 5 | Verified stock `boot` and `recovery` images for the **installed** build, with checksums, held outside the repository (G1–G3). Without them a written partition cannot be restored. | Owner obtains; research identifies the matching package |
| 6 | The owner's explicit acceptance that a non-Samsung image is reported to set the Knox warranty bit permanently. | Owner |
| 7 | The method: option A (`recovery`) or option B (lk2nd), and the single partition to be written. For option B, the partition, the allowed lk2nd commands, and a review of lk2nd as a third-party component. **Decided 2026-11-11 (decision B, [PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937)): method A for first-write planning, with the payload written only to `RECOVERY`.** The first probe then runs directly under the stock bootloader, with no lk2nd in the handoff being measured. It proves recovery-key execution only; a normal power-on boot of Revival OS is a later increment, and method B stays a separately reviewed later option for RAM-boot iteration. This is a planning decision, not approval of a write: the write plan (item 12) is still required. | Owner and orchestrator |
| 8 | The payload itself: a reviewed pull request with the entry code, the packer, host tests, a reproducible build and a recorded SHA-256. **Written and reviewed:** [PR #10](https://github.com/revival-systems/revival-os/pull/10), payload v1.3 at `be485e2`, verified by the reviewer from a clean export. The image is frozen at `payload.bin` `8ee519ae31a9d005f72e14e21ff5c0b7baadefbec225083013820d5700616a2b` and `payload.img` `bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02`; both hashes are pinned in the Makefile and checked by `make check` (test `payload-frozen`, [Trial kit](#trial-kit-host-only)). PR #10 was merged into `main` on 2026-11-11 as `8ff31f0`. | Implementer, then orchestrator review |
| 9 | A decision on the payload reading display-controller and timer registers, given that a read from an unclocked block can hang. | Research and orchestrator review; then hardware test |
| 10 | The deliberately invalid image for the ROADMAP's negative test, and the recovery steps that follow it. **The image is now built and tested on the host** ([Trial kit](#trial-kit-host-only)); it is not approved for any write. The recovery steps that follow it are still open and belong in the write plan. | Implementer; owner approves in the write plan |
| 11 | The five phone-only questions above, accepted in the write plan as open, with the expected observation and the recovery action for each outcome. | Hardware test |
| 12 | An approved write-plan issue naming the phase, partition, image, SHA-256, method and emergency rescue procedure. A draft of its text is in [write-plan-draft.md](write-plan-draft.md); it approves nothing, and the issue is opened by the implementer when the reviewer's task says so. | Owner and reviewer |

Items 1–6 are the same gates Phase 0 and the ROADMAP already set. Items 7–12 are new from this research.

## v1 payload decision

The first payload (built and tested in QEMU, not flashed) deliberately **lightens** the candidate specification above. It is implemented in [boot/samsung-serranolte/](../../boot/samsung-serranolte/) (`kstart.S`, `payload.rs`, `link.ld`), packed by [tools/pack_bootimg.py](../../tools/pack_bootimg.py), and tested by [tests/boot/](../../tests/boot/) under `make check` (target `test-payload`). This note covers **v1.3** (the third review revision of v1).

What it keeps: the entry capture (`r0`–`r3`, CPSR, SCTLR, run-time entry address), IRQ+FIQ masking, stack in the image's own static region, `.bss` zeroing, both candidate framebuffers painted (`0x88100000` bytes `FF 00 00`; `0x88300000` bytes `00 FF 00`) with the recorded words drawn as rows of bit cells, a masked `wfi` halt, and the packaging (Android boot image v0, page 2048, kernel at `0x80208000`, zImage words, 1-byte zero ramdisk, `SEANDROIDENFORCE` trailer). The image writes **only to framebuffers**, contains **no `svc`**, and links with zero undefined symbols.

**Order of operations: risky steps last.** The payload paints a visible result before it does anything that could hang or fault, so either still leaves evidence on screen:

1. fill both candidate framebuffers;
2. read `*r2` (guarded, below) and draw the eight handoff word rows in both;
3. **as the very last action**, read one display-controller register and act on it (below).

In v1.1 the compiled code did not follow this order: it read `*r2` before the fills. v1.2 moves that read after both fills in the source; it is a volatile read, so the compiler cannot move it back above the (volatile) fill writes, and the disassembly shows it after both fill loops.

**Halt-only exception vectors (v1.2): a safety net, not fault reporting.** v1.1 installed no vectors, so a fault ran whatever the bootloader had left in `VBAR`; in QEMU a write fault never reached the halt and the CPU ran away. The image now starts with the same header as lk2nd (`[LK] arch/arm/crt0.S:31-51`): a reset branch at `0x00`, the seven exception vectors at `0x04`–`0x1C`, a branch over the zImage words at `0x20`, and the three zImage words unchanged at `0x24`/`0x28`/`0x2C`. Every vector is a bare `b halt_loop`. Right after masking IRQ and FIQ, `kstart.S` points `VBAR` at the run-time address of `_start` that it has already captured. On a fault the payload **only halts**: no handler code, no stack use, nothing painted, no reset. Whatever was on screen before the fault stays there. This is deliberately **not** the Phase 3a capability (exception vectors that *report* an undefined instruction and a data abort, then reset); nothing here identifies or reports the fault. Limits to keep in mind:

- `VBAR` is used only while `SCTLR.V` (bit 13) is 0. The payload does not write `SCTLR`, so if the bootloader hands over with high vectors selected, the net is inert and a fault behaves as in v1.1. The painted `SCTLR` row shows bit 13, so a photograph says which case applied. lk2nd clears that bit itself (`[LK] arch/arm/crt0.S:63-77`). **Unknown** on this unit until measured. **Measured, 2026-11-18:** `SCTLR.V` = 0 at the handoff from `RECOVERY`, so the net was in effect once `VBAR` was set ([session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)).
- A fault taken before the `VBAR` write (the first ten instructions: the two header branches, the entry capture and the interrupt mask) is not caught.
- On the phone a halted fault and a normal halt look the same unless the picture is incomplete; only the emulator can read the CPU mode.

**ROADMAP Phase 2 negative test: decided (decision A).** [ROADMAP.md](../../ROADMAP.md) Phase 2 used to list "A payload that triggers an exception before any handler exists shows its observable behaviour". With these vectors this payload has no state in which "no handler exists" once `VBAR` is set, ten instructions after entry, so that test needed either a separate no-vector variant of the image or a change of wording. The orchestrator decided on 2026-11-11 ([PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937), decision A): `qemu-payload-fault-halts` is accepted as the Phase 2 exception-path test, scoped to QEMU after the halt-only vectors are active; deliberate on-device exception behaviour, reporting and reset are deferred to Phase 3a; and no separate no-vector phone image is built for Phase 2. The ROADMAP bullet now carries the orchestrator's wording verbatim. This changes the planned scope of Phase 2; it does not turn emulator evidence into a phone result. The two limits above still stand: the instructions before `VBAR` is set, and a handoff with `SCTLR.V` = 1, are outside what the test demonstrates.

**Stack alignment (v1.2).** `kstart.S` pushes eight words (`r4`–`r11`) instead of seven, so `sp` is 8-byte aligned at the call into Rust, as the AAPCS requires. The handoff array is still the first seven words; the eighth is padding.

What it still drops from the candidate spec, and why:

- **Almost no MMIO reads, and the one it does is last.** The payload reads **only CPU registers** plus one guarded word at `*r2`, and then — as the final step — the single **MDP4 DMA_P buffer-address register** (`0x05190008`, section 3) to discover the real framebuffer address. That read is last precisely because a read from a display block whose clock or power domain the bootloader left off can fail with no output. lk2nd's source says so, and checks the MDP power domain before reading where the platform defines that register ([`lk2nd/display/cont-splash/target_display.c:42-52`](https://github.com/msm8916-mainline/lk2nd/blob/cf45aefd22d744b2bf9b39455afae697ce430063/lk2nd/display/cont-splash/target_display.c#L42-L52), Source). The guard is compiled only when `MDP_GDSCR` or `MDSS_GDSCR` is defined, and `[LK] platform/msm8960/include/platform/iomap.h` defines neither, so on this SoC lk2nd reads the MDP registers unguarded (Inference from the source). By then both candidate buffers and the eight handoff rows are already painted. It still reads **no timer and no watchdog** register.
- **No timer.** Without a timer read the payload cannot hold the signal for a measured interval; it paints and halts, and the continuously-refreshed video-mode panel (section 3) keeps showing the last frame until the battery is pulled.
- **No reset and no watchdog interaction.** It neither pets nor disables the watchdog and never triggers a reset (every reset route has an unknown outcome, section 5). If the watchdog is running, the device resets itself and that interval is the measurement.

**Narrowed `*r2` read.** The guarded read of `*r2` is restricted to the tags page `[0x80200000, 0x80208000)` (word-aligned), where the bootloader's ATAGS/DTB pointer (`tags_addr 0x80200100`) should fall — not all of RAM. Anything else records the sentinel `0xFFFFFFFF` (as under QEMU, where `r2 == 0`).

**The MDP4 register as a ninth word, and the optional third buffer.** The register value is drawn as a ninth word row in both candidate buffers. If it names a **plausible framebuffer** — word-aligned; the whole 540×960×3 buffer inside device RAM `[0x80000000, 0xE0000000)`; not equal to either candidate; and not overlapping the image/stack, the tags page, SMEM, WCNSS or rmtfs (section "Write-region safety") — the payload also fills that address grey (`80 80 80`) and draws all nine rows there. Otherwise it paints nothing more.

**Rule change (v1.3): the bootloader's framebuffer reservation is allowed.** The v1.1 and v1.2 rule also rejected any address overlapping the reserved framebuffer region `[0x88300000, 0x88600000)`. That was a mistake: it is the one region where a framebuffer is expected, and section 3 records that the address inside it is Samsung's choice and differs between bootloader builds (`0x88300000` in the fork, `0x88100000` on the [LKML] unit). The GREEN fill covers `0x88300000` .. `0x8847BB00` only, so if this unit's buffer starts at `0x8847BB00` or above inside the reservation, neither candidate fill reaches it, and v1.2 also refused to paint it as the third buffer: the screen would have shown no sign of life. Reproduced on v1.2 with the register reading `0x8847C000`: nothing was painted there. v1.3 removes that region from the reserved list in the payload and in the oracle. The two exact candidate addresses are still excluded (they are already painted), and every other reserved region is still rejected. A discovered address that overlaps a candidate fill (for example `0x88400000`) is painted grey over part of it; that was already the case for addresses overlapping the RED fill.

The upper bound `0xE0000000` (`DEV_RAM_HI`) is **unverified on this unit**: it is the nominal 1.5 GiB above the DRAM base, not a measured end of usable RAM. A register value that passes the rule but is not backed by RAM makes the grey fill fault; the halt-only vectors then stop the CPU with both candidate buffers and all nine rows already painted.

**How the third-buffer code is tested (v1.2).** In QEMU `virt` the register address is flash and reads back `0x00000000` by default, which fails the rule: that is the plain run. v1.1 tested the other outcomes only through a Python mirror of the rule. v1.2 runs the Rust code itself on each of them by supplying the register value as a read-only emulated flash image (`-drive if=pflash,unit=1,...`, a 64 MiB sparse file with the little-endian word at offset `0x01190008` = `0x05190008` − `0x04000000`), one bounded QEMU run per value:

| Injected value | Why | Required result |
| --- | --- | --- |
| none (`0x00000000`) | the plain run | both candidates byte-exact; no third buffer |
| `0x89000000` | plausible | third buffer grey with all nine rows, byte-exact; both candidates byte-exact with row 9 = the value |
| `0x88100000` | a candidate address | nothing extra painted; both candidates byte-exact |
| `0x8F000000` | reserved (WCNSS) | the region it names stays all zero |
| `0x89000002` | not word-aligned | the region it names stays all zero |
| `0x8847C000` (v1.3) | inside the framebuffer reservation, past the end of the GREEN fill | third buffer grey with all nine rows, byte-exact; both candidates byte-exact with row 9 = the value (the regions do not overlap) |
| `0xBFF00000` | plausible for the device, but the buffer crosses the emulator's RAM end at `0xC0000000` | the fill takes a data abort: PC rests in `halt_loop`, CPU mode is ABT (`0x17`), both candidates byte-exact with nine rows |

In every run without a fault the CPU must still be in SVC mode at the halt, since a faulted run now also ends in `halt_loop`, and its stack pointer must be 8-byte aligned. The first `0x30` bytes of the image are also checked statically: each of the seven vectors must be a branch to `halt_loop`, and `halt_loop` must be exactly `wfi` and a branch to itself. Only the data-abort vector is exercised at run time.

**Tests for the paths the phone will run (v1.3).** Every run above enters with `r0` = `r1` = `r2` = 0, so the in-range `*r2` read never ran, although it is the path the phone takes. Two cases now enter through a five-instruction test-only shim, loaded outside the image at `0x80100000`, that sets `r0`–`r3` and jumps to the payload; known words are planted in RAM with QEMU's `-device loader,addr=A,data=V,data-len=4`. Nothing is added to the image.

| Case | Entry state | Required result |
| --- | --- | --- |
| Device-like handoff | `r0` = 0, `r1` = `0x00000E8F` (machine 3727, section 2), `r2` = `0x80200100`, with `0x00000005` stored there | rows show those values and row 7 (`*r2`) is `0x00000005`, byte-exact in both candidates; clean SVC halt |
| Guard edges, read | `r2` = `0x80200000`; `r2` = `0x80207FFC` (first and last word of the tags page) | row 7 is the word planted there |
| Guard edges, refused | `r2` = `0x80208000` (the image); `0x801FFFFC` (just below the page); `0x80200102` (not word-aligned) | row 7 is the sentinel `0xFFFFFFFF`, although other words are stored at or around those addresses |

Two more cases check what `kstart.S` claims about an image the bootloader loads somewhere else: the same bytes are loaded and started at `0x80A08000`. Both candidates must be byte-exact with the entry row = `0x80A08000` and a clean halt in the relocated `halt_loop`; and with `0xBFF00000` injected, the fault must still end in the relocated `halt_loop` in ABT mode, which shows `VBAR` follows the run-time address. (The stack and the empty `.bss` stay at their link addresses, which are RAM in both the emulator and the device memory map; the image has no `.rodata` or `.data` and makes no other absolute reference to itself.)

**Reading the picture on trial day.** Eight rows with no ninth row mean the display-register read hung or faulted: rows 1–8 are drawn before the read, and row 9 only after it returns. The fault half was checked by the reviewer on a copy with one instruction patched so the read hits an unmapped address: it halts in ABT mode with eight rows drawn and row 9 left as fill colour. There is no repository test for that. The [row-reading tool](#row-reading-tool) takes the eight rows and states this case.

**Word rows readable from a photograph (v1.2).** In v1.1 the 16×16 blocks touched, so a run of equal bits merged into one bar that cannot be counted from a photo. Each bit is now a separate cell, 12 px wide and 24 px tall, with the framebuffer's fill colour showing between cells: 4 px between bits, 7 px between nibbles, 8 px between rows, and a margin from the screen edge. Bit `b` (0 = most significant) of row `r` starts at `x = 6 + 16·b + 3·⌊b/4⌋`, `y = 16 + 32·r`. The last cell ends at x = 535 and y = 296, inside 540×960 (checked at compile time in `payload.rs`). White is 1 and black is 0, as before. The host oracle and decoder use the same geometry; this is the only v1.2 change that alters the expected framebuffer bytes.

**No device-side completion marker.** v1 briefly wrote a marker word so the harness could tell painting had finished; v1.1 removes it (the image writes only framebuffers). The QEMU harness instead polls the CPU's PC over QMP until it rests in the `halt_loop` symbol (resolved from the ELF), with a bounded timeout, then reads the CPU mode to tell a normal halt from a faulted one, and its QMP socket lives in a short temporary directory so a long checkout path cannot exceed the `AF_UNIX` limit.

**Write-region safety (step 3 check).** Every address the payload writes is in RAM and clear of the image, its stack, ATAGS and the documented reserved regions:

| Region | Range | Clear of |
| --- | --- | --- |
| Image + 64 KiB stack | `0x80208000` .. < `0x81208000` (16 MiB reserved, used < 1 MiB) | above ATAGS `0x80200100` and SMEM `0x80000000`+2 MiB (ends `0x80200000`); far below `0x88100000` |
| FB_RED fill | `0x88100000` .. `0x8827BB00` (1,555,200 B) | below FB_GREEN; above SMEM; not a documented reserved region (the contested LKML address, in the free `0x88000000`–`0x88300000` gap) |
| FB_GREEN fill | `0x88300000` .. `0x8847BB00` (1,555,200 B) | within the documented 3 MiB framebuffer reservation `0x88300000`+3 MiB (ends `0x88600000`); below WCNSS `0x8F000000` |
| Third buffer (only if plausible) | a discovered MDP4 address, 1,555,200 B | gated by the plausibility rule above, so by construction aligned, inside the nominal RAM range (upper bound unverified, above), not at either candidate address, and clear of the image/stack, the tags page, SMEM, WCNSS and rmtfs; it may lie in the bootloader's framebuffer reservation and may overlap a candidate fill (v1.3); painted in QEMU only by the injected-value runs |

The MDP4 read at `0x05190008` is a register **read**, not a write. The two candidate framebuffers do not overlap each other (`0x8827BB00` < `0x88300000`). None of these ranges is a bootloader-chain, `efs`, `persist` or `modem` partition; they are DRAM only. QEMU `-m 2048` (RAM `0x40000000`–`0xC0000000`) spans the image and both candidates, which is why the emulator test exercises the real addresses. The only system-control (CP15) register the payload writes is `VBAR`; it writes no memory outside the framebuffers and its own stack.

## Trial kit (host only)

Host-side preparation for the first trial. **Nothing here contacts a device, and nothing here is approved for a write**; every write still needs the approved write plan (blocker 12). The payload is frozen at the reviewed v1.3 bytes: `make check` (test `payload-frozen`) fails if the SHA-256 of `payload.bin` or `payload.img` changes.

| File (in `build/boot-serrano/`) | Size | SHA-256 |
| --- | --- | --- |
| `payload.bin` (frozen) | 1,636 bytes | `8ee519ae31a9d005f72e14e21ff5c0b7baadefbec225083013820d5700616a2b` |
| `payload.img` (frozen) | 6,160 bytes | `bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02` |
| `payload-invalid.img` (negative test) | 6,160 bytes | `34dc91c64811346a3766e71044c2260340fadec0a0ea327e4126a1ef7a584d7b` |

### Negative-test image (blocker 10)

ROADMAP Phase 2 asks for "a deliberately invalid image (bad header)" to show how the bootloader rejects images. `make payload-invalid` builds `build/boot-serrano/payload-invalid.img` from the same `payload.bin`, using the packer's `--invalid-magic` option, which is off by default. It prints the SHA-256 on a line that starts `INVALID-MAGIC-NEGATIVE-TEST`, so the hash cannot be taken for the payload's. `make build` and `make payload` do not build it and do not print it.

**One field is wrong, and only one.** The 8-byte magic at offset 0 reads `INVALID!` in place of `ANDROID!`. Every other byte is the same as in `payload.img`: the load addresses, the page size, the image id, the 1-byte ramdisk and the trailer. Four byte values actually differ (offsets 0, 2, 3 and 4), because `INVALID!` and `ANDROID!` share the letters at the other four positions.

**The kernel slot still holds the real payload, on purpose.** Whether Samsung's `aboot` checks the magic at all is Unknown (section 1). The trial then answers the question either way:

| What the phone does with `payload-invalid.img` | What it means |
| --- | --- |
| It refuses to start the image | The bootloader checks the magic. What it shows and does next is the ROADMAP's record of how it rejects an image. |
| The normal picture appears (fill colour and word rows) | The bootloader does not check the magic. That is a result too, and the payload ran from an image with a bad header. |

With a harmless or empty kernel slot the second outcome would show nothing, and could not be told apart from a hang. What the bootloader shows when it refuses an image, and the state it leaves the phone in, are still Unknown (section 1, "Behaviour on a failed check"). The recovery steps for each outcome are for the write plan, not for this document.

Tests, all under `make check`:

| Test | Pass when |
| --- | --- |
| `payload-invalid-magic-only` | `payload-invalid.img` has the same length as `payload.img`, starts with `INVALID!`, and is identical from offset 8 on; the reader accepts `payload.img` and rejects `payload-invalid.img` for the magic alone ([check_negative_img.py](../../tests/boot/check_negative_img.py)) |
| `payload-invalid-rejected-by-reader` (negative) | The repository's boot-image reader **exits nonzero** on `payload-invalid.img` and prints `magic b'INVALID!' != b'ANDROID!'` |
| `payload-invalid-repro-identical` | Two clean builds give a byte-identical `payload-invalid.img` |
| `payload-frozen` | `payload.bin` and `payload.img` have the SHA-256 values in the table above, so adding the packer option did not change the real image |
| `unit-python` | The option is off by default; only the magic differs; the checker reports a second differing byte, an unchanged magic, a different bad magic, a changed length and swapped arguments |

### Row-reading tool

[tools/read_rows.py](../../tools/read_rows.py) turns the rows typed from a photograph into the Phase 2 record. It runs on the host, uses only the Python standard library and contacts no device. It decodes what was typed, so its output is not hardware evidence by itself: the photograph is ([TESTING.md](../TESTING.md#recording-evidence)).

```sh
python3 tools/read_rows.py --fill blue 00000000 00000E8F 80200100 00000093 00C50078 80208000 00000005 22BECBA4 88100000
```

The input is the fill colour seen (`red`, `blue`, `green` or `grey`) and the rows from the top, each as eight hex digits: nine rows, or eight if the ninth is missing. A shorter word is refused, because a row is 32 cells and a short word is a dropped digit. The command above is the handoff section 2 expects, on a blue screen. Its CPSR and SCTLR words are examples that satisfy section 2 (SVC, IRQ masked, MMU and caches off); the other bits of those two registers are not predicted.

| Part of the record | What it says |
| --- | --- |
| First line | Whether row 8 equals `0x22BECBA4`, the checksum the Rust code computes. The payload can paint no other value there, so a mismatch means the rows were misread, and the record says so before anything else. A match vouches for row 8 only. |
| Rows as typed | Each row as 32 cells in groups of four (`#` white, `.` black), to compare with the photograph by eye. |
| `r0`, `r1`, `r2` | Against the expected handoff: 0, machine number 3727, and an address inside the tags page `[0x80200000, 0x80208000)`. |
| CPSR | The mode, the I, F and A masks, the Thumb bit and the endianness, as the bootloader left them. |
| SCTLR | MMU (M), data cache (C), instruction cache (I), alignment check (A) and high vectors (V). With V set, `VBAR` is ignored and the halt-only vectors were inert. |
| Entry address | The link address `0x80208000`, or relocated and by how much. |
| `*r2` | The sentinel `0xFFFFFFFF`, an ATAG_CORE header, the device-tree magic, or something else. |
| MDP4 word | A candidate address, a third buffer the payload painted grey, or rejected with the reason. The rule is the oracle's ([serrano_v1.py](../../tests/boot/serrano_v1.py), `fb_rejection`); the tool holds no copy of it or of its constants. |
| Fill colour | Which buffer is on screen and what it shows about the byte order: red or blue is `0x88100000` (red means byte 0 is red, blue means byte 0 is blue), green is `0x88300000`, grey is the MDP4 address. Green and grey do not show the order. |
| Row count | Nine rows: the display-register read returned. Eight rows: it hung or faulted. |

The record ends with a list of the fields that differ from the expected handoff. Inputs that contradict each other are listed separately as "cannot be right as typed": a grey screen whose ninth row is not an address the payload paints, or a `*r2` row that is not the sentinel when `r2` is an address the payload never reads. The exit status is 0 when the rows decode, 1 when the checksum row is wrong or the inputs contradict each other, and 2 for a usage error.

**What `*r2` holds.** The payload records the first word at `r2`. An ATAGS list starts with the ATAG_CORE header, whose first word is its size in words (5, or 2 for an empty core tag); the tag number `0x54410001` is the second word, which the payload does not record. A device tree starts with the bytes `d0 0d fe ed`, which a little-endian read returns as `0xEDFE0DD0`. The tool recognises those values, and the candidate specification's table above now names the same ones.

**The expected screen.** Each run also writes the screen for that colour and those rows as a 540×960 PNG, so the owner can see what to look for: by default `build/boot-serrano/expected-screen-<colour>-<n>rows.png`, or the path given with `--png`; `--no-png` writes none. The fill is drawn as it is seen, and an eight-row input leaves the ninth row unpainted. The PNG is never committed: a path inside the repository but outside `build/` is refused.

Limits: the tool knows only the four fills the payload paints, assuming the panel's order is red-green-blue or the reverse. Any other screen, or one with fewer than eight rows, is recorded as seen, not decoded.

Tests (`unit-python`, [test_read_rows.py](../../tests/boot/test_read_rows.py)): each decoded field; the plain QEMU words; the section-2 expected device words on red, blue and green; one changed field at a time; a misread checksum row, said first, with exit status 1; an eight-row input; the contradictory inputs; and the command line's refusals. The PNG is read back by a small reader in the test and decoded by the oracle to the same words, for every fill and for an eight-row picture.

## Sources

Checked 2026-11-10. Line numbers refer to the pinned commits in the table at the top.

- lk2nd: <https://github.com/msm8916-mainline/lk2nd> at `cf45aefd22d744b2bf9b39455afae697ce430063`; commits [`92d6f0f228`](https://github.com/msm8916-mainline/lk2nd/commit/92d6f0f228) (zImage header), [`2c81fe6c9b`](https://github.com/msm8916-mainline/lk2nd/commit/2c81fe6c9b) (1-byte ramdisk), [`64ab4e976d`](https://github.com/msm8916-mainline/lk2nd/commit/64ab4e976d) (dummy header addresses)
- Stock-derived kernel: <https://github.com/LineageOS/android_kernel_samsung_msm8930-common> at `94cbcc3691247ded64f6c772ca37b5916f9f4b4a`
- Community mainline fork: <https://github.com/msm8227-mainline/linux> at `b51f999a8ab27982c2b5ea07f963cd226058ac04`
- LineageOS device tree: <https://github.com/LineageOS/android_device_samsung_serrano-common/blob/lineage-18.1/BoardConfigCommon.mk>
- postmarketOS wiki, Samsung Galaxy S4 Mini LTE (names `lk2nd-msm8960.img` for this device): <https://wiki.postmarketos.org/wiki/Samsung_Galaxy_S4_Mini_LTE_(samsung-serranolte)>
- Kernel mailing list, January 2026: <https://lkml.iu.edu/hypermail/linux/kernel/2601.0/00939.html>, <https://lkml.iu.edu/hypermail/linux/kernel/2601.0/01442.html>
- Community reports of bootloader messages (not authoritative): the three forum threads linked in section 1
- Earlier research in this repository: [gt-i9195.md](../hardware/gt-i9195.md), especially [boot image format and handoff](../hardware/gt-i9195.md#boot-image-format-and-handoff), [debug output interfaces](../hardware/gt-i9195.md#debug-output-interfaces), [recovery mechanisms](../hardware/gt-i9195.md#recovery-mechanisms) and [Download mode and flashing tools](../hardware/gt-i9195.md#download-mode-and-flashing-tools)

The downloaded source trees were read outside this repository and are not committed. Nothing in them was built or run.
