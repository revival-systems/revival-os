# Phase 2 console session: 2026-11-19 (plan v5, amendment 1)

- **Performed by:** the owner, at the phone and in the owner's own `script` terminal: every physical step and every command that contacts the phone. The implementer (Claude Code on the Ubuntu write host) gave the steps from the plan, read the session log and the host's kernel log, and typed the screen text from the owner's photograph.
- **Plan:** [write plan v5](https://github.com/revival-systems/revival-os/blob/b170d3c2004e419fb85081c50898cce1069b7c2b/docs/phase-2/write-plan-draft.md) (file SHA-256 `ad1518762072b6f2d3230ac13fbe8e5b90ba0f7680d0e36837ca8537bb10bd87`, unchanged since the [2026-11-18 session](2026-11-18-v5-session.md)) and its [amendment 1](https://github.com/revival-systems/revival-os/issues/28#issuecomment-6994577826) in issue #28 (created and last updated 2026-11-18T23:22:20Z), approved by the reviewer. The owner's approval is the standing one of AGENTS.md rule 1. Phase 2, method A, `RECOVERY` only, one write (C1). Task R-17.
- **Result: no stop.** C1 ended `RECOVERY upload successful` with exit status 0. `console.img` started from `RECOVERY` in 3 of 3 trials and showed the same report each time (Owner-confirmed). The one photograph received shows the whole report, readable to the last character: `SELFTEST 22BECBA4 OK`, the handoff values of 2026-11-18, ten tag lines, the kernel command line, `MDP4 88100000 IS FB` and `TICK 00000056`. Download mode was reached after the trials (S3). After one Android start, the recovery keys showed the stock recovery menu (S4).
- **Not yet established: that the counter goes up, and the time of one counter step.** Trial 1's two photographs, with their times and TICK values, have not been received. The owner deferred them to a later step. One photograph was received for the three trials, and it does not say which trial it is from.

All times are CET, on 2026-11-19. "Kernel log" means the host's `journalctl -k`. Labels: **Measured** (read by the implementer from a log, a command's output or a photograph), **Owner-confirmed** (stated by the owner during the session), **Inference**, **Not established**.

## 1. Date, people, phase and steps

| Item | Value |
| --- | --- |
| Date | 2026-11-19, 08:35 to 11:20. Phone steps from 09:10 to about 11:20 |
| Who | The owner performed the steps. The implementer gave them in groups at the owner's request (section 9) and read the results |
| Phase | 2 |
| Steps run | P0–P6; section 3 with amendment 1's two added lines; C1 (D0–D6); trials 1 to 3 (T1–T5, T7); S3 (D1, D2, D3, D6); S4; S5 |
| Steps not run | W4 (its condition did not arise); A1–A5 (no unplanned Android start was reported); the transfer-failure procedure (the transfer did not fail); T6 (amendment 1, point 5) |

## 2. Device

The GT-I9195 of the [Phase 0 record](../phase-0/2026-11-13-linux-retest.md) and of the [2026-11-18 session](2026-11-18-v5-session.md), with the installed build `I9195XXSCQAN` / `I9195OXXCNK2`. No identifier is recorded here.

## 3. Images

