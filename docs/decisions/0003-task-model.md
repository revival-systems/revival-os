# ADR 0003 — The task model: what one task costs (emulator experiment)

- **Status:** Proposed. The reviewer decides.
- **Builds on:** [ADR 0002](0002-design-goals.md) goal 4 (scalable: thousands of tasks, one more task at a small, fixed cost) and goal 7 (the memory rule), and [ADR 0001](0001-rust-and-arm-assembly.md) (Rust; assembly only where Rust cannot work).
- **Scope:** QEMU's `virt` board with a Cortex-A15 CPU model, ARMv7-A. **Emulator only.** It does not start Phase 3 on the phone and claims nothing for the phone. **Emulator timing is not phone timing**, and no time below is a phone figure.

## Context

Goal 4 asks for many pieces of work at once, from dozens up to thousands. Nothing in the project showed what one piece of work costs. The roadmap's provisional sub-milestone 3g (tasks and scheduling) needs a task model before Phase 3 starts. This record measures two models in the emulator, stackful tasks and run-to-completion jobs, and sets them beside the third option.

## Options compared

| Option | What one unit of work holds | Memory per unit | What it allows | What it costs |
| --- | --- | --- | --- | --- |
| **Stackful tasks** (built here) | Its own stack and a table entry | Stack slot + 8 bytes | Any function can yield or block anywhere, at any call depth; code is written straight through | The stack must be sized for the deepest path. Without an MMU an overrun is caught after the fact (guard word); an MMU guard page catches it when it is touched, but works in 4 KiB pages, and a frame larger than the page can jump past it unless the compiler emits stack probes (this target emits none) |
| **Run-to-completion jobs** (built here) | A queue entry: a function and its state | A queue entry: **12 bytes** here (a function pointer and two words) | No stack per job and no context switch; every job runs on one runner's stack | A job cannot wait in the middle. Long work is split into steps, and its state lives outside the stack |
| **Stackless state machines** (Rust `async` without a heap; not built) | One state machine per task, sized by the compiler | The size of that state machine | Yield at any `.await` without a stack per task | Needs an executor and, with no heap, a static pool per task type. The state machine grows with what is held across each `.await` |

The first two were built and measured. The third is compared from how it works, not from measurements here.

## What was built

All of it is emulator test fixture code next to the Phase 1 kernel, in [tests/qemu/virt-armv7/](../../tests/qemu/virt-armv7/kernel.rs). There is no `kernel/` tree and nothing under `boot/` changed.

| File | What it is |
| --- | --- |
| [tasks.rs](../../tests/qemu/virt-armv7/tasks.rs) | `#![no_std]` Rust, no heap, no allocator. The task table, the stack arena, spawn, round-robin `yield_now`, task exit, the stack checks, the job queue and its runner, and the nine test cases (eleven images) |
| [switch.S](../../tests/qemu/virt-armv7/switch.S) | The only new assembly: `ctx_switch` (4 instructions), which cannot be Rust because Rust can neither name r4–r11 nor replace the stack pointer, and `task_trampoline` (3 instructions). The trampoline is assembly only because of the frame chosen here: `spawn` leaves the entry function and its argument in r4 and r5. A Rust entry shim that read them from the task's slot would need no assembly; that is an open choice |
| [tasks.ld](../../tests/qemu/virt-armv7/tasks.ld) | The Phase 1 link layout plus the task arena, and RAM up to what a flat 32-bit image can address |
| [tasks_oracle.py](../../tests/qemu/tasks_oracle.py) | Computes, independently, the order checksum that strict round robin must produce |
| [measure_tasks.sh](../../tests/qemu/measure_tasks.sh), [insn_profile.py](../../tests/qemu/insn_profile.py) | `make measure-tasks`: the measurements below |

**The design.**

- **Task table:** a fixed capacity, set when the image is built. Each entry is 8 bytes: the saved stack pointer and one link. That link is the ready ring while the task lives, or the free list once its slot is free.
- **Stacks:** one arena of equal slots, reserved by the linker, with one unused slot (the moat) below them, between the scheduler's own stack and the lowest task stack.
- **Switching:** cooperative and round robin, straight from one task to the next. `ctx_switch` pushes r4–r11 and lr, stores the stack pointer, loads the next one and pops. There is no VFP state, because the build is soft-float.
- **Limits are errors, not undefined behaviour:**
  - a full table refuses a spawn;
  - a spawn from inside a running task is refused, because the ring is built only by the scheduler;
  - every switch away from a task checks the guard word at the bottom of its slot, and checks that its stack pointer leaves room for the 36-byte switch frame above that word;
  - a failed check switches straight to the scheduler's stack, which reports the fault and exits without resuming any task;
  - a task whose function returns is ended and its slot goes back on the free list.
