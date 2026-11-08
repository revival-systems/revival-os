# Questions for Goose developers

**Status: draft, not sent.** Posting it needs the owner's authorization, as do the choice of venue and the wording. Prepared 2026-11-08 from the [dependency map](goose-runtime-dependency-map.md).

The message must stand on its own: this repository is internal, so it links nothing in it.

## Already answered upstream, so not asked again

| Topic | Upstream answer |
| --- | --- |
| 32-bit and WebAssembly support | Not supported unless it can be done well; the design depends on 64-bit address-space reservation ([#134](https://github.com/aardappel/goose/issues/134), 2026-10-29; [#246](https://github.com/aardappel/goose/issues/246), 2026-11-07) |
| Growth checks for targets without reservation | A proposal, not implemented ([`docs/design/wasm.md`](https://github.com/aardappel/goose/blob/v2026.3/docs/design/wasm.md); spec open item 15) |
| Calling exports from several host threads | Not supported: "Goose as a library" is single-threaded by design ([#232](https://github.com/aardappel/goose/issues/232)) |
| Unaligned typed access in generated C | Fixed by `aligned(1)` typedefs in [`cec434a`](https://github.com/aardappel/goose/commit/cec434a54b150ce1570b70fecedc0b0c4b928121), released in v2026.4 ([#114](https://github.com/aardappel/goose/issues/114), [#125](https://github.com/aardappel/goose/issues/125)) |
| Calling `static inline` C and macros from Goose | Under discussion in [#223](https://github.com/aardappel/goose/issues/223); `extern fn` emits its own prototype. Device-register access therefore goes through ordinary C functions |

## Recommended venue

- **The draft message: a comment on [#246](https://github.com/aardappel/goose/issues/246).** It continues the 32-bit discussion where the maintainer already answered, and he prefers to keep one topic in one place (he redirected #235 to #223 for that reason). A Q&A discussion would also fit, because the questions are about the runtime contract rather than a request. Discord suits quick follow-ups.
- **The bug report: a separate issue.** It is small and target-independent.

## Draft message

> **Freestanding embedding on ARMv7-A with an MMU: which runtime assumptions must hold?**
>
> Hi! A follow-up to #246 from a different angle. We are experimenting with Goose as the implementation language of a small OS for an old ARMv7-A phone (Qualcomm Krait, 1.5 GB RAM). Unlike the microcontrollers in #246, it has an MMU, and the OS owns the whole 32-bit address space. So each data stack can get a real reservation with an unmapped guard gap behind it (for example 32 MiB plus the default 1 MiB gap, backed up front or committed on fault), not a slice of a static buffer.
>
> We understand that 32-bit is not supported, and we are not asking for it. We use the compiler unchanged (`--header`, `goose_init`) and implement the `gs_*` entry points the generated C calls in our own code. We would like to know which assumptions we must not break:
>
> 1. **Guard gap and unwritten bumps.** Generated code bumps a stack's `top` with no capacity check and relies on the gap (spec App. C.4). Is there an upper bound on a single bump that is not written front to back, for example a large limited-array capacity or a large fixed aggregate placed on a data stack? Must `GS_STACK_GAP` be at least that bound for an overrun to be caught?
> 2. **Reservation size.** `gs_reserve_region` says a region smaller than `GS_STACK_RESERVE` is always safe. Does that hold for every check the compiler elides, and does anything depend on all regions having the same size?
> 3. **The `gs_*` interface.** Is the set of entry points the generated C calls stable within a release? Would a short document of it, or a switch that leaves the POSIX and Win32 code out of the runtime object, be welcome, with the platform side staying ours?
> 4. **32-bit assumptions in the generated C.** v2026.3 stored doubles through `double *` at packed offsets, which ARMv7 `STRD` faults on; cec434a fixed that. Do you know of other places that assume 8-byte pointers or a 64-bit `size_t`? If we report such issues, would fixes that cost nothing on 64-bit targets be accepted?
> 5. **Native stack.** Generated code has no native-stack checks. Is one unmapped guard page below each native stack enough, or can a single frame (for example `alloca` for a variable-size local) be larger than a page?
> 6. **64-bit bare metal.** Our later target is AArch64, where the address-space assumptions hold. Would a freestanding AArch64 target, with the OS providing reservation and fault handling, be something you'd consider supported?
>
> Thanks for Goose. We're happy to share the measurements behind these questions.

## Draft bug report

> **`goose --stacks` divides by zero when a worker holds no data-stack regions**
>
> With v2026.3, `goose --stacks -o out.c repro.goose` ends with "Floating point exception" (exit status 136) for:
>
> ```goose
> thread_fn work(n: i64) { if n < 0 { abort("neg"); } }
> fn main() {
>     let id = thread_spawn(work, 3);
>     if !thread_wait(id) { abort("failed"); }
> }
> ```
>
> Compiling without `--stacks` works. `CodeGen::StackReport` computes `spare / workerregions` with `workerregions == 0` (`src/codegen_stacks.h:146-147` in v2026.3, line 151 in v2026.4). `gs_rt_start` guards the same computation with `if (workerregions > 0)`. The same guard in the report would fix it.

## Why each question matters

| Question | Revival OS decision it informs |
| --- | --- |
| 1. Unwritten bumps | Whether a 1 MiB unmapped gap (one ARMv7 section) is enough, or the region provider must also bound or pre-touch large allocations |
| 2. Reservation size | Whether regions can be sized per program, and smaller than the default, without breaking elided checks |
| 3. The `gs_*` interface | How much the freestanding layer must change at each compiler pin change |
| 4. 32-bit assumptions | Whether the generated C can be trusted on ARMv7 beyond what the probes measured |
| 5. Native stack | How large each native stack's guard must be |
| 6. AArch64 | Whether the second hardware target is a supported configuration, which bears on the target order |
