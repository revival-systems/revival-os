# Phase 0 consolidated hardware evidence: 2026-11-13

**Decision: PASS WITH BLOCKERS for the observed subset; Phase 0 is not yet
complete.** Physical trial records and owner confirmations listed below remain
missing. Missing evidence is not a claim that a test failed or was never done.
[Phase 1 is separately reviewed as complete](../phase-1/2026-11-13-gate-review.md);
its host/emulator gate does not require Phase 0 to be closed.

Performed by: owner (physical phone actions), earlier Windows agent (2026-11-10
Heimdall session), ChatGPT (2026-11-13 read-only ADB, firmware acquisition and
evidence review). Checklist: [hardware verification](../../phase-0/hardware-verification-checklist.md)
at repository base `8ff31f0`, plus later evidence commits `9fbd570` and `8030920`.
Host: Windows build 26300, not the checklist's Ubuntu host.

No flashing, wiping, reset, rooting, unlocking or partition modification was
performed by this session. No new boot/reboot or mode-entry trials were started
to write this report. This is stock diagnostic evidence, not Revival OS device
execution.

## Sources and confidence

- **Observed now:** selected ADB properties, CPU, memory, kernel, partition
  aliases/sizes, camera-type sysfs files, battery service, Wi-Fi interface state,
  and Heimdall's Android-mode negative test. Redacted outputs are linked below.
- **Historical raw evidence inspected:** `detect.out.txt`,
  `F5-download-pit.out.txt`, `F5-download-pit.err.txt`, `F5-print-pit.txt`,
  `F5-pit-sha256.txt` and the private PIT under
  `Tools/Heimdall-Evidence/GT-I9195-phase0/`, outside Git. Originals unchanged.
- **Historical narrative only:** that directory's
  `DRAFT-phase-0-summary-windows-session.md` records host-driver changes and
  procedural deviations. The existing checklist records an earlier owner report
  of return to stock Android, but no method, timing or complete trial count.
- **Owner-confirmed in this conversation:** the phone is connected by USB, is
  dedicated to Revival OS, and the owner accepted the USB-debugging RSA prompt.
  No explicit physical-label/battery-inspection or 3/3 trial results are present
  in this conversation. A request for the earlier physical record is pending.
- **Firmware provenance:** the [firmware rescue report](2026-11-13-firmware-rescue.md)
  and [LFS download instructions](../../../firmware/GT-I9195/README.md).

## Complete checklist accounting

