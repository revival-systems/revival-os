# Testing Revival OS

Every test runs locally with `make` and prints one `PASS <name>` or `FAIL <name>: <reason>` line. A target exits nonzero on the first failure. Logs go to `build/logs/`. Nothing here needs GitHub.

## Test tiers

| Tier | Runs on | Make target | Counts as hardware evidence |
| --- | --- | --- | --- |
| Documentation | Host | `make check-docs` | No |
| Static analysis | Host | `make lint` | No |
| Build validation | Host (ARM cross build) | `make test-build` | No |
| Unit | Host (x86-64 Linux) | `make test-unit` | No |
| Emulator | QEMU `virt`, ARMv7-A | `make test-qemu` | **No.** QEMU is not the Samsung. |
| Reproducibility | Host | `make test-repro` | No |
| Device | The GT-I9195 | none: manual procedures with recorded evidence | Yes, when recorded as below |

`make test` runs build validation, unit, emulator and reproducibility tests. `make check` adds `doctor`, `lint` and `check-docs`, and is the gate to run before pushing.

Emulator and device tests are separate on purpose. No device milestone is marked complete from an emulator result ([ROADMAP.md](../ROADMAP.md#rules-for-every-phase)).

## What each test checks

### `make test-build`

| Test | Pass when |
| --- | --- |
| `build-runtime-surface` | The probe's Goose-generated C needs exactly `calloc gs_idxfail gs_panic gs_rt_start_<runtime>`, nothing more or less |
| `build-no-undefined` | Every probe image links with no undefined symbol, using only the stub and libgcc (no C library) |
| `build-elf-attributes` | The image is ARMv7-A, application profile, soft-float EABI |
| `build-no-system-calls` | The Goose-generated object contains no `svc`/`swi`/`smc`/`hvc` instruction |
| `build-hosted-code-is-rejected` (negative) | Linking Goose code that needs the hosted runtime **fails**, with an undefined reference to `gs_os_clock_ns` |

### `make test-unit`

| Test | Pass when |
| --- | --- |
| `unit-python` | The Python unit tests pass: the documentation checker, including its failure cases, and the checksum oracle |
| `unit-host-checksum` | `probe_checksum(1000)` through the hosted Goose runtime prints the oracle's value |
| `unit-host-index` | `probe_index(2)` returns 30 |
| `unit-host-index-out-of-range` (negative) | `probe_index(7)` **fails** with "index 7 out of bounds (length 4)" |
| `unit-sanitized-checksum`, `unit-sanitized-index` | The same calls pass under AddressSanitizer and UndefinedBehaviorSanitizer, which abort on any error |

### `make test-qemu`

| Test | Pass when |
| --- | --- |
| `qemu-checksum` | QEMU exits 0 and prints `probe_checksum(1000) = <oracle value>` |
| `qemu-index-out-of-range` (negative) | QEMU exits 1 with "panic: index out of range: 7 not in [0, 4)" |
| `qemu-hang-is-stopped` (negative) | A program that never exits is **stopped by the time limit**. This proves a hang cannot pass. |
| `qemu-undefined-instruction` (negative) | An undefined instruction is reported by the exception vectors ("unexpected exception, vector 1") and QEMU exits 1 |

### `make test-repro`

| Test | Pass when |
| --- | --- |
| `repro-identical` | Two clean builds in different directories produce byte-identical generated C, headers, ELF files and raw images |

### `make lint`

shellcheck on every shell script, cppcheck (warning, style, performance and portability checks) on our own C, and a syntax check of every Python file. Generated Goose C is not linted: it is the compiler's output, not ours.

## Evidence that a failure is reported

These were run on 2026-11-08 and each exited nonzero with the message shown:

| Situation | Result |
| --- | --- |
| Wrong expected checksum (`make BUILD=build/neg-expect PROBE_EXPECT=123 test-qemu`) | `FAIL qemu-checksum: QEMU exited 1, expected 0`; the console shows `probe: FAIL expected 123` |
| QEMU missing (`make QEMU=qemu-system-arm-missing test-qemu`) | `missing qemu-system-arm-missing: sudo apt install qemu-system-arm` |
| Goose compiler missing (`make GOOSE=/nonexistent/goose build`) | `missing Goose compiler at /nonexistent/goose: run make install-toolchain` |
| Any required tool missing (`tools/doctor.sh`) | `MISSING <tool> fix: …`, then exit 1 |
| Broken documentation links | `check_docs` lists each one, then exit 1 |

## Not implemented yet

These categories have **no target**, so nothing can pass by accident:

| Category | Why | When |
| --- | --- | --- |
| Unit tests of OS components | No OS component exists yet | With the first component (Phase 1–3) |
| Static analysis of Goose code | No Goose linter is known. `goose check` typechecking runs as part of every build. | When a tool exists |
| Memory-safety checks on the ARM target | Sanitizers need a runtime the freestanding target lacks; they run on the host build only | Revisit in Phase 3 |
| Coverage measurement | No tool chosen for Goose-generated C | When there is code worth measuring |
| QEMU tests of Samsung-specific code | QEMU has no MSM8930 machine; it emulates a generic ARMv7-A board | Never as a substitute for the device |
| Automated device tests | Device steps are manual and recorded | Phase 2 onward may add host-side tooling |

## Recording evidence

A device result counts only when it is recorded. For every device session, record:

1. The date, who performed it, and the phase and checklist step IDs.
2. The device: model from the label (B1) and from software (C5), with identifiers redacted, and the bootloader and build versions.
3. The exact image: commit, `make` target and SHA-256 of every image written or booted (none in Phase 0).
4. The observed result for each step, the number of trials and how many passed.
5. Every failure, what was done to recover, and the state afterwards.
6. A statement of every write made to the device, or that none was made.

Raw evidence (photos, full logs, `getprop` dumps, the PIT file, firmware) stays in a private directory outside every repository. Only the redacted summary is committed, under `docs/evidence/<phase>/`. Identifiers that are never committed: IMEI, serial numbers, MAC addresses, account names, personal photos.

### Phase 0 summary template

```markdown
# Phase 0 evidence: <date>

Performed by: <name>. Checklist: docs/phase-0/hardware-verification-checklist.md at <commit>.
Writes to the device: none.

| Step | Result | Trials | Notes |
| --- | --- | --- | --- |
| B1 model label | GT-I9195 / other | – | |
| B2 battery | ok / swollen | – | |
| C1 software identity | build, baseband, Android version | – | |
| C2 cold boot | n/3 | 3 | times in seconds |
| C4 adb unauthorized, then authorized | pass / fail | – | |
| C5 cpuinfo, meminfo, partitions | | – | Features line; MemTotal; by-name list |
| C6 rear camera sensor | IMX175 / S5K3H5XA / unknown | – | |
| C7 Wi-Fi ping | n/20 | 20 | band |
| C8 camera baseline | | 4 | resolutions |
| C9 buttons, display, battery | | – | battery health |
| C10 adb reboot | n/3 | 3 | |
| C11 USB ID (Android) | 04e8:xxxx | – | |
| C12 heimdall detect in Android (negative) | no device / unexpected | – | |
| E1 stock recovery | n/3 | 3 | header text |
| F1 Download-mode cancel (negative) | n/3 | 3 | warning text |
| F2 Download-mode status lines | | – | transcription |
| F3 USB ID (Download mode) | 04e8:xxxx | – | |
| F4 heimdall detect | detected / not | – | |
| F5 PIT | read / failed | – | partition list attached |
| F6 exit by battery removal | n/3 | 3 | |
| G1–G3 stock firmware | verified / missing | – | build, MD5 match |
| H1 final state unchanged | yes / no | – | |

Decision: PASS / PASS WITH BLOCKERS (<list>) / FAIL.
```