| Item | Value | Label |
| --- | --- | --- |
| Commit | `b170d3c2004e419fb85081c50898cce1069b7c2b` (tree `a29bc452a56e6f84f22350055d0b6ea6602a7d8f`), in a fresh clone in a new, empty directory (`mktemp -d`), made with `TMPDIR` unset and `GIT_LFS_SKIP_SMUDGE=1`; `git status --short` printed nothing | Measured |
| `make` target | `make check`: 104 PASS lines, no FAIL line, no NOTE line, `exit=0`. `PASS payload-frozen` (`payload.bin 8ee519ae…`, `payload.img bde09074…`) and `PASS console-frozen` (`console.bin afe35140…`, `console.img 9457fd48…`). Both `find` lines printed nothing. `ls build/boot-serrano/*.img` printed `build/boot-serrano/payload.img` only; `ls build/boot-serrano-console/*.img` printed `build/boot-serrano-console/console.img` only | Measured |
| C1 image | `console.img`, 12,304 bytes, `9457fd486719ccb379a4bc7f1aa166214cab948129898d23f1b41908b9ac0249`, equal to amendment 1 | Measured |
| Its boot header | Kernel 6,380 bytes at `0x80208000`; ramdisk 1 byte at `0x81200000`; second stage 0 bytes; tags at `0x80200100`; page 2,048; name and command line empty. Read by the implementer after the session from the same file, hash unchanged | Measured |
| Other images | `payload.img` `bde09074…ce02` and the stock `recovery.img` `0e309559…79c6` (the private copy named in section 1 of issue #28): hashes as in issue #28. Neither was written | Measured |
| Heimdall | `v2.1.0` (`heimdall version`), run as the normal user | Measured |

## 4. Results by step

| Step | Time | Result | Label |
| --- | --- | --- | --- |
| Authority | 08:35 | Plan v5 and amendment 1 read in full; the amendment unedited; its claims matched the repository (main at `b170d3c`, the plan's hash, the frozen hashes, no change under `boot/` since `40e224b`) | Measured |
| P0 | 08:44 | Rested, at least two free hours. The task said about 90 minutes; the implementer asked for the plan's two hours | Owner-confirmed |
| P1 | 08:44 | Issue #28: body unchanged (SHA-256 `4ebec513…676f`); every box in section 2 ticked; the E-4 statement and both approvals present | Measured |
| P2 | 08:48 | Battery and cable as required: "everything is good, everything is fine" | Owner-confirmed |
| P3 | 09:02:46 | Session log started with `script -q -f -a` | Measured |
| P4 | 09:02–09:03 | Section 3 above | Measured |
| P5 | before 09:10 | The camera recorded the session. Whether its clock was set to the host's was asked and not answered | Owner-confirmed (recording); Not established (clock) |
| P6 | 09:02:46 | `set +o history; history -c`, the first lines in the session terminal | Measured |
| C1 D0–D1 | before 09:10 | Video started; the download screen. The spoken label was given in the step and not reported back | Owner-confirmed |
| C1 D2 | before 09:10 | Status lines "same" as at S3 on 2026-11-18 (section 6); no reactivation-lock line. Photographed; the photograph was not received | Owner-confirmed |
| C1 D3 | 09:10:03 (kernel log) | `04e8:685d` (Download mode); `Device detected` | Measured |
| C1 D4 | 09:14:17 | The write: section 5 | Measured |
| C1 D5 | — | Not reported at the time; the photograph was not received. Asked at 11:19 when text had appeared on the phone, the owner placed the only text seen at S4 | Owner-confirmed |
| C1 D6 | 09:56:47 (kernel log: USB disconnect) | Cable unplugged, 42 minutes after the write ended (section 9) | Measured |
| Trials 1–3 | 09:56:47 to 10:16 | Section 7 | — |
| S3 D1 | before 11:09 | The download screen | Owner-confirmed |
| S3 D2 | — | No stop was reported. The lines were not reported and the photograph was not received | Not established |
| S3 D3 | 11:09:06 (kernel log) | `04e8:685d` (Download mode); `Device detected` | Measured |
| S3 D6 | 11:12:00 (kernel log: USB disconnect) | Cable unplugged | Measured |
| S4, Android start | 11:12–11:19 | Normal power-on, the lock screen, two minutes, power-off from Android's menu: given as one group, and the owner reported the result rather than each step. The kernel log shows no USB device after 11:12:00, so the cable was out for this start, as the reviewer's ruling 4 of 2026-11-18 asks | Owner-confirmed (result); Measured (no USB device) |
| S4, recovery keys | by 11:19 | **The stock recovery menu.** Photographed; the photograph was not received | Owner-confirmed |
| S4, end | by 11:20 | **reboot system now**; Android started normally ("I recovered normally to Android"). The power-off from Android's menu afterwards was not reported | Owner-confirmed |
| S5 | — | Nothing more written. The session log holds no command after S3's `heimdall detect`; the kernel log shows no USB device after 11:12:00 (read at 11:38) | Measured |

## 5. The write

Entered in the session terminal, from the clone's root, with `date +%T` on the line directly before and `echo "exit=$? $(date +%T)"` on the line directly after. The terminal echoed the three pasted lines before running them. Heimdall's output is quoted complete. The progress line is overwritten in place; the values it showed are given in brackets.

**C1.** The command, as in amendment 1:

```text
09:14:17
heimdall flash --RECOVERY build/boot-serrano-console/console.img --no-reboot

Heimdall v2.1.0

Copyright (c) 2010-2017 Benjamin Dobell, Glass Echidna https://glassechidna.com.au
Copyright (c) 2021-2024 Henrik Grimler
This software is provided free of charge. Copying and redistribution is encouraged.

Initialising connection...
Detecting device...
Claiming interface...
Initialising protocol...
Resetting device...
Protocol initialisation successful.

Beginning session...

Some devices may take up to 2 minutes to respond.
Please be patient!

Session begun.

Downloading device's PIT file...
PIT file download successful.

Uploading RECOVERY
100%        [0% 100%]
RECOVERY upload successful

Ending session...
Releasing device interface...

exit=0 09:14:25
```

The kernel log records the USB reset of "Resetting device..." at 09:14:19. No line starts `ERROR` or `WARNING`; there is no `Rebooting device...` line; no partition other than `RECOVERY` is named. The session lines are the ones of WS and W2 ([2026-11-18 record](2026-11-18-v5-session.md#5-the-writes)).

## 6. Status lines

**Before C1 (D2):** the same as at S3 on 2026-11-18 (Owner-confirmed, compared on the phone; photographed, photograph not received):

```text
ODIN MODE
PRODUCT NAME: GT-I9195
CURRENT BINARY: Custom
SYSTEM STATUS: Official
KNOX KERNEL LOCK: 0x0
KNOX WARRANTY VOID: 0x1
CSB-CONFIG-LSB: 0x30
BOOTLOADER RP SWREV: 2
WRITE PROTECTION: Enable
```

No reactivation-lock line. **At S3 (D2), after C1 and the trials:** not reported (section 4). Whether C1 or the console image changed a status line is not established.

## 7. Trials

Every trial began from a removed battery, with the cable unplugged, and used the recovery keys as in T2. All three count toward the series: no Android start, no reset and no Download-mode entry was reported between C1 and trial 3 (Owner-confirmed). The kernel log shows no USB device between 09:56:47 and 11:09:06 (Measured).

| Trial | Screen | Photograph received | Window asked |
| --- | --- | --- | --- |
| 1 | The report, the same in all three trials | Not identified (below) | 10 minutes from the first text |
| 2 | The same | Not identified | 2 minutes |
| 3 | The same | Not identified | 2 minutes |

The owner's words at 10:16: "3 times appear the same picture, so I'm sending to you here 1 picture." One photograph was received, a copy sent through a chat, without its metadata, so neither its trial nor its time is known. It is sharp, square on, and shows the whole screen. **Trial 1's two photographs (T4, amendment 1 point 4) and their times have not been received.**

**The screen text, typed by the implementer from that photograph** (40 lines of 30 columns; tag lines are indented one space and command-line words two; a word that runs past the 30th column continues in the first column of the next line). The console font's lowercase `g` resembles a `9` in the photograph; it is typed as `g`:

```text
REVIVAL OS
PHASE 2 IMAGE 2
SELFTEST 22BECBA4 OK
R0 00000000 R1 00000E8F
R2 80200100 R3 00001141
MACH 3727
CPSR 60000193 SVC I1 F0 A1 T0
SCTLR 00C5487A M0 C0 I0 A1 V0
ENTRY 80208000 OK
ATAGS 80200100
 CORE
 INITRD2 81200000 SZ 00000001
 REVISION 00000005
 SERIAL HIDDEN
 MEM 20000000 AT C0000000
 MEM 07E00000 AT 80200000
 MEM 00800000 AT 8E800000
 MEM 00300000 AT 8F800000
 MEM 00100000 AT 8FE00000
 MEM 30000000 AT 90000000
 CMDLINE mem=<4> console=<4>
  sec_log=<18> sec_dbg=<18>
  sec_debug.reset_reason=<10>
  normal_off=<1>
  lcd_attached=<1>
  etb_buf=<17>
  androidboot.debug_level=<6>
  sec_debug.enable=<1>
  sec_debug.enable_user=<1>
  msm_rtb.enabled=<1>
  androidboot.cp_debug_level=<
6>
  sec_debug.enable_cp_debug=<1
> cordon=<32> connie=<50>
  sysscope=<10> loglevel=<1>
  samsung.hardware=<8>
  androidboot.emmc_checksum=<1
> androidboot.warranty_bit=<1+
MDP4 88100000 IS FB
TICK 00000056
```

The command line shows each word's name and the length of its value, never the value ([console-payload.md](../../phase-2/console-payload.md)). The `+` in the last cell of line 38 means the report was longer than its 38 lines. Every wrapped line is exactly 30 characters, which fits the 30-column grid.

**Against the expected screen of amendment 1:** lines 1 to 10 match it character for character (`R3` is not fixed). The tag lines follow, the `+` is where the document puts it, and the last two lines are the fixed `MDP4 88100000 IS FB` and a `TICK` line. No line is sheared, doubled or missing, no earlier picture shows below the text, and there are no stripes.

**The outcome row.** The report with `MDP4` and a `TICK` line: either "a TICK counter going up" or "counter stuck for the whole window". Both rows say continue. Which one applies is not established until two photographs of one trial, or the video, are read.

**Times.** The counter's step time, key release to first text, and the windows' lengths: **not read**. The three trials lie between the cable's disconnect at 09:56:47 and the owner's message at 10:16, 19 minutes. The windows asked add up to 14 minutes, plus three starts and three battery removals. Whether trial 1 ran its full 10 minutes is not established. No reset was reported in any trial.

## 8. The stock recovery menu

**S4, after the Android start:** the owner reported the stock recovery menu and selected **reboot system now**. The photograph has not been received, so the menu is not transcribed here. The owner reported a text "something like 'recovery mode enter'" at S4 only, without its exact words or colour. On 2026-11-18 the S4 menu showed four yellow lines at the bottom, beginning `# MANUAL MODE #` ([section 8 of that record](2026-11-18-v5-session.md#8-the-stock-recovery-menu)); whether the text reported today is one of those is not established.

## 9. Departures from the procedure, and observations outside its steps

1. **Steps given in groups (the reviewer's clarification 3, one step per message).** At 08:48 the owner asked for the steps "all at once, like not repetition", because the owner already knew the process. The implementer gave them in groups and kept three stops: after section 3 (before the phone), after D3 (before the write), and after the write (D4: nothing touched until the implementer had read the output). The order of the steps did not change.
2. **The phone stayed connected in Download mode for 42 minutes after the write.** Heimdall ended at 09:14:25; D5 and D6 were given at 09:15:28; the cable was unplugged at 09:56:47 (kernel log). D5's report and photograph did not come at the time. The plan sets no limit there. No command was typed in that span (session log) and the kernel log shows no event for the device between the write's reset at 09:14:19 and the disconnect.
3. **Photographs.** One photograph was received for the three trials, as a chat copy without metadata and with no trial named. Not received: trial 1's second photograph, the times and TICK values of trial 1's two photographs, the photographs of trials 2 and 3, and those of C1 D2, D5, S3 D2 and S4. At 11:38 the owner asked for the report now and put the counter off to a later step: "later we're gonna see the tick". So T4's second still and T7's counter times are open (section 13).
4. **Not reported:** the camera clock (P5), the S3 status lines, and the power-off after S4's final Android start.

## 10. Failures, recovery and state

No step failed and no stop condition was met. The transfer-failure procedure, the "If Android starts" steps and the stop report were not needed.

**State afterwards:**

- The phone's last reported state: Android started normally after **reboot system now** at the end of S4 (Owner-confirmed). Whether it was then powered off was not reported.
- **`RECOVERY` holds a working stock recovery.** Known from: S4's recovery keys showed the stock recovery menu, after one Android start, with no write after C1. Before that start, `RECOVERY` held `console.img`: it started in all three trials. So Android replaced it with no host write, as on 2026-11-18. Download mode cannot read a partition back, so this rests on the list of writes and on what `RECOVERY` starts, not on a read-back.
- The status lines last read are those of C1 D2: `CURRENT BINARY: Custom`, `KNOX WARRANTY VOID: 0x1`.

## 11. Writes

| Write | Image | `date` before | USB reset (kernel log) | Exit status | Result |
| --- | --- | --- | --- | --- | --- |
| C1 | `console.img`, `9457fd48…0249` | 09:14:17 | 09:14:19 | `exit=0` (09:14:25) | `RECOVERY upload successful` |

**Nothing else was written.** Evidence:

- **Session log:** it holds exactly one `heimdall flash` command, `--RECOVERY`, and one Heimdall banner, so it ran once. The only other commands that contact the phone are `lsusb` and `heimdall detect`, at C1 D3 and S3 D3.
- **Kernel log:** it shows exactly one USB reset of the Download-mode device, at 09:14:19, C1's "Resetting device...".
- **Images:** no other partition, image, tool or option was used.
- **Budget:** C1 is amendment 1's one write. W4 was not used.

## 12. What this answers

**Amendment 1's pass criterion:** "the report's text is the same in 3 of 3 trials (counter aside), with `SELFTEST 22BECBA4 OK` each time and the counter seen going up in the video. S3 and S4 must be shown either way."

- The same text in 3 of 3 trials: Owner-confirmed. One photograph read by the implementer.
- `SELFTEST 22BECBA4 OK`: on the photograph read (Measured); in all three by the owner's "same picture" (Owner-confirmed).
- The counter going up: **not established** (section 13).
- S3 shown (Measured); S4 shown (Owner-confirmed; photograph not received).
- So the criterion is met except for the counter. Whether a pass stands before the counter is shown is the reviewer's decision.

**What the screen shows** (Measured from the photograph, unless labelled):

- **The image's self-test passed on the phone**, and the image says it entered at `0x80208000` (`ENTRY … OK`).
- **The handoff is the same as image 1's on 2026-11-18**, now as text: `r0 = 0`, `r1 = 0xE8F` (machine 3727), `r2 = 0x80200100`, CPSR `0x60000193` (SVC, IRQ masked, FIQ not masked, abort masked, ARM), SCTLR `0x00C5487A` (MMU, caches and high vectors off, alignment checking on).
- **`r3 = 0x00001141`**, read for the first time. What it holds is not established.
- **The tag list at `r2`:** `CORE` with no page size; `INITRD2 81200000 SZ 00000001`, which equals the boot header's ramdisk address and size (section 3), so the bootloader passes those two header fields through unchanged; `REVISION 00000005`; a serial-number tag (its words not drawn); six memory regions; and the kernel command line. The header's command line is empty, so every command-line word shown comes from the bootloader (Inference from the empty header field). The report stops at line 38: the rest of the command line, and any tag after it, are not shown.
- **The memory regions:** `0x07E00000` at `0x80200000`, `0x00800000` at `0x8E800000`, `0x00300000` at `0x8F800000`, `0x00100000` at `0x8FE00000`, `0x30000000` at `0x90000000` and `0x20000000` at `0xC0000000`, 1,418 MiB in all. The framebuffer at `0x88100000` lies in none of them, in the gap from `0x88000000` to `0x8E800000`. That the bootloader keeps the framebuffer out of the memory it hands over is an Inference.
- **`MDP4 88100000 IS FB`:** the display register names the buffer the image draws in, as row 9 of image 1 did.
- **A `TICK` line** with the value `00000056` at the moment of the photograph. Whether it goes up: not established.

**The five phone-only questions** ([section 8 of the plan](../../phase-2/write-plan-draft.md#8-the-five-phone-only-questions)): question 2 is answered again, with the same values as on 2026-11-18. Question 3: the display still scans out of `0x88100000`. Question 4: no reset was reported in any window; the windows' lengths are not read. Questions 1 and 5: not tested by this image.

## 13. Open and not established

- **The counter.** Trial 1's two photographs, each with its time to the second and its TICK value, which give the time of one counter step and show the counter going up. The owner deferred them to a later step (section 9).
- **The other photographs:** trials 2 and 3, C1 D2, D5, S3 D2 and the S4 menu; and which trial the photograph received is from.
- **Times from the videos:** key release to first text, and each window's length.
- **The S3 status lines,** and so whether C1 or the console image changed a status line.
- **The S4 text** reported as "something like 'recovery mode enter'": its exact words and colour.
- **`r3`'s meaning,** and the part of the report past line 38.
- **`RECOVERY`'s bytes:** not read back (section 10).

## Not committed

Private, outside every repository: the session log, the host's kernel log, the owner's videos and photographs, and the implementer's notes and typed screen text. No identifier, serial number, photograph or log is in this file.
