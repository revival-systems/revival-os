# Phase 2 write session: 2026-11-14 to 2026-11-15 (stopped at W1)

- **Performed by:** the owner, at the phone and in the owner's own terminal: every physical step and every command that contacts the phone. The implementer (Claude Code on the Ubuntu write host) prepared each step from the plan, checked the host-only results and read the session log.
- **Plan:** [write plan v4](../../phase-2/write-plan-draft.md) at commit `301a9574d509e104de7dcda4bdf22e3fcaecafc5` on `main`, approved in [issue #23](https://github.com/revival-systems/revival-os/issues/23) by the reviewer and the owner, with the reviewer's five clarifications. Phase 2, method A, `RECOVERY` only.
- **Result: W1 failed; the plan stopped at step D4.** All three runs of the W1 command ended with `ERROR: RECOVERY upload failed!`. The stop report is the [comment on issue #23](https://github.com/revival-systems/revival-os/issues/23#issuecomment-6886465423); a [correction](https://github.com/revival-systems/revival-os/issues/23#issuecomment-6887493736) followed once the full logs were read. Writes are suspended on the issue until an amendment is approved there. Whether and how the session continues is the reviewer's and the owner's decision.

> **Correction (2026-11-15).** The first commit of this file (`40013f3`) recorded two W1 runs and stated that Android had not been started since W1. That was wrong. The completed session log (which ends `Script done … 01:29:41`) and this host's kernel log (`journalctl`) show **three** runs of the W1 command, and that the phone was booted into Android and then flashed a third time **after** the stop report was posted (01:17:32). This file now records all three runs and the post-stop events, each with its source. The device's serial number, which is visible in the kernel log, is not reproduced here.
>
> **Further corrections (2026-11-15, midday).** After the reviewer's review of the first correction, four statements were corrected to what the sources establish: the bootloader's on-phone success line (Heimdall does not print the phone's messages, and no one transcribed the screen); E-17's command (a `heimdall download-pit`, not a detect); the idle-log window (bounded by the kernel log rather than asserted); and the 100 % download bar (owner-confirmed only for the runs the owner reported). The timing of run 2 is added as section 7.

All times are CET. P1 to P5 ran on 2026-11-14, the rest on 2026-11-15.

## 1. Date, people, phase and steps

| Item | Value |
| --- | --- |
| Date | 2026-11-14 23:02 to 2026-11-15 01:29 |
| Who | The owner performed the steps; the implementer read the results |
| Phase | 2 |
| Steps run | P1–P5, then W1 (D0–D4), which failed; then the transfer-failure procedure F-4 to F-7. After the stop report, and outside the approved plan: an Android boot and a third run of the W1 command |
| Steps not run | D5, D6; T1–T7; S1–S5; W2, W3, W4; the A steps |

## 2. Device

The GT-I9195 of the [Phase 0 record](../phase-0/2026-11-13-linux-retest.md), with the installed build `I9195XXSCQAN` / `I9195OXXCNK2`. No identifier is recorded here.

## 3. Images

| Item | Value | Label |
| --- | --- | --- |
| Commit | `301a9574d509e104de7dcda4bdf22e3fcaecafc5` (tree `5488ec67349a09eff2d193826ecb673932db0e67`), in a fresh clone made in a new, empty folder with `GIT_LFS_SKIP_SMUDGE=1` | Measured |
| `make` targets | `make check` (83 PASS lines, no FAIL line, `exit=0`, `PASS payload-frozen`), then `make payload-invalid` (`INVALID-MAGIC-NEGATIVE-TEST`) | Measured |
| Image whose write was attempted | `payload-invalid.img`, 6,160 bytes, `34dc91c64811346a3766e71044c2260340fadec0a0ea327e4126a1ef7a584d7b` | Measured; equal to section 1 of issue #23, compared by script |
| Also checked, not written | `payload.img` `bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02`; stock `recovery.img` `0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6` | Measured; equal to section 1 of issue #23 |
| Heimdall | `v2.1.0`, run as the normal user, no `sudo` | Measured |

## 4. Results by step

| Step | Time | Result | Label |
| --- | --- | --- | --- |
| P1 | 23:02:54 | Issue #23 checked by script: no open box in section 2; the E-4 statement, the reviewer's approval and the owner's approval are present | Measured |
| P2 | before 23:45 | A new battery; it lies flat; charge 100 %. The cable and port of E-17. The label's model and capacity were not recorded | Owner-confirmed |
| P3 | 23:45:03 | Session log started with `script -q -f -a`. The new, empty folder of clarification 2 was made by the implementer at 23:43 | Measured |
| P4, first run | 23:45–23:47 | The `cd` into the empty folder was not entered, so the clone was made in the home folder. Every check passed there. Not used, because clarification 2 requires the empty folder | Measured |
| P4 | 23:50–23:51 | In the empty folder: HEAD `301a957`; `git status --short` printed nothing; the results of section 3 above | Measured |
| P5 | — | The camera works and its clock matches the host's | Owner-confirmed |
| D0, D1 | before 00:39 | Video started; the warning screen, then the download screen | Owner-confirmed |
| D2 | 00:39 | The status lines below, identical to F2 ([section 10](../../phase-2/write-plan-draft.md#10-knox)); no reactivation-lock line. Photographed | Owner-confirmed |
| D3 | before 00:45:27 | `lsusb`: `04e8:685d` (Download mode); `heimdall detect`: `Device detected` | Measured |
| — | 00:45:27–00:51:48 | The session log ended and was restarted with `-a` three times. The host kernel log shows no device reset between 00:44:13 and 00:53:31, so no Heimdall session ran while the log was stopped; it also records a USB disconnect at 00:45:59 and a reconnect at 00:46:02 | Measured (kernel log) |
| D4, W1 | from 00:51:48 (pts/4) | `heimdall flash --RECOVERY build/boot-serrano/payload-invalid.img --no-reboot`, from the clone's root. **Run three times in all** (see section 6). The "Resetting device" step of each run is timed from the kernel log: run 1 at 00:53:31, run 2 at 00:54:46. Each printed the output below. `echo "exit=$?"` after run 2: `exit=1` | Measured (session + kernel log) |
| D4 | — | The owner watched the phone's download bar reach 100 % on the runs the owner reported (runs 1 and 2). Whether it also reached 100 % on run 3 is not established | Owner-confirmed (runs 1–2) |
| F-4, F-5 | about 01:07–01:15 | Two photographs at least 5 minutes apart, the same: the Download-mode screen | Owner-confirmed |
| F-6 | 01:15:20 | Cable unplugged (kernel log: USB disconnect). Battery removed; the exact time was not given | Measured (unplug); owner-confirmed (battery) |
| Stop report | 01:17:32 | Posted as a comment on issue #23. Everything below happened **after** this and is outside the approved plan | Measured |
| — (after the stop) | 01:27:38–01:27:56 | The phone came up in Android (kernel log: USB `04e8:6860`, Manufacturer SAMSUNG), then disconnected | Measured (kernel log) |
| — (after the stop) | 01:28:35 | Download mode re-entered (kernel log: USB `04e8:685d`) | Measured (kernel log) |
| W1, run 3 (after the stop) | 01:28:45 | The W1 command recalled from the shell history and run a third time, in the same terminal, as a fresh Heimdall session; the same output. Cable unplugged at 01:29:14; the session log closes at 01:29:41 | Measured (session + kernel log) |

Trials: none. No trial was run, so none counted and none showed the pass picture.

**Status lines before W1 (D2)**, the "before" state of section 10:

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

No status lines have been read since W1.

**Heimdall's output**, identical in all three runs. The copyright banner is left out.

```text
Heimdall v2.1.0

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
100%
ERROR: Failed to confirm end of file transfer sequence!
ERROR: RECOVERY upload failed!

Ending session...
Releasing device interface...
```

- No line starts `WARNING`. There is no `RECOVERY upload successful` line and no `Rebooting device...` line. No other partition is named. Heimdall prints only its own messages, not the phone's, and nobody transcribed the phone's screen, so whether the bootloader's success line `ODIN : partition '%s' updated` appeared on the phone is not recorded here.
- One session line differs from the lines E-17 recorded on this host ([write-host PIT read](2026-11-14-write-host-pit-read.md#heimdall-210-session-lines-on-this-host)): `Detecting device...` where E-17 has `Waiting for device...`. Every other line before the upload is the same. (E-17's command was `heimdall download-pit`, which printed `Waiting for device...`; W1's `heimdall flash` printed `Detecting device...`. The installed binary holds both strings; which command prints which line is not explained here.)

## 5. Failures, recovery and state

| Failure | What was done | Label |
| --- | --- | --- |
| W1 ended with `ERROR: Failed to confirm end of file transfer sequence!` and `ERROR: RECOVERY upload failed!` (D4 stop) | STOP. Transfer-failure procedure: F-4 photograph, F-5 a second photograph at least 5 minutes later (the same screen), F-6 cable unplugged, then battery removed. F-7: no trial, no further write under the plan | Measured (output); owner-confirmed (F-4 to F-6) |
| The W1 command was run a second time right after the first failed, and a third time after the stop report. The plan says a failed write is never repeated | Recorded. All three runs count against the four approved writes (reviewer's ruling, 2026-11-15) | Measured |
| After the stop report, the phone was booted into Android and then returned to Download mode for the third run | Recorded from the kernel log. Outside the approved plan | Measured (kernel log) |
| P4's first run was made outside the empty folder | P4 run again in the empty folder; the first clone was not used | Measured |

**State afterwards:**

- The last event in the logs is a USB disconnect at 01:29:14; the session log closes at 01:29:41. The phone's current physical state at the end of the session (battery in or out, and what the screen showed) is **not** established here, and Part B — the read-only checks that would have confirmed it — was cancelled (reviewer, 2026-11-15); the owner has since stated that the phone starts and works normally (section 8).
- `RECOVERY`: **unknown** (F-7). Each transfer reached 100 % on the host; the owner watched the phone's bar reach 100 % on runs 1 and 2, and whether it did on run 3 is not established. The end of the transfer was not confirmed. Heimdall does not print the phone's messages and nobody transcribed the phone's screen, so whether the bootloader's success line `ODIN : partition '%s' updated` appeared is not recorded. Download mode cannot read a partition back, so the content of `RECOVERY` cannot be established from this session.
- Android started once after the stop (01:27:38–01:27:56) and reached far enough to enumerate over USB. What it displayed is not recorded here.

## 6. Writes

| Write | Image | Time (reset step, kernel log) | Exit status | Result |
| --- | --- | --- | --- | --- |
| W1, run 1 | `payload-invalid.img`, `34dc91c6…4d7b` | 00:53:31 | Not entered | `ERROR: RECOVERY upload failed!` |
| W1, run 2 | the same | 00:54:46 | `exit=1` | `ERROR: RECOVERY upload failed!` |
| W1, run 3 (after the stop report) | the same | 01:28:45 | Not entered | `ERROR: RECOVERY upload failed!` |

All three runs named `RECOVERY` only. **Nothing else was written by any run:** no other partition, and no other image. W2, W3 and W4 were not run. The reviewer has ruled that all three runs count against the four approved writes.

## 7. Timing of W1 run 2 (added 2026-11-15)

Run 2 ended within about six seconds of its start. This bears on why W1 failed, so it is recorded here with its sources and its labels.

| Fact | Value | Label and source |
| --- | --- | --- |
| Run 2 "Resetting device" (USB reset) | 00:54:46 | Measured — host kernel log |
| Last time the session log was written for run 2 | 00:54:52 | Recorded — the implementer's stop-time note, made while the session was stopped (the log was later appended for run 3) |
| Elapsed, reset to end | about 6 seconds | Measured, from the two times above |
| A 3-second sleep after the session handshake | `usleep(3000000)` | Measured — disassembly of the installed `heimdall` v2.1.0 (`/usr/bin/heimdall`), a `usleep` call site at file offset 0x988c |
| The end-of-transfer wait is set to 120000 ms only when the device reports a non-zero packet size | a store of `0x1d4c0` (120000) guarded by a test-and-branch on the device-reported value | Measured — same binary, offsets 0x9870–0x98ab: a compare and a `test` on the reported value, then `movl $0x1d4c0,…`; when the value is zero the code branches past the store |
| The default wait | 30000 ms (30 seconds) | Inference for this binary — from the upstream source below; the installed binary may differ, though the disassembly matches it at the points checked |

Upstream source cited, with its exact address and the passage used. Repository `Benjamin-Dobell/Heimdall` (github.com/Benjamin-Dobell/Heimdall), file `heimdall/source/BridgeManager.cpp`:

- line 75: `kFileTransferSequenceTimeoutDefault = 30000 // 30 seconds`
- line 367: `fileTransferSequenceTimeout = kFileTransferSequenceTimeoutDefault;`
- lines 523–529: `unsigned int deviceDefaultPacketSize = beginSessionResponse.GetResult();` … `Sleep(3000); // Give the user time to read the message.` … `if (deviceDefaultPacketSize != 0) … { fileTransferSequenceTimeout = 120000; // 2 minutes! … }`
- line 1221: `success = ReceivePacket(fileTransferResponse, fileTransferSequenceTimeout);`
- line 1227: `Interface::PrintError("Failed to confirm end of file transfer sequence!\n");`

The line numbers are from the copy examined here; the one-line passages are quoted so they can be found if the numbering has drifted. These passages are the upstream project's, labelled **Inference** for the installed 2.1.0 binary, except the 3-second sleep and the conditional 120000 ms store, which the disassembly shows directly (**Measured**).

**What this shows (Measured):** a run of W1 sleeps 3 seconds after the handshake, then waits for the phone to confirm the end of the transfer for at most the timeout above, retrying the read a small number of times. Six seconds is far shorter than either the 120000 ms or the 30000 ms wait, and the few short retry pauses do not fill it either.

**Inference:** Heimdall did not wait out a timeout. The phone answered the end of the transfer quickly, with something Heimdall does not accept as the acknowledgement. That is consistent with the phone refusing the image; a transport fault would more likely show as a timeout or as repeated retries. This is still not proof, and Part B — the phone's screen and the recovery-key check that would have decided it — was cancelled (reviewer, 2026-11-15); no photograph or video of the night exists (Owner-stated), so it is not checked against the phone (section 8).

## 8. Closing: Part B not carried out (2026-11-15)

**Part B was not carried out.** The reviewer cancelled it on 2026-11-15, with its questions B1 to B4; nothing further is asked of the owner about the night of 2026-11-14 to 15.

**Owner-stated, relayed by the reviewer, 2026-11-15:** the owner has no photograph and no video of that night; the phone was in Download mode during the attempts; the owner has started the phone since, and it works normally.

With Part B cancelled, every item this file left "to be confirmed (Part B …)" is now **not established** and will not be checked against the phone: whether the download bar reached 100 % on run 3, and the phone's physical state at the end of the session.

The bootloader study ([pull request #26](https://github.com/revival-systems/revival-os/pull/26)) shows **from the code** that a recovery image whose first eight bytes are not `ANDROID!` is refused before the write; `payload-invalid.img`'s magic is `INVALID!`. That this is what the phone did at W1 stays an **Inference**: no one transcribed the phone's screen, and no photograph or video exists (Owner-stated).

## Not committed

Private, outside every repository: the session log, the host kernel log, the owner's video and photographs, and the implementer's notes. No identifier, serial number, photograph or log is in this file.
