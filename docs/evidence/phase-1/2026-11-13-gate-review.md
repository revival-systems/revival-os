# Phase 1 gate review: 2026-11-13

**Decision: PASS — Phase 1's Rust + ARM Assembly host/emulator foundation is
complete for the reviewed implementation.** Reviewer: ChatGPT, orchestrator.
This records the formal evidence review that the roadmap previously left
pending. It approves no phone write and does not close Phase 0.

## Evidence reviewed

- Tested commit: `3f1130a1a8ecc6796440402be572855a4990de97`, merged by
  [PR #5](https://github.com/revival-systems/revival-os/pull/5) as `6b0fbcb`.
- [Implementer's local test record](https://github.com/revival-systems/revival-os/pull/5#issuecomment-6759127753):
  clean Ubuntu build, QEMU 10.2.1, `make check` exit 0, 36 PASS / 0 FAIL;
  20/20 heartbeat runs with identical output and exit 0.
- [Successful independent hosted run](https://github.com/revival-systems/revival-os/actions/runs/42757111224),
  2026-11-10 at 05:38–05:41 Europe/Budapest, on that exact commit:
  clean Ubuntu 24.04.5 runner, QEMU 8.2.2, all steps successful.
  Its retrieved log contains **36 PASS lines and no FAIL lines**. The
  [check-summary extract](2026-11-10-ci-check-summary.txt) preserves those results.
- [Earlier orchestrator review and full local output](https://github.com/revival-systems/revival-os/pull/7#pullrequestreview-5856812819)
  also record the unchanged suite passing 36/0 on Ubuntu 26.04.1.
- [Working notes](../../phase-1/rust-foundation.md), source entry stub, Rust
  fixture, linker script, negative fixtures, and Makefile test rules inspected.

No new QEMU/build run was performed on this Windows host. This decision is based
on the linked recorded runs and inspection of their source and logs, not a
claim that Windows executed them.

## Gate-by-gate result

| Required criterion | Recorded evidence | Result |
| --- | --- | --- |
| Reproducible clean builds; recorded SHA-256 | `repro-identical`: 14 files identical across two clean builds; hashes below and in hosted log | PASS |
| Freestanding Rust and Assembly startup | `no_std`, `no_main`; entry sets stack, zeroes BSS, calls Rust; linker defines static layout and 64 KiB stack | PASS |
| No hosted C library or `std` dependency | `build-rust-symbols`: zero undefined symbols; target uses its own `core` and `compiler_builtins` | PASS |
| No undocumented supervisor calls | `build-rust-one-svc`: exactly the documented Assembly semihosting exit | PASS |
| ARMv7-A ELF attributes | `build-rust-elf-attributes`: ARMv7-A Application profile, soft-float EABI | PASS |
| Heartbeat emitted from Rust after startup, 20/20 | Local record: 20 starts, identical heartbeat/checksum, exit 0 each time; hosted heartbeat check also passes | PASS |
| Hosted-dependency rejection | `std` fixture rejected with E0463; valid `no_std` libc fixture compiles then link fails on `puts` | PASS |
| Panic reports its location | `qemu-rust-panic`, expected exit 1 and `panic:` output | PASS |
| Corrupted binary rejected | One-byte-corrupted copy fails SHA-256 comparison; original is unchanged | PASS |
| Out-of-bounds indexing reaches panic handler | `qemu-rust-bounds`, expected exit 1 and `panic:` output | PASS |
| Written support and limitation contract | Working notes document toolchain, startup, stack/static memory, soft-float, semihosting and absent MMU/heap | PASS |
| Independent milestone verification | Hosted `make check` successful on tested commit | PASS |

Observed heartbeat:

```text
revival-os: phase 1 rust heartbeat
revival-os: checksum=0x22becba4
```

| Reviewed image | Bytes | SHA-256 |
| --- | --- | --- |
| `kernel-heartbeat.elf` | 11,108 | `7ac79ff8bde24a58f1afb0d0808eca0036d61f53dd4756daec67b3852f5d946d` |
| `kernel-panic.elf` | 605,388 | `7e7fde4a2015a4d080c3002d08cfefdbcdc5f85594e5d015b7c84d303628c1a6` |
| `kernel-oob.elf` | 611,620 | `79feea1f59770bc70e867daf5f2063b9371ea96c514ee321571c3e3721aec022` |

Panic/bounds run in QEMU. Hosted-dependency rejection and corrupted-image
detection run on the host; they are not four device or four QEMU tests.

## Failures and scope limits

The [earlier hosted run](https://github.com/revival-systems/revival-os/actions/runs/42661958874)
on `d1ec367` failed `qemu-checksum` (exit 1, expected 0). The subsequent
[PR #6](https://github.com/revival-systems/revival-os/pull/6) disabled the unused
default QEMU NIC. The successful run reviewed above includes that fix; the
earlier failure is not omitted or counted as a pass.

The Rust fixture, Assembly entry, linker script, pinned Rust toolchain, negative
fixtures and QEMU runner remain unchanged between the tested commit and this
report's base `8030920`. Later Phase 2 work generalized the corruption-check
script with an optional output-name prefix; its default Phase 1 behavior is
unchanged. This review accepts the demonstrated Phase 1 gate, not every later
Phase 2 change or a fresh full-suite result for this documentation branch.

Physical verification is **not required by Phase 1**. Nothing in this evidence
shows Revival OS executing on the Samsung, a working device framebuffer/UART,
drivers, MMU, heap, watchdog handling or native stack-overflow protection.
Those capabilities remain outside this gate.

The [complete hardware evidence record](../phase-0/2026-11-13-hardware-summary.md)
belongs to Phase 0. Its missing physical records remain blockers to the Phase 2
entry gate. No new hosted workflow was started, no merge was made, and no
device-write authorization was issued during this review.

## Validation of this report update

`python -I tests/docs/check_docs.py` passes for 25 Markdown files, and
`git diff --check` passes. The 12 redacted hardware text snapshots were checked
for serial/IMEI fields, MAC addresses and IPv4 addresses; none remain. Full
`make check` cannot start on this Windows host because Make and WSL are absent;
the historical hosted result above is not represented as a new branch run.
Updates are committed and pushed only to the existing evidence branch for
review; `main` and workflow configuration are unchanged.
