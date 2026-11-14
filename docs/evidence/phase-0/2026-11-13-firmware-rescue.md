# Phase 0 firmware rescue evidence: 2026-11-13

**PASS for CSC identification and rescue-artifact acquisition.** Both original
images are downloaded, extracted and integrity-verified. Other Phase 0 checks
are not closed by this report; Phase 2 and device writes remain unauthorized.

## Phone identity

Authorized read-only ADB confirms:

| Property | Value |
| --- | --- |
| Model / Android | `GT-I9195` / `4.4.2` |
| Active CSC: `ro.csc.sales_code` | **`ROM` (Romania)** |
| Independent CSC evidence | `/system/csc/sales_code.dat` also says `ROM` |
| Installed CSC: `ril.official_cscver` | `I9195OXXCNK2` |
| CSC configuration | `/system/SW_Configuration.xml`: `I9195OXX` + `CNK2`, includes ROM |
| Bootloader / baseband | Both `I9195XXSCQAN` |
| Display ID / changelist | `KOT49H.I9195XXSCQAN` / `3173303` |
| USB / ADB | Android composite `04e8:6860`; one authorized `device` |

The owner accepted the RSA prompt. Final property reads match the initial
successful reads. No serial number is included here.

No existing ADB installation was found. Google's official
[Platform Tools](https://developer.android.com/tools/releases/platform-tools)
was downloaded to `Tools\Android\platform-tools\adb.exe`; it reports
`1.0.41` / `37.0.1-15733141`. Host setup and raw output stay outside Git.

## Samsung source and exact match

Samsung Smart FUS history for **GT-I9195 / ROM** lists this exact version tuple:
`I9195XXSCQAN/I9195OXXCNK2/I9195XXSCQAN/I9195XXSCQAN`.
The newer default uses `I9195YXXCNI1`; the exact historical version was explicitly
requested. Authenticated HTTPS metadata confirms model, ROM region, version,
filename and encrypted size.

- Metadata: <https://neofussvr.sslcs.cdngc.net/NF_SmartDownloadBinaryInform.do>
  (authenticated POST; `SmartHistory.do` on the same host supplies history).
- Payload: <https://cloud-neofussvr.samsungmobile.com/NF_SmartDownloadBinaryForMass.do?file=/neofus/9/GT-I9195_1_20170410164126_oc3dpjhzrn_fac.zip.enc4>
  (requires a FUS session; a bare browser URL may fail).
- Client: [samloader-rs 2.2.0, maintainer release](https://github.com/topjohnwu/samloader-rs/releases/tag/2.2.0).
  Windows release ZIP SHA-256 matched GitHub's published asset digest:
  `0132de1b79e208138f980c467f9a7eaa2ffcb72aae14afc3ed13799803c9b9ed`.
  Only help, version-history, download and offline `verify-md5` commands were used.
- The client's initial payload transfer uses HTTP. A separate authenticated
  HTTPS download was retained and independently decrypted to the identical ZIP.

BL, AP and CP package filenames contain `I9195XXSCQAN`; CSC contains
`I9195OXXCNK2`. BL's `aboot.mbn` also contains `I9195XXSCQAN`, matching the
phone's full bootloader revision. Package label `REV01` is not proof of an
anti-rollback fuse revision. No numeric fuse revision is inferred from archive
sites' generic “bit 0” field.

## Integrity and provenance

| Check | Result |
| --- | --- |
| Samsung encrypted size | PASS: 906,732,288 bytes |
| HTTPS metadata `BINARY_CRC` | PASS: CRC32 decimal `2710741519` |
| HTTPS payload ETag | PASS: encrypted MD5 `d253425020aac676ae8372fe8cf6d97b` |
| Independent comparison | PASS: stored HTTPS ciphertext equals reconstructed ciphertext; independent decryption equals downloaded ZIP |
| ZIP CRC | PASS: every entry |
| Appended TAR MD5 | PASS: all four original BL/AP/CP/CSC TAR payloads |
| Image structure | PASS: `ANDROID!`, consistent legacy headers, 2,048-byte pages |
| Existing PIT capacity | PASS: both images below 10,485,760 bytes (20,480 sectors each) |

Decrypted ZIP: `GT-I9195_1_20170410164126_oc3dpjhzrn_fac.zip`, 906,732,277 bytes.
SHA-256: `8347bdc4ff5bd8c289c19b22c4ce82b8cdc3b4587cccbcc9fdb1b676be40d74f`.
Encrypted source SHA-256:
`324bfc9a5ba5111091a82d3c212d86ff9983b45d7867458573f6f7ecd2540e7d`.

**Secondary-source discrepancy:** [SamFW's matching multi-CSC listing](https://samfw.com/firmware/GT-I9195/ORX/I9195XXSCQAN)
includes ROM and publishes MD5 `1e80e964a6e0d9e28b9abb5680ca5107`.
It matches neither Samsung's ZIP (`2c6713c2720d8f5ff9a00ce53d61e2ce`)
nor its encrypted form. Extraction initially stopped for investigation. The
secondary listing is not used as verification; its discrepancy is unexplained.
Samsung's independent HTTPS metadata and payload checks above pass.
Local SHA-256 values identify artifacts; alone they do not prove authenticity.
No independent Samsung signing-chain verification or rescue boot was performed.

## Images and locations

Original storage is under `Tools\Revival-Firmware\GT-I9195\`, outside Git,
relative to the Windows Developer workspace. Paths below are relative to that
root. The owner subsequently explicitly requested a GitHub copy of the firmware.
The complete decrypted ZIP and the two images are therefore also stored with
Git LFS under `firmware/GT-I9195/` in this internal repository, as a specific
exception to the firmware-storage rule. See the
[download instructions](../../../firmware/GT-I9195/README.md).

| Image path | Bytes | SHA-256 |
| --- | --- | --- |
| `I9195XXSCQAN_I9195OXXCNK2\boot.img` | 7,754,000 | `6918d25bfa63bd977279c3b064b74a5905f35a3d633173019f063c37e028cfe0` |
| `I9195XXSCQAN_I9195OXXCNK2\recovery.img` | 8,935,696 | `0e3095596253b713cf89da85a0293ad78651253c41805b90d397899dfa6b79c6` |

The ZIP, encrypted source and four original TAR packages are beside the images.
Only `boot.img` and `recovery.img` were extracted from the TARs. Other members:
BL: `aboot.mbn`, `sbl1.mbn`, `sbl2.mbn`, `sbl3.mbn`, `rpm.mbn`, `tz.mbn`;
AP: `system.img.ext4`, `persist.img.ext4`, `persdata.img.ext4`;
CP: `NON-HLOS.bin`; CSC: `SERRANOLTE_EUR_OPEN.pit`, `cache.img.ext4`,
`hidden.img.ext4`. ZIP also contains `SS_DL.dll`, neither extracted nor executed.
Protected firmware is never to be flashed.

Raw observations, firmware metadata, full listings, package/footer hashes,
verification scripts and the absolute-path report are outside Git under
`evidence-2026-11-13\`. Main records: `verification.json`,
`samsung-fus-integrity.json`, `samsung-encrypted-integrity.json`,
`samsung-smart-metadata.json`, `selected-properties.txt`,
`final-selected-properties.txt`, `firmware-evidence.md`.

## Safety, review and limitations

No acquisition blocker remains. The secondary MD5 discrepancy and absence of
independent signing-chain verification remain provenance limitations. Rescue
execution is untested. These are emergency artifacts for Revival OS development;
Android restoration is not the goal.

No flash, wipe, reset, root, unlock, partition write or agent-requested reboot
occurred. Phone commands were `devices`, `getprop`, `ls` and `cat` only.
Existing Heimdall evidence was read only and not overwritten.

Prepared on `agent/windows/phase0-firmware-evidence` from locally available
`origin/main`, following [AGENTS.md](../../../AGENTS.md) and the
[document-review workflow](../../DEVELOPMENT.md#workflow). The owner subsequently
authorized pushing this report and then explicitly requested uploading the
firmware on the same task branch for review by other agents. Only the verified
ZIP and two original rescue images are uploaded; raw device evidence remains
outside Git. Copied firmware SHA-256 values match the verified local originals.
No PR, merge or CI run is part of that request. Documentation validation passed:
`python -I tests/docs/check_docs.py` (21 Markdown files) and `git diff --check`.
`make check` was attempted before pushing but could not start: Windows has no
`make`, and WSL is not installed. Full validation remains outstanding on the
Ubuntu development host; this documentation-only push does not claim it passed.
Phase 2 was not started.
