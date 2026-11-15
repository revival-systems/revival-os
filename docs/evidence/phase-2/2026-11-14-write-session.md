# Phase 2 write session: 2026-11-14 to 2026-11-15 (stopped at W1)

- **Performed by:** the owner, at the phone and in the owner's own terminal: every physical step and every command that contacts the phone. The implementer (Claude Code on the Ubuntu write host) prepared each step from the plan, checked the host-only results and read the session log.
- **Plan:** [write plan v4](../../phase-2/write-plan-draft.md) at commit `301a9574d509e104de7dcda4bdf22e3fcaecafc5` on `main`, approved in [issue #23](https://github.com/revival-systems/revival-os/issues/23) by the reviewer and the owner, with the reviewer's five clarifications. Phase 2, method A, `RECOVERY` only.
- **Result: stopped at step D4 of W1.** Both runs of the W1 command ended with `ERROR: RECOVERY upload failed!`. The stop report is the [comment on issue #23](https://github.com/revival-systems/revival-os/issues/23#issuecomment-6886465423). Whether and how the session continues is the reviewer's and the owner's decision.

All times are CET. P1 to P5 ran on 2026-11-14, the rest on 2026-11-15.

## 1. Date, people, phase and steps

| Item | Value |
| --- | --- |
| Date | 2026-11-14 23:02 to 2026-11-15 01:15 |
| Who | The owner performed the steps; the implementer read the results |
| Phase | 2 |
| Steps run | P1–P5, then W1: D0–D4; then the transfer-failure procedure F-4 to F-7 |
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
| — | 00:45:27–00:51:48 | The session log ended and was restarted with `-a` three times. No command that contacts the phone ran while it was stopped | Measured |
| D4, W1 | 00:51:48–00:54:52 | `heimdall flash --RECOVERY build/boot-serrano/payload-invalid.img --no-reboot`, from the clone's root, **run twice**, one run after the other. Both runs printed the output below. `echo "exit=$?"` after the second run: `exit=1` | Measured |
| D4 | — | The download bar on the phone ran to 100 % | Owner-confirmed |
| F-4, F-5 | about 01:07–01:15 | Two photographs at least 5 minutes apart, the same: the Download-mode screen | Owner-confirmed |
| F-6 | before 01:15:41 | Cable unplugged, battery removed. The exact time was not given | Owner-confirmed |

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

**Heimdall's output**, the same in both runs. The copyright banner is left out.

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

- No line starts `WARNING`. There is no `RECOVERY upload successful` line and no `Rebooting device...` line. No other partition is named.
- One session line differs from the lines E-17 recorded on this host ([write-host PIT read](2026-11-14-write-host-pit-read.md#heimdall-210-session-lines-on-this-host)): `Detecting device...` where E-17 has `Waiting for device...`. Every other line before the upload is the same.

## 5. Failures, recovery and state

| Failure | What was done | Label |
| --- | --- | --- |
| W1 ended with `ERROR: Failed to confirm end of file transfer sequence!` and `ERROR: RECOVERY upload failed!` (D4 stop) | STOP. Transfer-failure procedure: F-4 photograph, F-5 a second photograph at least 5 minutes later (the same screen), F-6 cable unplugged, then battery removed. F-7: no trial, no further write | Measured (output); owner-confirmed (F-4 to F-6) |
| The W1 command was run a second time after the first run failed. The plan says a failed write is never repeated | Recorded. Not run a third time | Measured |
| P4's first run was made outside the empty folder | P4 run again in the empty folder; the first clone was not used | Measured |

**State afterwards:**

- The battery is out and the cable is unplugged.
- `RECOVERY`: **unknown** (F-7). The transfer reached 100 % on the host and on the phone's bar, and the end of the transfer was not confirmed. Download mode cannot read a partition back.
- The phone stayed on the Download-mode screen after both runs. Android has not been started since W1, and no recovery-key start has been tried.

## 6. Writes

| Write | Image | Time | Exit status | Result |
| --- | --- | --- | --- | --- |
| W1, first run | `payload-invalid.img`, `34dc91c6…4d7b` | 00:51:48–00:54:52 | Not entered | `ERROR: RECOVERY upload failed!` |
| W1, second run | the same | the same window, after the first | `exit=1` | `ERROR: RECOVERY upload failed!` |

Both runs named `RECOVERY` only. **Nothing else was written:** no other partition, and no other image. W2, W3 and W4 were not run.

## Not committed

Private, outside every repository: the session log, the owner's video and photographs, and the implementer's notes. No identifier, photograph or log is in this file.