| Step | Result / recorded trials | Evidence or missing detail |
| --- | --- | --- |
| A1 tools | ADB 1.0.41, Platform Tools 37.0.1; Heimdall 2.2.2 on Windows | Google ADB and maintainer Heimdall sources; versions differ from Ubuntu checklist |
| A2–A4 evidence and rules | Private evidence retained; current actions read-only | No raw device identifiers published |
| B1 under-battery label | NOT RECORDED | Software model is confirmed; physical label still needs owner record |
| B2 battery inspection | NOT RECORDED | Swelling, leakage, heat, battery model/capacity require physical observation |
| B3 charge | 93% snapshot | Meets the 60% level threshold at observation; not a battery-condition inspection |
| B4 SIM / microSD | NOT RECORDED | No card-presence assumption made |
| C1 software | PASS for queried fields | GT-I9195, Android 4.4.2, build/bootloader/baseband I9195XXSCQAN |
| C2 cold boot | Full 3/3 result and times NOT RECORDED | Current Android access does not establish cold-boot method/count |
| C3–C4 USB debugging / RSA negative and positive | PASS: initially unauthorized, then authorized device after owner's acceptance | Initial acceptance attempts still left unauthorized; host ADB server restarted once; later new prompt acceptance succeeded |
| C5 CPU / memory / partitions | PASS for read-only observations | Details and 28-entry comparison below |
| C6 camera sensor identity | PASS for reported sysfs types | Rear S5K3H5XA; front S5K6A3YX; image capture not tested |
| C7 Wi-Fi joined / 20 pings | NOT VERIFIED | Current wlan0 has NO-CARRIER, state DOWN, no IPv4 address; band and ping results absent |
| C8 rear/front photos and videos | Four baseline captures NOT RECORDED | No personal media inspected or copied |
| C9 buttons / display / battery | Service readings recorded; physical tests NOT RECORDED | Need full button/touch/display-condition results |
| C10 ADB reboot | 3/3 result NOT RECORDED | No reboot command run in this conversation |
| C11 Android USB | PASS: 04e8:6860 | Windows enumeration; MTP and ADB present |
| C12 Heimdall negative in Android | PASS: exit 1, no compatible Download-mode device | Expected negative result recorded now |
| D1 personal backup | Optional, not a completion criterion | Owner designated phone for experiments; no data-retention requirement |
| E1 stock recovery entry / exit | 3/3 result and recovery header NOT RECORDED | No recovery operation run in this conversation |
| F1 Download warning cancel | 3/3 result and warning transcription NOT RECORDED | Current Android does not establish this route |
| F2 Download screen status | NOT RECORDED | Need product/binary/system/Knox/secure-boot/reactivation-lock lines as shown |
| F3 Download USB | Historical PASS: 04e8:685d | Product string MSM8960, captured during Heimdall session |
| F4 Download-mode detection | Historical PASS: Device detected, exit 0 | Existing detect log; reliability over repeated entries not established |
| F5 PIT | Historical PASS: one 8,192-byte read, 28 entries | PIT checksum unchanged; Linux aliases and fixed sizes compared now |
| F6 battery-removal exit | Full 3/3 result NOT RECORDED | Earlier return to Android reported; exact exit action and counts absent |
| G1–G4 rescue firmware | PASS for identity/acquisition/integrity | ROM / I9195OXXCNK2; matching Samsung package and both images retained and downloadable via LFS |
| H1 final baseline | Same model/build/CSC observed | Wi-Fi reconnection not established; no new reboot or personal-data check |
| H2–H4 summary / decision / review | This consolidated report | Physical baseline gate remains open; no Phase 2 authorization |

## Actual device observations

Model `GT-I9195`, device `serranolte`, product `serranoltexx`. Android `4.4.2`,
display ID `KOT49H.I9195XXSCQAN`, bootloader and baseband `I9195XXSCQAN`,
active CSC **ROM (Romania)**, installed CSC `I9195OXXCNK2`, changelist `3173303`.
Both sales-code property and on-device sales-code file agree; the CSC
configuration explicitly includes ROM.

- CPU: two processors, ARMv7, implementer `0x51`, part `0x04d`, variant `0x2`,
  revision 0; hardware string `SAMSUNG SERRANO`, board revision `0005`.
- Features: `swp half thumb fastmult vfp edsp neon vfpv3 tls vfpv4`.
  `idiva`/`idivt` and LPAE are not listed; no inference of their presence.
- RAM: `MemTotal: 1363632 kB`. This is the stock kernel's usable-memory report.
- Kernel: `3.4.0-3173303`, SMP PREEMPT, build dated 2017-01-19.
- Board/platform properties and the USB product say `MSM8960`; PIT tag says
  `MSM8930`. Preserve those actual strings. The precise MSM8930AB commercial
  identification remains the hardware research's conclusion, not a silicon-ID
  measurement from these generic platform properties.
- `ro.boot.warranty_bit=0`, `ro.warranty_bit=0`, `ro.secure=1`,
  `ro.debuggable=0`, debug level `0x4f4c`. These properties do not replace the
  required Download-screen photograph/transcription or prove unlockability.
- Rear type `S.LSI_S5K3H5XA`, firmware `S08Q0LEGC01 S08Q0LEGC01`;
  front type `SLSI_S5K6A3YX`, firmware `S5K6A3YX S5K6A3YX`.
- Battery service: present, Li-ion, 93/100, voltage 4,354 mV, temperature
  266 tenths °C (26.6°C), status 2, health 2, current-now raw `185200`;
  AC and USB powered both true, wireless false. Raw codes retained; physical
  battery health, capacity and swelling have not been inspected by the agent.
