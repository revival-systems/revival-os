# Phase 1 working notes: the freestanding Rust + ARM Assembly foundation

**Status: working in QEMU.** The smallest freestanding Rust + ARM Assembly
kernel boots on the QEMU `virt` board (ARMv7-A), prints a deterministic
heartbeat and checksum from Rust, and exits through the documented semihosting
path. It is integrated into `make check` (36 PASS, 0 FAIL), with Phase 1 negative
tests for hosted-dependency rejection and corrupted-image detection.
**Nothing has run on the Samsung**, and
this is a QEMU result, not a hardware result: Phase 1's pass criteria are in
[ROADMAP Phase 1](../../ROADMAP.md#phase-1--rust--arm-assembly-freestanding-foundation).

This is a QEMU-only fixture, like the Goose probe before it. It is not the kernel
source tree (`kernel/` is a Phase 3 directory, [ARCHITECTURE.md](../../ARCHITECTURE.md#proposed-source-layout)),
and it is not the Samsung boot stub. Memory is the native Rust call stack plus
statically reserved data only: no heap, no arenas
([ADR 0001](../decisions/0001-rust-and-arm-assembly.md#memory-strategy)).

## Toolchain (actual)

| Component | Version |
| --- | --- |
| Rust | `rustc 1.99.1 (58cf8f9c3 2026-10-13)`, `cargo 1.99.1`, installed via `rustup 1.29.3` |
| Target | `armv7a-none-eabi` (ARMv7-A, 32-bit ARM, soft-float), precompiled `core` + `compiler_builtins` |
| Linker backend | Arm GNU `arm-none-eabi` 15.2.Rel1 (`bfd`), driven by rustc |
| Emulator | QEMU 10.2.1, machine `virt`, CPU `cortex-a15` |

Installed with no `sudo` and no PATH change, isolated under
`~/.local/share/revival-os/{rustup,cargo}`, by [tools/install-rust.sh](../../tools/install-rust.sh)
(official rustup-init, SHA-256 verified against the pin in [tools/pins.env](../../tools/pins.env)).
Pinned again in [rust-toolchain.toml](../../rust-toolchain.toml); verified by
[tools/doctor.sh](../../tools/doctor.sh). The Goose and Arm GNU pins are unchanged.

## Files

| File | Role | Language |
| --- | --- | --- |
| [tests/qemu/virt-armv7/kstart.S](../../tests/qemu/virt-armv7/kstart.S) | Entry stub: mask IRQ/FIQ, set VBAR, set the stack, zero `.bss`, call `kmain`; exception vectors; the one semihosting-exit `svc` | ARM Assembly |
| [tests/qemu/virt-armv7/kernel.rs](../../tests/qemu/virt-armv7/kernel.rs) | `kmain`, PL011 UART, the heartbeat and static-table checksum, the `#[panic_handler]`, `kexception` | Rust (`no_std`) |
| [tests/qemu/virt-armv7/link.ld](../../tests/qemu/virt-armv7/link.ld) | Reused unchanged from the probe fixture: RAM at `0x40000000`, `_start`, `__bss_*`, `__stack_top` | linker script |

rustc links its own `core` and `compiler_builtins` (which also supply `mem*` and
the ARM EABI helpers), so no C library and no `-lgcc` are added. The gated
`mem` module in `kernel.rs` is **not** needed and stays off by default.

## Build (exact)

Through make (the normal path): `make build` or `make test-rust`. The underlying
commands, per image (the mode `cfg` selects heartbeat / panic / oob):

```sh
# entry stub (Arm assembler)
arm-none-eabi-gcc -march=armv7-a -marm -mfloat-abi=soft -g -c kstart.S -o kstart.o

# kernel image (rustc drives the link; Arm bfd linker as backend; no -lgcc)
rustc --target armv7a-none-eabi --edition 2021 --crate-type bin \
      -C panic=abort -C opt-level=2 -C relocation-model=static -D warnings \
      --remap-path-prefix "$PWD"=. \
      -C linker=arm-none-eabi-gcc -C linker-flavor=gcc -C link-arg=-fuse-ld=bfd \
      -C link-arg=-nostartfiles -C link-arg=-nostdlib \
      -C link-arg=-Wl,--gc-sections -C link-arg=-Wl,--build-id=none \
      -C link-arg=-Wl,-T,link.ld -C link-arg=kstart.o \
      [--cfg kmode_panic | --cfg kmode_oob] \
      --emit link -o kernel-<mode>.elf kernel.rs
```

## Boot (exact) and observed serial output

```sh
qemu-system-arm -M virt -cpu cortex-a15 -m 64M -nographic -monitor none \
    -serial stdio -semihosting-config enable=on,target=native -kernel kernel-<mode>.elf
```

| Image | Serial console | QEMU exit |
| --- | --- | --- |
| heartbeat | `revival-os: phase 1 rust heartbeat` then `revival-os: checksum=0x22becba4` | 0 |
| panic | heartbeat lines, then `panic: tests/qemu/virt-armv7/kernel.rs:120` | 1 |
| bounds (oob) | heartbeat lines, then `panic: tests/qemu/virt-armv7/kernel.rs:128` | 1 |

The checksum `0x22becba4` is computed in Rust over a fixed static table and is
deterministic across runs. The panic and bounds images reach the Rust
`#[panic_handler]`, which reports the source location, then exit non-zero.

## Test results

`make check`: **36 PASS, 0 FAIL** (was 31; the five new negative-test checks are below). It runs
`doctor` (now including `rust rustc 1.99.1 (+ target armv7a-none-eabi)`), `lint`,
`check-docs`, and the full test suite.

| Check | Result |
| --- | --- |
| `qemu-rust-heartbeat` | exit 0, heartbeat text present |
| `qemu-rust-panic` | exit 1, `panic:` present (handler reached) |
| `qemu-rust-bounds` | exit 1, `panic:` present (bounds-check reached the handler) |
| `build-rust-symbols` | no undefined symbols; Rust links its own `core` |
| `build-rust-one-svc` | exactly one `svc` (the documented semihosting exit); none in the Rust code |
| `build-rust-elf-attributes` | ARMv7-A, Application profile, soft-float EABI |
| `build-rust-rejects-std` | a kernel that pulls in `std` is rejected at build time (Test A) |
| `build-rust-hosted-libc-compiles` | the libc negative fixture is valid `no_std` Rust, so the next check's failure is the libc symbol and not a compile error |
| `build-rust-rejects-libc` | a kernel that calls libc `puts` fails the link on that symbol (Test A) |
| `build-rust-corrupt-image-rejected` | a one-byte change to the image is rejected by SHA-256 (Test B) |
| `build-rust-image-unchanged` | the original image is byte-for-byte unchanged after the check (Test B) |
| `repro-identical` | 14 files byte-identical across two clean builds (includes the 3 kernel images) |

Separately, the heartbeat image was booted **20 times**: **20 of 20** succeeded
(exit 0 and the heartbeat and checksum present each time).

## Negative tests (hosted dependency and corrupted image)

Two Phase 1 negative tests prove the build rejects what it must. Both run inside
`test-rust` under `make check`, and neither is part of `make build`.

**Test A - hosted dependency rejection.** An unapproved hosted dependency must
fail, and be *detected* as the cause - it must not pass because the fixture
broke for an unrelated reason:

- `build-rust-rejects-std` builds
  [hosted_std.rs](../../tests/qemu/virt-armv7/hosted_std.rs), a kernel that omits
  `#![no_std]` and so pulls in `std`. The target has no `std`, so the build is
  rejected; the check requires the message "the armv7a-none-eabi target may not
  support the standard library" (rustc `E0463`).
- `build-rust-rejects-libc` links
  [hosted_libc.rs](../../tests/qemu/virt-armv7/hosted_libc.rs), a complete
  `no_std` kernel that also calls the libc function `puts`. It compiles cleanly -
  the separate `build-rust-hosted-libc-compiles` check proves that first - then
  fails the `-nostdlib` link with `puts` as the sole undefined reference (in
  `kmain`), so the failure is provably the libc dependency and nothing else.

The positive control is the real `kernel.rs`: it is `#![no_std]` and links clean
(`build-rust-symbols` reports zero undefined symbols).

**Test B - corrupted image detection.**
[check_image_integrity.sh](../../tests/build/check_image_integrity.sh) records
the SHA-256 of `kernel-heartbeat.elf`, writes a separate copy with one byte
flipped, and confirms `sha256sum -c` rejects the corrupted copy
(`build-rust-corrupt-image-rejected`) while the original image stays
byte-for-byte unchanged (`build-rust-image-unchanged`).

Exact commands, as `test-rust` runs them (`RUST_FLAGS` and `RUST_LINK` are the
same variables used for the heartbeat build above):

```sh
# Test A: a std-pulling kernel must FAIL to build.
rustc $RUST_FLAGS $RUST_LINK -C link-arg=kstart.o \
      --emit link -o kernel-hosted-std.elf hosted_std.rs    # error E0463: no std

# Test A: a libc-calling kernel compiles, then FAILS the link on puts.
rustc $RUST_FLAGS --emit obj -o hosted_libc.o hosted_libc.rs           # ok
rustc $RUST_FLAGS $RUST_LINK -C link-arg=kstart.o \
      --emit link -o kernel-hosted-libc.elf hosted_libc.rs  # undefined reference: puts

# Test B: corrupted-image detection against the built heartbeat image.
tests/build/check_image_integrity.sh \
      build/qemu-virt-armv7/kernel-heartbeat.elf build/rust-negative
```

Observed: the std build stops with `E0463` and the standard-library note; the
libc link stops with a single `undefined reference to puts` in `kmain`; the
corrupted copy is rejected and `kernel-heartbeat.elf` is unchanged. Both of
these tests run on the host build machine, not in QEMU: Test A is a
compile-and-link check and Test B is a SHA-256 check. The panic and bounds-check
tests above are the two that execute in QEMU. With all four in place, the
[ROADMAP Phase 1](../../ROADMAP.md#phase-1--rust--arm-assembly-freestanding-foundation)
negative-and-failure tests now pass - two in QEMU (panic, bounds) and two on the
host (hosted-dependency rejection, corrupted-image detection).

## Binary sizes and SHA-256

| Image | Size | SHA-256 |
| --- | --- | --- |
| `kernel-heartbeat.elf` | 11,108 B | `7ac79ff8bde24a58f1afb0d0808eca0036d61f53dd4756daec67b3852f5d946d` |
| `kernel-panic.elf` | 605,388 B | `7e7fde4a2015a4d080c3002d08cfefdbcdc5f85594e5d015b7c84d303628c1a6` |
| `kernel-oob.elf` | 611,620 B | `79feea1f59770bc70e867daf5f2063b9371ea96c514ee321571c3e3721aec022` |

## Development cycle status

Per [docs/DEVELOPMENT.md](../DEVELOPMENT.md#development-cycle):
**Build → Boot → Observe → Test → Reboot → Recover → Measure → Document.**

| Step | State |
| --- | --- |
| Build | Done. Reproducible; three images build warning-free (`-D warnings`) |
| Boot | Done. All three boot on QEMU `virt` / `cortex-a15` |
| Observe | Done. Heartbeat, checksum and panic location observed on the serial console |
| Test | Done. Integrated into `make check`; negative paths (panic, bounds, hosted-dependency rejection, corrupted-image detection) verified |
| Reboot / Recover | Host and emulator only: 20/20 clean QEMU starts and exits; no device involved |
| Measure | Done. Sizes and SHA-256 recorded above |
| Document | This file |

## Remaining limitations

- **QEMU, not hardware.** Nothing has run on the Samsung; the `virt` board's
  memory map, UART and boot handoff differ from the MSM8930.
- **Negative-test images are large** (~600 KB vs the 11 KB heartbeat): a reachable
  panic that formats (the `panic!` message and the bounds-check message) links
  `core::fmt`. On stable Rust without `build-std` this cannot be trimmed with
  `panic_immediate_abort`. The shipped heartbeat image is unaffected and tiny.
  A future lean panic path (format-free) would shrink the negative images.
- **No MMU, no heap, no arenas.** MMU-based native stack-overflow detection is a
  Phase 3 requirement, not Phase 1 ([ROADMAP](../../ROADMAP.md#phase-1--rust--arm-assembly-freestanding-foundation)).
- **Soft-float only**, pending the device's VFP confirmation in Phase 0.

## Next smallest milestone

With Phase 1's negative-and-failure tests now complete - panic and bounds-check
in QEMU, hosted-dependency rejection and corrupted-image detection on the host -
and still within host/emulator scope, the next small increment is a statically
reserved, fixed-capacity structure exercised and checksummed from Rust (for
example a bounded ring buffer in a `static`), to establish the static-memory
pattern with a negative test, before any arena is considered. Device work
(Phase 2) remains gated on Phase 0 hardware verification and an approved write
plan; it is not part of Phase 1.
