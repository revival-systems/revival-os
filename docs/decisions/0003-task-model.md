# ADR 0003 — The task model: what one task costs (emulator experiment)

- **Status:** Accepted by the reviewer, 2026-11-14, as the record of the experiment and the starting direction for ROADMAP 3g (provisional, rule 5). Emulator figures only.
- **Builds on:** [ADR 0002](0002-design-goals.md) goal 4 (scalable: thousands of tasks, one more task at a small, fixed cost) and goal 7 (the memory rule), and [ADR 0001](0001-rust-and-arm-assembly.md) (Rust; assembly only where Rust cannot work).
- **Scope:** QEMU's `virt` board with a Cortex-A15 CPU model, ARMv7-A. **Emulator only.** It does not start Phase 3 on the phone and claims nothing for the phone. **Emulator timing is not phone timing**, and no time below is a phone figure.
- **Rounds:** round 1 (pull request #18) built and measured stackful tasks and run-to-completion jobs. Round 2 (2026-11-14) fixed the two findings of round 1's review, F1 and F2, and built and measured the third model, stackless tasks. Every figure below is round 2's unless it is marked as round 1's.

## Context

Goal 4 asks for many pieces of work at once, from dozens up to thousands. Nothing in the project showed what one piece of work costs. The roadmap's provisional sub-milestone 3g (tasks and scheduling) needs a task model before Phase 3 starts. This record measures three models in the emulator: stackful tasks, run-to-completion jobs and stackless tasks.

## Options compared

| Option | What one unit of work holds | Memory per unit, measured | What it allows | What it costs |
| --- | --- | --- | --- | --- |
| **Stackful tasks** | Its own stack and a table entry | A stack slot + 8 bytes: **264 bytes** with 256-byte stacks | Any function can yield or block anywhere, at any call depth; code is written straight through | The stack must be sized for the deepest path. Without an MMU an overrun is caught after the fact (guard word); an MMU guard page catches it when it is touched, but works in 4 KiB pages, and a frame larger than the page can jump past it unless the compiler emits stack probes (this target emits none) |
| **Run-to-completion jobs** | A queue entry: a function and its state | **12 bytes** (a function pointer and two words), plus one runner for all | No stack per job and no context switch; every job runs on one runner's stack | A job cannot wait in the middle. Long work is split into steps by hand, and its state lives outside the stack |
| **Stackless tasks** (Rust `async`, no heap) | A state machine that the compiler builds, in a pool slot | **16 bytes** for the worker here (a 4-byte header and a 12-byte state machine), 48 for a task that holds eight values across its await; plus one executor for all | A task waits at any `.await` and keeps its place and its values, without a stack of its own; code is written straight through, as long as every wait is an await | The state machine's size is the compiler's and grows with what is held across each await. Without a heap, the pool has slots of one size. Every poll runs on the executor's stack. Here no task waits without being polled (no wake-up) |

## What was built

All of it is emulator test fixture code next to the Phase 1 kernel, in [tests/qemu/virt-armv7/](../../tests/qemu/virt-armv7/kernel.rs). There is no `kernel/` tree and nothing under `boot/` changed.

| File | What it is |
| --- | --- |
| [tasks.rs](../../tests/qemu/virt-armv7/tasks.rs) | `#![no_std]` Rust, `core` only: no heap, no allocator, no crate. The task table, the stack arena, spawn, the Rust half of a yield, task exit, the job queue and its runner, the stackless pool and its executor, and the test cases |
| [switch.S](../../tests/qemu/virt-armv7/switch.S) | The only new assembly, and its header says why each part cannot be Rust: `ctx_switch` (4 instructions: Rust can neither name r4–r11 nor replace the stack pointer); since round 2, the stack checks (`task_yield`, the end of `task_trampoline`, `stack_fault`), because they must read sp itself and write nothing to a failed stack (F1, F2); and `task_trampoline`, which starts a task from the frame `spawn` built (the entry function and its argument in r4 and r5) |
| [tasks.ld](../../tests/qemu/virt-armv7/tasks.ld) | The Phase 1 link layout plus the task arena and, since round 2, the stackless pool, and RAM up to what a flat 32-bit image can address |
| [tasks_oracle.py](../../tests/qemu/tasks_oracle.py) | Computes, independently, the order checksum that strict round robin must produce |
| [measure_tasks.sh](../../tests/qemu/measure_tasks.sh), [insn_profile.py](../../tests/qemu/insn_profile.py) | `make measure-tasks`: the measurements below |

**The design of the stackful tasks.**

- **Task table:** a fixed capacity, set when the image is built. Each entry is 8 bytes: the saved stack pointer and one link. That link is the ready ring while the task lives, or the free list once its slot is free.
- **Stacks:** one arena of equal slots, reserved by the linker, with one unused slot (the moat) below them, between the scheduler's own stack and the lowest task stack.
- **Switching:** cooperative and round robin, straight from one task to the next. `ctx_switch` pushes r4–r11 and lr, stores the stack pointer, loads the next one and pops. There is no VFP state, because the build is soft-float.
- **Limits are errors, not undefined behaviour:**
  - a full table refuses a spawn;
  - a spawn from inside a running task is refused, because the ring is built only by the scheduler;
  - every time control leaves a task, at a yield and at its exit, `switch.S` checks its stack before anything is written to it: the guard word at the bottom of its slot must be intact, and the stack pointer itself must leave 64 bytes above that word (what the switch path pushes next: at most 16 bytes in `yield_next` or `task_exited`, then the 36-byte frame of `ctx_switch`; the rest is slack);
  - a failed check records the fault and returns to the scheduler's stack without writing to the failed one, and the scheduler reports it and exits without resuming any task;
  - a task whose function returns is ended and its slot goes back on the free list.
- **What the guard word cannot do:** it catches only an overrun that writes over it. A frame that skips the word is not caught. An overrun may already have written into the slot below before the next switch finds it; no task runs after that. The MMU guard pages of ROADMAP 3b stop an overrun when it touches them; catching every overrun also needs stack probes, or a bound on frame size.
- **What the moat protects:** the scheduler's stack, and only from an overrun of the lowest task that is shorter than one slot (256 or 512 bytes here). A longer overrun runs through the moat into the scheduler's stack before any check sees it. An overrun of any other task lands in the task slot below. The moat is a margin, not a protection; the protection is the guard pages of 3b.
- **The calling contract:** `spawn`, `async_spawn` and `run` are called only from the scheduler context, `yield_now` only from a running task. The two spawns enforce their part (they refuse a running task); `yield_now` and `run` rely on the caller, which the test cases respect. The code that builds on this experiment (3g) must check them as the spawns do.

**Round 2, F1: the fault path wrote on the stack that had just failed.** In round 1 the checks and the fault path were Rust. A failed check called `fault()`, which recorded the fault and called `ctx_switch` to reach the scheduler's stack. Both pushed onto the task's stack: 16 bytes for `fault()` and 36 for the switch frame, on the very stack whose check had just failed.

- **Reproduced first,** on round 1's code with the new test case added. The case puts the culprit in the lowest slot (task 0), paints the moat, and yields from a frame too deep for a switch. The check found the fault ("stack pointer 0x40014278 leaves no room for a switch above the guard word at 0x40014258"). Afterwards the culprit's guard word read 0x00000000, and 5 words of the moat had changed, the highest at 0x40014254, just below the guard word: the 52 bytes written downward from that stack pointer.
- **The fix, and why this way:** the checks moved into `switch.S`, and a failed check now records the kind, the value and the address in `TASK_CHECK` (a static shared with Rust, whose field offsets `tasks.rs` asserts at compile time) and loads the scheduler's saved stack pointer, with no push and no call. `run()` then finds the record. Only assembly can promise that nothing is written. Every Rust function may push in its prologue, and a Rust fault path that first moved to another stack would still need assembly to move it.
- **After the fix,** the new test `qemu-tasks-fault-leaves-stack` finds the culprit's guard word intact and every word of the moat unchanged. Restoring round 1's path makes it fail: see the mutation table ("the old fault path").

**Round 2, F2: the stack-pointer check did not read sp.** Round 1 used the address of a local variable as a stand-in, and the compiler places a local where it likes. The check now reads sp itself.

- **Where the checks live:** in one assembly macro, `check_stack`, used at the two places where control leaves a task. These are `task_yield` (every yield, before the Rust half `yield_next` runs) and the end of `task_trampoline` (a task's exit, before `task_exited` runs).
- **Why there:** only there is the stack exactly as the task left it, and one copy of the check then serves both exits. The job runner and the stackless executor reach it through their yields.
- **The yield, measured again:** 48 instructions before (round 1: `yield_now` 44, `ctx_switch` 4) and **48 after**: `task_yield` 12, `yield_next` 32, `ctx_switch` 4 (`make measure-tasks`, part 2).
- **What the checks cost now:** `task_yield`'s 12 instructions are the two checks. Of `yield_next`'s 32, 7 store the next task's slot base in `TASK_CHECK` for the next check; round 1's Rust check computed the base from the task's index instead. That makes 19 instructions for the checks, against round 1's 22 (by the disassembly of the measured image; round 1 measured its 22 with the checks removed).
- **What F2 saved:** the task's stack. The checks no longer need a Rust frame on it, so a worker's deepest stack use fell from 84 bytes to 60 (round 1 measured 60 with no checks at all), and from 92 to 68 bytes in the image whose loop is not unrolled.

**The second experiment: run-to-completion jobs.**

- **The queue:** a ring buffer of fixed capacity in `.bss`. Each entry is 12 bytes: the step function and two words of state.
- **The runner:** one stackful task runs every job, one step at a time, in FIFO order:
  - it pops a job and runs its step to completion;
  - it yields: it is the only task, so the yield only runs the stack checks and returns;
  - if the step returns "again", it queues the job at the tail.
- **The order matches the tasks:** that FIFO order is the order in which round robin runs the tasks, so the same oracle checks both models. 1,000 jobs of 100 steps give the same order checksum as 1,000 tasks of 100 yields, `0x4d4c5bc0`.
- **Limits are errors here too:** a full queue refuses a job, and a step that overruns the runner's stack is reported right after that step, before the next job runs.
- **One condition:** a job that is not done is queued again into the entry its own pop freed. That cannot be refused as long as no step queues a job itself, which holds here. A step that fans out would take the freed entry, and the runner would then end the run; a design that keeps fan-out would run the step in place at the head and advance it afterwards.

**The third experiment: stackless tasks** (round 2; Rust `async` with `core` only, stable features of the pinned toolchain, no heap, no allocator, no new crate).

- **The task:** the worker's work written as a function that returns an `async` block: the same bookkeeping per iteration as a worker task, then one await. The await is on `YieldOnce`, which returns Pending on its first poll and Ready on its second, so one await is one step back to the executor. The tasks are not `async fn`s, because this compiler keeps an `async fn`'s argument twice, once as passed and once as the body's local: the same worker is 16 bytes as an `async fn` against 12 as a block (part 5's holder run prints both).
- **The pool:** stable Rust cannot name an async block's type, so a typed static array of tasks cannot be declared; that needs `impl Trait` in a type alias, which is not stable. **The pool is therefore memory that the linker reserves, the way it reserves the task arena** (`tasks.ld`, `.async_pool`), in slots of one size. Each slot is a 4-byte header, the slot's poll function or none when the slot is free, followed by the task's state machine. A free slot keeps the next free slot's index in its first word.
- **Spawning:** `async_spawn` checks at compile time that the state machine fits a slot and needs no more than 4-byte alignment. It refuses a full pool and a spawn from a running task, and writes the state machine into the slot. There it stays, so it is pinned by construction: the pool is static memory, and nothing copies a slot. Each case also checks at compile time that the slot size it is built with is exactly the header plus its largest state machine, so a slot is what one task costs.
- **The executor:** one stackful task. It polls every live slot in slot order, round robin, until every task is done, and frees the slot of a task that is done. After each poll it yields. It is the only task, so the yield switches nowhere and runs only the stack checks, and a poll that overran the executor's stack is reported before the next poll, as a job step is. The waker does nothing (`Waker::noop`), because every live task is polled each round anyway.
- **The order matches:** slot order is spawn order, so 1,000 tasks of 100 awaits give the same checksum as 1,000 stackful tasks and 1,000 jobs, `0x4d4c5bc0`.
- **Its limits:**
  - **No wait without polling.** A task that is not ready is polled again in the next round. An executor that waits for events needs wake-ups that queue a task when its event comes, a ready queue, and, with interrupts, both made safe against them.
  - **Slots of one size per pool,** the largest state machine's. A pool of mixed task types pays for the largest in every slot, or needs one pool per size.
  - **At most 4-byte alignment.** A task that holds a `u64` across an await is refused at compile time.
  - **Spawning only from the scheduler context,** before `run()`, as with the stackful tasks.
  - **Every poll runs on the executor's stack.** That stack must hold the deepest poll of any task, and a poll that does not return stops every task.
  - **The state machine's size is the compiler's.** The only check is that it fits its slot, at compile time.

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
| `qemu-tasks-fault-leaves-stack` (round 2) | The culprit in the lowest slot yields from a frame too deep for a switch: the stack-pointer check reports it (task 0, after 2 iterations), and afterwards the culprit's guard word is intact and every word of the painted moat unchanged |
| `qemu-tasks-return` | 64 tasks that return are ended and reclaimed; a second wave of 64 runs in the same slots; a spawn from inside a task is refused |
| `qemu-tasks-registers` | 64 tasks each hold eight values, a seed and a counter across 50 yields, more live values than there are free callee-saved registers, so the compiler keeps them in r4–r11; every value is unchanged after every switch |
| `qemu-jobs-1000` | 1,000 jobs × 100 steps on one runner: exactly 100,000 steps and the same order checksum as 1,000 tasks; the queue is empty and the runner has ended |
| `qemu-jobs-100000` | 100,000 jobs × 10 steps, to the same standard |
| `qemu-jobs-queue-full` | Job 65 into a 64-entry queue is refused, and the 64 jobs then run to the expected total and order checksum |
| `qemu-jobs-stack-overrun` | A step that overruns the runner's 512-byte stack is reported right after that step: one step ran before it, and the next job is still queued |
| `qemu-async-1000` (round 2) | 1,000 stackless tasks × 100 awaits on one executor: exactly 100,000 steps and the same order checksum as 1,000 tasks, `0x4d4c5bc0`; no task left, every pool slot free again, the executor ended |
| `qemu-async-100000` (round 2) | 100,000 stackless tasks × 10 awaits, to the same standard |
| `qemu-async-pool-full` (round 2) | Task 65 into a 64-slot pool is refused ("pool full"); a spawn tried from a running task while the pool is full is refused as such; the 64 tasks then run to the expected total and order checksum, so a refusal that overwrote a slot fails it |
| `qemu-async-stack-overrun` (round 2) | A task whose first poll overruns the executor's 512-byte stack is reported right after that poll: one step ran (task 0's), task 2 was never polled, no task is done |
| `build-tasks-symbols` | Every symbol that `kstart.o` and `switch.o` reference, weak ones included, is defined in the image, and none is undefined |
| `build-tasks-one-svc` | One system-call instruction, the semihosting exit: the switch makes none |

