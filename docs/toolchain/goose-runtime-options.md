# Goose runtime options for Revival OS

**Status:** research for review, 2026-11-08. It compares the three runtime routes in the [freestanding notes](goose-freestanding-notes.md#decisions-needed-before-phase-1-implementation). The recommendation below is **not a decision**; the orchestrator and the owner decide. Evidence comes from the [dependency map](goose-runtime-dependency-map.md), upstream Goose, Arm documentation and QEMU. **Nothing ran on the Samsung.**

## Recommendation (for review)

1. **Take route A:** a minimal freestanding runtime layer in Revival OS behind the compiler's `gs_*` interface. It grows one group of entry points at a time, each with tests, and is re-validated at every compiler pin change.
2. **Pursue a narrow form of C in parallel.** Ask upstream about the contract the layer must honour (the [draft questions](goose-upstream-questions.md)), not for 32-bit support.
3. **Do not take route B** (porting the hosted runtime).
4. **Decide the compiler pin before Goose code with packed data runs on ARMv7.** v2026.3's generated C makes doubleword accesses at unaligned addresses that ARMv7 faults on. Upstream fixed this in v2026.4 ([finding 1](goose-runtime-dependency-map.md#32-bit-findings)). Moving the pin is a reviewed change: the pin is shared with Revival Server, and ROADMAP's Phase 1 entry gate names v2026.3.
5. **Bring an identity-mapped MMU into the Phase 1 QEMU support layer.** Both Goose's memory model (guard gaps) and its unaligned accesses need it. Today it is planned for Phase 3b.
6. **Record the strategic risk explicitly.** Goose's author does not support 32-bit targets ([#134](https://github.com/aardappel/goose/issues/134), [#246](https://github.com/aardappel/goose/issues/246)). Revival OS on the GT-I9195 would be an unsupported configuration that this project maintains. Whether to accept that, or to revisit the order of targets (the planned AArch64 second target fits Goose's design), is the owner's decision.

## The constraint behind every option

Goose's memory model (spec [§1.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#12-memory-model), [§10.4](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#104-runtime-environment), [App. C](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#c4-guard-pages-and-commit-order)) works like this:

- Each program has a compile-time number of **data stacks**. Each one is a large reservation of address space.
- Allocation bumps a pointer with **no capacity check**.
- An unmapped guard gap behind each region turns an overrun into a safe abort.

Upstream sizes this for 64-bit address spaces: 2 GiB per stack by default, a 32 TiB budget. The maintainer's position is direct:

- **#134 (2026-10-29):** Goose "derives a lot of its power from being able to reserve large amounts of address space, which pretty much requires a 64-bit system, and one with address space reservation functionality".
- **#246 (2026-11-07):** "its design was made possible specifically by having all that address space in 64-bit", and 32-bit support should come only "if we can do it well".

**How the GT-I9195 differs from the cases in those issues.** Those were microcontrollers without an MMU, and WebAssembly. Krait is ARMv7-A with a VMSAv7 MMU, and Revival OS owns the whole 32-bit address space. It can therefore provide what the model assumes: a reservation per stack, an unmapped gap behind it, and pages committed on fault or up front. The difference is the budget. A single data stack can never exceed its region, so a program that needs one very large buffer needs a large region.

**Address-space budget.** Regions × (reserve + gap) must fit in the virtual address space left after RAM, device registers and the kernel are mapped. On the GT-I9195 that is roughly 1 to 2 GiB if all 1.5 GB of RAM is mapped. Per-region reserve with a 1 MiB gap:

| Regions in use | Budget 1 GiB | Budget 2 GiB |
| --- | --- | --- |
| 6 (median sample) | 169 MiB | 340 MiB |
| 26 (largest sample) | 38 MiB | 77 MiB |
| 100 (several programs) | 9 MiB | 19 MiB |
| 1,024 (`GS_MAX_STACKS`) | 0 | 1 MiB |

Regions built from 1 MiB sections come in whole MiB, and the default gap is exactly one unmapped section. Fully backed regions cost RAM equal to the reserve. Committing pages on fault costs only what is touched, but needs the frame allocator (Phase 3c).

## The three options

### A. A minimal freestanding layer, grown incrementally