- **What the guard word cannot do:** it catches only an overrun that writes over it. A frame that skips the word is not caught. An overrun may already have written into the slot below before the next switch finds it; no task runs after that. The MMU guard pages of ROADMAP 3b stop an overrun when it touches them; catching every overrun also needs stack probes, or a bound on frame size.
- **The calling contract:** `spawn` and `run` are called only from the scheduler context, `yield_now` only from a running task. `spawn` enforces its part (it refuses a running task); `yield_now` and `run` rely on the caller, which the test cases respect. The code that builds on this experiment (3g) must check them as `spawn` does.

**The second experiment: run-to-completion jobs.**

- **The queue:** a ring buffer of fixed capacity in `.bss`. Each entry is 12 bytes: the step function and two words of state.
- **The runner:** one stackful task runs every job, one step at a time, in FIFO order:
  - it pops a job and runs its step to completion;
  - it yields (it is the only task, so the yield only checks its stack and returns);
  - if the step returns "again", it queues the job at the tail.
- **The order matches the tasks:** that FIFO order is the order in which round robin runs the tasks, so the same oracle checks both models. 1,000 jobs of 100 steps give the same order checksum as 1,000 tasks of 100 yields, `0x4d4c5bc0`.
- **Limits are errors here too:** a full queue refuses a job, and a step that overruns the runner's stack is reported right after that step, before the next job runs.

## Tests