**Each check can fail.** Each mutation below was applied alone to a scratch copy of a clean export of commit `0cd7991` (tree `fcf38a6`), this pull request's code, and every test was then run on its own. The whole table comes from one run on that tree. An unchanged copy was run in the same run as a control, and no test failed on it.

| Mutation | Tests that failed |
| --- | --- |
| `yield_next` skips the next task | `qemu-tasks-1000`, `-10000`, `-table-full`, `-return`, `-registers`, and the three overrun tests (their iteration count) |
| `ctx_switch` does not save r11 | every QEMU test of the three models |
| `ctx_switch` saves r12 in place of one of r4–r11 (eight mutations, each alone; the frame keeps its size) | each of the eight fails `qemu-tasks-registers`; r8, r9 and r10 fail only that test. r4, which holds a new task's entry function, fails every QEMU test, and r5, its argument, fails 10; r6, r7 and r11 fail 6, 2 and 3 tests |
| `spawn` puts the new task at the head of the ring, not the tail | `qemu-tasks-1000`, `-10000` (the order checksum), `-fault-leaves-stack` (4 iterations before the fault, not 2) |
| The worker task runs one iteration too few | `qemu-tasks-1000`, `-10000`, `-table-full` |
| No capacity check in `spawn` | `qemu-tasks-table-full` only |
| No guard-word check (one macro in `switch.S`: at every yield and every exit, so after a job step or a poll too) | `qemu-tasks-stack-overrun`, `-overrun-at-exit`, `qemu-jobs-stack-overrun`, `qemu-async-stack-overrun` |
| No stack-pointer check (`switch.S`) | `qemu-tasks-stack-pointer`, `-fault-leaves-stack` |
| No stack check at a task's exit (`task_trampoline`) | `qemu-tasks-overrun-at-exit` only |
| **The old fault path:** round 1's checks in Rust and its Rust fault path, restored | `qemu-tasks-fault-leaves-stack` only: the fault is found, but afterwards the culprit's guard word reads `0x40014278` (a stack address the fault path pushed) and 7 words of the moat have changed |
| The guard word is never written | every QEMU test but `qemu-async-stack-overrun`, whose first check then fails at the very point its overrun would be found |
| An ended task's slot is not reclaimed | `qemu-tasks-1000`, `-10000`, `-table-full`, `-return`, `-registers`, `qemu-jobs-1000`, `-100000`, `-queue-full`, `qemu-async-1000`, `-100000`, `-pool-full` |
| An ended task is not unlinked from the ring | `qemu-tasks-return`, `qemu-async-pool-full` (its prober task ends while the executor runs) |
| A spawn from a running task is not refused | `qemu-tasks-return` only |
| A system call added to `ctx_switch` | every QEMU test of the three models, and `build-tasks-one-svc` (2 found) |
| `task_exited` renamed, its reference in `switch.S` made weak (the link then succeeds, and a task that returns runs off the end of `task_trampoline`) | `build-tasks-symbols` (`task_exited` missing), and the cases in which a task returns |
| Jobs: no queue-full check in `push` | `qemu-jobs-queue-full` only |
| Jobs: a refused `push` overwrites the oldest queued job (and still reports "full") | `qemu-jobs-queue-full` only (the order checksum) |
| Jobs: the runner skips its stack check after a step | `qemu-jobs-stack-overrun` only |
| Jobs: a job queued again skips a step | `qemu-jobs-1000`, `-100000`, `-queue-full` |
| Jobs: the ring's tail does not wrap | `qemu-jobs-1000`, `-100000`, `-queue-full` |
| Async: an await never returns Pending (each task runs to its end in one poll) | `qemu-async-1000`, `-100000`, `-pool-full` (the order checksum), `-stack-overrun` |
| Async: the worker runs one await too few | `qemu-async-1000`, `-100000`, `-pool-full`, `-stack-overrun` |
| Async: no capacity check in `async_spawn` | `qemu-async-pool-full` only |
| Async: a refused spawn overwrites the task in slot 0 (and still reports "full") | `qemu-async-pool-full` only (the order checksum) |
| Async: a spawn from a running task is not refused | `qemu-async-pool-full` only |
| Async: a done task's slot is not put back on the free list | `qemu-async-1000`, `-100000`, `-pool-full` |
| Async: the executor skips its stack check after a poll | `qemu-async-stack-overrun` only |