Revival OS implements the entry points the generated C calls, starting with the ones in the dependency map's ["provide first"](goose-runtime-dependency-map.md#what-revival-os-must-provide-first) list:

- the failure path
- data-stack regions with guard gaps
- a native-stack guard
- an output sink
- formatting

Each group arrives with tests, including failure tests. The pinned compiler is used unchanged, as ROADMAP's Phase 1 gate requires. Two existing safeguards catch interface drift: the link fails on a runtime hash mismatch, and `build-runtime-surface` checks the exact symbol set.

### B. Port the hosted runtime

Compile upstream's `runtime_impl.h`, `runtime_threads.h` and `runtime_os.h` for `arm-none-eabi` with shims for their 79 C-library and POSIX symbols:
- threads
- `mmap`/`mprotect`/`madvise`
- signals and `sigaltstack`
- stdio
- files and directories
- clocks
- `setjmp`/`longjmp`
- the `malloc` family

Today the runtime object does not compile for bare metal: `sys/mman.h` is missing and `_longjmp` is undeclared.

### C. Official freestanding support upstream

Upstream would provide a supported freestanding profile, for example a documented platform interface or a `GS_FREESTANDING`-style switch, so that Revival OS supplies only the platform services. Prior art is the unmerged [`mogenson/goose`](https://github.com/mogenson/goose) `32bit` branch (Apache-2.0, one commit, 41 behind upstream). It adds:
- static `.bss` stacks with software growth checks (`gs_check_space`)
- 32-bit lengths
- 32-bit division
- a `GS_FREESTANDING` gate

It targets MMU-less microcontrollers and WebAssembly, and the maintainer has not accepted the direction.

## Comparison

| Criterion | A. Minimal layer | B. Port hosted runtime | C. Upstream support |
| --- | --- | --- | --- |
| Engineering effort | Small per step: today about 200 lines; the "provide first" list adds an MMU setup, a fault path and a region provider, a few hundred lines of C and assembly | Large: shims for 79 hosted symbols, which amounts to re-creating a POSIX subset, plus about 4,000 lines of upstream code to carry | Small for Revival OS if upstream does it; otherwise none of it exists |
| Maintainability | Coupled to an internal, undocumented interface. v2026.4 changed 9 entry points; drift is caught at link time and by `build-runtime-surface` | Worst: every release must be merged into the ported copy (v2026.4: +1,442/−126 runtime lines) | Best: upstream maintains it |
| Portability | Architecture-specific parts (regions, faults, output) are small and isolated; the same layer serves the AArch64 target later | Inherits POSIX and x86 assumptions (signals, CPUID, `pthread_getattr_np`) | Depends on upstream's design |
| Performance | Only what is needed; no signal machinery. Fully backed regions cost RAM until commit-on-fault exists | Carries machinery the OS does not need | Unknown. The fork's per-bump software checks cost time on every growth |
| Security and safety | Smallest trusted code; Goose's safety rules (guard gaps, failure semantics) must be re-proved by our tests. Main risk: breaking a compiler assumption that is not documented | Large surface; emulating signals and memory mapping adds failure modes | Guarantees owned upstream |
| Upstream compatibility | Compiler unchanged; runtime layer ours | Compiler unchanged; runtime a diverging copy | Full, if accepted |
| Licensing | Our own code | Imports Apache-2.0 runtime code (licence and NOTICE kept) | None |
| Availability | Now | Now, with large effort | Not for 32-bit, by the maintainer's stated position; unknown for a documented platform interface |

## ARMv7-A constraints

| Constraint | Evidence | Consequence |
| --- | --- | --- |
| With the MMU off, data accesses are Strongly-ordered; unaligned accesses there are architecturally unpredictable unless they fault | Arm ARM (DDI 0406); QEMU 10.2.1: alignment fault (`DFSR.FS` 1) on an unaligned `LDR` | Goose code must run with the MMU on and RAM mapped as Normal memory, or be built with `-mno-unaligned-access` |
| `LDRD`/`STRD`, `LDM`/`STM` (and `VLDR`/`VSTR`) need word alignment whatever `SCTLR.A` says | Arm ARM alignment table; QEMU: `STRD` at an odd address faults with the MMU on | v2026.3's `*(double *)p` at packed offsets faults. Needs a compiler with `cec434a` (v2026.4) |
| 32-bit virtual address space; VMSAv7 short-descriptor tables: 16 KiB first level of 1 MiB sections, 1 KiB second-level tables of 4 KiB pages | Arm ARM | Region sizes come from the budget above; 1 MiB sections give the 1 MiB gap directly |
| No integer divide assumed (`-march=armv7-a`); it is optional in ARM state, reported in `ID_ISAR0` | Arm ARM; Krait reports `idiva idivt` in later kernels | Division stays in libgcc. Goose's `i32` division is 64-bit anyway (dependency map finding 3) |
| VFP and NEON must be enabled (`CPACR`, `FPEXC.EN`) before use; hard-float changes the ABI | Arm ARM | Keep soft-float until Phase 0 C5 confirms VFPv4 and NEON; hard-float is a separate reviewed change |
| Thread-local storage is read from `TPIDRURO` (`c13, c0, 3`) | Measured: 4 reads in the threads sample | Threads need a TLS block per thread and `TPIDRURO` set on every switch |
| Exclusive accesses (`LDREX`/`STREX`, `LDREXD`/`STREXD`) are specified for Normal memory | Arm ARM, synchronization primitives | Atomics, including the hosted runtime's `gs_end`, only after the MMU is on |
| Exceptions enter banked modes with their own `sp`; fault status and address are in `DFSR`/`DFAR`, `IFSR`/`IFAR` | Arm ARM; read successfully in the QEMU measurements | Overrun and fault reports need per-mode stacks and these registers; today's fixture has neither |
| AAPCS: 8-byte stack alignment at public interfaces; 64-bit values in register pairs | AAPCS (IHI 0042) | The entry stub keeps `sp` 8-byte aligned (already true) |

## GT-I9195 / MSM8930 constraints

Addresses and facts are from [gt-i9195.md](../hardware/gt-i9195.md#memory-map-and-on-chip-addresses) and mainline Linux's [`qcom-msm8960.dtsi`](https://github.com/torvalds/linux/blob/master/arch/arm/boot/dts/qcom/qcom-msm8960.dtsi). All of them are unverified on this device.

| Constraint | Status | Consequence for the runtime |
| --- | --- | --- |
| RAM 1.5 GB from `0x80000000`, with reserved regions: shared memory at `0x80000000`, framebuffer at `0x88300000`, WCNSS at `0x8f000000`, rmtfs at `0x8fb00000` | Community and fork sources | The region provider takes frames only from the bootloader's memory map, never the reserved ranges (Phase 3c) |
| Entry state (mode, MMU, caches, registers) unmeasured; the Linux boot protocol expects MMU and data cache off, SVC or HYP mode | Unmeasured until Phase 2 | The entry stub must enable the MMU before Goose code runs, and must check the mode |
| Timekeeping is the KPSS timer (`qcom,kpss-timer`, `0x0200a000`, 27 MHz); the mainline device tree has no `arm,armv7-timer` node | Mainline device tree | A monotonic clock for `gs_os_clock_ns` needs the KPSS timer driver (Phase 3d), not the generic timer |
| The KPSS watchdog shares that block (`qcom,kpss-wdt-msm8960`); whether the bootloader leaves it running is unknown | Unknown | A long runtime test on the device may be reset by the watchdog. Phase 2 records its behaviour |
| The second core starts through the KPSS ACC (`enable-method = "qcom,kpss-acc-v1"`), not PSCI | Mainline device tree | Goose threads on two cores need SoC-specific bring-up; single core first |
| Krait VFP and NEON are present, VFPv4 and integer divide reported inconsistently by older kernels | Kernel threads and commits | Phase 0 C5 records the `Features` line before any hard-float or divide decision |
| Console: UART-DM v1.3 on GSBI5 at `0x16440000` (1.8 V, through the micro-USB JIG mode) or the bootloader's framebuffer | Unverified | The failure path and `gs_out_bytes` need one of them on the device |

## References and licences

Studied as engineering references only. **No code, tables or comments are copied from GPL sources**, and reviews should check that.

| Reference | What it shows | Licence | Use |
| --- | --- | --- | --- |
| Arm Architecture Reference Manual ARMv7-A/R (DDI 0406C) | Memory types, alignment, VMSAv7 tables, exceptions, exclusives, CP15 | Arm documentation | Specification |
| AAPCS (IHI 0042) and run-time ABI (IHI 0043) | Calling convention, `__aeabi_*` helpers | Arm documentation | Specification |
| Linux [`Documentation/arch/arm/booting.rst`](https://github.com/torvalds/linux/blob/master/Documentation/arch/arm/booting.rst) | What a bootloader leaves at entry | GPL-2.0 | Reference |
| Linux [`arch/arm/kernel/head.S`](https://github.com/torvalds/linux/blob/master/arch/arm/kernel/head.S), [`arch/arm/mm/proc-v7.S`](https://github.com/torvalds/linux/blob/master/arch/arm/mm/proc-v7.S) | Early MMU and cache enable on ARMv7 | GPL-2.0-only | Study only |
| Linux [`arch/arm/kernel/entry-armv.S`](https://github.com/torvalds/linux/blob/master/arch/arm/kernel/entry-armv.S) | Exception entry and per-mode stacks | GPL-2.0-only | Study only |
| Linux [`arch/arm/mm/alignment.c`](https://github.com/torvalds/linux/blob/master/arch/arm/mm/alignment.c) | Emulating unaligned `LDRD`/`STRD`/`LDM`/`STM` after a fault (`do_alignment_ldrdstrd`): a fallback if the compiler pin cannot move | GPL-2.0-only | Study only |
| Linux [`arch/arm/mach-qcom/platsmp.c`](https://github.com/torvalds/linux/blob/master/arch/arm/mach-qcom/platsmp.c) | Starting the second Krait core | GPL-2.0-only | Study only (later) |
| Linux [`timer-qcom.c`](https://github.com/torvalds/linux/blob/master/drivers/clocksource/timer-qcom.c), [`qcom-wdt.c`](https://github.com/torvalds/linux/blob/master/drivers/watchdog/qcom-wdt.c), [`msm_serial.c`](https://github.com/torvalds/linux/blob/master/drivers/tty/serial/msm_serial.c) | KPSS timer, watchdog, UART-DM | GPL-2.0-only | Study only (Phases 2 to 3) |
| [lk2nd](https://github.com/msm8916-mainline/lk2nd) and LK | Android boot-image handoff on this phone | LK is MIT; lk2nd's own files carry their own headers (GitHub reports no single licence) | Reference; check per file before any reuse |
| [`mogenson/goose`](https://github.com/mogenson/goose) `32bit` branch | Software growth checks, 32-bit layout, freestanding gating | Apache-2.0 | Prior art; not used |
| Goose upstream (`src/runtime/`, [`docs/design/wasm.md`](https://github.com/aardappel/goose/blob/v2026.3/docs/design/wasm.md)) | The runtime interface; growth-check designs for targets without reservation | Apache-2.0 | Primary source |

**Licensing notes.**

- The program half of Goose's runtime (Apache-2.0) is copied into every generated C file, so every Revival OS image contains Apache-2.0 code. Distributing images therefore requires the licence text and any NOTICE.
- Route B would bring in the whole runtime under the same terms.
- Revival OS itself has **no `LICENSE` yet**. The owner should choose one before any third-party code is copied into the repository.

## Unresolved questions

**Hardware** (answered by the phase named):

1. The `Features` line: VFPv4, NEON, `idiva`/`idivt`, LPAE (Phase 0 C5).
2. The CPU mode and the MMU, cache and watchdog state at entry (Phase 2).
3. Whether the non-secure `VBAR` behaves as on QEMU under Samsung's TrustZone (Phase 2–3a).
4. Krait's alignment behaviour, confirmed against QEMU's (first device run that executes Goose code).

**Goose** (asked in the [draft questions](goose-upstream-questions.md)):

1. The largest unwritten bump compared with the guard gap.
2. Whether any elided check needs a minimum reservation.
3. The status of the `gs_*` interface.
4. Other 64-bit assumptions in the generated C.
5. The native-stack frame bound.
6. Freestanding support on AArch64.

## What this does not show

- **No device measurement.** Address budgets, costs and alignment behaviour are QEMU results or documented architecture, not Krait results.
- **No effort estimate beyond line counts**, which are indications, not commitments.
- **Not a decision.** It is input for one.
