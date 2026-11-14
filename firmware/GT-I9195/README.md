# GT-I9195 emergency rescue firmware

The owner explicitly requested uploading this firmware to the internal GitHub
repository on 2026-11-13, as a specific exception to AGENTS.md's firmware-storage
rule. This does not authorize other vendor uploads or any phone write.

Verified phone: GT-I9195, active CSC **ROM (Romania)**, bootloader/AP/baseband
`I9195XXSCQAN`, CSC firmware `I9195OXXCNK2`.

[Acquisition and verification evidence](../../docs/evidence/phase-0/2026-11-13-firmware-rescue.md)
records Samsung's source, integrity checks and provenance limitations, including
a secondary archive's differing MD5. Independent signing-chain verification and
rescue execution were not performed.

## Download

The complete original decrypted Samsung ZIP and its original `boot.img` and
`recovery.img` are stored with **Git LFS** under
`I9195XXSCQAN_I9195OXXCNK2/`. The ZIP contains all four verified original TAR
packages; separately uploaded copies of those TARs are unnecessary.

**Pull only when the firmware is needed.** The download is about 924 MB
(923,421,973 bytes for the three files below), and Git LFS downloads are
metered, so each one costs part of the organization's paid quota. A verified copy is
already in the private firmware directory on the development machine,
`~/revival-firmware/gt-i9195/`
([re-verification](../../docs/evidence/phase-0/2026-11-13-linux-retest.md#firmware-re-verified-on-ubuntu));
use it instead. Clone, fetch and check out with `GIT_LFS_SKIP_SMUDGE=1`
([AGENTS.md](../../AGENTS.md#ci-and-cost-rules)).

When a download is needed, check out `main` and run:

```sh
git lfs install
git lfs pull --include="firmware/GT-I9195/I9195XXSCQAN_I9195OXXCNK2/*"
```

Without LFS download, Git may show small pointer files rather than firmware.
Check the downloaded files against
[SHA256SUMS.txt](I9195XXSCQAN_I9195OXXCNK2/SHA256SUMS.txt).

| Artifact | Bytes |
| --- | --- |
| `GT-I9195_1_20170410164126_oc3dpjhzrn_fac.zip` | 906,732,277 |
| `boot.img` | 7,754,000 |
| `recovery.img` | 8,935,696 |

These are emergency rescue artifacts for Revival OS development. No file here
is a write plan. Do not flash bootloader-chain, EFS, persist or modem partitions.
The vendor DLL inside the original ZIP was not executed. Phase 2 is not started
or authorized by uploading these files.
