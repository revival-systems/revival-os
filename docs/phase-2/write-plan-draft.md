# Phase 2 write plan, method A (`RECOVERY` only): DRAFT v3.2

**This is a draft. It approves nothing.**

- **No command in this document may be run** until an approved write-plan issue exists ([AGENTS.md](../../AGENTS.md#hardware-safety-contract), rule 1).
- **The issue is opened by the implementer when the reviewer's task says so.** This file is the proposed text of that issue. The reviewer reviews it, and **the owner approves the finished plan**.
- Every `heimdall flash` line below is a proposal. Until the issue is approved, the only commands allowed on the phone are the read-only ones in the [Phase 0 checklist](../phase-0/hardware-verification-checklist.md#rules-for-this-checklist) (rule 5).
- Written 2026-11-11 from the repository's documents and public sources, revised the same day (v2), and revised on 2026-11-14 (v3) with the recorded Phase 0 facts and the decisions below. v3.1, the same day, marks the reviewer's confirmed wordings as decided and adds the two-minute wait at the lock screen. **No device was touched and no flash command was run to write it.** v3.2, the same evening, records E-16 and E-17: the read-only PIT read from the write host, which is a command the [Phase 0 checklist](../phase-0/hardware-verification-checklist.md#allowed) allows. No flash command was run.

**Phase:** 2, first bare-metal boot ([ROADMAP.md](../../ROADMAP.md#phase-2--first-bare-metal-boot)). **Method:** A, decided by the former orchestrator on 2026-11-11 ([PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937), decision B). **Partition:** `RECOVERY`, and no other.

What a pass of this plan proves, and what it does not: the payload runs when the phone is started with the recovery keys. That is the initial proof-of-execution sub-milestone of method A. It is **not** a normal power-on boot of Revival OS, which stays open as its own milestone, and it does not close Phase 2 as a whole.

## Labels

The labels are the ones the research documents use ([gt-i9195.md](../hardware/gt-i9195.md), [boot-payload-research.md](boot-payload-research.md)).

| Label | Meaning |
| --- | --- |
| **Source** | Stated in a cited file and line, or in the output of the installed tool. |
| **Recorded** | Recorded in this repository's Phase 0 evidence; the file is cited. |
| **Community** | Reported by a project's wiki or by users. Not authoritative for this phone. |
| **Inference** | Our conclusion from the sources. No source states it. |
| **Unknown** | Not known for this phone or this build. The entry says what resolves it. |
| **Open** | An entry condition or decision not yet met. The entry says who closes it. |

Raw values from the phone stay in the private evidence directories: `$EV0` for Phase 0 (checklist step A2) and `$EV2` for Phase 2 (section 11). Neither is in any repository (rule 7). The redacted Phase 0 record in this repository is cited instead wherever it holds the value.

## Decisions this plan carries

The 2026-11-11 decisions were recorded by the former orchestrator in the [PR #12 comment of 2026-11-11](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441) ("the 2026-11-11 decisions", items 1–6 and the v2 points). They stand. The 2026-11-14 decisions are the reviewer's. The owner approves the finished plan.

| Decision | Source | Where applied |
| --- | --- | --- |
| Order (b): invalid image first, then the payload | 2026-11-11 decisions, item 1 | Sections 1, 4, 5 |
| A silent screen stays ambiguous; two silent screens cannot establish acceptance or rejection; a running payload from the invalid image is a result, not rejection evidence | 2026-11-11 decisions, item 1 | Sections 5, 6, 7 |
| Rule 4 needs an explicit reviewed amendment; the Knox bit may change at the transfer or at an attempted boot | 2026-11-11 decisions, item 2 | Sections 2 (E-15), 10 |
| W3 at most once, on evidence that the payload was replaced; at most four host writes; no retry or extra write implied | 2026-11-11 decisions, item 3 | Sections 1, 4 |
| Eight rows may pass the initial proof-of-execution sub-milestone in 5 of 5, on stated conditions | 2026-11-11 decisions, item 4 | Section 6 |
| Filming windows; reset and latency are observations | 2026-11-11 decisions, item 5 | Sections 4, 6, 8 |
| Phase 1 passed within its host/QEMU scope | 2026-11-11 decisions, item 6 | Section 2 (E-2) |
| `BOOT` is outside this plan, not forbidden under any plan; D4 must not equate a host timeout with a stopped write | 2026-11-11 decisions, v2 points | Sections 1, 4 |
| Trials after an Android start caused by a self-reset end before the reset time seen | Reviewer decision, 2026-11-14 (p) | Section 4 |
| Any Android start restarts the count | Reviewer decision, 2026-11-14 (q) | Section 4 |
| Transfer-failure procedure | Reviewer decision, 2026-11-14 (r) | Section 4 |
| Rescue check between the two images | Reviewer decision, 2026-11-14 (s) | Sections 4, 9 |
| No rehearsal write before W1 | Reviewer decision, 2026-11-14 (t) | Sections 1, 2 (E-17) |
| Roles and proof of the owner's acceptance; E-15 stays open | Reviewer decision, 2026-11-14 (u) | Sections 2, 10 |
| Fresh clone without LFS download; no hosted run | Reviewer decision, 2026-11-14 (v) | Sections 3, 12 |
| PRs #10, #11 and #14 merged; E-11 names the commit on `main` once the plan is final | Reviewer decision, 2026-11-14 (w) | Sections 1, 2 (E-11) |
| Reset loop: a second self-reset in one window ends the trial and the series | Reviewer decision, 2026-11-14 (v3 review) | Section 4 |
| Stop rule A5: a second unplanned Android start during the payload's trials ends the series | Reviewer decision, 2026-11-14 (v3 review) | Section 4 |
| The 30-minute bound of the transfer-failure procedure (F-5) | Reviewer decision, 2026-11-14 (v3 review) | Section 4 |
| The 10-second key hold that defines the key-release event (T2) | Reviewer decision, 2026-11-14 (v3 review) | Section 4 |
| Two minutes at the lock screen before powering off, so the restore can finish (S2, A1) | Reviewer decision, 2026-11-14 (v3 review) | Section 4 |

## Two facts that change the procedure

### Stock Android rewrites the recovery partition at every start

| Point | Finding | Label and evidence |
| --- | --- | --- |
| The mechanism in AOSP | Android's `init` starts a one-shot service at every boot that runs `/system/etc/install-recovery.sh`. | Source: AOSP `system/core`, tag `android-4.4.2_r1`, [`rootdir/init.rc:513-515`](https://github.com/aosp-mirror/platform_system_core/blob/android-4.4.2_r1/rootdir/init.rc#L513-L515). The same three lines are in tag `android-4.2.2_r1` at `rootdir/init.rc:475-477`. Those are the two Android versions Samsung released for this phone ([gt-i9195.md](../hardware/gt-i9195.md#specifications), Community). |
| What the script does | It checks the SHA-1 of the recovery partition against the stock recovery image. If they differ, it rebuilds the stock recovery from the `boot` partition and the patch `/system/recovery-from-boot.p`, and writes it to the recovery partition. | Source: AOSP `build`, tag `android-4.4.2_r1`, [`tools/releasetools/ota_from_target_files:348-399`](https://github.com/aosp-mirror/platform_build/blob/android-4.4.2_r1/tools/releasetools/ota_from_target_files#L348-L399); the script text is lines 381-387. |
| Samsung phones in general | LineageOS's install instructions for Samsung phones, the ones its data file selects for this model, say: "Be sure to reboot into recovery immediately after installing the custom recovery. If you don't the stock ROM will overwrite the custom recovery with the stock recovery, and you'll need to flash it again." TWRP's page for this model says "many devices will replace your custom recovery automatically during first boot". | Community: LineageOS wiki, [`recovery_install_samloader_rs.md:73`](https://github.com/LineageOS/lineage_wiki/blob/bc00760c9307ebf166ccfbfd933ad957d342067d/_includes/templates/recovery_install_samloader_rs.md#L73), selected by [`serranoltexx.yml:16`](https://github.com/LineageOS/lineage_wiki/blob/8e9d82c86a4913c66419b7e0d1ab42de18652fa5/_data/devices/serranoltexx.yml#L16); [TWRP](https://twrp.me/samsung/samsunggalaxys4minilte.html). |
| This phone's build | **Both files are present:** `/system/etc/install-recovery.sh` (1,665 bytes) and `/system/recovery-from-boot.p` (2,173,989 bytes). The script itself could not be read (`adb pull` was refused with `Permission denied`), so the hashes it checks are not known. | Recorded (E-13): [recovery-restore check](../evidence/phase-0/2026-11-13-linux-retest.md#recovery-restore-check-write-plan-e-13), [output](../evidence/phase-0/2026-11-13-linux/recovery-restore-check.txt). |

**This plan assumes that this phone rewrites `RECOVERY` with stock recovery at every Android start** (Inference from the two files and the AOSP mechanism; E-13). What follows:

1. **Every Android start is treated as replacing the test image with stock recovery,** until a trial shows otherwise. The content of `RECOVERY` after an Android start is not known until it is observed.
2. **Every trial therefore goes from a removed battery straight to the recovery keys.** Android must not start between a write and the last trial of that image, except the plan's own starts: the rescue check (S2), after the invalid image's last trial, and the reboot from the stock recovery menu in A3 that precedes W3.
3. **If Android does start,** section 4 says what to do. Any Android start restarts the count of the payload's trials (reviewer decision, 2026-11-14).
4. **It is the expected rescue route.** One Android start should put stock recovery back with no write from the host. The rescue check between the two images (S2) shows whether it does, before the payload is written (section 9, R3).

### What `--no-reboot` leaves, and how to reach the recovery keys

| Point | Finding | Label and evidence |
| --- | --- | --- |
| What the option does | "`--no-reboot` causes the device to remain in download mode after the action is completed. If you wish to perform another action whilst remaining in download mode, then the following action must specify the `--resume` flag." | Source: the output of `heimdall help` from the installed Heimdall v2.1.0 (Ubuntu package `heimdall-flash` 2.1.0-1build1), under the `flash` action. |
| What is sent to the phone | With `--no-reboot`, Heimdall ends the session and does not send the reboot request. Without it, Heimdall sends the reboot request and the phone restarts, normally into Android. | Source for the original project: Heimdall [`BridgeManager.cpp:558-612`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/BridgeManager.cpp#L558-L612) and [`FlashAction.cpp:458`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/FlashAction.cpp#L458), `:570`. The installed 2.1.0 is a maintained fork whose source could not be fetched, so for 2.1.0 this is an Inference from the identical help text. |
| What the phone shows | "The device will continue to display `Downloading... Do not turn off target!!` even after the process is complete." | Community: LineageOS wiki, [`recovery_install_samloader_rs.md:70`](https://github.com/LineageOS/lineage_wiki/blob/bc00760c9307ebf166ccfbfd933ad957d342067d/_includes/templates/recovery_install_samloader_rs.md#L70). **On this phone:** after the PIT read from the write host with `--no-reboot` (E-17, 2026-11-14), the phone stayed on the Download-mode screen, photographed 10 seconds after Heimdall exited (owner-confirmed, [write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md)). The screen's text was not transcribed. |
| Why the option exists | "It's mostly in place so you can manually boot straight into recovery mode after a flash (rather than booting up normally)." The manual adds: "You can still safely reboot your phone manually (with the power button) after executing `--no-reboot` commands." | Source: Heimdall [`Linux/README:162-164`](https://github.com/Benjamin-Dobell/Heimdall/blob/8709370bc48310604dfd4407538f650b3cc4f0ae/Linux/README#L162-L164), `:217-218`; the installed `heimdall(1)` manual page has the second sentence. |
| How to leave from there | Remove the battery, then hold the recovery keys from power-off. LineageOS gives the same route: "Manually reboot into recovery, this may require pulling the device's battery out and putting it back in". | Recorded: the battery exit from an idle Download mode works 3 of 3 (F6, owner-confirmed, [checklist results](../evidence/phase-0/2026-11-13-linux-retest.md#checklist-results)). Exit after a `--no-reboot` session on the write host: recorded by E-17 on 2026-11-14. After the cable was unplugged and the battery removed, the screen went dark, and the phone recovered and works normally (owner-confirmed, [write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md#steps-e-17)). Community: LineageOS wiki, same file, line 71. Recovery keys: [gt-i9195.md](../hardware/gt-i9195.md#download-mode-and-flashing-tools). |

What follows for the plan:

1. **Every write uses `--no-reboot`.** Without it the phone restarts into Android, which rewrites `RECOVERY` (above).
2. **After the write, the owner waits for Heimdall to exit, waits 10 seconds, photographs the screen, then unplugs the cable and removes the battery.** The battery is never removed while Heimdall is running, and never during the transfer-failure procedure until its step F-6 allows it (section 4).
3. **The power button is not used to leave Download mode.** The manual says it is safe, but a restart by the power button boots normally, which is what the plan avoids.

## 1. What is written

Only `RECOVERY` is written, with these images. The two test images are built at the commit named in the issue (E-11). Their hashes come from a clean export; `make check` checks both (test `payload-frozen` pins `payload.img`; the invalid image is reproducible byte for byte).

| Image | Size | SHA-256 |
| --- | --- | --- |
| `build/boot-serrano/payload.img` | 6,160 bytes | `bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02` |
| `build/boot-serrano/payload-invalid.img` | 6,160 bytes | `34dc91c64811346a3766e71044c2260340fadec0a0ea327e4126a1ef7a584d7b` |
| Stock `recovery.img` of the installed build `I9195XXSCQAN` / `I9195OXXCNK2` (rescue only, W4) | 8,935,696 bytes | `0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6` |

The stock image is Recorded: [firmware evidence](../evidence/phase-0/2026-11-13-firmware-rescue.md) and its [re-verification on Ubuntu](../evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu), where the copy inside Samsung's AP package is byte-identical to the standalone image. **W4 uses the private copy** in `~/revival-firmware/gt-i9195/I9195XXSCQAN_I9195OXXCNK2/recovery.img`, after a hash check (section 3). The Git LFS copy under `firmware/GT-I9195/` is not downloaded again for this plan.

**Merge state.** The payload ([PR #10](https://github.com/revival-systems/revival-os/pull/10)), the trial kit ([PR #11](https://github.com/revival-systems/revival-os/pull/11)) and the Phase 0 evidence ([PR #14](https://github.com/revival-systems/revival-os/pull/14)) are merged into `main` (reviewer decision, 2026-11-14). The two images are unchanged by those merges. Once this plan is final, the issue names the commit on `main` to build from (E-11).

### The partition

| Field | Value | Status |
| --- | --- | --- |
| PIT partition name, as Heimdall takes it | `RECOVERY` | Recorded: [partition map](../evidence/phase-0/2026-11-13-readonly/partition-map.md), from the Windows PIT read (F5). |
| PIT identifier | `14` | Recorded, same file. |
| Size | 20,480 sectors of 512 bytes = 10,485,760 bytes, starting at sector 241,664 | Recorded, same file. Linux agrees: `recovery` is `mmcblk0p14`, 10,240 KiB ([by-name](../evidence/phase-0/2026-11-13-linux/by-name.txt), [partitions](../evidence/phase-0/2026-11-13-linux/partitions.txt)). |
| PIT read from the write host | PIT SHA-256 `1ec0d73501ca5b956b80b85583f9b578ea819e961e8fba3ccc1784b195f51432`, equal to the Windows read | Recorded (E-17), 2026-11-14: `RECOVERY` is identifier 14, 20,480 blocks, from block 241,664 ([write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md)). |

Heimdall refuses a name that is not in the phone's PIT (Source for the original project: [`FlashAction.cpp:220-224`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/FlashAction.cpp#L220-L224); Inference for 2.1.0). Each test image is 6,160 bytes, far below the partition size, so `--skip-size-check` is never used. Whether bytes of `RECOVERY` beyond the image's length are changed by the transfer is **Unknown**; the plan does not depend on it.

### Known differences from the stock images

Read from the headers on the host ([stock images](../evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu); test images from the build). Any of them may be a reason for the bootloader to refuse a test image. **A refusal for one of these reasons looks like any other refusal** in sections 6 and 7; this plan cannot tell them apart.

| Field | Stock `boot.img` / `recovery.img` | `payload.img` / `payload-invalid.img` |
| --- | --- | --- |
| Magic | `ANDROID!` | `ANDROID!` / `INVALID!` |
| After the last page | `SEANDROIDENFORCE`, then 256 non-zero bytes: signature-sized, **not verified** against any key | `SEANDROIDENFORCE` only |
| Ramdisk | at `0x82200000` (gzip, read from the private copy on the host; not in the Phase 0 record) | 1 byte, at `0x81200000` |
| Command line | `console=null androidboot.hardware=qcom user_debug=31` | empty |
| Kernel | 6,699,384 bytes at `0x80208000` | 1,636 bytes at `0x80208000` |
| Tags, second stage, page size | `0x80200100`; none at `0x81100000`; 2,048 bytes | the same |

### The writes

Order (b), decided ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 1).

| # | Image | SHA-256 | Partition | Proposed command (run from the repository root) | Why |
| --- | --- | --- | --- | --- | --- |
| W1 | `payload-invalid.img` | `34dc91c6…4d7b` (full value above) | `RECOVERY` | `heimdall flash --RECOVERY build/boot-serrano/payload-invalid.img --no-reboot` | ROADMAP negative test: a deliberately invalid image shows how the bootloader rejects images (section 7). |
| W2 | `payload.img` | `bde09074…ce02` (full value above) | `RECOVERY` | `heimdall flash --RECOVERY build/boot-serrano/payload.img --no-reboot` | The proof of execution: five trials of the same image (section 6). Written only after the rescue check (S2). |
| W3 | `payload.img` again | as W2 | `RECOVERY` | as W2 | **Conditional, at most once.** Only on evidence that the payload was **replaced**: after an Android start, the check trial shows the stock recovery menu (section 4, A3). Android merely starting is not enough. |
| W4 | Stock `recovery.img` | `0e309559…79c6` (full value above) | `RECOVERY` | `heimdall flash --RECOVERY ~/revival-firmware/gt-i9195/I9195XXSCQAN_I9195OXXCNK2/recovery.img --no-reboot` | **Conditional, rescue only, at most once.** Only if required for recovery (section 9). Not a routine step. |

Rules for every row:

- One partition argument per command, and no other option: no `--repartition`, no `--pit`, no `--skip-size-check`, no `--tflash`, no partition identifier in place of the name.
- `--resume` is added only if an earlier Heimdall command in the same Download-mode session used `--no-reboot`. The procedure in section 4 has no such command before a write, so no write uses it.
- A write that fails or is interrupted is **not repeated** under this plan. Follow the transfer-failure procedure (section 4) and report (rule 8).
- **No rehearsal write before W1** (reviewer decision, 2026-11-14). The PIT read from the write host (E-17) already exercises the Heimdall session and the `--no-reboot` exit without writing, and writing the same stock bytes back could not show that they landed.

**Maximum number of host writes this plan asks approval for: four**, all to `RECOVERY`: W1 and W2 planned, W3 and W4 conditional ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 3). No retry or extra write is implied. One write more than that, or a write of anything else, needs a new approval.

**Outside this plan:** `BOOT` (a normal power-on increment needs its own separately approved plan), `system`, `userdata`, `cache` and every other partition. **Never written, under any plan** (rule 2): the bootloader chain (`sbl1`, `sbl2`, `sbl3`, `aboot`, `rpm`, `tz` and any other boot-firmware partition), `efs`, `persist` and `modem` ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), v2 points).

## 2. Entry conditions

Every box is ticked in the issue, with its evidence, before the first write. A box ticked here is backed by the cited evidence; the issue re-checks it. No identifier is copied into the issue or the repository.

### ROADMAP Phase 2 entry gate

- [x] **E-1. Phase 0 has passed, with the stock `boot` and `recovery` images for the installed build verified and Download mode shown to be reliable.**
  Evidence: [Phase 0 addendum, decision](../evidence/phase-0/2026-11-13-linux-retest.md#decision): PASS, owner-directed, 2026-11-13, merged in PR #14. Images: [firmware evidence](../evidence/phase-0/2026-11-13-firmware-rescue.md) and [re-verification](../evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu). Download mode: F1 and F6 3 of 3 (owner-confirmed), F4 `Device detected` on this host (measured) ([checklist results](../evidence/phase-0/2026-11-13-linux-retest.md#checklist-results)). **Rescue execution remains untested.**
- [x] **E-2. Phase 1 has passed, within its host/QEMU scope.**
  Evidence: the former orchestrator's acceptance ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 6), copied here: Phase 1 PASSED within its host/QEMU scope, on the merged Rust foundation PR #5 at `3f1130a1a8ecc6796440402be572855a4990de97`, its [successful manual CI run](https://github.com/revival-systems/revival-os/actions/runs/42757111224) (the former orchestrator verified that its `make check` step succeeded and that its exact head is an ancestor of the reviewed trial-kit head), and the working notes in [`docs/phase-1/rust-foundation.md`](../phase-1/rust-foundation.md). The full local suite passed 61 PASS / 0 FAIL on the trial-kit tree, and the heartbeat ran 20 of 20: every run exited 0 and contained both the heartbeat and checksum `0x22becba4`; heartbeat SHA-256 `7ac79ff8bde24a58f1afb0d0808eca0036d61f53dd4756daec67b3852f5d946d`. Recorded in the [Phase 1 gate review](../evidence/phase-1/2026-11-13-gate-review.md#gate-by-gate-result). No new hosted CI run was started for it. **It is not Phase 0 or Samsung evidence.** The issue adds the final source revision (E-11).
- [ ] **E-3. A write-plan issue names the method, partition, image hash and recovery steps.**
  Closed by: the implementer opens it when the reviewer's task says so.
  Evidence: the issue itself, made from this draft with every Open entry closed or explicitly accepted.
- [ ] **E-4. The owner has explicitly accepted that flashing a non-Samsung image is reported to trip the irreversible Knox warranty bit.**
  Closed by: the owner.
  Evidence: **the owner's own statement, in the owner's words, quoted in the issue with its date** (section 10). Every agent posts through the owner's GitHub account, so a comment alone is not proof of who wrote it (reviewer decision, 2026-11-14).
- [ ] **E-5. The reviewer has approved the plan, and the owner has approved the finished plan.**
  Closed by: the reviewer, then the owner.
  Evidence: both approvals quoted in the issue, after E-4.

### Open blockers from the research

The numbers are those of the research's [list](boot-payload-research.md#blockers-before-any-write).

- [x] **Blocker 1. Phase 0 passed, with its evidence reviewed.** The same condition as E-1.
- [x] **E-6 (blocker 2). The installed build is recorded: bootloader version, build, baseband, CSC (C5, F2).**
  Evidence: bootloader and baseband `I9195XXSCQAN`, build `KOT49H.I9195XXSCQAN`, CSC `ROM`, installed CSC `I9195OXXCNK2` ([properties](../evidence/phase-0/2026-11-13-linux/selected-properties.txt), [About device photograph](../evidence/phase-0/2026-11-13-linux-retest.md#about-device-c1)).
- [x] **E-7 (blocker 3). The Download-mode status lines are photographed and transcribed: Knox warranty bit, secure boot, reactivation lock, write protection (F2).**
  Evidence: [Download mode (F2)](../evidence/phase-0/2026-11-13-linux-retest.md#download-mode-f2): `KNOX WARRANTY VOID: 0x0`, `WRITE PROTECTION: Enable`; no reactivation-lock line is shown. No Download-mode line names secure boot: `CSB-CONFIG-LSB: 0x30` is recorded and its meaning is not established; "Secure boot status: Type: Samsung" is from About device (C1). These lines are the "before" state (section 10).
- [x] **E-8 (blocker 4). Download mode is shown reliable (F1 3 of 3, F6 3 of 3), Heimdall detects the phone (F4), and the PIT lists the boot and recovery partitions with sizes (F5).**
  Evidence: F1 and F6 owner-confirmed 3 of 3; F4 measured on this host ([output](../evidence/phase-0/2026-11-13-linux/download-mode-usb-detect.txt)); F5 from the Windows PIT read ([partition map](../evidence/phase-0/2026-11-13-readonly/partition-map.md)). The PIT read from the write host is E-17.
- [x] **E-9 (blocker 5). Verified stock `boot` and `recovery` images for the installed build are held in a private copy outside the repository (G1–G4).** By the owner's exception they are also in Git LFS ([AGENTS.md](../../AGENTS.md#hardware-safety-contract), rule 7).
  Evidence: `boot.img`, 7,754,000 bytes, SHA-256 `6918d25bfa63bd977279c3b064b74a5905f35a3d633173019f063c37e028cfe0`, and `recovery.img`, 8,935,696 bytes, SHA-256 `0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6`, checked again on this host from the private copy ([re-verification](../evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu)). Signing-chain verification was not done. **Rescue execution (W4) remains untested.**
- [ ] **Blocker 6. The owner's Knox acceptance.** The same condition as E-4.
- [ ] **E-10 (blocker 11). The five phone-only questions are accepted as open, with the expected observation and the recovery action for each outcome.**
  Closed by: the reviewer, then the owner.
  Evidence: their approval of sections 6, 7, 8 and 9 of the issue.
- [ ] **Blocker 12. The approved write-plan issue.** The same condition as E-3 and E-5.

Blockers 7 to 10 are not open: 7 is decided (method A), 8 and 9 are the reviewed payload, and 10's image is built; its recovery steps are sections 4 and 9 of this plan.

### Conditions this draft adds

- [ ] **E-11. The issue names the commit on `main` to build from.** PRs #10, #11 and #14 are merged.
  Closed by: the reviewer, once this plan is final.
  Evidence: the commit SHA in the issue. `make check` on it prints `PASS payload-frozen` with the hashes in section 1.
- [x] **E-12. The recovery keys reach stock recovery 3 of 3 (E1), and the battery exit from Download mode works 3 of 3 (F6).**
  Evidence: owner-confirmed 3 of 3 each, with the stock recovery menu photographed ([stock recovery](../evidence/phase-0/2026-11-13-linux-retest.md#stock-recovery-e1), [checklist results](../evidence/phase-0/2026-11-13-linux-retest.md#checklist-results)).
- [x] **E-13. The recovery-restore check has been run and recorded.**
  Evidence: both files present ([recovery-restore check](../evidence/phase-0/2026-11-13-linux-retest.md#recovery-restore-check-write-plan-e-13)). The plan is written for a phone that rewrites `RECOVERY` at every Android start.
- [x] **E-14. The order of the two images and the maximum number of writes are decided.**
  Evidence: order (b), invalid image first; at most four host writes ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), items 1 and 3).
- [ ] **E-15. Rule 4 is amended by a reviewed change.**
  Closed by: a later reviewed change to [AGENTS.md](../../AGENTS.md#hardware-safety-contract) rule 4, made **after** the owner's statement for E-4. **It is not made in this pull request.** Until it is effective, rule 4's current wording binds ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 2; reviewer decision, 2026-11-14).
- [x] **E-16. The write host is the Ubuntu development host used for the 2026-11-13 Phase 0 re-test, with the cable and USB port used for E-17, and `heimdall version` prints `v2.1.0`.** Whether Heimdall needs `sudo` for USB access is recorded in E-17; the writes use the same form.
  Closed by: the owner.
  Evidence: [write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md#host-cable-and-port-e-16), 2026-11-14. The host is the one of the 2026-11-13 re-test. The cable is the same as on 2026-11-13, in the left front USB port (owner-confirmed). `heimdall version` prints `v2.1.0`, and `make doctor` exits 0 (measured). Heimdall needs no `sudo`, so the writes run without it.
- [x] **E-17. The PIT has been read from the write host.** Read-only, with the owner at the phone in Download mode:

  ```sh
  heimdall download-pit --output "$EV0/private/pit-linux.bin" --no-reboot
  sha256sum "$EV0/private/pit-linux.bin"       # expected 1ec0d73501ca5b956b80b85583f9b578ea819e961e8fba3ccc1784b195f51432
  heimdall print-pit --file "$EV0/private/pit-linux.bin"
  ```

  After Heimdall exits, the owner waits 10 seconds, photographs the screen, then unplugs the cable and removes the battery.
  Closed by: the owner performs it; the implementer records it.
  Evidence: the hash equals the Windows PIT; the `RECOVERY` entry reads identifier 14, 20,480 blocks; Heimdall's complete output, whose lines become step D4's expected lines; the photograph, which answers what the phone shows after `--no-reboot` on this host. The PIT file and the photograph stay outside Git. Any line starting `ERROR` stops it.
  **Recorded 2026-11-14** ([write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md)):
  - Heimdall exited 0, with no `ERROR` or `WARNING` line.
  - The hash equals the Windows PIT, and `RECOVERY` reads identifier 14, 20,480 blocks (measured).
  - Heimdall's session lines are recorded there for D4.
  - The phone stayed on the Download-mode screen, and the photograph was taken (owner-confirmed).
  - After the battery exit, the screen went dark and the phone recovered (owner-confirmed).

## 3. Host and tools

| Item | Value |
| --- | --- |
| Host | The Ubuntu development machine used for the 2026-11-13 Phase 0 re-test ([DEVELOPMENT.md](../DEVELOPMENT.md#one-time-setup)). No other computer, no virtual machine, no USB hub. |
| Heimdall | `v2.1.0` as printed by `heimdall version`: Ubuntu package `heimdall-flash` 2.1.0-1build1. A different version stops the plan until the issue is updated. |
| Other flashing tools | None. No Odin, no fastboot, no lk2nd. |
| Repository | A fresh clone of the commit named in the issue (E-11), made in a shell with `GIT_LFS_SKIP_SMUDGE=1` exported, so that neither the clone nor the checkout downloads the firmware again, with nothing else in it (reviewer decision, 2026-11-14). |
| Stock image | The private copy named in section 1. |
| Row decoder | [tools/read_rows.py](../../tools/read_rows.py) at that commit ([Trial kit](boot-payload-research.md#row-reading-tool)). |
| Camera | A second device that records video with sound and takes sharp still photographs. Its clock is set to the host's. |
| Hosted CI | None. No hosted run is part of this plan (reviewer decision, 2026-11-14). |

**How the images' hashes are checked immediately before a write.** On the day, in the fresh clone, with the phone not yet connected:

```sh
# Host only. Nothing here contacts the phone.
export GIT_LFS_SKIP_SMUDGE=1   # for the clone and the checkout: the firmware is not downloaded
git clone https://github.com/revival-systems/revival-os.git && cd revival-os
git checkout <commit named in the approved issue>
git status --short        # must print nothing
make check                # must exit 0 and print: PASS payload-frozen (payload.bin 8ee519ae…, payload.img bde09074…)
make payload-invalid      # prints the line that starts INVALID-MAGIC-NEGATIVE-TEST
sha256sum build/boot-serrano/payload.img build/boot-serrano/payload-invalid.img
sha256sum ~/revival-firmware/gt-i9195/I9195XXSCQAN_I9195OXXCNK2/recovery.img
```

- At the reviewed commit `make check` prints 61 PASS lines and no FAIL line.
- The three `sha256sum` lines must equal the three values in section 1, compared character by character against the issue, not against this draft.
- Nothing is rebuilt between this check and the write. If `make` is run again for any reason, the check is run again.

**Stop** if the commit, the tree, any test or any hash differs. A different hash means a different image, which this plan does not cover.

## 4. Procedure for the owner

The owner performs every physical step (rule 6). An agent may prepare the commands and read the results; it does not run a write. **Stop** means: do nothing further to the phone except what the step says, remove the battery if the step says so, and report in the issue (rule 8). A stopped step is not retried until the owner and the reviewer have answered.

**Precedence.** The safety stops (heat, smell, swelling, an unexpected screen or prompt) and the unexpected-outcome stops come first. They override every filming time and every count below.

### Preflight

Before the phone is touched.

| Step | Action | Stop if |
| --- | --- | --- |
| P1 | Confirm every box in section 2 is ticked in the issue, and the issue carries the owner's E-4 statement and both approvals (E-5). | Any box is open. |
| P2 | Inspect and charge the battery as in checklist B2 and B3: not swollen, at least 60 %. Use the cable and USB port of E-17. | The battery is swollen, hot or below 60 %. |
| P3 | Create the Phase 2 evidence directory and start the session log (section 11). Record the date, the time and who performs the steps. | — |
| P4 | Run the hash check in section 3. Save its output. | Section 3's stop conditions. |
| P5 | Check that the camera works and that its clock matches the host's. | — |

### Writing an image

For W1 and W2, and for W3 or W4 if their condition applies.

| Step | Action | Expected | Stop if |
| --- | --- | --- | --- |
| D0 | Start the video recording if it is not running, with the phone's screen in frame. Say the date, the time, the write number (W1–W4), the image name and the first eight characters of its hash. Keep recording until D6. | — | — |
| D1 | Power the phone off. Hold Volume Down + Home + Power until the warning screen appears, then release. Press Volume Up to continue. | The warning screen, then the download screen. | Any other screen appears, or the warning does not appear in two attempts. |
| D2 | Photograph the status lines at the top left and transcribe them. Before W1 this is the "before" photograph (section 10). | Before W1: exactly the lines recorded in F2 (section 10). Before a later write: record what is shown. | Before W1, a line differs from F2. At any write, a reactivation-lock line appears that reads on. |
| D3 | Connect the cable. Run `lsusb \| grep -i 04e8`, then `heimdall detect`. | `04e8:685d` and `Device detected`, as recorded on this host ([output](../evidence/phase-0/2026-11-13-linux/download-mode-usb-detect.txt)). | No device, a different ID, or any error. |
| D4 | Read the proposed command for this write aloud from the **issue**, compare the file name and the partition name with section 1, then run it. Do not touch the phone, the cable or the battery while it runs. | The session lines recorded by E-17 on this host, including any `WARNING` lines seen there; then the upload messages for this one partition, `Uploading RECOVERY` and `RECOVERY upload successful`; then `Ending session...`, with no `Rebooting device...` line after it. Save the complete output. | Any line starts `ERROR`; Heimdall asks any question or names any other partition; it exits with a non-zero status or without the line `RECOVERY upload successful`; or it is still running once its output has stopped (a 6,160-byte write normally takes seconds). In each case **do not press Ctrl-C and do not touch the phone: follow the transfer-failure procedure below**, which waits up to 10 minutes from the command's start. Never repeat the command. |
| D5 | Wait until the shell prompt has returned. Wait 10 more seconds without touching the phone or the cable, then photograph the phone's screen. | What E-17's photograph showed after `--no-reboot`. | The phone restarts by itself. If Android then appears: "If Android starts", A1–A2, then stop and report. Run no trial and no S2 until the owner and the reviewer have answered. |
| D6 | Only after the photograph: unplug the cable, remove the battery and wait 10 seconds. | The screen goes dark. | — |

The upload and end-of-session messages named in D4 are the original project's (Source: [`FlashAction.cpp:255-260`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/FlashAction.cpp#L255-L260), `BridgeManager.cpp:560` and `:586`); E-17 recorded the installed 2.1.0's session lines on this host, with no `WARNING` line ([write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md#heimdall-210-session-lines-on-this-host)). The upload lines are not part of a PIT read, so for 2.1.0 their wording stays an Inference. A line that is none of the expected ones and does not start `ERROR` is recorded and reported; the write is not repeated because of it.

### Transfer failure

Reviewer decision, 2026-11-14. A timeout or Ctrl-C on the host does not show that the phone stopped writing.

| Step | Action |
| --- | --- |
| F-1 | Keep filming the phone. Wait up to 10 minutes from the start of the command, touching nothing. |
| F-2 | If Heimdall ends within that time, act on its output. A successful end (exit status 0, the line `RECOVERY upload successful`, and no `ERROR` line) continues with D5; any other end continues with F-4. |
| F-3 | If Heimdall has not ended after 10 minutes, stop the host process and save its complete output. |
| F-4 | Photograph the phone's screen. |
| F-5 | Leave the phone and the cable untouched until two photographs taken 5 minutes apart are identical. If they still differ after 30 minutes (the 30-minute bound: reviewer decision, 2026-11-14), keep leaving it untouched and report; wait for the reviewer. |
| F-6 | Only then unplug the cable and remove the battery. |
| F-7 | The content of `RECOVERY` is now unknown. Run no trial and repeat no write. Stop and report. |

Heat, smell or swelling overrides F-1 to F-5: unplug and remove the battery at once, and record that it was done during a possible transfer.

### One trial

Repeated; the steps are the same for both images.

| Step | Action | Expected | Stop if |
| --- | --- | --- | --- |
| T1 | Leave the cable unplugged. Start the video recording and say the trial number and the time. The whole screen is in frame. | — | — |
| T2 | Insert the battery. Hold **Volume Up + Home + Power**, as in checklist E1. When the Samsung logo appears, release Power only and keep holding the other two until the screen changes, or for 10 seconds after releasing Power if it does not change, whichever comes first (the 10-second hold: reviewer decision, 2026-11-14); then release them. That release is the **key-release event**, read from the video. | The image in `RECOVERY` starts. Sections 6 and 7 list what may appear. | Android's boot animation appears: go to "If Android starts". |
| T3 | Keep filming without touching the phone, for the trial's window ("How long to film"). | A picture that does not change, or one of the other outcomes in sections 6 and 7. | The phone becomes hot, or smells: remove the battery at once. |
| T4 | While filming continues, take a sharp still photograph of the whole screen, square on, with no reflection across the rows. | Every cell of every row is countable in the photograph. | — |
| T5 | End the trial at the end of its window: remove the battery. Say the time. Wait 10 seconds. Stop the recording. | The screen goes dark. | The screen stays lit with the battery out. |
| T6 | Type the rows from the photograph into `tools/read_rows.py` with the fill colour seen, compare its echo of the cells with the photograph, and save its output and its PNG. A screen that is not a fill with eight or nine rows is described in words and not typed. | The record's first line reads `Checksum row OK`. | It reads `ROWS MISREAD`: read the photograph again; do not go on to the next trial until the rows are read or declared unreadable. |
| T7 | Fill in the trial's line of the evidence table (section 11). | — | The outcome is not in section 6 or 7. |

### How long to film

[2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 5, with one exception (reviewer decision, 2026-11-14).

| Trial | Window | Measured from |
| --- | --- | --- |
| The first trial of each image | 10 minutes | The picture appearing |
| Later trials of that image | `max(2 minutes, first-trial reset interval + 30 seconds)`; 2 minutes if the first trial showed no reset | The picture appearing |
| A trial with no visible picture | 10 minutes | The key-release event (T2) |
| **Exception:** every later trial of the same image, after a self-reset of that image that started Android | Ends **before** the reset time seen: the battery is out at least 10 seconds before it, after the still photograph (T4) | The picture appearing |

Rules for every window:

- **One fixed window per trial.** A reset does not restart it. The trial ends at the window's end, whatever happened inside it.
- **The first self-reset:** keep filming and touch no key. What the phone starts next is part of the result (section 6).
- **Reset loop** (reviewer decision, 2026-11-14): a second self-reset in one window ends the trial and the series. If the phone resets by itself a second time within one window, remove the battery at once (unless Android's boot animation is showing, below), record a reset loop with each reset's time, and stop the series after this trial.
- **Android ends the window.** If Android's boot animation appears at any point in a window, after a reset or otherwise, the window and the reset-loop rule no longer apply. Do not remove the battery: follow "If Android starts" from A1. A second reset that started Android is recorded as a reset loop after A2, and it too ends the series.
- **The exception** replaces the formula only for the image whose self-reset started Android, including after W3 for `payload.img`. A reset seen with `payload-invalid.img` does not shorten any `payload.img` window. The reset time and what started next are recorded from the trial that showed them; they are not measured again. If the reset comes too soon to photograph the screen and remove the battery, stop and report.
- **Observations only.** A reset and its latency are recorded as observations. Timing alone does not prove that a watchdog caused a reset, and no reset in ten minutes does not prove that the watchdog is off. The reference timeouts in the research, 0.39 and 48 seconds ([section 4](boot-payload-research.md#4-watchdog)), are not known to apply.

### The series

| Step | Action | Stop if |
| --- | --- | --- |
| S1 | **W1, then `payload-invalid.img`:** up to 3 trials. One trial is enough if it ends in Android starting, because `RECOVERY` is then assumed rewritten with stock recovery (E-13), which S2 checks. | The trials' results differ from each other. |
| S2 | **Rescue check** (reviewer decision, 2026-11-14), required before W2. Insert the battery and power on normally. Let Android start once and reach the lock screen, accepting no prompt; it should rewrite `RECOVERY`. Once the lock screen shows, wait two minutes, touching nothing, so that the restore has time to finish (reviewer decision, 2026-11-14). Then power off from Android's menu, remove the battery and wait 10 seconds. With the camera recording, insert the battery and hold the recovery keys as in T2. The stock recovery menu proves the restore route with no host write: photograph it, select **reboot system now** and nothing else, let Android start, and power off from its menu. Only then go on to W2. | The stock recovery menu does not appear. Stop and report. |
| S3 | **W2, then `payload.img`:** 5 trials, each started from a removed battery (T1–T7), with no Android start and no Download-mode entry between them. The pass criterion is in section 6. | Two trials differ: record both, stop, report. A failed trial is recorded, not repeated or replaced. |
| S4 | After the last trial: enter Download mode (D1), photograph and transcribe the status lines (D2), run `heimdall detect` (D3), and leave by removing the battery (D6). | Download mode cannot be reached: section 9. |
| S5 | Write nothing more. `RECOVERY` is left holding `payload.img`; a stock image is not restored unless section 9 requires it. | — |

The Download-mode entry for W2 (D1–D3) also shows that Download mode is still reachable after the invalid image and the rescue check.

### If Android starts

At any point after W1, outside the rescue check (S2), before the last trial. Any Android start restarts the count of the payload's trials, even if the payload survives (reviewer decision, 2026-11-14).

| Step | Action | Why, and what follows |
| --- | --- | --- |
| A1 | Do not remove the battery. Let Android reach the lock screen, then wait two more minutes, touching nothing (reviewer decision, 2026-11-14). Accept no prompt in Android: no update, no setup. Keep filming and note the time the lock screen appeared. | Android is assumed to be rewriting `RECOVERY` at that moment (E-13). The two minutes give the restore time to finish; interrupting it would leave the partition half written. |
| A2 | Power off from Android's own power menu, and do nothing else in Android. Remove the battery and wait 10 seconds. Record that Android started, and what led to it: the keys, a restart after the write, a self-reset during a trial, or a rejected image. | The content of `RECOVERY` is now not known. |
| A3 | Run one **check trial** (T1–T7). If Android was started by a self-reset, end it before the reset time seen ("How long to film"). | **The payload appears:** it survived. This check trial is **trial 1 of a new series**; earlier trials are recorded, not counted. **The stock recovery menu appears:** if at least one trial since the last write showed the payload before this Android start, the payload was replaced: select **reboot system now** and nothing else, let Android start, power off from its menu, then A4. If no trial since the last write had shown the payload, this is not evidence of replacement: stop and report; no W3. **Any other screen:** end the trial as its section 6 row says, record it, then stop and report; `RECOVERY`'s content is not established, and W3 is not allowed on it. **During the invalid image's trials:** the check trial is not needed; go to S2. |
| A4 | Only for `payload.img`, and only on the evidence in A3 that it was replaced (the payload was seen running after the last write, and then replaced): W3, once. The series then restarts with five trials, each from a removed battery. | No other reason allows W3. |
| A5 | **Stop rule** (reviewer decision, 2026-11-14). A second unplanned Android start during the payload's trials, counted from W2, ends the series: stop and report. The plan's own Android starts (S2, and every "reboot system now" from the stock recovery menu) are not counted. | The write budget stays at four; a phone that keeps starting Android is a result to report, not a reason for more writes. |

## 5. Order of the two images

**Decided: (b), invalid image first** ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 1; E-14). Both columns are kept as the record of the choice. The cost is explicit: the first write ever made to this phone is the image built to be refused, so every entry condition must already be met; the order waives none of them.

| | (a) Payload first | (b) Invalid image first: **decided** |
| --- | --- | --- |
| Sequence | Write `payload.img`; 5 trials. Write `payload-invalid.img`; up to 3 trials. Write a known-good image again (`payload.img`), so that the payload can be shown to restart after the negative test and `RECOVERY` does not end holding an image built to be rejected. | Write `payload-invalid.img`; up to 3 trials. Rescue check. Write `payload.img`; 5 trials. |
| Planned writes | 3 | 2 |
| Maximum with the conditional rows (one repeat, one rescue) | 5 | 4 |
| The first write ever made to this phone | The image whose layout copies lk2nd's, which the bootloader is reported to accept. | The image built to be refused. How the bootloader refuses, and what state that leaves, is Unknown. |
| If the payload shows nothing (logo or black screen) | Read before any refusal has been seen. | Read after the invalid image's result. It stays ambiguous either way. |
| If the invalid image shows nothing | Read after the payload's result. | Read before the payload's result. It stays ambiguous either way. |
| ROADMAP, after each test: "show that the payload can be restarted" | After the negative test the payload is no longer in `RECOVERY`. Showing that it restarts needs the third write. | Met without an extra write: the payload is written after the negative test, and its five trials are the restarts. |
| State at the end | `RECOVERY` holds `payload.img`, after one more write. | `RECOVERY` holds `payload.img`. |

**Silent screens.** A silent screen (the Samsung logo or black, unchanging) is ambiguous in either order. Two silent screens cannot establish acceptance or rejection, and comparing the two images' screens does not resolve it. A running payload from the invalid image is a result, not evidence of rejection ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 1).

## 6. Outcomes for `payload.img`

Every outcome is recorded with the video, the still photograph and the times. "Rows" are typed into `tools/read_rows.py`, whose record states what each row means ([Trial kit](boot-payload-research.md#row-reading-tool)). Small text that the bootloader adds at the top of the screen, such as a `Set Warranty Bit` line, is transcribed exactly; if it covers a row, that row is recorded as unreadable and not guessed.

| On screen | What it means | What to record | What to do next |
| --- | --- | --- | --- |
| **Green fill, nine rows** | The payload ran. The panel is scanning out of `0x88300000`. Green does not show the byte order. | The nine rows; the tool's record; whether row 9 (the display register) names the same address. | Continue the series. |
| **Red or blue fill, nine rows** | The payload ran. The panel is scanning out of `0x88100000`. Red: byte 0 is red. Blue: byte 0 is blue, the order the research expects. | As above. | Continue the series. |
| **Grey fill, nine rows** | The payload ran. The panel is scanning out of the address in row 9, which is neither candidate; the payload found it in the display register and painted it. | As above. The tool reports a contradiction if row 9 is not an address the payload paints grey. | Continue the series. |
| **Green, red or blue fill, eight rows** | The payload ran and painted, and the display-register read then failed or did not return: rows 1–8 are drawn before that read, row 9 only after it returns. This does not show a successful read, a normal completion or a measured exception mode. | The eight rows; the tool's record for an eight-row input; the missing ninth row recorded as **a failed or non-returning display-register read**. | Continue the series; the result must be the same in every trial. |
| **Grey fill, eight rows** | Not a valid picture of this payload: grey is painted only after the register read that row 9 records. | The photograph and the rows. | Stop after this trial and report. It does not qualify for the pass. |
| **A fill with no rows, or with fewer than eight** | The payload ran and filled the screen, then stopped before or while drawing the rows. With no rows, the guarded read at `r2` is the step between the fill and the rows. | The photograph, the number of complete rows, and their cells if readable. The tool is not used. | Stop after this trial and report. |
| **A partial fill, bands, a sheared picture, or colours other than the four** | The payload ran and wrote to memory the panel is showing, and the panel's geometry or pixel format is not the one assumed (540×960, 3 bytes per pixel, stride 1620). | The photograph and a description. The rows are not typed. | Stop after this trial and report. The picture is the evidence for the next payload revision. |
| **The Samsung logo, or a black screen, that never changes** | Not decided by this screen. Either the bootloader did not start the image (for example for one of the [known differences](#known-differences-from-the-stock-images)), or the payload ran and nothing it wrote is being shown, or it hung before painting. Comparing it with the invalid image's screen does not decide it ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 1). | The screen, for the full window; whether and when it resets; any small text. If the image was accepted, this is the ROADMAP's fail criterion "no observable output after the image is accepted"; this plan cannot show whether it was. | End the trial by removing the battery. Run one more trial; if it is the same, stop and report. |
| **The stock recovery menu** | `RECOVERY` does not hold the payload. After an Android start (A3): Android replaced it. With no Android start since the last write: the write did not take effect. | The menu's header text, as in checklist E1. | **In A3's check trial, after an Android start:** follow A3 (it decides whether A4 applies). **In any other trial:** select **reboot system now** only, let Android start, power off from its menu, then stop and report. This is not evidence for W3. |
| **Android starts** | The recovery keys were not taken, or the bootloader passed over `RECOVERY` and loaded `BOOT`. | The time, and how the keys were held. | "If Android starts", from A1. |
| **The phone resets by itself** | A reset, observed. Its latency from the picture is recorded; timing alone does not show that a watchdog caused it. This observation is the ROADMAP's watchdog record. | That time, from the video, and what starts next without any key held: the payload again, Android, Download mode, or another screen. | The payload again: the window keeps running; a second reset in the window is a reset loop ("How long to film"). Android: "If Android starts"; from then on every trial ends before the reset time seen. Anything else: remove the battery, stop, report. |
| **Download mode, or an error screen with text** | The bootloader refused `payload.img`, or failed to start it. Not expected: images with this layout are reported to be accepted. | Every line of text, transcribed exactly, and a photograph. | Touch no key. Remove the battery. Stop and report; section 9 says what is checked next. |
| **Anything else** | Not foreseen. | The video and a description. | Remove the battery. Stop and report (rule 8). |

**Pass of the initial proof-of-execution sub-milestone:**

1. One of the three nine-row pictures, the same in 5 of 5 trials, with the checksum row equal to `0x22BECBA4` each time; **or**
2. The eight-row picture in 5 of 5 trials, on all of these conditions ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 4):
   - the reviewed valid image (`payload.img`, `bde09074…ce02`);
   - the same candidate fill (green, red or blue) and the same eight-row outcome in every trial;
   - clear photographs;
   - all eight words decoded;
   - the checksum row equal to `0x22BECBA4` each time;
   - no contradictory input.

Grey with eight rows does not qualify. Either way, Download mode and the recovery route must still be shown (S4, section 9), and the other entry and observation requirements still apply. **A pass does not close the normal power-on boot or Phase 2 as a whole.** Everything else is a recorded result that is not a pass.

## 7. Outcomes for `payload-invalid.img`

The image differs from `payload.img` in the magic alone, and its kernel slot is the real payload ([Trial kit](boot-payload-research.md#negative-test-image-blocker-10)). So the trial asks one question: does the bootloader check the magic? Because the image shares the [known differences](#known-differences-from-the-stock-images) from the stock images, a refusal cannot be attributed to the magic alone.

| On screen | What it means | What to record | What to do next |
| --- | --- | --- | --- |
| **An error screen, or Download mode, with text** | The bootloader refuses the image. This is the ROADMAP's record of how it rejects an image. | Every line of text, exactly; how long the screen stays; whether the phone then does anything by itself. | Touch no key. Remove the battery. Continue with S1, then S2. |
| **The normal picture: a fill with rows** | A result: the payload ran from an image with a bad header. It is not evidence of rejection. | The rows, as in section 6. | Continue with S1. Report that the negative test did not produce a rejection; a different invalid field is a new image and a new plan. |
| **The Samsung logo, or a black screen, that never changes** | Ambiguous: a refusal that shows nothing, or an accepted image whose payload shows nothing. It cannot establish acceptance or rejection, and the payload's later screen does not resolve it ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 1). | The screen for the full window; whether and when it resets. | Remove the battery. Continue with S1, then S2. |
| **Android starts** | The bootloader refused the image and loaded `BOOT` in its place, or the keys were not taken. | The time, and how the keys were held. | "If Android starts", A1–A2. One trial is enough for this image (S1); then S2. |
| **The stock recovery menu, with no Android start since W1** | `RECOVERY` does not hold the invalid image: the write did not take effect. | The menu's header text. | Select **reboot system now** only; power off from Android. Stop and report. |
| **The phone resets by itself, repeatedly** | Resets, observed: the bootloader refusing and restarting, or another cause. Timing alone does not tell which. | The interval, from the video, and what starts each time. | Remove the battery (reset loop). Continue with S2. |
| **Anything else** | Not foreseen. | The video and a description. | Remove the battery. Stop and report. |

After this image, **recovery is proven** (ROADMAP) by the rescue check (S2) and by the Download-mode entry for W2 (D1–D3). Only then is `payload.img` written and started.

## 8. The five phone-only questions

The questions are the research's ([list](boot-payload-research.md#questions-only-the-phone-can-answer)). For each: the observation in this plan that answers it, and what stays unanswered.

| # | Question | Answered by | Still unanswered after this plan |
| --- | --- | --- | --- |
| 1 | Does the bootloader accept a kernel without the zImage words, a zero-length ramdisk, or a missing trailer, and what does it show and do when it rejects an image? | Only the magic is varied (section 7). If the invalid image is refused, the refusal screen and what follows it are recorded. | The zImage words, the 1-byte ramdisk and the marker are present in both images, and the stock images' 256-byte signature-sized block is absent from both, so whether each is required is not tested. If the bootloader does not check the magic, its rejection behaviour is not seen at all. |
| 2 | The actual load address and entry state: `r0`–`r2`, mode, interrupt masks, MMU and caches. | Rows 1–6: `r0`, `r1`, `r2`, CPSR, SCTLR and the run-time entry address. Row 7: the first word at `r2` (ATAGS or a device tree). The tool's record sets each against the expectation. | `r3` is captured but not painted. Only the first word at `r2` is read, not the tag list. The second core's state, and whether HYP mode exists, are not shown. |
| 3 | Is the display still scanning out when a non-Samsung image is started from `RECOVERY`, what is the framebuffer address on this unit, and what is the byte order? | Any fill appearing answers the first part. The fill colour gives the address (section 6). Red or blue gives the byte order. Row 9 gives the display register's own value. | The byte order if the fill is green or grey. The stride and size registers are not read. The same questions for an image started from `BOOT` are outside this plan. |
| 4 | Is the watchdog running at handoff, and what is its timeout? | Whether the phone resets by itself within the window, and after how long, recorded as an observation. | Timing alone does not prove that a watchdog caused a reset. No reset in 10 minutes does not prove that the watchdog is off: the watchdog registers are not read, so a stopped watchdog and a longer timeout look the same. |
| 5 | What does a `PS_HOLD` drop or a watchdog bite do in the state the bootloader leaves, and how does the bootloader treat the next boot? | Not answered. This payload triggers no reset. If the phone resets by itself, what starts next is recorded, which is a partial observation. | Everything else. A payload that resets on purpose is a later increment ([section 5](boot-payload-research.md#5-deterministic-halt-and-reset)). |

All five are accepted as open by approving this plan (E-10). No trial is repeated, and no image is changed, to chase an answer.

## 9. Rescue

Rule 1 sets the aim: a safe route for further Revival OS testing. That route is **Download mode on an untouched bootloader chain, with `RECOVERY` writable again**. Restoring Android is not the aim.

| # | Route | Depends on | Use | Label |
| --- | --- | --- | --- | --- |
| R1 | Remove the battery. | Nothing | Ends any hang, loop, error screen or stuck mode. Used to end every trial. Never used while a transfer may be running (section 4, transfer failure). | Recorded: F6 3 of 3, owner-confirmed ([checklist results](../evidence/phase-0/2026-11-13-linux-retest.md#checklist-results)) |
| R2 | Download mode: Volume Down + Home + Power from power-off. | The bootloader chain, which is never written | The anchor for every later write. Checked before W2 (D1–D3) and after the last trial (S4). | Recorded: F1 3 of 3, F4 on this host. Inference: it does not depend on `RECOVERY` or `BOOT` |
| R3 | Normal power-on. | `BOOT`, `system` and the rest, none of which this plan writes | Starts Android from the untouched `BOOT`. Android is expected to rewrite stock recovery into `RECOVERY` with no host write (E-13). **Exercised once on purpose by the rescue check (S2)**, which shows whether the restore happens. Not a pass condition. | Recorded: the restore files are present (E-13). Inference: the rewrite. Shown on this phone by S2 |
| R4 | Write the verified stock `recovery.img` to `RECOVERY` (W4). | R2, Heimdall, and the private copy of the verified image | **Only if required for recovery.** | Recorded: the image ([re-verification](../evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu)). **Rescue execution remains untested** |

**When R4 is "required".** Only in one of these cases, and only after the owner and the reviewer have agreed in the issue that the case applies:

1. With a test image in `RECOVERY`, the phone no longer reaches a state from which testing can continue: for example it shows an error at every power-on, including a normal one, so R3 cannot run.
2. The owner and the reviewer decide that stock recovery must be back before the next increment, and R3 has not restored it.

A test image that hangs, shows nothing, or is refused when started with the recovery keys does **not** require R4: R1 ends it, and R2 and R3 are unaffected (Inference: separate partitions and separate key paths, [gt-i9195.md](../hardware/gt-i9195.md#recoverability-after-failed-boot-experiments)).

**R4, step by step** (proposed):

```sh
# PROPOSED. Not to be run until the approved issue exists and case 1 or 2 is agreed in it.
sha256sum ~/revival-firmware/gt-i9195/I9195XXSCQAN_I9195OXXCNK2/recovery.img
# must equal 0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6, 8,935,696 bytes
heimdall flash --RECOVERY ~/revival-firmware/gt-i9195/I9195XXSCQAN_I9195OXXCNK2/recovery.img --no-reboot
```

1. Hash check first, as in section 3. **Stop** if it differs.
2. Enter Download mode and detect the phone (D1–D3), write (D4, with the transfer-failure procedure if needed), wait, unplug, remove the battery (D5, D6).
3. Start with the recovery keys once. Expected: the stock recovery menu, as recorded in E1 ([stock recovery](../evidence/phase-0/2026-11-13-linux-retest.md#stock-recovery-e1)). Select **reboot system now** only. If the stock menu does not appear: remove the battery, stop and report.
4. Record the write and its result (section 11).

**Excluded from this plan, and from any plan:**

- **The full stock firmware flash.** It restores `system`, `boot`, `recovery` and the modem, and it **also rewrites bootloader images** ([gt-i9195.md](../hardware/gt-i9195.md#recovery-mechanisms), mechanism 4). Rule 2 forbids writing the bootloader chain and `modem` under any plan, so this is not a rescue route here, however bad the state.
- Repartitioning (`--repartition`, `--pit`), Odin, and any other tool.
- Qualcomm emergency download and hardware "debrick" methods: not usable plans (gt-i9195.md, mechanisms 6 and 7).

Writing `BOOT` is outside this plan; it would need its own approved plan.

**If Download mode cannot be reached,** there is no further route in this plan. Stop, leave the battery out, and report. Do not try other key combinations or tools.

## 10. Knox

**What the owner accepts.** Writing a non-Samsung image to `RECOVERY` is reported to set the Knox warranty bit permanently: `KNOX WARRANTY VOID: 0x1`, described as a hardware fuse that cannot be reset ([gt-i9195.md](../hardware/gt-i9195.md#bootloader-lock-and-knox), Community). The owner accepts that:

- the mark is permanent and no later step, including restoring stock images, removes it;
- Samsung's Knox features, and anything that checks the bit, may stop working on this phone;
- the bit may change at the transfer or at an attempted boot of the image; this plan does not say which. W1 is the first such write, so the acceptance is needed before W1, whether or not any trial succeeds.

**Where the acceptance is recorded.** The owner's own statement, in the owner's words, quoted in the issue with its date, before the approvals (E-4). Every agent posts through the owner's GitHub account, so a comment alone does not show who wrote it (reviewer decision, 2026-11-14). The Phase 2 evidence summary refers to that statement; it is not recorded anywhere else.

**The "before" state.** Recorded on 2026-11-13 ([Download mode (F2)](../evidence/phase-0/2026-11-13-linux-retest.md#download-mode-f2)):

```text
ODIN MODE
PRODUCT NAME: GT-I9195
CURRENT BINARY: Samsung Official
SYSTEM STATUS: Official
KNOX KERNEL LOCK: 0x0
KNOX WARRANTY VOID: 0x0
CSB-CONFIG-LSB: 0x30
BOOTLOADER RP SWREV: 2
WRITE PROTECTION: Enable
```

No reactivation-lock line is shown. D2 before W1 must show exactly these lines.

**After a write: Unknown.** What `CURRENT BINARY`, `SYSTEM STATUS` and `KNOX WARRANTY VOID` read after a write is Unknown. The status lines are photographed and transcribed:

1. **before W1:** step D2, compared with the lines above;
2. **before W2:** step D2, after the invalid image's trials and the rescue check;
3. **before W3 or W4,** if either is used: step D2;
4. **after the last trial:** step S4.

The transcriptions go into the evidence (section 11). A changed line is a result to record, not a reason to stop, unless it reports a lock that was not there before, such as a reactivation lock that reads on.

**Rule 4.** Rule 4 forbids bootloader unlocking and Knox or security-setting changes. This plan makes no such change on purpose: it unlocks nothing, sets nothing, and uses no exploit. Even so, rule 4's current wording binds until a reviewed amendment is effective ([2026-11-11 decisions](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441), item 2). That amendment is a later reviewed change, made after the owner's statement for E-4, and **is not made in this pull request** (E-15).

## 11. Evidence

The rule is in [TESTING.md](../TESTING.md#recording-evidence): a device result counts only when it is recorded. Raw evidence stays in a private directory outside every repository:

```sh
export EV2="$HOME/revival-evidence/gt-i9195/phase-2/$(date +%F)"
mkdir -p "$EV2/private"
script -q -a "$EV2/private/session.log"
```

**After each write:** the time; the exact command; Heimdall's complete output; the image's name and SHA-256 as checked that day; the status-line photograph taken before it.

**After each trial:**

| Item | Where |
| --- | --- |
| Trial number, image name and SHA-256, date and time; whether it counts toward the series or is a recorded, uncounted trial | The evidence table |
| The video, from before the keys are pressed to after the battery is removed | `$EV2/private/` |
| The still photograph of the screen | `$EV2/private/` |
| The outcome, by its row in section 6 or 7 | The evidence table |
| The rows as typed, and the output and PNG of `tools/read_rows.py` | `$EV2/`. The rows are register values, not identifiers. |
| Times: key release to picture; picture to battery removal, or to each reset | The evidence table, read from the video |
| Any failure, what was done to recover, and the state afterwards | The evidence table |

**At the end**, the six items TESTING.md lists for every device session:

1. The date, who performed it, the phase (2) and the step IDs of this plan.
2. The device: model and the bootloader and build versions, as in the Phase 0 record, with identifiers redacted.
3. The exact images: the commit, the `make` targets (`make check`, `make payload-invalid`) and the SHA-256 of every image written.
4. The observed result of each step, the number of trials, which counted, and how many showed the pass picture.
5. Every failure, the recovery action, and the state afterwards.
6. A statement of every write made: which of W1–W4, when, and that nothing else was written.

Also: the reboot counts; the status-line transcriptions (section 10); the rescue check's result (S2); the entry state decoded from the rows; the reset observations; and the state of the partitions after the phase, which is "`RECOVERY` holds `<image>`; no other partition was written by this plan". Download mode cannot read a partition back ([gt-i9195.md](../hardware/gt-i9195.md#recovery-mechanisms)), so that statement rests on the list of writes and on what `RECOVERY` starts, not on a read-back.

**Where the redacted summary goes.** A pull request adds it under `docs/evidence/phase-2/`, for the reviewer's review. Redacted photographs of the device's screen may be added there as [TESTING.md](../TESTING.md#recording-evidence) allows. Never committed: videos, original photographs, the session log, the PIT file, firmware, and any IMEI, serial number, MAC address or account name.

## 12. What this plan does not do

- **No write to `BOOT`.** `BOOT` is outside this plan, and a normal power-on keeps loading it untouched.
- **No lk2nd**, and no other third-party bootloader. Method B is a separately reviewed later option.
- **No normal power-on boot of Revival OS.** This plan proves execution from the recovery keys only. The normal power-on route is a separate milestone with its own 5 of 5, and it stays open.
- **No on-device exception test.** By decision A the exception path is tested in QEMU (`qemu-payload-fault-halts`), and on-device exception behaviour is deferred to Phase 3a.
- No payload-triggered reset, no watchdog petting or disabling, no UART.
- No change to the payload or to either image. A different hash is a different plan.
- No rehearsal write, and no write beyond the four in section 1.
- No erase, wipe or factory reset, and no recovery-menu action other than **reboot system now**.
- No full stock firmware flash (section 9).
- No new download of the Git LFS firmware, no hosted CI run, and no merge.

## Unknown and open

Everything this draft leaves open, in one place.

| Item | Status | Resolved by |
| --- | --- | --- |
| PIT read from the write host; what the phone shows after `--no-reboot` there; Heimdall 2.1.0's exact session lines | Recorded, 2026-11-14 | E-17 ([write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md)) |
| Heimdall 2.1.0's wording of the upload lines of a flash | Inference | The first write (D4) |
| The write-plan issue; the owner's Knox statement; both approvals | Open | E-3, E-4, E-5 |
| Rule 4 amendment | Open | E-15, a later reviewed change |
| The commit on `main` to build from | Open | E-11 |
| The five phone-only questions accepted as open | Open | E-10 |
| The write host, cable and port | Recorded, 2026-11-14 | E-16 ([write-host PIT read](../evidence/phase-2/2026-11-14-write-host-pit-read.md#host-cable-and-port-e-16)) |
| Does this phone's Android actually rewrite `RECOVERY`? | Assumed yes (E-13) | The rescue check (S2) |
| Rescue by W4 | Untested | Only if section 9 requires it |
| Signing-chain verification of the stock images | Not done | Not needed for this plan; recorded as a limit |
| Are bytes of `RECOVERY` beyond the image's length changed by the transfer? | Unknown | Not resolved; not relied on |
| How the bootloader rejects an image, and what state that leaves | Unknown | Section 7 |
| Whether the bootloader checks the magic, or refuses for one of the other known differences | Unknown | Section 7, in part; the reasons cannot be told apart |
| Whether the bootloader adds text over the picture | Unknown | The first trial |
| What the status lines read after a write | Unknown | Section 10's photographs |
| The five phone-only questions | Unknown | Section 8, in part |

## Sources

Checked 2026-11-11, and the repository evidence on 2026-11-14. Line numbers refer to the pinned tag or commit.

- AOSP `system/core`, tags `android-4.4.2_r1` and `android-4.2.2_r1`, `rootdir/init.rc`: <https://github.com/aosp-mirror/platform_system_core/blob/android-4.4.2_r1/rootdir/init.rc>
- AOSP `build`, tag `android-4.4.2_r1`, `tools/releasetools/ota_from_target_files`: <https://github.com/aosp-mirror/platform_build/blob/android-4.4.2_r1/tools/releasetools/ota_from_target_files>
- LineageOS wiki, Samsung recovery installation template at `bc00760c9307ebf166ccfbfd933ad957d342067d`, and the device data file at `8e9d82c86a4913c66419b7e0d1ab42de18652fa5`: <https://github.com/LineageOS/lineage_wiki>
- TWRP, Samsung Galaxy S4 Mini (International LTE): <https://twrp.me/samsung/samsunggalaxys4minilte.html>
- Heimdall, installed: `heimdall help` and the `heimdall(1)` manual page of Ubuntu package `heimdall-flash` 2.1.0-1build1 (homepage <https://git.sr.ht/~grimler/Heimdall/>; its source could not be fetched on the day)
- Heimdall, original project at `3997d5cc607e6c603c6e7c0d07e42e9868c62af2` (`BridgeManager.cpp`, `FlashAction.cpp`) and `Linux/README` at `8709370bc48310604dfd4407538f650b3cc4f0ae`: <https://github.com/Benjamin-Dobell/Heimdall>
- Decisions: the former orchestrator's [PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937) and [PR #12 comment of 2026-11-11](https://github.com/revival-systems/revival-os/pull/12#issuecomment-6796999441); the reviewer's decisions of 2026-11-14, marked where they apply.
- Phase 0 evidence: the [addendum](../evidence/phase-0/2026-11-13-linux-retest.md), the [partition map](../evidence/phase-0/2026-11-13-readonly/partition-map.md), the [firmware evidence](../evidence/phase-0/2026-11-13-firmware-rescue.md) and the [hardware summary](../evidence/phase-0/2026-11-13-hardware-summary.md). Phase 1: the [gate review](../evidence/phase-1/2026-11-13-gate-review.md).
- In this repository: [AGENTS.md](../../AGENTS.md#hardware-safety-contract), [ROADMAP.md](../../ROADMAP.md#phase-2--first-bare-metal-boot), [TESTING.md](../TESTING.md#recording-evidence), [gt-i9195.md](../hardware/gt-i9195.md), the [Phase 0 checklist](../phase-0/hardware-verification-checklist.md) and [boot-payload-research.md](boot-payload-research.md).

The downloaded source files were read outside this repository and are not committed.