All under `make check`, each run bounded by the QEMU time limit. They are listed in [TESTING.md](../TESTING.md#make-test-tasks).

| Test | Shows |
| --- | --- |
| `qemu-tasks-1000` | 1,000 tasks × 100 yields: exactly 100,000 iterations, the oracle's order checksum, every task ended, every slot free again |
| `qemu-tasks-10000` | 10,000 tasks × 10 yields, with 256-byte stacks, to the same standard |
| `qemu-tasks-table-full` | The 65th spawn into a 64-entry table is refused, and the 64 tasks then run to the expected total |
| `qemu-tasks-stack-overrun` | A task that writes 512 bytes of locals on a 512-byte stack is reported by the guard-word check at its next yield: task 1, after exactly 3 iterations (two of task 0, one of task 2), no task resumed; the run exits 1 |
| `qemu-tasks-stack-pointer` | A task that yields from inside a frame too deep to leave room for a switch, without writing past its slot, is reported by the stack-pointer check at that yield, to the same standard |
| `qemu-tasks-overrun-at-exit` | A task that overruns its slot and then returns without yielding is reported by the check at its exit, to the same standard |
| `qemu-tasks-return` | 64 tasks that return are ended and reclaimed; a second wave of 64 runs in the same slots; a spawn from inside a task is refused |
| `qemu-tasks-registers` | 64 tasks each hold eight values, a seed and a counter across 50 yields, more live values than there are free callee-saved registers, so the compiler keeps them in r4–r11; every value is unchanged after every switch |
| `qemu-jobs-1000` | 1,000 jobs × 100 steps on one runner: exactly 100,000 steps and the same order checksum as 1,000 tasks; the queue is empty and the runner has ended |
| `qemu-jobs-100000` | 100,000 jobs × 10 steps, to the same standard |
| `qemu-jobs-queue-full` | Job 65 into a 64-entry queue is refused, and the 64 jobs then run to the expected total |
| `qemu-jobs-stack-overrun` | A step that overruns the runner's 512-byte stack is reported right after that step: one step ran before it, and the next job is still queued |
| `build-tasks-symbols` | Every symbol that `kstart.o` and `switch.o` reference, weak ones included, is defined in the image, and none is undefined. (Its first version only counted `nm -u` lines, which this link always leaves empty: a strong undefined reference fails the link, and a weak one is resolved to 0 and dropped from the symbol table. An independent review found that; this version fails on a weak `task_exited` left undefined.) |
| `build-tasks-one-svc` | One system-call instruction, the semihosting exit: the switch makes none |

**Each check can fail.** Each mutation below was applied alone to a scratch copy of the tree, and every test was then run on its own. An unchanged copy was run as a control, and no test failed on it.

| Mutation | Tests that failed |
| --- | --- |
| `yield_now` skips the next task | `qemu-tasks-1000`, `-10000`, `-table-full`, `-return`, and the three overrun tests (their iteration count) |
| `ctx_switch` does not save r11 | every QEMU test of the task and job cases |
| `ctx_switch` saves r12 in place of r9 (the frame keeps its size) | `qemu-tasks-registers` only: no other test keeps a value in r9 across a switch |
| `spawn` puts the new task at the head of the ring, not the tail | `qemu-tasks-1000`, `-10000` (the order checksum) |
| The worker runs one iteration too few | `qemu-tasks-1000`, `-10000`, `-table-full` |
| No capacity check in `spawn` | `qemu-tasks-table-full` only |
| No guard-word check (at a yield, at an exit, after a job step) | `qemu-tasks-stack-overrun`, `qemu-tasks-overrun-at-exit`, `qemu-jobs-stack-overrun` |
| No stack-pointer check | `qemu-tasks-stack-pointer` only |
| No stack check at a task's exit | `qemu-tasks-overrun-at-exit` only |
| The guard word is never written | every QEMU test of the task and job cases |
| An ended task's slot is not reclaimed | `qemu-tasks-1000`, `-10000`, `-table-full`, `-return`, `qemu-jobs-1000`, `-100000`, `-queue-full` |
| An ended task is not unlinked from the ring | `qemu-tasks-return` only |
| A spawn from a running task is not refused | `qemu-tasks-return` only |
| A system call added to `ctx_switch` | every QEMU test of the task and job cases, and `build-tasks-one-svc` (2 found) |
| `task_exited` renamed, its reference in `switch.S` made weak (the link then succeeds with the call going to address 0) | `build-tasks-symbols` (`task_exited` missing), and the cases in which a task returns |
| Jobs: no queue-full check in `push` | `qemu-jobs-queue-full` only |
| Jobs: the runner skips its stack check after a step | `qemu-jobs-stack-overrun` only |
| Jobs: a job queued again skips a step | `qemu-jobs-1000`, `-100000`, `-queue-full` |
| Jobs: the ring's tail does not wrap | `qemu-jobs-1000`, `-100000`, `-queue-full` |

Two tests were tightened after a mutation first passed them. The job overrun test was first written to check only that an overrun was reported. The mutation "the runner skips its stack check" passed that test, because the overrun was still caught later, when the runner ended. The test now also requires that exactly one step ran before the fault and that the next job is still queued. With that, the mutation fails it. The same applies to the task overrun tests, which now require the kind of check, the task and the iteration count (an independent review pointed out that a detection one switch late would have passed), and to `build-tasks-symbols` (above).

The first version of the order checksum (rotate and xor) was found too weak while it was being measured. Its rotation repeats every 32 steps, so with 1,000,000 tasks (a multiple of 32) and 4 yields every task's contributions cancelled out. A task that never ran would have gone unseen. It was replaced by an FNV-1a style step (xor, then multiply by an odd constant), in the guest and in the oracle alike.

## Measurements

All are from this pull request's code, built by the Makefile's own rule. Each figure names its source: `make measure-tasks` (its printed tables, and its run logs under `build/measure/logs/`), `make test-tasks` (its logs under `build/logs/`), or `arm-none-eabi-objdump -d` for the disassembly breakdown. Times are host wall time for a whole QEMU run, not phone time.

**Bytes**

| Figure | Value | Source |
| --- | --- | --- |
| One task-table entry | 8 bytes | `size_of::<Tcb>()`, printed by every run |
| One task, as tested at 10,000 tasks and in the sweep | 8 + 256 = **264 bytes** | The "cost per task" line of `qemu-tasks-10000`'s log and of the sweep's run logs |
| One task, as tested at 1,000 tasks | 8 + 512 = 520 bytes | `qemu-tasks-1000`'s log |
| Deepest stack use of a worker task, by stack painting | 84 bytes when a task runs 10 or fewer yields (the compiler unrolls the worker's loop): `qemu-tasks-10000` and the sweep from 10,000 tasks up; 92 bytes in the 100-yield images (the loop is kept, and two more registers are saved), at 256- or 512-byte stacks; 76 bytes in the 64-task images; **60 bytes without the stack checks** | "deepest stack use" in each run's log; the last from a scratch copy with `check_stack` emptied |
| Scheduler code: `ctx_switch` 16, `task_trampoline` 12, `yield_now` 240, `task_exited` 320, `spawn` 356, `run` 152, `fault` 60, `sched_init` 88 | **1,244 bytes** in all | `arm-none-eabi-nm -S` of the capacity-1,000 image (`make measure-tasks`, part 3) |
| The whole capacity-1,000 image, loadable: `.text` 11,688 + `.rodata` 4,368 + `.ARM.exidx` 8 + `.data` 48 | 16,112 bytes | `arm-none-eabi-size -A` (part 3). Most of it is the test cases' reporting and Rust core's panic-message formatting, not the scheduler |
| The same image, reserved: the task table (8,000 bytes, plus 4 bytes of test counter in `.bss`), the scheduler's stack, the arena (1,001 slots of 256 bytes) | 8,004 + 65,536 + 256,256 bytes | The same |

**The largest task count that ran.** Case "many", 256-byte stacks, all tasks spawned before the run and every iteration checked:

| Tasks | Yields each | QEMU RAM | Result | Host seconds |
| --- | --- | --- | --- | --- |
| 1,000 | 100 | 64 MiB | PASS | 0.09 |
| 10,000 | 10 | 64 MiB | PASS | 0.10 |
| 100,000 | 10 | 256 MiB | PASS | 0.29 |
| 1,000,000 | 4 | 512 MiB | PASS | 1.46 |
| 4,000,000 | 2 | 2 GiB | PASS | 4.79 |
| 8,000,000 | 2 | 3 GiB | PASS | 9.71 |
| **12,000,000** | 2 | 3 GiB | PASS | 14.99 |

12,000,000 tasks is close to the limit. The image runs with the MMU off from `0x40000000`, so it can use at most the 3 GiB below 4 GiB. At 264 bytes per task that is about 12.2 million tasks, less the image and the scheduler's stack. **Memory is the limit, not the scheduler.**

**The cost of one switch.** One yield: the yielding task's `yield_now` (its stack checks, picking the next task) plus `ctx_switch`, ending in the next task's return from its own `yield_now`.

| Figure | Value | Source |
| --- | --- | --- |
| One yield | **48 instructions**: `yield_now` 44 + `ctx_switch` 4 | `make measure-tasks` part 2: QEMU's instruction trace (one instruction per translation block) of two capacity-1,000 runs with 2 and 4 yields per task. The difference is divided by the 2,000 extra yields |
| The same, from the code | `yield_now`: 42 instructions up to and including the call, 2 on return; `ctx_switch`: 4 | `arm-none-eabi-objdump -d` of the same image; agrees with the trace |
| Where `yield_now`'s 44 go | the check code itself 18 (the guard word 7; the stack pointer 11, which `black_box` forces through memory); bounds checks on the table 6; the frame 5; addresses, loads and the ring 15 | The same disassembly |
| What the stack checks cost | **22 instructions per yield and 24 bytes of stack per task.** With `check_stack` emptied, a yield is 26 instructions (`yield_now` 22 + `ctx_switch` 4) and the deepest stack use 60 bytes. The 4 instructions beyond the check code load the arena's address and keep a stack frame, which only the checks need | The same trace method on a scratch copy with `check_stack` emptied (found by an independent review, then measured again) |
| Code bytes | `ctx_switch` 16; `yield_now` 240, its cold fault and bounds-check paths included | `arm-none-eabi-nm -S` |
| The worker's own iteration, for comparison | 9 instructions (the test's two counters and the call; the compiler unrolls the 2- and 4-yield loops, and the first and last iterations cancel in the difference). In the 100-yield image, where the loop is kept, one iteration is 12 | The same trace |

These are instruction counts on the emulated CPU. Cycles on the phone's Krait cores, with its caches, are not known from them.

**Run-to-completion jobs** (`make measure-tasks`, part 4; one runner task with a 512-byte stack):

| Figure | Value | Source |
| --- | --- | --- |
| One queued job | **12 bytes** (a step function and two words of state) | "cost per queued job" in each job run's log |
| The runner, shared by every job | 8 + 512 = 520 bytes; its deepest stack use 64 bytes | The same line |
| Jobs that ran, 12 bytes each | 1,000 × 100 steps (0.09 s), 100,000 × 10 (0.25 s), 1,000,000 × 4 (0.60 s), **10,000,000** × 2 (2.91 s, 512 MiB of QEMU RAM) | Part 4's table; host seconds, not phone time |
| One job step | **104 instructions**: the runner's pop, push and loop 45, its stack check (`yield_now` with one task) 36, the step itself 23 (an indirect call and the same bookkeeping as the worker task's 9) | Part 4's trace difference over 2,000 extra steps |