Round 1 found that a switch which stopped saving r4, r10 or r11 passed every test, because `yield_now`'s own prologue saved them. With the yield's Rust half now entered after the checks, each of r4–r11 is observable (the third row). The AAPCS requires `ctx_switch` to save all of them in any case.

Tests that were tightened after a mutation first passed them (round 1): the job overrun test (one step before the fault, the next job still queued), the task overrun tests (the kind of check, the task and the iteration count), `build-tasks-symbols` (weak references) and `qemu-jobs-queue-full` (the order checksum). Round 1 also replaced a first order checksum (rotate and xor) that was too weak: its rotation repeats every 32 steps, so every task's contributions cancelled for 1,000,000 tasks of 4 yields. The FNV-1a style step (xor, then multiply by an odd constant) replaced it, in the guest and in the oracle alike.

## Measurements

**Source.** Every figure in this section comes from one run of `make measure-tasks` on a clean export of commit `0cd7991` (tree `fcf38a6`), this pull request's code; the commits after it change only documentation. Figures marked as round 1's come from round 1's record. The parts named are those of the script's output. Times are host wall time for a whole QEMU run, not phone time. The breakdowns by instruction come from `arm-none-eabi-objdump -d` of the images that the same run traced.

**Stackful tasks: bytes** (parts 1 and 3):

