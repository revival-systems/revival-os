# Next runtime experiment: data-stack regions with guard gaps on QEMU

**Status:** proposal for review, 2026-11-08. **Not implemented.** It runs on QEMU's ARMv7-A `virt` board only. It needs no device, no flashing and no hosted CI.

## Why this experiment

- **The dependency it addresses is data stacks.** Every Goose sample beyond pure integer code calls `gs_reserve_region`: 25 of 25 samples ([dependency map](goose-runtime-dependency-map.md#data-stacks)). Today's fixture refuses any program that needs it. That blocks strings that are built, resizable arrays, printing and pools: almost all real Goose code.
- **It answers the central question for this target, at the smallest scale.** Upstream says Goose's design needs address-space reservation ([#134](https://github.com/aardappel/goose/issues/134), [#246](https://github.com/aardappel/goose/issues/246)). Can Revival OS provide reservation with an unmapped guard gap on ARMv7-A, using the MMU ([options](goose-runtime-options.md#the-constraint-behind-every-option))?
- **It turns the MMU on**, which unaligned accesses in Goose's packed data need anyway ([finding 1](goose-runtime-dependency-map.md#32-bit-findings)).

## What it would add

All of it is test fixture code, as the current probe is, not Revival OS code. Everything under test is Goose. C and assembly are used only where Goose cannot reach: CP15 registers, exception entry, and an aligned translation table.

| File | Change | Why not Goose |
| --- | --- | --- |
| `tests/qemu/virt-armv7/mmu.c` (new) | A first-level table of 1 MiB sections: the image and RAM as Normal memory, the UART as Device, and a data-stack window where each region of *k* MiB is followed by one **unmapped** section. Then enable the MMU. Caches stay off | CP15 writes, barriers, a 16 KiB-aligned table |
| `tests/qemu/virt-armv7/start.S` | An abort-mode stack; the data-abort vector calls a C handler | Exception entry and banked stack pointers |
| `tests/qemu/virt-armv7/minirt.c` | `gs_rt_start` records the sizes and refuses what it cannot honour. `gs_reserve_region` hands out the next region. The data-abort handler reads `DFSR`/`DFAR` and reports a data-stack overrun (address in a gap), an alignment fault, or another fault | It implements the compiler's C interface |
| `tests/goose/stacks.goose` (new) | Exported functions that grow `i64` arrays, build `u8` text, use several stacks at once, and grow without bound | It is the Goose under test |
| `tests/goose/checksum_oracle.py` | Expected values for the new functions | — |
| `Makefile`, `docs/TESTING.md` | The new targets and what each checks | — |

The size estimate is about 300 lines of C and assembly, mostly the page table and the abort handler.

**Region layout on `virt` (64 MiB of RAM at `0x40000000`):** the image stays in the first 16 MiB. From `0x41000000`, eight regions of 4 MiB each have a 1 MiB unmapped section after them, 40 MiB in total. The program under test is compiled with `--stack-reserve 4M` and `-D GS_STACK_GAP=1048576`. Its sizes then match what the provider gives it, and `gs_rt_start` refuses anything else.

## Tests and pass/fail criteria

**Build checks (host):**

| Test | Pass when |
| --- | --- |
| `build-runtime-surface` (updated) | The program needs exactly `calloc gs_panic gs_reserve_region gs_rt_start_<hash>`, plus `gs_idxfail` if it indexes |
| `build-link-map` (new) | The image contains only the fixture objects, the program and libgcc members. This replaces `build-no-undefined`, which the foundation review found cannot fail on its own |
| `build-no-system-calls`, `build-elf-attributes`, `build-hosted-code-is-rejected` | Unchanged |
| `repro-identical` | Unchanged, covering the new images |

**QEMU, results:**

| Test | Pass when |
| --- | --- |
| `stacks-grow` | 100,000 `i64` pushed into one 4 MiB region (800 KB) give the oracle's checksum; exit status 0 |
| `stacks-many` | A function that holds several stacks at once gets distinct regions inside the window; its results equal the oracle |
| `stacks-reuse` | 1,000 grow-and-release cycles (scope exit restores the watermark) finish without exhausting a region |
| `stacks-text` | `u8` text built with `append` equals the oracle's bytes |

**QEMU, negative and failure:**

| Test | Pass when |
| --- | --- |
| `stacks-overrun` | Growth past a region faults in its gap, is reported as `goose runtime error: data stack overrun` naming the region, and exits 1. Nothing after it runs |
| `stacks-too-many` | A program that needs more regions than the window holds is refused at startup with a message; exit 1 |
| `stacks-misconfigured` | A program built with a reserve larger than a region, or a gap smaller than one section, is refused by `gs_rt_start`; exit 1 |
| `stacks-alignment-canary` | An `STRD` at an odd address with the MMU on is reported as an alignment fault (`DFSR.FS` 1), not as an overrun; exit 1 |
| The four existing QEMU tests | Still pass, now with the MMU on |

**Stability:** every QEMU test passes in 20 of 20 runs.

**Dependence check** (recorded in the pull request, not a `make` target): with the gap sections mapped instead of unmapped, `stacks-overrun` must fail. That proves the test depends on the gap.

## Exit criteria

- **Pass:**
  - every test above passes
  - the pinned compiler is unchanged
  - the list of runtime entry points the fixture supports is updated
- **Fail (recorded and re-planned, per [ROADMAP rule 6](../../ROADMAP.md#rules-for-every-phase)):**
  - an overrun that is not caught
  - a test that needs a compiler change
  - behaviour that relies on an undocumented compiler assumption, which then goes to upstream as [question 1](goose-upstream-questions.md#draft-message)

## What it does not show

- **Nothing about Krait or the MSM8930 memory map.** QEMU results are not hardware results ([TESTING.md](../TESTING.md#test-tiers)).
- **Commit on fault.** Regions are fully backed.
- **Native-stack overflow detection.** It is the natural next step and reuses the same MMU and abort handler.
- **Printing, threads, TLS, `libm` and the OS layer.**
- **The bound on unwritten bumps.** Until upstream answers question 1, the overrun test covers front-to-back growth only.
- **Performance.** Caches stay off.

## Alternatives considered

- **Failure paths first.** Every §9.3 abort reachable without data stacks, with no MMU. Smaller, but it leaves untouched the dependency that blocks almost all Goose code. It fits as the following step, or inside this experiment's fault messages.
- **A separate alignment experiment.** The QEMU measurements already answer it ([finding 1](goose-runtime-dependency-map.md#32-bit-findings)). What remains is the compiler-pin decision, not an experiment.
- **The native-stack guard first.** It uses the same mechanism, but data stacks unlock more code. The guard can reuse this experiment's MMU and handler.

## Decisions it needs

Only approval of this proposal. It uses the pinned compiler unchanged, soft-float and QEMU, and it does not depend on the compiler-pin decision:

- The Goose under test keeps each `i64` array at the 8-byte-aligned base of its region, and text in a stack of its own.
- An unexpected alignment fault would be reported, not hidden.
