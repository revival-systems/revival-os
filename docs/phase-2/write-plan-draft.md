# Phase 2 write plan, method A (`RECOVERY` only): DRAFT

**This is a draft. It approves nothing.**

- **No command in this document may be run** until an approved write-plan issue exists ([AGENTS.md](../../AGENTS.md#hardware-safety-contract), rule 1).
- **The issue is opened by the owner or the orchestrator, not by an agent.** This file is the proposed text of that issue, for the two of them to review, correct and approve.
- Every `heimdall flash` line below is a proposal. Until the issue is approved, the only commands allowed on the phone are the read-only ones in the [Phase 0 checklist](../phase-0/hardware-verification-checklist.md#rules-for-this-checklist) (rule 5).
- Written 2026-11-11 from the repository's documents and public sources. **No device was touched and no flash command was run to write it.**

**Phase:** 2, first bare-metal boot ([ROADMAP.md](../../ROADMAP.md#phase-2--first-bare-metal-boot)). **Method:** A, decided by the orchestrator on 2026-11-11 ([PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937), decision B). **Partition:** `RECOVERY`, and no other.

What a pass of this plan proves, and what it does not: the payload runs when the phone is started with the recovery keys. That is the initial probe of method A. It is **not** a normal power-on boot of Revival OS, which stays open as its own milestone.

## Labels

The labels are the ones the research documents use ([gt-i9195.md](../hardware/gt-i9195.md), [boot-payload-research.md](boot-payload-research.md)).

| Label | Meaning |
| --- | --- |
| **Source** | Stated in a cited file and line, or in the output of the installed tool. |
| **Community** | Reported by a project's wiki or by users. Not authoritative for this phone. |
| **Inference** | Our conclusion from the sources. No source states it. |
| **Unknown** | Not known for this phone or this build. The entry says what resolves it. |
| **Pending** | A value that Phase 0 evidence supplies. It is left blank here on purpose and is not guessed. |

Values that come from the phone are written as placeholders that point at the private evidence directory, for example `<$EV0/F5-print-pit.txt>`. `$EV0` is the Phase 0 evidence directory (checklist step A2) and `$EV2` is the Phase 2 one (section 11). Neither is in any repository (rule 7).

## Two facts that change the procedure

### Stock Android may write the recovery partition back at boot

| Point | Finding | Label and evidence |
| --- | --- | --- |
| The mechanism in AOSP | Android's `init` starts a one-shot service at every boot that runs `/system/etc/install-recovery.sh`. | Source: AOSP `system/core`, tag `android-4.4.2_r1`, [`rootdir/init.rc:513-515`](https://github.com/aosp-mirror/platform_system_core/blob/android-4.4.2_r1/rootdir/init.rc#L513-L515). The same three lines are in tag `android-4.2.2_r1` at `rootdir/init.rc:475-477`. Those are the two Android versions Samsung released for this phone ([gt-i9195.md](../hardware/gt-i9195.md#specifications), Community). |
| What the script does | It checks the SHA-1 of the recovery partition against the stock recovery image. If they differ, it rebuilds the stock recovery from the `boot` partition and the patch `/system/recovery-from-boot.p`, and writes it to the recovery partition. | Source: AOSP `build`, tag `android-4.4.2_r1`, [`tools/releasetools/ota_from_target_files:348-399`](https://github.com/aosp-mirror/platform_build/blob/android-4.4.2_r1/tools/releasetools/ota_from_target_files#L348-L399); the script text is lines 381-387. |
| Samsung phones in general | LineageOS's install instructions for Samsung phones, the ones its data file selects for this model, say: "Be sure to reboot into recovery immediately after installing the custom recovery. If you don't the stock ROM will overwrite the custom recovery with the stock recovery, and you'll need to flash it again." TWRP's page for this model says "many devices will replace your custom recovery automatically during first boot". | Community: LineageOS wiki, [`recovery_install_samloader_rs.md:73`](https://github.com/LineageOS/lineage_wiki/blob/bc00760c9307ebf166ccfbfd933ad957d342067d/_includes/templates/recovery_install_samloader_rs.md#L73), selected by [`serranoltexx.yml:16`](https://github.com/LineageOS/lineage_wiki/blob/8e9d82c86a4913c66419b7e0d1ab42de18652fa5/_data/devices/serranoltexx.yml#L16); [TWRP](https://twrp.me/samsung/samsunggalaxys4minilte.html). Both are general notes, not tests of this build. |
| This phone's build | **Unknown.** Samsung builds its own system image, and nothing found says whether this build carries the script and the patch. | Resolved before the first write by the read-only check E-13 in section 2, and on the phone by what happens if Android starts (section 4, "If Android starts"). |

What follows for the plan, whichever way the check comes out (Inference):

1. **One normal Android boot may replace the payload with stock recovery.** The payload is then gone, and a trial after it shows the stock recovery menu.
2. **Every trial therefore goes from Download mode, or from a removed battery, straight to the recovery keys.** Android must not start between the write and the last trial.
3. **If Android does start,** the plan says what to do (section 4). The partition's content is treated as not known until it is observed.
4. **It is also a rescue route.** If this build has the script, a normal Android boot puts stock recovery back without any write from the host (section 9).

### What `--no-reboot` leaves, and how to reach the recovery keys

| Point | Finding | Label and evidence |
| --- | --- | --- |
| What the option does | "`--no-reboot` causes the device to remain in download mode after the action is completed. If you wish to perform another action whilst remaining in download mode, then the following action must specify the `--resume` flag." | Source: the output of `heimdall help` from the installed Heimdall v2.1.0 (Ubuntu package `heimdall-flash` 2.1.0-1build1), under the `flash` action. |
| What is sent to the phone | With `--no-reboot`, Heimdall ends the session and does not send the reboot request. Without it, Heimdall sends the reboot request and the phone restarts, normally into Android. | Source for the original project: Heimdall [`BridgeManager.cpp:558-612`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/BridgeManager.cpp#L558-L612) and [`FlashAction.cpp:458`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/FlashAction.cpp#L458), `:570`. The installed 2.1.0 is a maintained fork whose source could not be fetched (its host returned an error), so for 2.1.0 this is an Inference from the identical help text. |
| What the phone shows | "The device will continue to display `Downloading... Do not turn off target!!` even after the process is complete." | Community: LineageOS wiki, [`recovery_install_samloader_rs.md:70`](https://github.com/LineageOS/lineage_wiki/blob/bc00760c9307ebf166ccfbfd933ad957d342067d/_includes/templates/recovery_install_samloader_rs.md#L70). Written for another flashing tool with the same option; **Unknown** on this phone until seen. |
| Why the option exists | "It's mostly in place so you can manually boot straight into recovery mode after a flash (rather than booting up normally)." The manual adds: "You can still safely reboot your phone manually (with the power button) after executing `--no-reboot` commands." | Source: Heimdall [`Linux/README:162-164`](https://github.com/Benjamin-Dobell/Heimdall/blob/8709370bc48310604dfd4407538f650b3cc4f0ae/Linux/README#L162-L164), `:217-218`; the installed `heimdall(1)` manual page has the second sentence. |
| How to leave from there | Remove the battery, then hold the recovery keys from power-off. LineageOS gives the same route: "Manually reboot into recovery, this may require pulling the device's battery out and putting it back in". | Source: checklist step F6 proves the battery exit from an idle Download mode, including after a `--no-reboot` command, 3 of 3 (**Pending** its recorded evidence). Community: LineageOS wiki, same file, line 71. Recovery keys: [gt-i9195.md](../hardware/gt-i9195.md#download-mode-and-flashing-tools). |

What follows for the plan:

1. **Every write uses `--no-reboot`.** Without it the phone restarts into Android, which may undo the write (above).
2. **After the write, the owner waits for Heimdall to exit, then removes the battery.** The battery is never removed while Heimdall is running.
3. **The power button is not used to leave Download mode.** The manual says it is safe, but a restart by the power button boots normally, which is what the plan avoids.

## 1. What is written

Only `RECOVERY` is written, with these images, built at the reviewed commit. Both hashes come from a clean export; the first is pinned in the Makefile and checked by `make check` (test `payload-frozen`).

| Image | Size | SHA-256 |
| --- | --- | --- |
| `build/boot-serrano/payload.img` | 6,160 bytes | `bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02` |
| `build/boot-serrano/payload-invalid.img` | 6,160 bytes | `34dc91c64811346a3766e71044c2260340fadec0a0ea327e4126a1ef7a584d7b` |
| Stock `recovery.img` of the installed build (rescue only) | **Pending** E-9 | **Pending** E-9; kept in the private evidence, never in the repository |

**Reviewed commit:** the images were reviewed at `85f9c8b` ([PR #11](https://github.com/revival-systems/revival-os/pull/11)) and are unchanged in its merge with `main`, `6a38a79`. The issue names the commit on `main` that contains both pull requests (**Pending** their merge, E-11).

**The partition.**

| Field | Value | Status |
| --- | --- | --- |
| PIT partition name, as Heimdall takes it | `<RECOVERY_PIT_NAME>` | **Pending F5.** Copied character for character from `<$EV0/F5-print-pit.txt>`. Decision B and public project data call it `RECOVERY`; the spelling is not assumed here. |
| PIT identifier | `<from F5>` | **Pending F5** |
| Size | `<from F5>` | **Pending F5.** LineageOS's board file gives 10,485,760 bytes ([gt-i9195.md](../hardware/gt-i9195.md#partition-layout), Source); the PIT decides. |

Heimdall refuses a name that is not in the phone's PIT (Source for the original project: [`FlashAction.cpp:220-224`](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/FlashAction.cpp#L220-L224); Inference for 2.1.0). Each test image is 6,160 bytes, far below the partition size, so `--skip-size-check` is never used. Whether bytes of `RECOVERY` beyond the image's length are changed by the transfer is **Unknown**; the plan does not depend on it.

**The writes.** The rows are in the order of option (b) in section 5. The orchestrator decides the order; under option (a) the rows change as that section says.

| # | Image | SHA-256 | Partition | Proposed command (run from the repository root) | Why |
| --- | --- | --- | --- | --- | --- |
| W1 | `payload-invalid.img` | `34dc91c6…4d7b` (full value above) | `RECOVERY` | `heimdall flash --<RECOVERY_PIT_NAME> build/boot-serrano/payload-invalid.img --no-reboot` | ROADMAP negative test: a deliberately invalid image shows how the bootloader rejects images (section 7). |
| W2 | `payload.img` | `bde09074…ce02` (full value above) | `RECOVERY` | `heimdall flash --<RECOVERY_PIT_NAME> build/boot-serrano/payload.img --no-reboot` | The proof of execution: five trials of the same image (section 6). |
| W3 | `payload.img` again | as W2 | `RECOVERY` | as W2 | **Conditional, at most once.** Only if Android started before the five trials were complete and stock recovery was then seen in place of the payload (section 4, "If Android starts"). |
| W4 | Stock `recovery.img` | **Pending** E-9 | `RECOVERY` | `heimdall flash --<RECOVERY_PIT_NAME> <private firmware directory>/recovery.img --no-reboot` | **Conditional, rescue only.** Only if required for recovery (section 9). Not a routine step. |

Rules for every row:

- One partition argument per command, and no other option: no `--repartition`, no `--pit`, no `--skip-size-check`, no `--tflash`, no partition identifier in place of the name.
- `--resume` is added only if an earlier Heimdall command in the same Download-mode session used `--no-reboot`. The procedure in section 4 has no such command before a write, so no write uses it.
- A write that fails or is interrupted is **not repeated** under this plan. Stop and report (rule 8).

**Maximum number of writes this plan asks approval for: four**, all to `RECOVERY`: W1 and W2 planned, W3 and W4 conditional. Under option (a) the maximum is five. One write more than that, or a write of anything else, needs a new approval.

**Never written, under this or any plan:** `BOOT`; the bootloader chain (`sbl1`, `sbl2`, `sbl3`, `aboot`, `rpm`, `tz` and any other boot-firmware partition); `efs`; `persist`; `modem`. `system`, `userdata`, `cache` and every other partition are also outside this plan.

## 2. Entry conditions

Every box is ticked in the issue, with its evidence, before the first write. "Evidence" names a file in the private evidence directory or a reviewed pull request; no identifier is copied into the issue or the repository.

### ROADMAP Phase 2 entry gate

- [ ] **E-1. Phase 0 has passed, with the stock `boot` and `recovery` images for the installed build verified and Download mode shown to be reliable.**
  Closed by: the owner performs it; the orchestrator reviews it.
  Evidence: the merged pull request that adds the redacted summary under `docs/evidence/phase-0/` (checklist H2–H4). The checklist's status is "In progress" today.
- [ ] **E-2. Phase 1 has passed.**
  Closed by: the orchestrator.
  Evidence: the orchestrator's statement in the issue. No document in the repository records Phase 1 as passed yet (**Pending**).
- [ ] **E-3. A write-plan issue names the method, partition, image hash and recovery steps.**
  Closed by: the owner or the orchestrator, who opens it.
  Evidence: the issue itself, made from this draft with every **Pending** value filled in.
- [ ] **E-4. The owner has explicitly accepted that flashing a non-Samsung image is reported to trip the irreversible Knox warranty bit.**
  Closed by: the owner.
  Evidence: the owner's own comment on the issue (section 10).
- [ ] **E-5. The orchestrator has approved the plan.**
  Closed by: the orchestrator.
  Evidence: the orchestrator's approving comment on the issue, after the owner's.

### Open blockers from the research

The numbers are those of the research's [list](boot-payload-research.md#blockers-before-any-write).

- [ ] **Blocker 1. Phase 0 passed, with its evidence reviewed.** The same condition as E-1, closed with it.
- [ ] **E-6 (blocker 2). The installed build is recorded: bootloader version, build, baseband, CSC (C5, F2).**
  Closed by: the owner.
  Evidence: `<$EV0/C5-getprop-selected.txt>`; the versions appear in the redacted Phase 0 summary.
- [ ] **E-7 (blocker 3). The Download-mode status lines are photographed and transcribed: Knox warranty bit, secure boot, reactivation lock, write protection (F2).**
  Closed by: the owner.
  Evidence: `<$EV0/F2-download-mode-lines.txt>` and its photograph in `<$EV0/private/>`. Reactivation lock must be off, or its account known.
- [ ] **E-8 (blocker 4). Download mode is shown reliable (F1 3 of 3, F6 3 of 3), Heimdall detects the phone (F4), and the PIT lists the boot and recovery partitions with sizes (F5).**
  Closed by: the owner.
  Evidence: `<$EV0/F4-heimdall-detect.txt>`, `<$EV0/F5-print-pit.txt>`. The recovery partition's PIT name, identifier and size are copied from the second file into section 1.
- [ ] **E-9 (blocker 5). Verified stock `boot` and `recovery` images for the installed build are held outside the repository (G1–G4).** For this plan, also: `recovery.img` is extracted from the verified package into the private firmware directory, identified with `file`, and its SHA-256 and size are recorded. Extraction is a host-only step; nothing is flashed.
  Closed by: the owner obtains them; the orchestrator reviews that the build identifiers match.
  Evidence: `<$EV0/G3-firmware-contents.txt>`, `<$EV0/G3-firmware-sha256.txt>`, and a new `<$EV0/private/G-recovery-img-sha256.txt>`.
- [ ] **Blocker 6. The owner's Knox acceptance.** The same condition as E-4, closed with it.
- [ ] **E-10 (blocker 11). The five phone-only questions are accepted as open, with the expected observation and the recovery action for each outcome.**
  Closed by: the owner and the orchestrator.
  Evidence: their approval of sections 6, 7, 8 and 9 of the issue.
- [ ] **Blocker 12. The approved write-plan issue.** The same condition as E-3 and E-5, closed with them.

Blockers 7 to 10 are not open: 7 is decided (method A), 8 and 9 are the reviewed payload, and 10's image is built; its recovery steps are section 9 of this plan.

### Conditions this draft adds

- [ ] **E-11. Pull requests #10 and #11 are merged into `main`, and the issue names the commit to build from.**
  Closed by: the orchestrator.
  Evidence: the commit SHA in the issue. `make check` on it prints `PASS payload-frozen` with the two hashes in section 1.
- [ ] **E-12. The recovery keys reach stock recovery 3 of 3 (E1), and the battery exit from Download mode works 3 of 3 (F6).** Both are part of Phase 0; they are listed because every trial depends on them.
  Closed by: the owner.
  Evidence: rows E1 and F6 of the Phase 0 summary.
- [ ] **E-13. The recovery-restore check has been run and recorded.** With the phone in Android and USB debugging authorised: `adb shell ls -l /system/etc/install-recovery.sh /system/recovery-from-boot.p`. It is read-only, and `adb shell ls` is on the Phase 0 allowed list.
  Closed by: the owner.
  Evidence: `<$EV0/E13-install-recovery-ls.txt>`. Both files listed: assume Android rewrites `RECOVERY` at boot. "No such file" for both: the AOSP mechanism is not installed, and whether Samsung has another one stays **Unknown**. The procedure is the same either way.
- [ ] **E-14. The order of the two images (section 5) and the maximum number of writes (section 1) are decided.**
  Closed by: the orchestrator.
  Evidence: the decision recorded in the issue.
- [ ] **E-15. The reading of rule 4 in section 10 is confirmed.**
  Closed by: the owner and the orchestrator.
  Evidence: their comments on the issue.
- [ ] **E-16. The host is the one used for Phase 0, with the same cable and USB port, and `heimdall version` prints `v2.1.0`.** Whether Heimdall needed `sudo` for USB access in F4 is recorded; the write uses the same form.
  Closed by: the owner.
  Evidence: the Phase 0 session log (private), and the `make doctor` output on the day.

## 3. Host and tools

| Item | Value |
| --- | --- |
| Host | The development machine used for Phase 0: Ubuntu 26.04 LTS on x86-64 ([DEVELOPMENT.md](../DEVELOPMENT.md#one-time-setup)). No other computer, no virtual machine, no USB hub. |
| Heimdall | `v2.1.0` as printed by `heimdall version`: Ubuntu package `heimdall-flash` 2.1.0-1build1. A different version stops the plan until the issue is updated. |
| Other flashing tools | None. No Odin, no fastboot, no lk2nd. |
| Repository | A fresh clone of the commit named in the issue (E-11), with nothing else in it. |
| Row decoder | [tools/read_rows.py](../../tools/read_rows.py) at that commit ([Trial kit](boot-payload-research.md#row-reading-tool)). |
| Camera | A second device that records video with sound and takes sharp still photographs. Its clock is set to the host's. |

**How the image's hash is checked immediately before a write.** On the day, in the fresh clone, with the phone not yet connected:

```sh
# Host only. Nothing here contacts the phone.
git rev-parse HEAD        # must print the commit named in the approved issue
git status --short        # must print nothing
make check                # must exit 0 and print: PASS payload-frozen (payload.bin 8ee519ae…, payload.img bde09074…)
make payload-invalid      # prints the line that starts INVALID-MAGIC-NEGATIVE-TEST
sha256sum build/boot-serrano/payload.img build/boot-serrano/payload-invalid.img
```

- At the reviewed commit `make check` prints 61 PASS lines and no FAIL line.
- The two `sha256sum` lines must equal the two values in section 1, compared character by character against the issue, not against this draft.
- Nothing is rebuilt between this check and the write. If `make` is run again for any reason, the check is run again.
- For W4, the same comparison is made with `sha256sum` on the stock `recovery.img` against the value recorded for E-9.

**Stop** if the commit, the tree, any test or any hash differs. A different hash means a different image, which this plan does not cover.

## 4. Procedure for the owner

The owner performs every physical step (rule 6). An agent may prepare the commands and read the results; it does not run a write. **Stop** means: do nothing further to the phone except what the step says, remove the battery if the step says so, and report in the issue (rule 8). A stopped step is not retried until the owner and the orchestrator have answered.

### Preflight

Before the phone is touched.

| Step | Action | Stop if |
| --- | --- | --- |
| P1 | Confirm every box in section 2 is ticked in the issue and the issue carries both approvals. | Any box is open. |
| P2 | Inspect and charge the battery as in checklist B2 and B3: not swollen, at least 60 %. Use the Phase 0 cable and USB port. | The battery is swollen, hot or below 60 %. |
| P3 | Create the Phase 2 evidence directory and start the session log (section 11). Record the date, the time and who performs the steps. | — |
| P4 | Run the hash check in section 3. Save its output. | Section 3's stop conditions. |
| P5 | Start the camera and say aloud the date, the time, the image name and the first eight characters of its hash. | — |

### Writing an image

For W1 and W2, and for W3 or W4 if their condition applies.

| Step | Action | Expected | Stop if |
| --- | --- | --- | --- |
| D1 | Power the phone off. Hold Volume Down + Home + Power until the warning screen appears, then release. Press Volume Up to continue. | The warning screen, then the download screen, as recorded in F1 and F2. | Any other screen appears, or the warning does not appear in two attempts. |
| D2 | Photograph the status lines at the top left. Before the first write this is the "before" photograph for Knox (section 10). | The lines recorded in F2. | A line differs from F2 before the first write, or reactivation lock reads on. |
| D3 | Connect the cable. Run `lsusb \| grep -i 04e8`, then `heimdall detect`. | The Download-mode USB ID recorded in F3; `Device detected`. | No device, a different ID, or any error. |
| D4 | Read the proposed command for this write aloud from the **issue**, compare the file name and the partition name with section 1, then run it. Do not touch the phone, the cable or the battery while it runs. | Heimdall reports the upload as successful and ends the session without rebooting the phone. Save the complete output. | Heimdall prints any error, asks any question, names any other partition, or runs for more than 2 minutes. After 2 minutes, interrupt it with Ctrl-C, unplug the cable and remove the battery; the content of `RECOVERY` is then not known. In every case, do not repeat the command. |
| D5 | Wait until the shell prompt has returned. Look at the phone. | The phone still shows the download screen. | The phone restarts by itself. If Android then appears, go to "If Android starts". |
| D6 | Unplug the cable. Remove the battery and wait 10 seconds. | The screen goes dark. | — |

### One trial

Repeated; the steps are the same for both images.

| Step | Action | Expected | Stop if |
| --- | --- | --- | --- |
| T1 | Leave the cable unplugged. Start the video recording and say the trial number and the time. The whole screen is in frame. | — | — |
| T2 | Insert the battery. Hold **Volume Up + Home + Power**. When the Samsung logo appears, release Power only and keep holding the other two until the screen changes, as in checklist E1. | The image in `RECOVERY` starts. Sections 6 and 7 list what may appear. | Android's boot animation appears: go to "If Android starts". |
| T3 | Keep filming without touching the phone. Film for the time in "How long to film" below. | A picture that does not change, or one of the other outcomes in sections 6 and 7. | The phone becomes hot, or smells: remove the battery at once. |
| T4 | While filming continues, take a sharp still photograph of the whole screen, square on, with no reflection across the rows. | Every cell of every row is countable in the photograph. | — |
| T5 | End the trial: remove the battery. Say the time. Wait 10 seconds. Stop the recording. | The screen goes dark. | The screen stays lit with the battery out. |
| T6 | Type the rows from the photograph into `tools/read_rows.py` with the fill colour seen, compare its echo of the cells with the photograph, and save its output and its PNG. A screen that is not a fill with eight or nine rows is described in words and not typed. | The record's first line reads `Checksum row OK`. | It reads `ROWS MISREAD`: read the photograph again; do not go on to the next trial until the rows are read or declared unreadable. |
| T7 | Fill in the trial's line of the evidence table (section 11). | — | The outcome is not in section 6 or 7. |

### How long to film

Proposed; the issue fixes the numbers.

| Trial | Time from the picture appearing | Why |
| --- | --- | --- |
| The first trial of each image | 10 minutes | The watchdog question: does the phone reset by itself, and after how long. The reference timeouts in the research are 0.39 and 48 seconds ([section 4](boot-payload-research.md#4-watchdog)); neither is known to apply. |
| Later trials | 2 minutes, or 30 seconds beyond the reset time seen in the first trial | Enough to see the same behaviour again. |
| A trial where nothing appears | 10 minutes from the key release | A black or unchanging screen needs the same time to show a reset. |

If the phone resets by itself, keep filming and do not touch any key: what it starts next is part of the result (section 6).

### The series

| Step | Action | Stop if |
| --- | --- | --- |
| S1 | For `payload-invalid.img`: up to 3 trials. One trial is enough if it ends in Android starting, because `RECOVERY` may then have changed. | The three results differ from each other. |
| S2 | For `payload.img`: 5 trials, each started from a removed battery (T1–T7), with no Android boot and no Download-mode entry between them. The pass criterion is the same picture in 5 of 5. | Two trials differ: record both, stop, report. A failed trial is recorded, not repeated or replaced. |
| S3 | After the last trial of each image: enter Download mode (D1), photograph the status lines (D2), run `heimdall detect` (D3), and leave by removing the battery (D6). Under option (b) the entry for W2 is this check for the first image. | Download mode cannot be reached: section 9. |
| S4 | Write nothing more. `RECOVERY` is left holding the last image written; a stock image is not restored unless section 9 requires it. | — |

### If Android starts

At any point after W1 and before the last trial.

| Step | Action | Why, and what follows |
| --- | --- | --- |
| A1 | Do not remove the battery. Let Android reach the lock screen. Keep filming and note the time. | If this build restores recovery at boot, Android may be writing `RECOVERY` at that moment (Inference). Interrupting it would leave the partition half written. |
| A2 | Power off from Android's own menu. Record that Android started, and what led to it: the keys, a restart after the write, a reset during a trial, or a rejected image. | The content of `RECOVERY` is now not known. |
| A3 | Run one trial (T1–T5) to see what `RECOVERY` holds. | The test image's own outcome again: the image survived an Android boot, which answers E-13's question for this build; continue the series. The stock recovery menu: the image was replaced; select **reboot system now** and nothing else, as in checklist E1, let Android start, and power off from its menu. |
| A4 | If `payload.img` was replaced and its five trials are not complete, W3 may be used, once. | A second Android start after W3: stop and report. No further write is covered. |

## 5. Order of the two images

Both orders run the same two tests. They differ in the number of writes and in what is known when each result has to be read.

| | (a) Payload first | (b) Invalid image first |
| --- | --- | --- |
| Sequence | Write `payload.img`; 5 trials. Write `payload-invalid.img`; up to 3 trials. Write a known-good image again (`payload.img`), so that `RECOVERY` does not end holding an image built to be rejected. | Write `payload-invalid.img`; up to 3 trials. Write `payload.img`; 5 trials. |
| Planned writes | 3 | 2 |
| Maximum with the conditional rows (one repeat, one rescue) | 5 | 4 |
| The first write ever made to this phone | The image whose layout copies lk2nd's, which the bootloader is reported to accept. | The image built to be refused. How the bootloader refuses, and what state that leaves, is Unknown. |
| If the payload shows nothing (logo or black screen) | Read without knowing what a refusal looks like. It cannot be told apart from a refusal until the invalid image has been tried. | Read against a refusal already seen: a different screen means the image was accepted and the payload itself failed to show. |
| If the invalid image shows nothing | Read against a payload result already seen. | Cannot be told apart from an accepted image whose payload is invisible, until the payload has been tried. |
| State at the end | `RECOVERY` holds `payload.img`, after one more write. | `RECOVERY` holds `payload.img`. |

In both orders the ambiguity of a silent screen is resolved only once both images have been tried. The rejection path is exercised in both, because the ROADMAP requires the negative test.

**The reviewer suggests (b):** two writes, and the rejection behaviour is known before a silent payload result has to be interpreted. **The orchestrator decides** (E-14). Sections 1 and 4 are written for (b). Under (a) the rows of section 1 become: W1 `payload.img`, W2 `payload-invalid.img`, W3 `payload.img` again, W4 the conditional repeat, W5 the conditional rescue.

## 6. Outcomes for `payload.img`

Every outcome is recorded with the video, the still photograph and the times. "Rows" are typed into `tools/read_rows.py`, whose record states what each row means ([Trial kit](boot-payload-research.md#row-reading-tool)). Small text that the bootloader adds at the top of the screen, such as a `Set Warranty Bit` line, is transcribed exactly; if it covers a row, that row is recorded as unreadable and not guessed.

| On screen | What it means | What to record | What to do next |
| --- | --- | --- | --- |
| **Green fill, nine rows** | The payload ran. The panel is scanning out of `0x88300000`. Green does not show the byte order. | The nine rows; the tool's record; whether row 9 (the display register) names the same address. | Continue the series. |
| **Red or blue fill, nine rows** | The payload ran. The panel is scanning out of `0x88100000`. Red: byte 0 is red. Blue: byte 0 is blue, the order the research expects. | As above. | Continue the series. |
| **Grey fill, nine rows** | The payload ran. The panel is scanning out of the address in row 9, which is neither candidate; the payload found it in the display register and painted it. | As above. The tool reports a contradiction if row 9 is not an address the payload paints grey. | Continue the series. |
| **Any of those fills, eight rows** | The payload ran and painted, and the read of the display register then hung or faulted: rows 1–8 are drawn before that read, row 9 only after it returns. | The eight rows; the tool's record for an eight-row input. | Continue the series; the result must be the same in every trial. Report it: the register read is the open point of blocker 9. |
| **A fill with no rows, or with fewer than eight** | The payload ran and filled the screen, then stopped before or while drawing the rows. With no rows, the guarded read at `r2` is the step between the fill and the rows. | The photograph, the number of complete rows, and their cells if readable. The tool is not used. | Stop after this trial and report. |
| **A partial fill, bands, a sheared picture, or colours other than the four** | The payload ran and wrote to memory the panel is showing, and the panel's geometry or pixel format is not the one assumed (540×960, 3 bytes per pixel, stride 1620). | The photograph and a description. The rows are not typed. | Stop after this trial and report. The picture is the evidence for the next payload revision. |
| **The Samsung logo, or a black screen, that never changes** | Not decided by this screen. Either the bootloader did not start the image, or the payload ran and nothing it wrote is being shown, or it hung before painting. Compare with what the invalid image showed (section 5). | The screen, for the full 10 minutes; whether and when it resets; any small text. If the image was accepted, this is the ROADMAP's fail criterion "no observable output after the image is accepted". | End the trial by removing the battery. Run one more trial; if it is the same, stop and report. |
| **The stock recovery menu** | `RECOVERY` does not hold the payload. Android replaced it, or the write did not take effect. | The menu's header text, as in checklist E1. | Select **reboot system now** and nothing else; let Android start; power off from its menu. Then "If Android starts", step A4. |
| **Android starts** | The recovery keys were not taken, or the bootloader passed over `RECOVERY` and loaded `BOOT`. | The time, and how the keys were held. | "If Android starts", from A1. |
| **The phone resets by itself** | A watchdog, or the bootloader's own timer, is running. The time from the picture to the reset is the ROADMAP's watchdog measurement. | That time, from the video, and what starts next without any key held: the payload again, Android, Download mode, or another screen. | The payload again: let it run for the filming time; if it keeps resetting, remove the battery and record a reset loop. Android: "If Android starts". Anything else: remove the battery, stop, report. |
| **Download mode, or an error screen with text** | The bootloader refused `payload.img`, or failed to start it. Not expected: images with this layout are reported to be accepted. | Every line of text, transcribed exactly, and a photograph. | Touch no key. Remove the battery. Stop and report; section 9 says what is checked next. |
| **Anything else** | Not foreseen. | The video and a description. | Remove the battery. Stop and report (rule 8). |

**Pass, for this plan:** one of the first three rows, the same in 5 of 5 trials, with the checksum row equal to `0x22BECBA4` each time. The eight-row picture in 5 of 5 also shows the payload executing; whether it counts as the pass is for the orchestrator to say. Everything else is a recorded result that is not a pass.

## 7. Outcomes for `payload-invalid.img`

The image differs from `payload.img` in the magic alone, and its kernel slot is the real payload ([Trial kit](boot-payload-research.md#negative-test-image-blocker-10)). So the trial answers one question either way: does the bootloader check the magic?

| On screen | What it means | What to record | What to do next |
| --- | --- | --- | --- |
| **An error screen, or Download mode, with text** | The bootloader checks the magic and refuses the image. This is the ROADMAP's record of how it rejects an image. | Every line of text, exactly; how long the screen stays; whether the phone then does anything by itself. | Touch no key. Remove the battery. Continue with S1, then S3. |
| **The normal picture: a fill with rows** | The bootloader does not check the magic, and the payload ran from an image with a bad header. | The rows, as in section 6. | Continue with S1. Report that the negative test did not produce a rejection; a different invalid field is a new image and a new plan. |
| **The Samsung logo, or a black screen, that never changes** | A refusal that shows nothing, or an accepted image whose payload shows nothing. Not decided until `payload.img` has been tried (section 5). | The screen for the full 10 minutes; whether and when it resets. | Remove the battery. Continue with S1, then S3. |
| **Android starts** | The bootloader refused the image and loaded `BOOT` in its place, or the keys were not taken. | The time, and how the keys were held. | "If Android starts". One trial is enough for this image (S1); `RECOVERY` may now hold stock recovery. |
| **The stock recovery menu** | `RECOVERY` does not hold the invalid image. | The menu's header text. | Select **reboot system now** only; power off from Android. Stop and report: the write did not take effect or was replaced. |
| **The phone resets by itself, repeatedly** | The bootloader refuses the image and restarts, or a watchdog fires. | The interval, from the video, and what starts each time. | Remove the battery. Continue with S3. |
| **Anything else** | Not foreseen. | The video and a description. | Remove the battery. Stop and report. |

After this image, **recovery is proven** (ROADMAP) by S3: Download mode is entered and the phone is detected. Under option (b), `payload.img` is then written and started.

## 8. The five phone-only questions

The questions are the research's ([list](boot-payload-research.md#questions-only-the-phone-can-answer)). For each: the observation in this plan that answers it, and what stays unanswered.

| # | Question | Answered by | Still unanswered after this plan |
| --- | --- | --- | --- |
| 1 | Does the bootloader accept a kernel without the zImage words, a zero-length ramdisk, or a missing trailer, and what does it show and do when it rejects an image? | Only the magic is tested (section 7). If the invalid image is refused, the refusal screen and what follows it are recorded. | The zImage words, the 1-byte ramdisk and the trailer are present in both images, so whether each is required is not tested. If the bootloader does not check the magic, its rejection behaviour is not seen at all. |
| 2 | The actual load address and entry state: `r0`–`r2`, mode, interrupt masks, MMU and caches. | Rows 1–6: `r0`, `r1`, `r2`, CPSR, SCTLR and the run-time entry address. Row 7: the first word at `r2` (ATAGS or a device tree). The tool's record sets each against the expectation. | `r3` is captured but not painted. Only the first word at `r2` is read, not the tag list. The second core's state, and whether HYP mode exists, are not shown. |
| 3 | Is the display still scanning out when a non-Samsung image is started from `RECOVERY`, what is the framebuffer address on this unit, and what is the byte order? | Any fill appearing answers the first part. The fill colour gives the address (section 6). Red or blue gives the byte order. Row 9 gives the display register's own value. | The byte order if the fill is green or grey. The stride and size registers are not read. The same questions for an image started from `BOOT` are outside this plan. |
| 4 | Is the watchdog running at handoff, and what is its timeout? | Whether the phone resets by itself within the filmed time, and after how long (section 4, "How long to film"). | If it does not reset in 10 minutes, the answer is only "not within 10 minutes": the watchdog registers are not read, so a stopped watchdog and a longer timeout look the same. |
| 5 | What does a `PS_HOLD` drop or a watchdog bite do in the state the bootloader leaves, and how does the bootloader treat the next boot? | Not answered. This payload triggers no reset. If a watchdog resets the phone by itself, what starts next is recorded, which is a partial answer for that one case. | Everything else. A payload that resets on purpose is a later increment ([section 5](boot-payload-research.md#5-deterministic-halt-and-reset)). |

All five are accepted as open by approving this plan (E-10). No trial is repeated, and no image is changed, to chase an answer.

## 9. Rescue

Rule 1 sets the aim: a safe route for further Revival OS testing. That route is **Download mode on an untouched bootloader chain, with `RECOVERY` writable again**. Restoring Android is not the aim.

| # | Route | Depends on | Use | Label |
| --- | --- | --- | --- | --- |
| R1 | Remove the battery. | Nothing | Ends any hang, loop, error screen or stuck mode. Used to end every trial. | Source (removable battery); proven for Download mode by F6 (**Pending** its evidence) |
| R2 | Download mode: Volume Down + Home + Power from power-off. | The bootloader chain, which is never written | The anchor for every later write. Checked after each image (S3). | Source (keys); Inference (it does not depend on `RECOVERY` or `BOOT`) |
| R3 | Normal power-on. | `BOOT`, `system` and the rest, none of which this plan writes | Shows the phone starts from the untouched `BOOT`. It is not a pass condition. If this build restores recovery at boot (E-13), it also puts stock recovery back in `RECOVERY` with no write from the host. | Inference ([gt-i9195.md](../hardware/gt-i9195.md#recoverability-after-failed-boot-experiments)); the restore is **Unknown** for this build |
| R4 | Write the verified stock `recovery.img` to `RECOVERY` (W4). | R2, Heimdall, and the verified image (E-9) | **Only if required for recovery.** | Source (Heimdall); the image is **Pending** E-9 |

**When R4 is "required".** Only in one of these cases, and only after the owner and the orchestrator have agreed in the issue that the case applies:

1. With a test image in `RECOVERY`, the phone no longer reaches a state from which testing can continue: for example it shows an error at every power-on, including a normal one.
2. The owner and the orchestrator decide that stock recovery must be back before the next increment.

A test image that hangs, shows nothing, or is refused when started with the recovery keys does **not** require R4: R1 ends it, and R2 and R3 are unaffected (Inference: separate partitions and separate key paths, [gt-i9195.md](../hardware/gt-i9195.md#recoverability-after-failed-boot-experiments)).

**R4, step by step** (proposed):

```sh
# PROPOSED. Not to be run until the approved issue exists and case 1 or 2 is agreed in it.
sha256sum "<private firmware directory>/recovery.img"     # must equal the value recorded for E-9
heimdall flash --<RECOVERY_PIT_NAME> "<private firmware directory>/recovery.img" --no-reboot
```

1. Hash check first, as in section 3. **Stop** if it differs.
2. Enter Download mode and detect the phone (D1–D3), write (D4), wait, unplug, remove the battery (D5, D6).
3. Start with the recovery keys once. Expected: the stock recovery menu, as recorded in E1. Select **reboot system now** only.
4. Record the write and its result (section 11).

**Excluded from this plan, and from any plan:**

- **The full stock firmware flash.** It restores `system`, `boot`, `recovery` and the modem, and it **also rewrites bootloader images** ([gt-i9195.md](../hardware/gt-i9195.md#recovery-mechanisms), mechanism 4). Rule 2 forbids writing the bootloader chain and `modem` under any plan, so this is not a rescue route here, however bad the state.
- Writing `BOOT`, repartitioning (`--repartition`, `--pit`), Odin, and any other tool or partition.
- Qualcomm emergency download and hardware "debrick" methods: not usable plans (gt-i9195.md, mechanisms 6 and 7).

**If Download mode cannot be reached,** there is no further route in this plan. Stop, leave the battery out, and report. Do not try other key combinations or tools.

## 10. Knox

**What the owner accepts.** The first non-Samsung image written to `RECOVERY` is reported to set the Knox warranty bit permanently: `KNOX WARRANTY VOID: 0x1`, described as a hardware fuse that cannot be reset ([gt-i9195.md](../hardware/gt-i9195.md#bootloader-lock-and-knox), Community). Whether this unit's bootloader has Knox at all depends on its firmware and is read from the status lines (E-7). The owner accepts that:

- the mark is permanent and no later step, including restoring stock images, removes it;
- Samsung's Knox features, and anything that checks the bit, may stop working on this phone;
- it happens at the first write, W1, whichever image that is, and whether or not the trial succeeds.

**Where the acceptance is recorded.** In the owner's own comment on the write-plan issue, in the owner's words, before the orchestrator's approval (E-4). The Phase 2 evidence summary refers to that comment; it is not recorded anywhere else.

**Photographs.** The Download-mode status lines are photographed and transcribed:

1. **before** the first write: step D2 of W1, compared with the Phase 0 record (F2);
2. **after** the first image's trials: step S3;
3. **after** the last trial: step S3 again.

The transcriptions go into the evidence (section 11). A changed line is a result to record, not a reason to stop, unless it reports a lock or write protection that was not there before.

**Rule 4.** Rule 4 forbids bootloader unlocking and Knox or security-setting changes. This plan makes no such change on purpose: it unlocks nothing, sets nothing, and uses no exploit. The warranty bit changing is a side effect of the write that the ROADMAP's entry gate requires the owner to accept. This draft reads rule 4 as not forbidding that side effect once accepted; **the owner and the orchestrator confirm or correct that reading** (E-15).

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
| Trial number, image name and SHA-256, date and time | The evidence table |
| The video, from before the keys are pressed to after the battery is removed | `$EV2/private/` |
| The still photograph of the screen | `$EV2/private/` |
| The outcome, by its row in section 6 or 7 | The evidence table |
| The rows as typed, and the output and PNG of `tools/read_rows.py` | `$EV2/`. The rows are register values, not identifiers. |
| Times: key release to picture; picture to battery removal, or to a reset | The evidence table, read from the video |
| Any failure, what was done to recover, and the state afterwards | The evidence table |

**At the end**, the six items TESTING.md lists for every device session:

1. The date, who performed it, the phase (2) and the step IDs of this plan.
2. The device: model and the bootloader and build versions, as in the Phase 0 summary, with identifiers redacted.
3. The exact images: the commit, the `make` targets (`make check`, `make payload-invalid`) and the SHA-256 of every image written.
4. The observed result of each step, the number of trials, and how many showed the pass picture.
5. Every failure, the recovery action, and the state afterwards.
6. A statement of every write made: which of W1–W4, when, and that nothing else was written.

Also: the reboot counts; the three status-line transcriptions (section 10); the entry state decoded from the rows; the watchdog observation; and the state of the partitions after the phase, which is "`RECOVERY` holds `<image>`; no other partition was written by this plan". Download mode cannot read a partition back ([gt-i9195.md](../hardware/gt-i9195.md#recovery-mechanisms)), so that statement rests on the list of writes and on what `RECOVERY` starts, not on a read-back.

**Where the redacted summary goes.** A pull request adds it under `docs/evidence/phase-2/`, for the orchestrator's review. Never committed: videos, photographs, the session log, the PIT file, firmware, and any IMEI, serial number, MAC address or account name.

## 12. What this plan does not do

- **No write to `BOOT`.** A normal power-on keeps loading the untouched `BOOT`.
- **No lk2nd**, and no other third-party bootloader. Method B is a separately reviewed later option.
- **No normal power-on boot of Revival OS.** This plan proves execution from the recovery keys only. The normal power-on route is a separate milestone with its own 5 of 5, and it stays open.
- **No on-device exception test.** By decision A the exception path is tested in QEMU (`qemu-payload-fault-halts`), and on-device exception behaviour is deferred to Phase 3a.
- No payload-triggered reset, no watchdog petting or disabling, no UART.
- No change to the payload or to either image. A different hash is a different plan.
- No erase, wipe or factory reset, and no recovery-menu action other than **reboot system now**.
- No full stock firmware flash (section 9).
- No hosted CI run, and no merge.

## Unknown and pending

Everything this draft leaves open, in one place.

| Item | Status | Resolved by |
| --- | --- | --- |
| PIT name, identifier and size of the recovery partition | Pending | F5 (E-8) |
| Phase 0 passed, with reviewed evidence | Pending | E-1 |
| Phase 1 recorded as passed | Pending | E-2 |
| Installed build identifiers; Download-mode status lines | Pending | E-6, E-7 |
| Stock `recovery.img` for the installed build: size and SHA-256 | Pending | E-9 |
| Recovery keys 3 of 3; battery exit from Download mode 3 of 3 | Pending | E-12 |
| The commit on `main` to build from | Pending | E-11 |
| Order of the two images; maximum number of writes | Pending decision | E-14 |
| The reading of rule 4 | Pending decision | E-15 |
| Filming times; whether the eight-row picture counts as the pass; whether W3 is allowed | Pending decision | The issue's review |
| Does this build's Android rewrite `RECOVERY` at boot? | Unknown | E-13 (the two files), then the phone if Android starts |
| What the phone shows after a `--no-reboot` write, on this unit | Unknown | Step D5 |
| Does Heimdall 2.1.0's end-of-session code match the original project's? | Unknown (source not fetched) | Step D5 shows the behaviour |
| Are bytes of `RECOVERY` beyond the image's length changed by the transfer? | Unknown | Not resolved; not relied on |
| How the bootloader rejects an image, and what state that leaves | Unknown | Section 7 |
| Whether the bootloader checks the magic at all | Unknown | Section 7 |
| Whether the bootloader adds text over the picture | Unknown | The first trial |
| Whether the Knox bit exists on this unit and changes | Unknown | Section 10's photographs |
| The five phone-only questions | Unknown | Section 8, in part |

## Sources

Checked 2026-11-11. Line numbers refer to the pinned tag or commit.

- AOSP `system/core`, tags `android-4.4.2_r1` and `android-4.2.2_r1`, `rootdir/init.rc`: <https://github.com/aosp-mirror/platform_system_core/blob/android-4.4.2_r1/rootdir/init.rc>
- AOSP `build`, tag `android-4.4.2_r1`, `tools/releasetools/ota_from_target_files`: <https://github.com/aosp-mirror/platform_build/blob/android-4.4.2_r1/tools/releasetools/ota_from_target_files>
- LineageOS wiki, Samsung recovery installation template at `bc00760c9307ebf166ccfbfd933ad957d342067d`, and the device data file at `8e9d82c86a4913c66419b7e0d1ab42de18652fa5`: <https://github.com/LineageOS/lineage_wiki>
- TWRP, Samsung Galaxy S4 Mini (International LTE): <https://twrp.me/samsung/samsunggalaxys4minilte.html>
- Heimdall, installed: `heimdall help` and the `heimdall(1)` manual page of Ubuntu package `heimdall-flash` 2.1.0-1build1 (homepage <https://git.sr.ht/~grimler/Heimdall/>; its source could not be fetched on the day)
- Heimdall, original project at `3997d5cc607e6c603c6e7c0d07e42e9868c62af2` (`BridgeManager.cpp`, `FlashAction.cpp`) and `Linux/README` at `8709370bc48310604dfd4407538f650b3cc4f0ae`: <https://github.com/Benjamin-Dobell/Heimdall>
- In this repository: [AGENTS.md](../../AGENTS.md#hardware-safety-contract), [ROADMAP.md](../../ROADMAP.md#phase-2--first-bare-metal-boot), [TESTING.md](../TESTING.md#recording-evidence), [gt-i9195.md](../hardware/gt-i9195.md), the [Phase 0 checklist](../phase-0/hardware-verification-checklist.md), [boot-payload-research.md](boot-payload-research.md), and the orchestrator's [PR #10 comment](https://github.com/revival-systems/revival-os/pull/10#issuecomment-6792632937)

The downloaded source files were read outside this repository and are not committed.