| Figure | Value | Source |
| --- | --- | --- |
| One task-table entry | 8 bytes | `size_of::<Tcb>()`, printed by every run |
| One task, at 256-byte stacks | 8 + 256 = **264 bytes** | Part 1, the "cost per task" line of each run's log |
| Deepest stack use of a worker task, by stack painting | **60 bytes** when a task runs 10 or fewer yields (the compiler unrolls the worker's loop), 68 bytes in the 100-yield image. Round 1: 84 and 92 bytes; the 24 bytes saved were the Rust checks' frame | Part 1, the "deepest" column |
| Deepest stack use of the stackful holder (case registers: eight values, a seed and a counter held across 50 yields) | 124 bytes (round 1: 148) | Part 3 |
| Scheduler code: `ctx_switch` 16, `task_trampoline` 56, `task_yield` 48, `stack_fault` 40, `yield_next` 164, `task_exited` 296, `spawn` 352, `run` 312, `sched_init` 88 | **1,372 bytes** in all (round 1: 1,244) | Part 3, `nm -S` of the capacity-1,000 image |
| The whole capacity-1,000 image, loadable: `.text` 11,860 + `.rodata` 4,348 + `.ARM.exidx` 8 + `.data` 52 | 16,268 bytes. Most of it is the test cases' reporting and Rust core's panic-message formatting, not the scheduler | Part 3, `size -A` |
| The same image, reserved: `.bss` 8,024 (8,000 of it the task table), the scheduler's stack 65,536, the arena 256,256 (1,001 slots of 256 bytes) | 329,816 bytes | Part 3 |

**Stackful tasks: the largest count that ran.** Case "many", 256-byte stacks, all tasks spawned before the run and every iteration checked.

| Tasks | Yields each | QEMU RAM | Result | Host seconds |
| --- | --- | --- | --- | --- |
| 1,000 | 100 | 64 MiB | PASS | 0.08 |
| 10,000 | 10 | 64 MiB | PASS | 0.10 |
| 100,000 | 10 | 256 MiB | PASS | 0.29 |
| 1,000,000 | 4 | 512 MiB | PASS | 1.49 |
| 4,000,000 | 2 | 2 GiB | PASS | 4.65 |
| 8,000,000 | 2 | 3 GiB | PASS | 10.17 |
| **12,000,000** | 2 | 3 GiB | PASS | 15.56 |

12,000,000 tasks is close to the limit. The image runs with the MMU off from `0x40000000`, so it can use at most the 3 GiB below 4 GiB. At 264 bytes per task that is about 12.2 million tasks, less the image and the scheduler's stack. **Memory is the limit, not the scheduler.**

**Stackful tasks: the cost of one switch.** One yield: the yielding task's `task_yield` (the checks) and `yield_next` (picking the next task) plus `ctx_switch`, ending in the next task's return from its own yield.

| Figure | Value | Source |
| --- | --- | --- |
| One yield | **48 instructions**: `task_yield` 12, `yield_next` 32, `ctx_switch` 4 (round 1: 48, `yield_now` 44 and `ctx_switch` 4) | Part 2: QEMU's instruction trace (one instruction per translation block) of two capacity-1,000 runs with 2 and 4 yields per task; the difference is divided by the 2,000 extra yields |
| Where `yield_next`'s 32 go | storing the next task's slot base for the check 7; the table's bounds checks 6; the frame 3; the ring, its loads and stores, and the switch's arguments 16 | The disassembly of the traced image |
| The worker's own iteration | 9 instructions: the test's two counters and the call. The compiler unrolls the 2- and 4-yield loops and keeps the counters' addresses and constants in r4–r7 across every yield | Part 2 |
| One step of work, all in | **57 instructions**: the yield 48 and the work 9 | Part 2, "per step in total" |

These are instruction counts on the emulated CPU. Cycles on the phone's Krait cores, with its caches, are not known from them.

**Run-to-completion jobs** (part 4; one runner task with a 512-byte stack):

| Figure | Value | Source |
| --- | --- | --- |
| One queued job | **12 bytes** (a step function and two words of state) | "cost per queued job" in each job run's log |
| The runner, shared by every job | 8 + 512 = 520 bytes; its deepest stack use 52 bytes (round 1: 64) | The same line; part 4's "deepest" column |
| Jobs that ran, 12 bytes each | 1,000 × 100 steps (0.10 s), 100,000 × 10 (0.34 s), 1,000,000 × 4 (0.74 s), **10,000,000** × 2 (3.73 s, 512 MiB of QEMU RAM) | Part 4's table |
| One job step | **93 instructions** (round 1: 104): the runner 45 (its loop, the queue's pop and push, and the indirect call to the step); the step 23 (its frame, constants and the same bookkeeping as the worker task's 9); the yield after the step 25 (`task_yield` 12, the checks, and `yield_next` 13, which finds no other task and returns) | Part 4's trace difference over 2,000 extra steps |

The job sweep stops at 10,000,000 by choice, not at a limit. The queue is a Rust static, so the build needs host memory in proportion (round 1: about 0.8 GB for 10,000,000 jobs; it also ran 20,000,000 once by hand). At 12 bytes a job, the 3 GiB the image can address would hold over 200 million queued jobs; that is a division, not a run. A queue reserved by the linker, as the stackless pool is, would remove the build's cost; that is not built.

**Stackless tasks** (part 5; one executor task with a 512-byte stack):

| Figure | Value | Source |
| --- | --- | --- |
| One task | **16 bytes**: a 4-byte header (the slot's poll function) and a 12-byte state machine (the task's id, its counter, the `YieldOnce` flag and the state) | "cost per async task" in each run's log |
| The executor, shared by every task | 8 + 512 = 520 bytes; its deepest stack use **56 bytes** (100 awaits) and 64 bytes (10 or fewer) | The same line; part 5's "deepest" column |
| The state machine's growth (the holder shape: eight values, a seed and a counter held across each await) | the worker 12 bytes, the holder **44 bytes** (a 48-byte slot); the worker written as an `async fn` 16 bytes. The executor's deepest stack use with the holders: 76 bytes | Part 5, the holder run (64 tasks × 50 awaits, every value unchanged) |
| Tasks that ran, 16 bytes each | 1,000 × 100 awaits (0.09 s), 100,000 × 10 (0.24 s), 1,000,000 × 4 (0.85 s, 256 MiB), 10,000,000 × 2 (4.99 s, 512 MiB), 100,000,000 × 2 (45.43 s, 2 GiB), **200,000,000** × 2 (94.46 s, 3 GiB) | Part 5's table |
| One step | **75 instructions**: the poll 36, the executor 14, the yield after the poll 25 (`task_yield` 12 and `yield_next` 13, as a job step's) | Part 5's trace difference over 2,000 extra awaits |
| Where the poll's 36 go | resuming the state machine 11 (load the state, branch, test the `YieldOnce` flag, load and test the counter); the step's work 19, the same bookkeeping as the worker task's 9, with every address and constant loaded again, because nothing stays in a register between two polls; suspending 6 (store the flag and the state, return Pending) | The disassembly of the traced image |
| Where the executor's 14 go | load the slot's header and test it, compute the state machine's address, the indirect call, test the result, the call to the yield, the next slot | The same |
| Code | `executor` 192, `poll_slot` (one per task type) 176, `async_spawn` (one per task type) 168, `pool_init` 96 bytes | Part 5, `nm -S` |

200,000,000 tasks is close to the limit: at 16 bytes a task, the 3 GiB hold about 201 million, less the image. **Memory is the limit here too.** The pool is reserved by the linker, so the build does not grow with it.

**The three models side by side** (capacity 1,000, the same work per step):

| | Memory per unit | Shared by all units | Instructions per step | The largest count that ran |
| --- | --- | --- | --- | --- |
| Stackful task | 264 bytes (256-byte stack) | — | 57: the yield 48 (`task_yield` 12, `yield_next` 32, `ctx_switch` 4), the work 9 | 12,000,000 (the 3 GiB) |
| Run-to-completion job | 12 bytes | one 520-byte runner | 93: the runner 45, the step 23, the stack check 25 | 10,000,000 (the sweep stops there) |
| Stackless task | 16 bytes (a 12-byte state machine) | one 520-byte executor | 75: the poll 36, the executor 14, the stack check 25 | 200,000,000 (the 3 GiB) |

- **Memory:** a stackless task costs 16.5 times less memory than a stackful one (16 bytes against 264) and 4 bytes more than a job.
- **Holding values across a wait:** a stackful task holding ten values needed 124 bytes of its 256-byte stack. A stackless task holding the same ten values is a 44-byte state machine, and its slot grows with it (48 bytes).
- **Instructions per step:** the stackless step costs 18 more instructions than the stackful one (75 against 57). It saves on the switch itself: the executor's 14 against the 29 that picking the next task and `ctx_switch` take. It pays more for three things:
  - every poll resumes and suspends a state machine in memory (17);
  - the work reloads what a stackful task keeps in registers (19 against 9);
  - the stack check after each poll costs 25 against the 19 that the stackful yield spends on it.
- **Against jobs:** the stackless step costs 18 fewer instructions than a job step (75 against 93). The executor's scan and indirect call cost 14 against the 45 of the queue's pop and push and the runner's indirect call, and the poll costs 13 more than the job's step (36 against 23).
- **What the jobs and stackless numbers rest on:** both models check the stack after every step. In both, every pending unit is ready, so the executor's scan never visits an idle task. A real mix of waiting tasks would cost the scan a poll per idle task per round (see the limits).

## Recommendation, for which kind of work

These are recommendations for the reviewer, from emulator measurements only. Round 2 changed them only where its numbers moved; each change is named.

1. **Stackful tasks are cheap enough for the first proof point.** At 264 bytes a task, 1,000 tasks take 264,000 bytes: about 0.02 % of the 1,363,632 kB the phone's stock kernel reports usable ([Phase 0 hardware evidence](../evidence/phase-0/2026-11-13-hardware-summary.md#actual-device-observations)). Use them for long-lived activities that wait in the middle of their work, at any call depth: a service loop, a protocol handler, a driver's state. They are also the cheapest per step measured here (57 instructions).
2. **Size each kind of task's stack from its measured depth**, by painting as here, plus a stated margin; do not use one large stack for all. The worker here needs 60 to 68 bytes, depending on how the compiler shapes its loop, and a task that holds ten values needs 124; that spread is itself a reason for the margin. Real tasks need their own measurement, and the panic path's depth must be measured before any size is set (open questions). *Round 2: the figures changed (the checks no longer use the task's stack), and the panic path was added.*
3. **Where memory decides, use stackless tasks or jobs**: 16 or 12 bytes a unit, against a task's 264. A million pending units take 16,000,000 or 12,000,000 bytes where a million tasks take 264,000,000. *Round 2 changed this recommendation, because stackless tasks are now measured:*
   - choose stackless tasks where the work waits in the middle: an await keeps the task's place and its values, where a job must be split into steps by hand. Here they also cost fewer instructions per step than jobs (75 against 93);
   - choose jobs where the work never waits: the smallest unit (12 bytes), whose size the code sets and the compiler does not.
4. **Measure what this stackless experiment leaves out before 3g relies on it.** The numbers favour stackless tasks for very many small activities: 16 bytes a task, and 200,000,000 ran where 12,000,000 stackful tasks did. But four things are not built here:
   - wake-ups and a ready queue (here every live task is polled every round, so an idle task still costs a poll per round);
   - pools of several slot sizes;
   - interrupts;
   - a bound on the deepest poll, which every task's poll shares on the executor's stack.

   *Round 2 replaced "measure stackless state machines before choosing them", which it has now done.*
5. **Keep the stack checks, and add MMU guard pages where they fit.**
   - **What the checks cost now:** they run in assembly before anything is written to the task's stack, leave a failed stack untouched, use none of the task's stack, and cost 19 of the 48 instructions of a yield.
   - **What they still cannot do:** they find an overrun only after the fact, and the moat below the lowest task covers only an overrun shorter than one slot.
   - **Guard pages:** a guard page stops an overrun that touches it (catching every overrun also needs stack probes). But on ARMv7 each guarded stack becomes at least one 4 KiB page, so 1,000 tasks would need 4,096,000 bytes of stack instead of 256,000.
   - **Open:** a mixed scheme (pages for the few deep stacks, words for the many small ones) is an open question for 3b and 3g.

   *Round 2: the cost figures changed, and the moat's limit was added.*

## Open questions

- **Preemption.** A timer interrupt that switches tasks must save every register, not only r4–r11, and needs an interrupt stack. That is not built, and on QEMU it would use board-specific timer and interrupt-controller code.
- **Two cores.** Run queues per core, locking with `LDREX`/`STREX`, and moving tasks between cores.
- **The phone.** Cycles per switch on Krait, and the cache cost of thousands of small stacks or state machines, can only be measured there.
- **Bounding a stack before running.** Here a stack's depth is measured by painting; a static bound (call-graph analysis) would let the build refuse a task whose stack is too small, and bound the executor's stack, which every poll shares.
- **The panic path's depth on a task's stack is not measured** (round 2). A panic inside a task, such as an index out of range or a failed assertion, runs Rust core's panic machinery and the panic handler on that task's stack, or on the executor's for a stackless task. How deep that goes is not known. A stack sized from painting the normal path may be too small for a panic, and the panic could overrun it before the handler halts. To measure: paint, panic from a task, count.
- **Spawning from a task, blocking and waking, priorities.** None is built. A spawn from a running task is refused in both the stackful and the stackless model, and the stackless executor has no wake-up.
- **A cheaper job path:** one stack check per batch of steps instead of per step, and queue operations without bounds checks, each measured against the 93 instructions here.
- **A cheaper yield:** `yield_next` stores the next task's slot base for the check on every switch (7 instructions). A check that found the base from the task's index would trade those stores for loads in the check. Not measured.
- **The calling contract** of `yield_now` and `run` (above) is documented, not checked.

## Consequences

- If the reviewer accepts this direction, Phase 3's sub-milestone 3g starts from these numbers, and ADR 0002's goal 4 has its first emulator figures for all three models.
- Nothing here changes the phone, the frozen payload or the hardware-safety contract.

## Scope of round 2

Emulator fixture code, a measurement script and documentation. No device was contacted, nothing under `boot/` changed, no hosted CI ran, and no firmware was downloaded.
