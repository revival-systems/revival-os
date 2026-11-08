# Next runtime experiment: data-stack regions with guard gaps on QEMU

**Status:** proposal for review, revised 2026-11-08 after the foundation corrections were merged. **Not implemented.** It runs on QEMU's ARMv7-A `virt` board only. It needs no device, no flashing, no hosted CI and no change to the pinned compiler.

## Why this experiment

- **Data stacks are the gate.** Every Goose sample beyond pure integer code calls `gs_reserve_region`: 25 of 25 samples ([dependency map](goose-runtime-dependency-map.md#data-stacks)). Today's fixture refuses any program that needs it. That blocks built strings, resizable arrays, printing and pools: almost all real Goose code.
- **It tests the safety claim, not only the mechanism.** Goose promises that a data-stack overrun is a safe abort, never corruption ([spec §9.3](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#93-what-the-runtime-still-checks)). Generated code has no capacity checks; the promise rests on an unmapped guard gap behind each region. On ARMv7-A, regions must be small and packed together, and the pinned compiler can advance a stack's top far past its region **without writing** ([finding 8](goose-runtime-dependency-map.md#32-bit-findings)). Whether the guarantee holds there is **not established**. This experiment measures it.
- **It turns the MMU on**, which both guard gaps and the unaligned accesses in Goose's packed data need ([finding 1](goose-runtime-dependency-map.md#32-bit-findings)).

## What it must answer

1. Can the fixture provide regions with unmapped gaps, and report a data abort in a gap as a data-stack overrun?
2. Does growth written front to back always fault in the gap before it changes anything outside its region?
3. Can an unwritten advance put the next write past the gap, into mapped memory, with no fault? Can the address wrap on a 32-bit target?
4. Are alignment faults told apart from overruns?

Questions 1, 2 and 4 are about our runtime. Question 3 is about the compiler. Our runtime is not called between an advance and the next write, so it cannot check the advance ([dependency map](goose-runtime-dependency-map.md#data-stacks)).

## What it would add

All of it is test fixture code, as the current probe is, not Revival OS code. Everything under test is Goose. C and assembly are used only where Goose cannot reach: CP15 registers, exception entry, an aligned translation table, and the memory checks the test itself makes.

| File | Change | Why not Goose |
| --- | --- | --- |
| `tests/qemu/virt-armv7/mmu.c` (new) | A first-level table of 1 MiB sections: the image and RAM as Normal memory, the UART as Device, and a data-stack window where each region of *k* MiB is followed by one **unmapped** section. Then enable the MMU. Caches stay off | CP15 writes, barriers, a 16 KiB-aligned table |
| `tests/qemu/virt-armv7/start.S` | An abort-mode stack; the data-abort vector calls a C handler | Exception entry and banked stack pointers |
| `tests/qemu/virt-armv7/minirt.c` | `gs_rt_start` records the sizes and refuses what it cannot honour. `gs_reserve_region` hands out the next region and records it. The data-abort handler reads `DFSR`/`DFAR` and reports a data-stack overrun (address in a gap), an alignment fault, or another fault | It implements the compiler's C interface |
| `tests/goose/stacks.goose` (new) | Exported functions that grow `i64` arrays, build `u8` text, hold several stacks at once, grow without bound, and make the large advances described under criterion 6 | It is the Goose under test |
| A driver, like `alloc_main.c` (new) | Calls the exports; fills every region not in use, and RAM outside the window, with a canary pattern, and checks it afterwards | It inspects memory that Goose cannot address |
| `tests/goose/checksum_oracle.py` | Expected values for the new functions | — |
| `Makefile`, `docs/TESTING.md` | The new targets and what each checks | — |

The size estimate is about 300 lines of C and assembly, mostly the page table and the abort handler.

**Region layout on `virt`** (64 MiB of RAM at `0x40000000`, the runner's `-m 64M`):

- The image stays in the first 16 MiB.
- From `0x41000000`, eight regions of 4 MiB each have a 1 MiB unmapped section after them, 40 MiB in total.
- The program under test is compiled with `--stack-reserve 4M` and `-D GS_STACK_GAP=1048576`. Its sizes then match what the fixture provides, and `gs_rt_start` refuses anything else.
- The regions are consecutive, so the memory just past one region's gap is the next region. A 32-bit system must pack its regions like this, and it is what makes question 3 observable.

## Build checks (host)

| Test | Pass when |
| --- | --- |
| A runtime-surface check for the new program | Its C needs exactly `calloc gs_abort gs_panic gs_reserve_region gs_rt_start_<hash>`, plus `gs_idxfail` if it indexes. Measured for a `[..cap]` probe: exactly the first five |
| `build-link-map` (exists since the foundation corrections) | The new image is added with its expected objects: entry stub, driver, program, runtime stub and `mmu.o`. No C library, and every reference resolves. `LIBGCC_APPROVED` stays empty, so the test program must avoid 64-bit division. Any libgcc member is added only in review, with its reason |
| `build-no-system-calls`, `build-elf-attributes`, `build-hosted-code-is-rejected` | Unchanged |
| `repro-identical` | Unchanged, covering the new image |

## Acceptance criteria

Each QEMU test passes 20 of 20 runs.

| # | Criterion | Test | Pass when |
| --- | --- | --- | --- |
| 1 | Normal data-stack growth | `stacks-grow` | 100,000 `i64` pushed into one 4 MiB region (800 KB) give the oracle's checksum; exit status 0 |
| 2 | Reuse after scope exit | `stacks-reuse` | 1,000 cycles that each grow 1 MiB and leave the scope finish in one 4 MiB region, which is possible only if scope exit returns the space |
| 3 | Several regions at once | `stacks-many` | A function that holds several stacks at once gets distinct, non-overlapping regions inside the window, as recorded by the fixture. Its results equal the oracle |
| 4 | Exhaustion and refusal of oversized requests | `stacks-too-many`, `stacks-misconfigured`, `stacks-cap-range` | More regions than the window holds are refused at startup with a message. So are a reserve larger than a region and a gap smaller than one section, refused by `gs_rt_start`. A `[..cap]` with a capacity over `UINT32_MAX` stops at the compiler's own check, with its message. Each exits 1. Our runtime can refuse only what it is shown: sizes and region counts at startup. Growth never reaches it |
| 5 | Crossing into the guard gap | `stacks-overrun` | Growth written front to back past a region faults in its gap. It is reported as `goose runtime error: data stack overrun`, naming the region, and exits 1. Nothing after it runs, and every canary is intact |
| 6 | A large advance that may skip the gap | `stacks-skip` (three cases) | The [finding 8](goose-runtime-dependency-map.md#32-bit-findings) probe: a grow-only array of structs that each hold a `[..cap]` array. Its capacity is chosen so that the first write after the advance lands: **(a)** inside the gap; **(b)** past the gap, in the next region; **(c)** past the top of the 4 GiB address space, where the address wraps into canary-filled RAM. For each case, the driver records whether a data abort occurred, its address (`DFAR`), and whether any canary changed |
| 7 | Detection or rejection of unsafe growth | Decided from criterion 6 | Passes **only if** every case of criterion 6 ends in a reported abort before any byte outside the stack's own region and gap changes. Case (a) is expected to pass. Cases (b) and (c) are predicted to fail with the pinned compiler. The generated code writes to mapped memory there, and no runtime code runs before the write ([finding 8](goose-runtime-dependency-map.md#32-bit-findings)). A failure is recorded as the blocker below, not worked around |
| 8 | Alignment failures | `stacks-alignment-canary` | An `STRD` at an odd address with the MMU on is reported as an alignment fault (`DFSR.FS` 1), not as an overrun, and exits 1. In v2026.3 the `[..cap]` header store compiles to `STRD`, so the advance probes keep their stack tops word-aligned. An unexpected alignment fault is reported, never hidden |
| 9 | The existing regression tests | All of `make check` | The five QEMU tests (`qemu-checksum`, `qemu-index-out-of-range`, `qemu-hang-is-stopped`, `qemu-undefined-instruction`, `qemu-alloc-bounds`) still pass. So do the build checks, the unit tests and `repro-identical` |

**Dependence check** (recorded in the pull request, not a `make` target): with the gap sections mapped instead of unmapped, `stacks-overrun` must fail. That proves the test depends on the gap.

## If criterion 7 fails: an architectural blocker

The result would mean that, with the pinned compiler, guard gaps cannot provide Goose's "safe abort, never corruption" on ARMv7-A. That holds for any program that makes an unwritten advance larger than the gap, such as a run-time `[..cap]` inside a value that later writes follow on the same stack.

- **Our runtime cannot fix it.** The advance is inline code, and nothing calls the runtime between the advance and the next write.
- **It is recorded and stops Phase 1 for a decision**, as the roadmap requires. Phase 1 needs "a stack-limit overrun is caught, not silently corrupting memory", and fails if success "would require changing the pinned compiler" ([ROADMAP Phase 1](../../ROADMAP.md#phase-1--freestanding-goose-toolchain), [rule 6](../../ROADMAP.md#rules-for-every-phase)).
- **None of these options is verified or proposed for implementation here.** They are for the owner and the orchestrator:
  - ask upstream for a bound or check on unwritten advances (route C; [question 1](goose-upstream-questions.md#draft-message))
  - a rule that Revival OS code never uses a run-time `[..cap]`, which needs an enforcement mechanism that does not exist today
  - a later compiler, if one adds a check. v2026.4 does not: it compiles `[..cap]` the same way (read, not run)
  - revisit the order of targets. AArch64 has room for a gap larger than any such advance

## Exit criteria

- **Complete:**
  - every test above has run and its result is recorded
  - criteria 1–5, 8 and 9 pass
  - criterion 7's outcome is recorded, pass or blocker
  - the pinned compiler is unchanged, and the list of runtime entry points the fixture supports is updated
- **Fail (recorded and re-planned, per [ROADMAP rule 6](../../ROADMAP.md#rules-for-every-phase)):**
  - growth written front to back that is not caught
  - a test that needs a compiler change
  - behaviour that relies on an undocumented compiler assumption, which then goes to upstream as [question 1](goose-upstream-questions.md#draft-message)

## What it does not show

- **Nothing about Krait or the MSM8930 memory map.** QEMU results are not hardware results ([TESTING.md](../TESTING.md#test-tiers)).
- **No general safety guarantee.** Even if every case passes, it shows only the tested constructs and sizes. A guarantee needs the compiler's contract ([question 1](goose-upstream-questions.md#draft-message)) or an audit of every place the compiler advances a stack: 58 in v2026.3, of which three are known to leave bytes unwritten.
- **Commit on fault.** Regions are fully backed.
- **Native-stack overflow detection.** It is the natural next step and reuses the same MMU and abort handler.
- **Printing, threads, TLS, `libm` and the OS layer.**
- **Performance.** Caches stay off.

## Alternatives considered

- **Failure paths first.** Every §9.3 abort reachable without data stacks, with no MMU. Smaller, but it leaves untouched the dependency that blocks almost all Goose code. It fits as the following step, or inside this experiment's fault messages.
- **A static audit only.** Reading the generator found the unwritten advance. Only a run shows where the write lands and what the abort handler sees.
- **A separate alignment experiment.** The QEMU measurements already answer it ([finding 1](goose-runtime-dependency-map.md#32-bit-findings)). What remains is the compiler-pin decision, not an experiment.
- **The native-stack guard first.** It uses the same mechanism, but data stacks unlock more code. The guard can reuse this experiment's MMU and handler.

## Decisions it needs

- **Approval of this proposal.** It uses the pinned compiler unchanged, soft-float and QEMU. It does not depend on the compiler-pin decision: the Goose under test keeps each `i64` array at the 8-byte-aligned base of its region, and text in a stack of its own.
- **Afterwards, if criterion 7 fails,** a decision on the blocker (see above). An unexpected alignment fault is reported, not hidden.