The job sweep stops at 10,000,000 because the queue is a Rust static, and compiling a larger one needs more memory than the build host has, as the arena did before it moved to the linker script. At 12 bytes a job, the 3 GiB the image can address would hold over 200 million queued jobs, a division, not a run.

**The two models side by side** (capacity 1,000, the same work per step):

| | Memory per unit | Instructions per step |
| --- | --- | --- |
| Stackful task | 264 bytes (256-byte stack) | 57: the yield 48 (of it, the stack checks 22), the work 9 |
| Run-to-completion job | 12 bytes, plus one 520-byte runner for all | 104: the queue 45, the stack check 36, the step 23 |

Jobs cost 22 times less memory per unit. In this implementation they cost nearly twice the instructions per step: the queue operations and a stack check after every step cost more than the context switch they replace.

## Recommendation, for which kind of work

These are recommendations for the reviewer, from emulator measurements only.

1. **Stackful tasks are cheap enough for the first proof point.** At 264 bytes a task, 1,000 tasks take 264,000 bytes: about 0.02 % of the 1,363,632 kB the phone's stock kernel reports usable ([Phase 0 hardware evidence](../evidence/phase-0/2026-11-13-hardware-summary.md#actual-device-observations)). Use them for long-lived activities that wait in the middle of their work: a service loop, a protocol handler, a driver's state.
2. **Size each kind of task's stack from its measured depth**, by painting as here, plus a stated margin; do not use one large stack for all. The worker here needs 84 to 92 bytes, depending on how the compiler shapes its loop; that spread is itself a reason for the margin. Real tasks need their own measurement.
3. **Use run-to-completion jobs where memory decides**: very many pending pieces of short work (an event, a packet, one step of a longer job). A queued job costs 12 bytes against a task's 264, so a million pending jobs take 12,000,000 bytes where a million tasks take 264,000,000. Where instructions decide, a few stackful tasks are cheaper per step here (57 against 104). The job path has obvious savings to measure next: one stack check per batch of steps instead of per step, and a cheaper queue.
4. **Measure stackless state machines before choosing them** for heavy concurrency: they avoid a stack per task, but their size depends on the code, and without a heap they need a static pool per task type.
5. **Keep the stack checks, and add MMU guard pages where they fit.** The two checks cost 22 of the 48 instructions of a yield and 24 bytes of each task's stack, and catch an overrun after the fact. A guard page stops an overrun that touches it (catching every overrun also needs stack probes), but on ARMv7 each guarded stack becomes at least one 4 KiB page: 1,000 tasks would need 4,096,000 bytes of stack instead of 256,000. A mixed scheme (pages for the few deep stacks, words for the many small ones) is an open question for 3b and 3g.

