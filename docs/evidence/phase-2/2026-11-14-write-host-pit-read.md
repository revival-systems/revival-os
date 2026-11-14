# Write-host PIT read: 2026-11-14 (write plan E-16, E-17)

- **Performed by:** the owner at the phone: Download mode, the cable and the photograph. The implementer (Claude Code on the Ubuntu host) ran the host commands and recorded the results.
- **Plan:** [write-plan draft](../../phase-2/write-plan-draft.md#2-entry-conditions) (v3.1 when the session ran; v3.2 records it), entry conditions E-16 and E-17. This session is one of Phase 2's entry conditions, and it is **read-only**.
- **No write was made to the phone.**

## Device

A GT-I9195 with bootloader `I9195XXSCQAN`, the phone of the [Phase 0 record](../phase-0/2026-11-13-linux-retest.md). No identifier is recorded here.

## Host, cable and port (E-16)

| Item | Value | Label |
| --- | --- | --- |
| Host | The Ubuntu development host used for the 2026-11-13 Phase 0 re-test, where F4 was [measured](../phase-0/2026-11-13-linux/download-mode-usb-detect.txt) | Recorded |
| Cable and port | The same cable as on 2026-11-13, in the left front USB port | Owner-confirmed |
| `heimdall version` | `v2.1.0` | Measured |
| `make doctor` | `doctor: all required tools present`, exit 0, `heimdall v2.1.0` | Measured |
| `sudo` for USB access | Not needed: Heimdall ran as the normal user | Measured |

## Steps (E-17)

All times are CET.

| Step | Time | Result | Label |
| --- | --- | --- | --- |
| Phone in Download mode, cable connected | 18:58:12 | `lsusb`: `04e8:685d` (Download mode), the ID recorded on 2026-11-13 | Measured |
| `heimdall download-pit --output "$EV0/private/pit-linux.bin" --no-reboot` | 18:58:19 | Exit 0. No line starts `ERROR` or `WARNING` | Measured |
| `sha256sum` of the PIT file | — | `1ec0d73501ca5b956b80b85583f9b578ea819e961e8fba3ccc1784b195f51432`, **equal to the Windows PIT read** ([partition map](../phase-0/2026-11-13-readonly/partition-map.md)) | Measured |
| `heimdall print-pit --file …` | — | Exit 0. 28 entries. `RECOVERY`: identifier 14, 20,480 blocks, from block 241,664. `BOOT`: identifier 13, 20,480 blocks | Measured |
| Screen 10 seconds after Heimdall exited | — | **The phone stayed on the Download-mode screen.** The owner photographed it | Owner-confirmed. The photograph stays outside Git |
| Exit: cable unplugged, battery removed | — | Done: the screen went dark. The phone is recovered and works normally | Owner-confirmed |

The PIT bytes are identical to the Windows read, so every entry matches the [partition map](../phase-0/2026-11-13-readonly/partition-map.md).

## Heimdall 2.1.0 session lines on this host

The copyright banner is left out.

```text
Heimdall v2.1.0

Initialising connection...
Waiting for device...
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

Ending session...
Releasing device interface...
```

- `Resetting device...` appears during protocol initialisation. The phone stayed on the Download-mode screen, so this line did not restart it.
- No `Rebooting device...` line follows `Ending session...`: `--no-reboot` sent no reboot request.
- No `WARNING` line appeared.
- These are the session lines that step D4 expects. The upload lines of a flash, `Uploading RECOVERY` and `RECOVERY upload successful`, are not part of a PIT read, so their wording stays an Inference.

## Writes

**None.** The only command that talked to the phone was `heimdall download-pit`, which reads. `lsusb` lists the host's USB devices. `sha256sum` and `heimdall print-pit` read the file on the host.

## Raw evidence (private, not in Git)

All of it is in `$EV0/private/`:

- `pit-linux.bin`
- `E-17-pit-read-2026-11-14.txt`: Heimdall's complete output, the hash, `print-pit`, and the owner's statements
- `E-16-doctor-2026-11-14.txt`

The owner's photograph is kept by the owner.
