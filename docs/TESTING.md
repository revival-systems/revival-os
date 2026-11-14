# Testing Revival OS

Every test runs locally with `make` and prints one `PASS <name>` or `FAIL <name>: <reason>` line. A target exits nonzero on the first failure. Logs go to `build/logs/`. Nothing here needs GitHub.

## Test tiers

| Tier | Runs on | Make target | Counts as hardware evidence |
| --- | --- | --- | --- |
| Documentation | Host | `make check-docs` | No |
| Static analysis | Host | `make lint` | No |
| Build validation | Host (ARM cross build) | `make test-build` | No |
| Unit | Host (x86-64 Linux) | `make test-unit` | No |
| Emulator | QEMU `virt`, ARMv7-A | `make test-qemu`, `make test-tasks`, `make test-exceptions` | **No.** QEMU is not the Samsung. |
| Reproducibility | Host | `make test-repro` | No |
| Device | The GT-I9195 | none: manual procedures with recorded evidence | Yes, when recorded as below |

`make test` runs build validation, unit, emulator and reproducibility tests. `make check` adds `doctor`, `lint` and `check-docs`, and is the gate to run before pushing.

Emulator and device tests are separate on purpose. No device milestone is marked complete from an emulator result ([ROADMAP.md](../ROADMAP.md#rules-for-every-phase)).

## What each test checks

### `make test-build`

| Test | Pass when |
| --- | --- |
| `build-runtime-surface` | The probe's Goose-generated C needs exactly `calloc gs_idxfail gs_panic gs_rt_start_<runtime>`, nothing more or less |
| `build-link-map` | Every image (the four probe images and the allocator test image) is linked from exactly its own objects: entry stub, driver, Goose program if any, runtime stub. The link uses no archive but the toolchain's ARMv7-A libgcc, and no libgcc member that is not approved; none is approved today. Every reference of every input, strong or weak, resolves. It reads each link's map and the symbol tables of its inputs ([check_link.py](../tests/build/check_link.py)) |
| `build-link-map-rejects-c-library` (negative) | A link that also uses the C library (`strlen` from newlib's `libc.a`) **is rejected**, naming the member and what pulled it in |
| `build-link-map-rejects-unapproved-libgcc` (negative) | A link that needs a libgcc helper (a 64-bit division: `__aeabi_uldivmod`) **is rejected**, naming each member |
| `build-link-map-rejects-weak-unresolved` (negative) | A weak reference to a function that nothing defines **is rejected**. The linker accepts it silently as address 0, and the image's symbol table does not show it. |
| `build-link-map-rejects-ignored-unresolved` (negative) | A reference to a missing function, linked with `--unresolved-symbols=ignore-all`, **is rejected** |
| `build-link-map-rejects-unexpected-object` (negative) | A link with one object more than expected **is rejected** |
| `build-elf-attributes` | The image is ARMv7-A, application profile, soft-float EABI |
| `build-no-system-calls` | The Goose-generated object contains no `svc`/`swi`/`smc`/`hvc` instruction |
| `build-hosted-code-is-rejected` (negative) | Linking Goose code that needs the hosted runtime **fails**, with an undefined reference to `gs_os_clock_ns` |

`build-link-map` replaces `build-no-undefined`, which counted the undefined symbols in each image. With this project's link flags, the linker already rejects an undefined strong reference in code it keeps, so the count added nothing. The image's symbol table can also leave out a reference that the linker accepted: always for a weak one, and for an ignored one when sections are not garbage-collected.

### `make test-unit`

| Test | Pass when |
| --- | --- |
| `unit-python` | The Python unit tests pass: the documentation checker, including its failure cases, the checksum oracle, and the link check's parsing and rules |
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
| `qemu-alloc-bounds` | All 28 boundary cases of the stub's allocator pass on the 32-bit target, and QEMU exits 0. Requests are **refused** (NULL) when `count * size` overflows `size_t`, when rounding the size up to 8 would wrap, or when the size is larger than what is left of the 64 KiB arena. Blocks are 8-byte aligned and rounded up to 8. A zero-size request gets a block of its own. The arena fills exactly, and then refuses every request |

### `make test-tasks`

The emulator-only task experiment ([ADR 0003](decisions/0003-task-model.md)): stackful tasks with a cooperative context switch, a fixed task table and one stack slot per task, each slot with a guard word that every switch checks; and, as a second model, run-to-completion jobs on a bounded queue, all run by one runner task on one stack. One image per case; each run is bounded by the QEMU time limit. It claims nothing for the phone.

| Test | Pass when |
| --- | --- |
| `qemu-tasks-1000` | 1,000 tasks, 100 yields each, end with exactly 100,000 iterations and the order checksum that `tests/qemu/tasks_oracle.py` computes for strict round robin; every task ended and every slot is free again |
| `qemu-tasks-10000` | The same for 10,000 tasks with 10 yields each and 256-byte stacks |
| `qemu-tasks-table-full` (negative) | With all 64 slots in use, spawn 65 **is refused** ("table full"), and the 64 tasks then run to the expected total |
| `qemu-tasks-stack-overrun` (negative) | A task that writes past the bottom of its stack slot **is reported** at its next switch ("FAULT stack overflow in task 1: guard word"), no task is resumed, and QEMU exits 1 |
| `qemu-tasks-return` | 64 tasks whose entry functions return are ended and their slots reclaimed: a second wave of 64 runs in the same slots. A spawn tried from inside a running task **is refused** |
| `qemu-jobs-1000` | 1,000 jobs of 100 steps each, all run to completion one step at a time by one runner task, end with exactly 100,000 steps and the same order checksum as 1,000 tasks; the queue is empty and the runner has ended |
| `qemu-jobs-100000` | The same for 100,000 jobs of 10 steps each |
| `qemu-jobs-queue-full` (negative) | With all 64 queue entries in use, job 65 **is refused** ("queue full"), and the 64 jobs then run to the expected total |
| `qemu-jobs-stack-overrun` (negative) | A job whose step overruns the runner's stack **is reported** right after that step, before the next job runs, and QEMU exits 1 |
| `build-tasks-symbols` | The task image has no undefined symbols |
| `build-tasks-one-svc` | The task image has exactly one system-call instruction, the semihosting exit: the context switch makes none |

`make measure-tasks` prints the experiment's measurements (task counts up to QEMU's RAM, instructions per switch, code bytes). It is not a test and is not part of `make check`.

### `make test-exceptions`

Emulator-only exception reporting, a step toward ROADMAP 3a: vectors ([exc_vectors.S](../tests/qemu/virt-armv7/exc_vectors.S), [exc.rs](../tests/qemu/virt-armv7/exc.rs)) that report which exception happened, the address of the instruction that caused it and, for an abort, the fault status and fault address, then halt. Each case states beforehand what it expects, and the report is checked against it. The faults are made at known addresses: an undefined instruction and a load in two assembly triggers, and a jump to an address QEMU has nothing behind. It claims nothing for the phone; 3a is tested on the device.

| Test | Pass when |
| --- | --- |
| `qemu-exc-undefined-instruction` (negative) | An undefined instruction is reported as one, at the exact address of the instruction, and the run halts (QEMU exits 1) |
| `qemu-exc-data-abort` (negative) | A load from an address with nothing behind it is reported as a data abort at the exact address of the load, with the fault address and a synchronous external abort status (DFSR, DFAR) |
| `qemu-exc-prefetch-abort` (negative) | A jump to that address is reported as a prefetch abort at that address, with the fault address and status (IFSR, IFAR) |

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
| The allocator before its rounding fix (`minirt.c` as of commit `26460d6`) | `FAIL qemu-alloc-bounds: QEMU exited 1, expected 0`; the console shows `calloc(1, 4294967289) = 0x40000b78, expected NULL` and `alloc: FAIL (15 of 28 cases)` |
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

A device result counts only when it is recorded. **Phase 0 records the stock Android/bootloader hardware baseline once. Phase 2 and later count only Revival OS code execution and Revival OS boot/reboot behavior as operating-system milestone evidence.** Restoring a stock image is an emergency rescue action, not routine success evidence; Android user data and personal-file retention are not required. For every device session, record:

1. The date, who performed it, and the phase and checklist step IDs.
2. The device: model from the label (B1) and from software (C5), with identifiers redacted, and the bootloader and build versions.
3. The exact image: commit, `make` target and SHA-256 of every image written or booted (none in Phase 0).
4. The observed result for each step, the number of trials and how many passed.
5. Every failure, what was done to recover, and the state afterwards.
6. A statement of every write made to the device, or that none was made.

Apart from the two exceptions below, raw evidence (original photos, full logs, `getprop` dumps, the PIT file, firmware) stays in a private directory outside every repository. Only the redacted summary, and redacted photographs as described below, are committed, under `docs/evidence/<phase>/`.

The owner made two exceptions on 2026-11-13 ([AGENTS.md](../AGENTS.md#hardware-safety-contract), rule 7):

- **Rescue firmware:** the GT-I9195 rescue firmware for the installed build, in Git LFS under [`firmware/GT-I9195/`](../firmware/GT-I9195/README.md).
- **Redacted photographs:** photographs of the device and its screens under `docs/evidence/`, with every identifier blacked out and the image metadata stripped, as in [the Phase 0 addendum](evidence/phase-0/2026-11-13-linux-retest.md#owner-photographs).

Everything else stays out of the repository: no other vendor files, and never an IMEI, serial number, MAC address, account name, personal photo or unredacted photograph. The repository must never be public while its history or Git LFS storage holds vendor firmware. It is internal on purpose, so that the owner's other agents and machines can read it; the owner decided this on 2026-11-14.

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
| H1 Phase 0 stock baseline unchanged | yes / no | – | firmware identity and Wi-Fi; no personal-data check |

Decision: PASS / PASS WITH BLOCKERS (<list>) / FAIL.
```
