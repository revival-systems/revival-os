# Goose runtime dependency map (pinned v2026.3)

**Status:** research for the runtime-route decision ([decisions needed](goose-freestanding-notes.md#decisions-needed-before-phase-1-implementation)), 2026-11-08. Everything here ran on the development machine and in QEMU. **Nothing ran on the Samsung.** No Revival OS code depends on this document yet.

**Sources:**

- Upstream Goose at tag [`v2026.3`](https://github.com/aardappel/goose/tree/v2026.3) (commit `8511ae34`, Apache-2.0): the runtime in `src/runtime/` (about 4,000 lines) and the compiler code that calls into it. File links below point at that tag.
- The runtime C that the pinned binary writes (`goose --emit-runtime`, `GS_RUNTIME_VERSION 4d3da949e563`).
- The language specification shipped with the release (`docs/goose_spec.md`, v4 draft), cited as "spec §".
- Measurements: 25 distribution samples and 34 one-construct probes, compiled by the pinned compiler and cross-compiled with this repository's ARMv7-A flags ([method](#method)), plus QEMU runs of individual instructions.

## How Goose code reaches the runtime

Goose compiles to C. The runtime comes in two halves ([implementation §7](https://github.com/aardappel/goose/blob/v2026.3/docs/implementation.md#7-the-runtime)):

- **The program half** ([`runtime.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h), [`runtime_ext.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_ext.h)) is copied into every program's C: types, integer helpers, bounds and division checks, varints, the data-stack state `gs_stks`, and the startup functions. It is part of every image.
- **The runtime object** ([`runtime_impl.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h), [`runtime_threads.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_threads.h), [`runtime_os.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_os.h)) holds the failure paths, data-stack regions, threads and queues, the OS layer behind `stdlib/os.goose`, text forms and output, slice-pool freelists and byte search. It is the only part that includes platform headers, and it has exactly two platform branches: Windows and POSIX.

The halves meet through **43 `GS_API` entry points** in v2026.3. The interface is internal: it is not documented as an API, and the runtime's hash renames `gs_rt_start_<hash>` so that a program and runtime from different compilers fail to link. It changes between releases. v2026.4 (16 days and 323 commits later) removed `gs_out_int`, `gs_out_uint`, `gs_out_flt`, `gs_out_f32` and `gs_out_bool`, added `gs_dl_bind`, `gs_qfree`, `gs_rt_stop` and `gs_stack_overflow`, and changed the runtime sources by +1,442/−126 lines.

| Group | Entry points (v2026.3) |
| --- | --- |
| Failure, all `noreturn` (12) | `gs_panic`, `gs_abort`, `gs_abort_msg`, `gs_exit`, `gs_idxfail`, `gs_divfail`, `gs_divovf`, `gs_ovf`, `gs_ovf_neg`, `gs_asfail_i`, `gs_asfail_u`, `gs_asfail_f` |
| Startup and regions (4) | `gs_rt_start_<hash>`, `gs_reserve_region`, `gs_release_regions`, `gs_stack_stats` |
| Threads and queues (10) | `gs_hardware_threads`, `gs_thread_start`, `gs_thread_wait`, `gs_free_msg`, `gs_qinit`, `gs_qput`, `gs_qget`, `gs_qwait`, `gs_qpoll`, `gs_qlimit` |
| Slice pools (3) | `gs_spans_alloc`, `gs_spans_regrow`, `gs_spans_free` |
| Text forms and output (12) | `gs_fmt_i64`, `gs_fmt_u64`, `gs_fmt_f64`, `gs_fmt_f32`, `gs_fmt_bool`, `gs_fmt_quoted`, `gs_out_int`, `gs_out_uint`, `gs_out_flt`, `gs_out_f32`, `gs_out_bool`, `gs_out_bytes` |
| Byte search (2) | `gs_scan_any`, `gs_scan_pair` |
| OS layer (declared in `runtime_ext.h`) | `gs_os_*`: files, directories, stdin/stdout/stderr, arguments, environment, wall and monotonic clocks, sleep, random |

**Startup** ([`runtime.h:888-905`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h#L888-L905)):

1. The host calls `goose_init(argc, argv)`.
2. `goose_init` runs `gs_program_init`, which calls `gs_rt_init`.
3. `gs_rt_init` calls `gs_rt_start_<hash>(argc, argv, GS_STACK_RESERVE, GS_STACK_GAP, GS_STACK_BUDGET, mainregions, workerregions)`, then `gs_stack_block(mainstacks)`.
4. `gs_stack_block` `calloc`s one control block per data stack (a `NULL` result goes to `gs_panic`) and calls `gs_reserve_region()` once per stack.
5. The globals are initialized.

Every exported function panics if `goose_init` has not run.

The hosted `gs_rt_start` ([`runtime_impl.h:1332`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L1332)) does six things:
- records the sizes
- computes the worker cap
- makes `stdout` unbuffered
- installs `SIGSEGV`/`SIGBUS` handlers
- allocates the region registry, sets up an alternate signal stack and reads the native stack's bounds
- runs x86 CPUID detection for byte search

## Measured runtime surface

### By construct

Each probe is a few lines of Goose that use one construct, with inputs the optimizer cannot fold (exported functions). The **baseline** every program needs is `calloc`, `gs_panic` and `gs_rt_start_<hash>`. The table lists what each construct adds.

| Construct | Adds (release build) | Adds in `--debug` |
| --- | --- | --- |
| Integers, loops, fixed arrays, `enum` and `match`, a string literal read byte by byte | nothing | nothing |
| An index that may be out of range | `gs_idxfail` | — |
| `assert(...)` | `gs_abort` | — |
| `abort("msg")` | `gs_abort_msg` | — |
| `exit(code)` | `gs_exit` | — |
| `i64` `/` | `gs_divfail`, `gs_divovf`, `__aeabi_ldivmod` | — |
| `i64` `%` (Euclidean) | `gs_divfail`, `__aeabi_ldivmod` | — |
| `i32` `/` | `gs_divfail`, `__aeabi_ldivmod` (64-bit, see [finding 3](#32-bit-findings)) | `gs_ovf` |
| Push to a limited array (`u8[..8]`) | `gs_abort` | — |
| `pop` on a grow-shrink array (`[>..<]`) | `gs_abort`, `gs_reserve_region` | — |
| `i32` `+` | nothing (wraps) | `gs_ovf` |
| Narrowing `as` (`i64` to `i32`) | nothing (truncates) | `gs_asfail_i` |
| `f64` to `i32` `as` | `fmod`, `trunc`, soft-float helpers | `gs_asfail_f` (no `fmod`/`trunc`) |
| `recursive fn` | nothing: no native-stack check is emitted | `gs_ovf` (the arithmetic) |
| `f64` arithmetic and `sqrt` (`import math`) | `sqrt`, `__aeabi_dadd`, `__aeabi_dmul` | — |
| Grow-only array (`[>..]`) | `gs_reserve_region` | — |
| Text building (`append`, `format`) | `gs_reserve_region`, `gs_fmt_i64` | — |
| `print("literal")` | `gs_reserve_region`, `gs_out_bytes`, `memcpy` | — |
| `print(integer)` | as above, plus `gs_fmt_i64` | — |
| `reusable` pool (`alloc_index`, `free`) | `gs_reserve_region`, `gs_idxfail`, `memcpy` | — |
| Slice pool (`reusable[]`, `alloc_slice`, `realloc_slice`, `free_slice`) | `gs_reserve_region`, `gs_spans_alloc`, `gs_spans_free`, `gs_abort`, `memset` | — |
| `thread_spawn`, `thread_wait` | `gs_thread_start`, `gs_thread_wait`, `gs_abort_msg`, `gs_reserve_region`, `free`, and thread-local storage | — |
| `thread_spawn_contained` | as above, plus `gs_free_msg`, `gs_abort`, `memcpy` | — |
| `import os`, `clock()` | `gs_os_clock_ns`, `gs_out_bytes`, `gs_reserve_region`, soft-float helpers | — |

### Across the samples

The 25 non-graphical distribution samples that compile for ARM need the following. `24_call_c` does not compile for ARM; see [finding 4](#32-bit-findings).

| Needed | Samples |
| --- | --- |
| Data stacks (`gs_reserve_region`), output (`gs_out_bytes`, `gs_fmt_*`), `calloc`, `memcpy`, `gs_panic` | 25 of 25 |
| `gs_idxfail` | 22 |
| `gs_abort` | 19 |
| 64-bit division helpers (`__aeabi_ldivmod`, `__aeabi_uldivmod`) | 14 |
| Soft-float helpers (`__aeabi_d*`, `__aeabi_f*`) | 12 |
| `libm` (`fmod`, `trunc`, `sqrt`, `sqrtf`, `floorf`, `pow`, `sin`) | 10 |
| OS layer (`gs_os_*`) | 10 |
| Threads and queues | 1 |
| Slice pools | 1 |

Data stacks per sample (`goose --stacks`): 3 to 26 regions for the main program, median 6. The default is 2 GiB reserved per stack with a 1 MiB guard gap, and a compile-time cap of 1,024 stacks.

### Method

```sh
G=$HOME/.local/share/goose/v2026.3/goose
CC=$HOME/.local/share/revival-os/toolchains/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin/arm-none-eabi-gcc
export GOOSE_HOME=$(mktemp -d)                 # keep ~/.goose untouched
"$G" [--debug] --header probe.h -o probe.c probe.goose
"$CC" -march=armv7-a -marm -mfloat-abi=soft -std=gnu11 -O2 -ffreestanding -fno-builtin \
      -fno-common -ffunction-sections -fdata-sections -w -c probe.c -o probe.o
"${CC%gcc}nm" -u probe.o                       # the runtime surface this construct needs
"$G" --stacks -o /dev/null sample.goose        # data stacks per program
```

Samples use `-o` alone (they have `main`). Nothing is linked or run, except the QEMU instruction tests cited in the findings.

## Dependency map by topic

**Layer** says where the capability lives: *compiler* (expanded inline into the program's C), *program half* (runtime code copied into the program), *runtime object*, or *OS*.

| Topic | Layer | Works with no OS today? | What Revival OS must provide | When |
| --- | --- | --- | --- | --- |
| [Startup](#startup) | program half; `gs_rt_start` in the runtime object | Yes, with the fixture stub | Entry stub, a `goose_init` call, a `gs_rt_start` that honours or refuses the sizes it is given | Now (exists as a fixture) |
| [Runtime-internal allocation](#runtime-internal-allocation) | `calloc` (stack block), `malloc`/`free` (messages, queues) | Yes, with a bounded allocator | A zeroing, bounded allocator that fails loudly | Now; a freeing allocator with threads |
| [Data stacks](#data-stacks) | compiler (bump, no capacity check); `gs_reserve_region` | **No**: needs `mmap`, `mprotect` and signals | Reserved regions with an unmapped guard gap, and a fault path that reports overruns | **Next**: needs the MMU |
| [Strings](#strings-and-arrays) | compiler; builders on data stacks | Literals yes; building no | Data stacks | With data stacks |
| [Arrays](#strings-and-arrays) | compiler; resizable kinds on data stacks; slice pools in the runtime object | Fixed arrays and slices yes | Data stacks; `gs_spans_*` is portable C | With data stacks |
| [Bounds checks](#bounds-checks) | compiler + `gs_idxfail` | Yes (shown in QEMU) | The failure path | Now |
| [Panic, abort, assert, exit](#panic-abort-assert-and-exit) | `gs_fail` in the runtime object | Only through a stub | Message, location and status to a console, then halt or reset, with no heap | Now |
| [Integer overflow](#integer-overflow) | compiler; `--debug` calls `gs_ovf`, `gs_asfail_*` | Yes | The failure path | Now |
| [Division](#division) | compiler checks; libgcc 64-bit helpers | Yes (libgcc is linked) | The failure path | Now |
| [Floating point and math](#floating-point-and-math) | soft-float in libgcc; `libm` behind `math` and float-to-int `as` | Arithmetic yes; `libm` no | A licence-reviewed `libm` subset, or the functions in Goose | When a service needs them |
| [Native call stack](#native-call-stack) | nothing in generated code; the hosted runtime uses signals | No detection | A guard page below each native stack and a fault path | With the MMU (a Phase 1 negative test) |
| [Threads, queues, TLS, atomics](#threads-queues-tls-and-atomics) | runtime object (pthreads); `__thread` | No | TLS blocks and `TPIDRURO` per thread, a scheduler, locks, atomics on Normal memory | Later (after Phase 3 scheduling) |
| [Contained workers](#contained-workers) | `setjmp`/`longjmp` and `malloc` | No | Non-local exit; only with threads | Later |
| [Text forms and output](#text-forms-and-output) | runtime object (digit loops, not `printf`) | The formatting is portable C; the sink is not | A byte sink (UART or framebuffer) behind `gs_out_bytes` | With data stacks (printing uses one) |
| [OS layer](#os-layer) | `runtime_os.h` (POSIX or Win32) | No | One function at a time, as services need it: a monotonic clock first | Later |
| [Hardware access](#hardware-access) | `extern fn` into C | Yes, through C or assembly helpers | Small accessors for device registers and CP15 | When drivers start |

### Startup

- **Language:** a program has an entry and initialized globals ([spec §11.1](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#111-modules-and-globals)). An embedding host calls `goose_init` once before any export ([spec §7.11](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#711-exporting-goose-functions-to-c)).
- **v2026.3:** see [startup](#how-goose-code-reaches-the-runtime). Unbuffered `stdout`, signal handlers, the alternate signal stack and CPUID are implementation choices.
- **Revival OS:** the entry stub zeroes `.bss`, sets the stacks and calls `goose_init`. `gs_rt_start` records the sizes and refuses any it cannot honour.
- **Test:** a program with *n* data stacks starts and gets *n* regions. Calling an export before `goose_init` must panic with its message (negative).

### Runtime-internal allocation

- **Language:** there is no general heap. All dynamic data lives on data stacks ([spec §1.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#12-memory-model)). The runtime may allocate for its own needs.
- **v2026.3:**
  - `calloc` allocates the stack block at startup ([`runtime.h:888`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h#L888)).
  - `malloc` allocates failure messages (`gs_fail`), queue nodes, the region registry and the alternate signal stack.
  - `free` releases them.
- **Revival OS:** a bounded, zeroing allocator for the startup block, which the fixture's 64 KiB arena already provides. The failure path should not need a heap. A freeing allocator is needed only with threads and queues.
- **Test:** exhaust the allocator (a small arena), then check for `out of memory allocating stack block` and a failure status.

### Data stacks

- **Language** (spec [§1.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#12-memory-model), [§9.3](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#93-what-the-runtime-still-checks), [§10.4](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#104-runtime-environment), [App. C.1 and C.4](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#c4-guard-pages-and-commit-order)):
  - Every resizable value lives on one of *N* data stacks. *N* is fixed at compile time (here 3 to 26 per sample).
  - Allocation is `top += size`, and scope exit restores a watermark.
  - Nothing moves, so references stay valid as stacks grow.
  - An overrun must end in a **safe abort, never corruption**.
  - A stack is at most 2^48 bytes. A platform may reserve less.
- **What the compiler relies on:** generated code bumps the top **with no capacity check**. A `push` compiles to `*(int64_t *)t7 = v; t7 += 8;` and a text append to `memcpy(top, p, n); top += n` ([`runtime_ext.h:22`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_ext.h#L22)). Safety comes from three things:
  - the unmapped guard gap behind each region (default 1 MiB, `GS_STACK_GAP`)
  - construction writing front to back
  - the runtime's rule that the checks the compiler leaves out "assume no more than `GS_STACK_RESERVE` bytes in a stack", so a smaller region is always safe ([`runtime_impl.h:548-555`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L548-L555))
- **v2026.3** (implementation choices) ([`runtime_impl.h:497`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L497), [`:555`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L555), [`:399`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L399)):
  - `mmap` of 2 GiB plus the gap with `MAP_NORESERVE`, then `mprotect(PROT_NONE)` on the gap.
  - A refused reservation is retried at half the size, down to 1 MiB.
  - A per-thread registry lets a `SIGSEGV`/`SIGBUS` handler tell an overrun from a crash and print without stdio.
- **Revival OS:** reserve each region in virtual address space with an unmapped gap behind it, which needs the MMU (ARMv7-A short-descriptor tables), and report a data abort in a gap as an overrun. Regions can be fully backed at reservation; committing pages on fault can come later, with the frame allocator. The address-space budget is in the runtime options research.
- **Test:** growth within a region matches an oracle. Growth past it is reported as an overrun (negative). Too many regions is refused (negative). The gap is required: with it mapped instead, the overrun test must fail.

### Strings and arrays

- **Language** ([spec §3.3](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#33-the-array-family), [§3.7](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#37-strings), [§5](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#5-the-resizableshrink-rules)):
  - A string is a `u8` array. Literals are static data.
  - Fixed and limited arrays are inline.
  - Grow-only, grow-shrink and pool arrays live on data stacks. Slices are views.
- **v2026.3:**
  - Literals, fixed arrays, slices and `enum`s need nothing beyond the baseline (measured).
  - Building text, resizable arrays, `print`, `reusable` pools and slice pools need `gs_reserve_region`.
  - Slice pools also need `gs_spans_*`, a B+ tree freelist in plain C with no OS dependency ([`runtime_impl.h:874`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L874)).
- **Revival OS:** data stacks. The slice-pool code needs no platform service.
- **Test:** build text and arrays of known content and compare bytes with an oracle. Limited-array overflow and `pop` on an empty array must fail through `gs_abort` (negative).

### Bounds checks

- **Language:** an out-of-range index aborts ([spec §9.3](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#93-what-the-runtime-still-checks)). Checks proved unnecessary are elided ([spec §10.5](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#105-bounds-check-elimination)).
- **v2026.3:** inline compare, then `gs_idxfail(i, n, file, line)`, which formats with `vsnprintf`. Checks stay in release builds.
- **Revival OS:** the failure path. Already shown in QEMU (`qemu-index-out-of-range`).
- **Test:** the existing positive and negative tests.

### Panic, abort, assert and exit

- **Language** ([spec §9.3](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#93-what-the-runtime-still-checks)):
  - Aborts print `goose runtime error: <msg>` and end the program. They cannot be caught, except inside a contained worker.
  - `exit(code)` ends normally with a status.
  - None of them returns.
- **v2026.3:** `gs_fail` builds the message with `snprintf` in a `malloc`ed buffer, appends ` (file:line)`, writes it to `stderr` and calls `gs_end`. In a contained worker it `longjmp`s instead. `gs_end` uses an atomic so that only the first ender proceeds, then `fflush` and `_Exit` ([`runtime_impl.h:49-160`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L49-L160), [`:536`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L536)).
- **Revival OS:** the same text and location written byte by byte to the console with no heap and no `printf`, then a defined halt or reset. A crash record is added in Phase 3e.
- **Test:** every §9.3 route reachable without data stacks gives its message, location and failure status. Measured routes: `gs_abort`, `gs_abort_msg`, `gs_exit`, `gs_idxfail`, `gs_divfail`, `gs_divovf`, `gs_ovf`, `gs_asfail_i` and `gs_asfail_f`.

### Integer overflow

- **Language** ([spec §6.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#62-integer-semantics)):
  - Each operation runs at its own width.
  - Overflow is checked in debug builds only.
  - Unsigned arithmetic wraps by definition.
- **v2026.3:** release helpers are macros that compute in 64 bits and truncate (`gs_add_i32`, [`runtime.h:572`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h#L572)). `--debug` calls `gs_ovf`, `gs_ovf_neg` and the `as` failures.
- **Revival OS:** nothing beyond the failure path. Kernel code that must detect overflow has two choices: `--debug` builds, which check every operation, or explicit checks. That is a policy decision, still open in the [freestanding notes](goose-freestanding-notes.md#decisions-needed-before-phase-1-implementation).
- **Test:** a release build wraps and matches an oracle. A `--debug` build reports the overflow with its location (negative).

### Division

- **Language:** division and modulo by zero always abort. `%` is Euclidean. `INT64_MIN / -1` overflows.
- **v2026.3:** inline checks call `gs_divfail` or `gs_divovf`. The division itself is a C operation. On ARMv7 every 64-bit division, **and every `i32` division**, is a libgcc call ([finding 3](#32-bit-findings)).
- **Revival OS:** libgcc, already linked, and the failure path.
- **Test:** quotients and remainders match an oracle across signs. Division by zero and `INT64_MIN / -1` must fail with their messages (negative).

### Floating point and math

- **Language:** `f32` and `f64` are IEEE types. `math` binds C functions through `extern fn`.
- **v2026.3:**
  - The program calls `sqrt`, `sin`, `pow`, `fmod`, `trunc`, `floorf` and similar `libm` functions directly.
  - A float-to-integer `as` in a release build uses `fmod` and `trunc` even without `import math`.
  - With `-mfloat-abi=soft`, arithmetic goes through libgcc's `__aeabi_*` helpers.
- **Revival OS:** keep soft-float until the VFP features are confirmed (Phase 0 C5). Floating point is not needed by the kernel core. When a service needs `libm`, the options are:
  - a licence-reviewed freestanding subset, for example from a permissively licensed C library
  - Goose implementations
- **Test:** results compared with the host bit for bit, and with a reference within a stated error for `libm` functions.

### Native call stack

- **Language:** recursion uses only the native stack and must be declared `recursive`. Running out is a safe abort ([spec §7.8](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#78-recursion), §9.3).
- **v2026.3:** generated code contains **no** native-stack check (measured). The hosted runtime catches overflow by address: a fault within 64 KiB below the thread's stack, found by a signal handler running on an alternate stack ([`runtime_impl.h:399-480`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L399-L480)).
- **Revival OS:** an unmapped guard page below every native stack, and a data-abort path that reports the overflow from a separate abort-mode stack. Without the MMU, a deep recursion silently overwrites `.bss`, as in today's fixture.
- **Test:** unbounded recursion must be reported as a native stack overflow (negative). This is also a Phase 1 negative test.

### Threads, queues, TLS and atomics

- **Language** ([spec §11.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#112-concurrency)):
  - Workers are separate program instances that share nothing mutable.
  - Flat values cross between them through typed queues.
  - `hardware_threads()` is capped by the data-stack budget.
- **v2026.3:**
  - Threads are pthreads.
  - Queues use mutexes and condition variables.
  - `sysconf` gives the CPU count.
  - Atomics run through `__atomic`.
  - A program that spawns threads compiles with `GS_NEED_THREADS 1`, so `gs_stks`, `gs_gl` and the region registry are `__thread`. On ARMv7, GCC reads the thread pointer from `TPIDRURO` (`mrc p15, 0, rN, c13, c0, 3`, four reads in the threads sample) and emits `.tdata`/`.tbss`. Single-threaded programs use no TLS.
  - "Goose as a library" is single-threaded by design ([#232](https://github.com/aardappel/goose/issues/232)). With no threads, the data-stack state is one plain global, so a second caller corrupts it silently.
- **Revival OS:** later, after scheduling exists. Each thread needs a TLS block and `TPIDRURO`, and atomics need Normal memory. Until then, interrupt handlers must not call Goose code that uses data stacks while Goose code may be running. They should hand events to the Goose main loop.
- **Test:** later. A first one is a worker that returns a value through a queue, compared with an oracle.

### Contained workers

- **Language:** an abort in a worker started with `thread_spawn_contained` ends only that worker ([spec §11.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#112-concurrency)).
- **v2026.3:** `_setjmp` and `_longjmp` with a `malloc`ed message ([`runtime_threads.h:161`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_threads.h#L161)). This is one of the two reasons the runtime object does not compile for `arm-none-eabi` (`_longjmp` is undeclared there).
- **Revival OS:** a small `setjmp`/`longjmp` in assembly, only when threads exist.
- **Test:** later.

### Text forms and output

- **Language:** `print`, `format` and `str` render any value as text ([spec §3.7](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#37-strings)).
- **v2026.3:**
  - `gs_fmt_*` write digits into a data-stack buffer without `printf`.
  - `gs_out_bytes` writes to `stdout` with `fwrite`.
  - Floats are formatted by the runtime ([`runtime_impl.h:1381`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L1381)).
  - Printing even a literal needs a data stack (measured).
- **Revival OS:** a byte sink behind `gs_out_bytes`: UART on QEMU, then UART-DM or the framebuffer console on the device. The formatting code is portable C.
- **Test:** console bytes equal the expected text for integers, unsigned values, booleans, quoted text and selected floats.

### OS layer

- **Language:** `stdlib/os.goose` binds `gs_os_*` through `extern fn`. It is a library, not part of the core language.
- **v2026.3:** POSIX and Win32 calls for files, directories, stdio, arguments, environment, `clock_gettime`, `nanosleep` and random numbers ([`runtime_os.h`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_os.h)).
- **Revival OS:** none at first. Each function arrives with the service that needs it. A monotonic clock comes first; on the GT-I9195 it would come from the KPSS timer (Phase 3d). Storage arrives in Phase 4. Code that imports `os` keeps failing the freestanding link, which the existing negative test checks.
- **Test:** the clock is monotonic and advances (QEMU, then the device). Each later function gets its own test.

### Hardware access

- **Language:** Goose has no raw pointers, no `volatile` and no device-register type. C is reached through `extern fn` ([spec §7.10](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#710-extern-fn)).
- **v2026.3:** an `extern fn` emits its own prototype and includes no header. It therefore cannot bind a `static inline` function or a macro ([#235](https://github.com/aardappel/goose/issues/235), [#223](https://github.com/aardappel/goose/issues/223)).
- **Revival OS:** device registers, CP15 and barriers are reached through small C or assembly functions, each one an out-of-line call (link-time optimization may inline them). [ARCHITECTURE.md](../../ARCHITECTURE.md#goose-and-low-level-code) already limits assembly to what Goose cannot express.
- **Test:** an `extern fn` accessor reads a QEMU device register (the PL011 flag register) and returns its documented reset value.

## Language requirements and implementation choices

**What the language requires** (any Revival OS runtime must keep these):

1. *N* data stacks per program instance, *N* fixed at compile time, each contiguous, never moving, with a bump top and a watermark restored at scope exit.
2. Overrunning a data stack is a safe abort, never corruption. Generated code relies on the region and its guard, not on checks of its own.
3. A smaller reservation is allowed; a larger single stack than reserved is not.
4. Failed checks abort with a message and location. Division by zero is always checked. Overflow and range checks exist only in debug builds.
5. Native-stack exhaustion is a safe abort.
6. Program instances (workers) share no mutable state. Exported functions are single-threaded.
7. Packed layouts: values sit at any byte address ([spec App. C.2](https://github.com/aardappel/goose/blob/v2026.3/docs/goose_spec.md#c2-value-layouts)), so the target must allow unaligned access or the C must avoid it ([finding 1](#32-bit-findings)).

**What is an implementation choice of the hosted runtime** (Revival OS need not copy them):

- `mmap` with overcommit and `MAP_NORESERVE`; `mprotect` for gaps; halving refused reservations.
- Signal handlers, `sigaltstack` and `pthread_getattr_np` for overrun reporting.
- pthreads, mutexes and condition variables; `sysconf` for the CPU count.
- stdio for output, `snprintf` and `malloc` for messages, unbuffered `stdout`, `_Exit`.
- `setjmp`/`longjmp` for contained workers.
- x86 CPUID and SSE2/SSSE3 byte search, which falls back to scalar code on other CPUs.
- Default sizes: 2 GiB per stack, 1 MiB gap, 32 TiB budget.

## What Revival OS must provide first

1. **Failure path:** console output of `goose runtime error: <msg> (file:line)`, then a defined halt or reset, for all twelve failure entry points, with no heap.
2. **Data-stack regions with guard gaps**, which require an identity-mapped MMU in the fixture, plus overrun reporting from the data-abort handler.
3. **Native-stack guard** below the stack, reported the same way.
4. **Output sink** behind `gs_out_bytes`, and the portable `gs_fmt_*` functions.
5. **`libgcc`** (already linked) and `memcpy`, `memmove`, `memset`, `memcmp` (already in the fixture).

**Can wait:** threads, queues and TLS; contained workers; the OS layer except a monotonic clock; `libm`; slice pools (portable, add when used); commit-on-fault for regions; caches and performance work.

## 32-bit findings

1. **v2026.3's generated C makes typed accesses at unaligned addresses, and ARMv7 faults on them.**
   - The runtime's own header says the C needs "unaligned scalar access" ([`runtime.h:2`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h#L2)). In the JSON sample, a number is stored after a tag byte, a varint and the key bytes: `*(double *)t76 = t73;`. GCC 15.2 compiles that to `strd r0, [r3, #1]`.
   - On ARMv7, `LDRD`/`STRD` (and `LDM`/`STM`) need word alignment whatever `SCTLR.A` says.
   - Upstream fixed the C in commit [`cec434a`](https://github.com/aardappel/goose/commit/cec434a54b150ce1570b70fecedc0b0c4b928121) (2026-10-27, "Fix alignment of packed values in generated C"). It makes packed accesses go through `aligned(1)` typedefs. That commit is in **v2026.4, not in the pinned v2026.3**.
   - QEMU results (QEMU 10.2.1, `cortex-a15`, `DFSR.FS` read in the abort handler; not hardware results):

   | Access (address `buf + 1` unless noted) | MMU off | MMU on, Normal memory |
   | --- | --- | --- |
   | `LDR` (word) | alignment fault | completes |
   | `STRD` | alignment fault | alignment fault |
   | `STRD` at `buf + 4` (word-aligned) | completes | completes |
   | GCC's code for `*(double *)p = x` | — | `strd`: alignment fault |
   | GCC's code for the same store through an `aligned(1)` typedef (the v2026.4 form) | completes (8 `strb`) | completes (8 `strb`) |

   - With GCC's default for ARMv7-A (`-munaligned-access`), 32- and 64-bit `aligned(1)` accesses compile to plain `ldr`/`str`, which need the MMU on. `-mno-unaligned-access` turns them into byte accesses.
   - So Goose code with packed data needs both of these before it can run on ARMv7: **a compiler with `cec434a`**, and **either the MMU on or `-mno-unaligned-access`**.

2. **With the MMU off, all memory is Strongly-ordered.** Unaligned accesses there are architecturally unpredictable unless they fault, and in QEMU they fault. Today's probe works only because its accesses are aligned.
3. **Narrow integer division is 64-bit.** The release helpers compute `i8` to `i32` in 64 bits ([`runtime.h:482`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime.h#L482)), so every `i32` `/` and `%` is a call to libgcc's `__aeabi_ldivmod`. This is correct, but slow on a CPU whose hardware divide, if present, is 32-bit.
4. **`extern fn` prototypes conflict with newlib.** `24_call_c` does not compile for `arm-none-eabi`. `extern fn abs(x: i32) -> i32` emits `int32_t abs(int32_t)`, while newlib's `int32_t` is `long`, which conflicts with `<stdlib.h>`'s `int abs(int)`. On x86-64 Linux `int32_t` is `int`, so the conflict does not appear there.
5. **Reservations of 4 GiB or more truncate on 32-bit.** `gs_rt_start` takes `uint64_t` sizes but stores them as `size_t` ([`runtime_impl.h:1336`](https://github.com/aardappel/goose/blob/v2026.3/src/runtime/runtime_impl.h#L1336)). The 2 GiB default fits; nothing that large is usable on a 32-bit target anyway. [#134](https://github.com/aardappel/goose/issues/134) describes an older `size_t` signature.
6. **Float-to-integer `as` needs `libm` in release builds** (`fmod`, `trunc`), even without `import math`.
7. **Address space:** with 3 to 26 regions per program and a 1 MiB gap each, 32-bit regions can be tens to a few hundred MiB, not 2 GiB. The budget is worked through in the runtime options research.

## Side finding: `goose --stacks` divides by zero

`goose --stacks` crashes with `SIGFPE` (exit status 136) for a program whose worker holds no data-stack regions, such as a worker taking one `i64` that only asserts on it. `CodeGen::StackReport` computes `spare / workerregions` without the guard that the runtime's own `gs_rt_start` has ([`codegen_stacks.h:146-147`](https://github.com/aardappel/goose/blob/v2026.3/src/codegen_stacks.h#L146-L147); unchanged in v2026.4 at line 151). Compiling without `--stacks` is unaffected. No upstream issue was found for it.

## What this does not show

- **Nothing about the Samsung.** Every run here is QEMU or the host. The alignment results describe QEMU's model of ARMv7-A. Krait must be checked in Phase 2 or later.
- **Not every construct.** The probes cover one construct at a time. Interactions (for example a value of one stack built while another grows) were not measured.
- **v2026.4 was read, not run.** The `aligned(1)` result uses a hand-written C store of the same form, not v2026.4's generated code.
- **No performance figures.**
- **Not the compiler's internal invariants**, for example the largest unwritten bump relative to the gap. Those are asked upstream.