- Wi-Fi: administratively UP, but NO-CARRIER / operational DOWN, no IPv4.
  No network was joined and no ping was sent in this review.

Sources: [properties](2026-11-13-readonly/selected-properties.txt),
[CPU](2026-11-13-readonly/cpuinfo.txt),
[memory](2026-11-13-readonly/meminfo-top.txt),
[kernel](2026-11-13-readonly/proc-version.txt),
[camera](2026-11-13-readonly/camera-types.txt),
[battery](2026-11-13-readonly/battery.txt),
[Wi-Fi](2026-11-13-readonly/wifi-status.txt),
[expected Heimdall error](2026-11-13-readonly/heimdall-android-negative.err.txt)
and [exit status](2026-11-13-readonly/heimdall-android-negative.exit.txt).
Serials, MAC addresses and network addresses are excluded.

## Partition, rescue and tooling evidence

The [full 28-entry partition comparison](2026-11-13-readonly/partition-map.md)
confirms all 24 Linux by-name mappings and all 23 fixed-size partition sizes.
BOOT is ID 13 / `mmcblk0p13`, RECOVERY is ID 14 / `mmcblk0p14`; each holds
10,485,760 bytes. Disk size: 7,634,944 KiB. USERDATA is observed as 5,685,231 KiB,
correcting the historical draft's estimated 5,685,215 KiB. No partition contents
were read or written to make this comparison.

Private PIT SHA-256 remains
`1ec0d73501ca5b956b80b85583f9b578ea819e961e8fba3ccc1784b195f51432`.
The historical PIT transfer completed with the nonfatal warning:
`WARNING: Empty bulk transfer after receiving packet failed. Continuing anyway...`.
The draft also records a first libusb error -5 on the Samsung driver, a
host-side switch to Microsoft WinUSB, and one `close-pc-screen --no-reboot
--verbose` session test outside the checklist's command list. These are recorded
deviations, not silently treated as the prescribed Ubuntu sequence.

Firmware from Samsung: `I9195XXSCQAN/I9195OXXCNK2/I9195XXSCQAN/I9195XXSCQAN`.
Samsung's authenticated metadata, HTTPS payload size/CRC/ETag, ZIP CRCs and all
four TAR MD5 footers pass. Both images have valid legacy Android headers and fit
their recorded capacities. The [firmware report](2026-11-13-firmware-rescue.md)
records full source URLs, hashes, sizes and the unexplained differing SamFW MD5;
no independent Samsung signing-chain verification or actual rescue execution
was performed.

| Original image | Bytes | SHA-256 |
| --- | --- | --- |
| `boot.img` | 7,754,000 | `6918d25bfa63bd977279c3b064b74a5905f35a3d633173019f063c37e028cfe0` |
| `recovery.img` | 8,935,696 | `0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6` |

Complete original ZIP and both images were uploaded under
`firmware/GT-I9195/I9195XXSCQAN_I9195OXXCNK2/` with Git LFS in `8030920`,
at the owner's explicit request. All three remote objects were confirmed
downloadable with the expected object IDs and byte sizes. This is an explicit
firmware-storage exception; raw unit identifiers and the private PIT remain
outside Git. Originals and complete private evidence remain under
`Tools/Revival-Firmware/GT-I9195/` in the Windows Developer workspace.

## What still prevents closing Phase 0

The owner's earlier physical evidence is needed for B1/B2, complete C2/C10/E1/F1/F6
trial counts and cold-boot times, the F2 status-screen transcription, C7/C8/C9
baseline results, and the owner's overall confirmation that no unrecorded write
occurred. Current Android operation, sensor names and battery service readings
cannot establish those facts. Record existing evidence first; do not repeat
physical operations merely to replace a missing report.

No new failure requires abandoning the device. Phase 1 is complete on its own
recorded gate; Phase 0 remains incomplete, and the Phase 2 entry gate stays
closed. No agent action in this report is a write plan or approval.
