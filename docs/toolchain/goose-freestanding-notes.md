# Goose on bare-metal ARMv7-A: feasibility findings

**Status:** experiment results from 2026-11-08. This is **pre-Phase-1 feasibility work**, not a Phase 1 pass: Phase 1's entry gate and criteria are in [ROADMAP.md](../../ROADMAP.md#phase-1--freestanding-goose-toolchain). Everything here ran on the development machine and in QEMU. **Nothing ran on the Samsung.**

Every result below can be reproduced with `make build test-build test-unit test-qemu test-repro` ([TESTING.md](../TESTING.md)).

## Setup

| Item | Version |
| --- | --- |
| Goose compiler | v2026.3, `goose runtime 4d3da949e563`, binary SHA-256 verified ([tools/pins.env](../../tools/pins.env)) |
| Cross compiler | Arm GNU Toolchain 15.2.Rel1 (`arm-none-eabi-gcc` 15.2.1), archive SHA-256 verified |
| Emulator | QEMU 10.2.1, machine `virt`, CPU `cortex-a15` |
| Target flags | `-march=armv7-a -marm -mfloat-abi=soft -ffreestanding -fno-builtin`, linked with `-nostdlib` and libgcc only |

## How Goose produces code

Goose compiles to C ([`goose help c`](https://github.com/aardappel/goose); spec §7.11 in the distribution's `docs/goose_spec.md`):

- `goose -o out.c` writes the program's C.
- `goose --emit-runtime runtime.c` writes the runtime's C. `--standalone` puts both in one file.
- `--header out.h` builds the program for a C host. It has no `main`; the host calls `goose_init(argc, argv)` once, then calls the functions declared `export fn`.

The probe ([tests/goose/probe.goose](../../tests/goose/probe.goose)) uses that last form. A small C driver and assembly entry stub call its exported functions on QEMU.

## Findings

1. **The program's generated C compiles freestanding for ARMv7-A without errors.** It includes `<stdio.h>`, `<stdlib.h>`, `<string.h>` and `<math.h>`, which here come from the Arm toolchain's newlib headers. They are used for declarations only; newlib is **not linked**.
2. **For pure Goose code, that C depends on exactly four runtime symbols:** `calloc`, `gs_idxfail`, `gs_panic` and `gs_rt_start_4d3da949e563`. This is checked by `build-runtime-surface`, so a change in this set fails the build check.
3. **A stub of about 200 lines is enough to link and run it with no C library:** [tests/qemu/virt-armv7/minirt.c](../../tests/qemu/virt-armv7/minirt.c), plus libgcc's compiler-support routines. The final images have no undefined symbols (`build-no-undefined`).
4. **The generated code contains no system-call instructions** (`build-no-system-calls`). The only `svc` in the image is the stub's documented semihosting exit, a QEMU test convention.
5. **The ARM result matches an independent oracle and the host build.** `probe_checksum(1000) = 562641396` on QEMU, on the host, and in [checksum_oracle.py](../../tests/goose/checksum_oracle.py) (`qemu-checksum`, `unit-host-checksum`).
6. **Bounds checks stay in release builds and reach the runtime's failure path on ARM.** `probe_index(7)` ends in `gs_idxfail` on QEMU (`qemu-index-out-of-range`), as it does through the hosted runtime (`unit-host-index-out-of-range`).
7. **Release builds wrap on 32-bit integer overflow.** The generated `gs_add_i32` is a plain cast. Overflow is detected only in `--debug` builds. Kernel code that must detect overflow cannot rely on release-build checks.
8. **Code that needs hosted features fails the freestanding link, as it should.** [hosted_probe.goose](../../tests/goose/hosted_probe.goose) (the OS clock) needs `gs_os_clock_ns` and `gs_reserve_region` (data stacks), and the link is rejected (`build-hosted-code-is-rejected`).
9. **The upstream runtime does not build for bare metal.** Its C needs `sys/mman.h` and `_longjmp`, and fails to compile for `arm-none-eabi`. On the x86-64 host, its object references 79 C-library and POSIX symbols: threads (`pthread_*`), memory mapping (`mmap`, `mprotect`, `madvise`), signals (`sigaction`, `sigaltstack`), stdio, file and directory calls, `clock_gettime`, `nanosleep`, `syscall`, `setjmp`/`longjmp` and the `malloc` family.
10. **Builds are reproducible.** The generated C is byte-identical across runs, and two clean builds in different directories produce 10 byte-identical files (`repro-identical`).
11. **The runtime interface is internal to the compiler.** The `gs_*` entry points are not a documented API. Their version is encoded in `gs_rt_start`'s name, so a freestanding runtime is tied to the pinned compiler. A compiler change makes the link fail by design, and the runtime layer must then be re-validated.
12. **The default data-stack reservation does not fit a 32-bit address space.** `GS_STACK_RESERVE` defaults to 2 GiB per stack (`--stack-reserve` changes it). The probe uses no data stacks. Which Goose constructs need them, and how much, is not yet known.

## What this does not show

- **Nothing about the Samsung.** QEMU `virt` is not an MSM8930: memory map, UART, interrupt controller, timer and boot handoff all differ, and Krait itself is not emulated.
- **Only a small subset of Goose:** integer arithmetic, loops, fixed arrays and exported functions. Strings, growable arrays, data stacks, floating point, threads and printing are not exercised.
- **No performance or size claims.**
- **The stub is a test fixture, not the Revival OS runtime.** Its design (a bump allocator that never frees, exits through semihosting) is for tests only.

## Decisions needed before Phase 1 implementation

These are for review, not decided here:

1. **Runtime route.**
   - **A.** A freestanding runtime layer in Revival OS that implements the internal `gs_*` interface for the subset the OS uses. Small and fast to reach, but coupled to compiler internals.
   - **B.** Port the upstream runtime with shims for its 79 hosted symbols. Large, and imports hosted assumptions.
   - **C.** Ask upstream Goose for a supported freestanding runtime profile. Cleanest, but depends on someone else.
2. **Data stacks:** which constructs need `gs_reserve_region`, and a reservation size that suits a 32-bit, 1.5 GB device.
3. **Floating point:** keep the soft-float ABI, or move to hard-float after Phase 0 confirms the VFP features on the device.
4. **Overflow policy:** `--debug` builds for kernel code, explicit checks, or both.