## Open questions

- **Preemption.** A timer interrupt that switches tasks must save every register, not only r4–r11, and needs an interrupt stack. That is not built, and on QEMU it would use board-specific timer and interrupt-controller code.
- **Two cores.** Run queues per core, locking with `LDREX`/`STREX`, and moving tasks between cores.
- **The phone.** Cycles per switch on Krait, and the cache cost of thousands of small stacks, can only be measured there.
- **Bounding a stack before running.** Here a stack's depth is measured by painting; a static bound (call-graph analysis) would let the build refuse a task whose stack is too small.
- **Spawning from a task, blocking and waking, priorities.** None is built; spawn from a running task is refused.
- **Stackless state machines** are not measured yet (above).
- **A cheaper job path:** the stack check per batch instead of per step, and queue operations without bounds checks, each measured against the 104 instructions here.
- **The calling contract** of `yield_now` and `run` (above) is documented, not checked.
- **Coverage left:** `yield_now`'s own prologue saves r4, r10 and r11 in this build, so a switch that stopped saving those three is not observable through any test here (`ctx_switch` saving r12 in place of r10 passes them all); the registers case covers r5 to r9. The AAPCS still requires `ctx_switch` to save all of r4–r11, because another caller could rely on them. The task-case parameters live in the Makefile and are not a prerequisite of the images, so an edited parameter needs a clean build (`make measure-tasks` deletes each image before building it).

## Consequences

- If the reviewer accepts this direction, Phase 3's sub-milestone 3g starts from these numbers, and ADR 0002's goal 4 has its first emulator figures.
- Nothing here changes the phone, the frozen payload or the hardware-safety contract.

## Scope of this pull request

Emulator fixture code, a measurement script and documentation. No device was contacted, nothing under `boot/` changed, no hosted CI ran, and no firmware was downloaded.
