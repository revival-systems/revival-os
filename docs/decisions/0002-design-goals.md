# ADR 0002 — Design goals, and how each one is measured

- **Status:** Proposed. The eight goals are the owner's, stated on 2026-11-10 and 2026-11-14 and relayed in the reviewer's task of 2026-11-14. How each goal is measured, and where its number is set, is this record's proposal, for the reviewer's review.
- **Builds on:** [ADR 0001](0001-rust-and-arm-assembly.md) (Rust and ARM Assembly; the memory strategy), [ARCHITECTURE.md](../../ARCHITECTURE.md#goals) (goals and engineering standards) and the [roadmap rules](../../ROADMAP.md#rules-for-every-phase).
- **Does not change:** the hardware-safety contract, the phase-by-phase method, or any pass criterion already in the roadmap.

## Context

The project's goals are only partly written down. [ARCHITECTURE.md](../../ARCHITECTURE.md#engineering-standards) covers bounded resources, recovery, portability, security by default and "measured performance". [ADR 0001](0001-rust-and-arm-assembly.md#memory-strategy) covers the memory strategy. Nothing states the headline goals, gives a number to hold to, plans for many tasks at once, or leaves room for original ideas. The roadmap has no milestone for tasks or scheduling.

This record writes the owner's goals down, says what each means in engineering terms here, and says how each will be measured. It invents no number: its figures are measurements, and its only targets are the owner's (thousands of tasks) and the reviewer's proposed first proof point (1,000 tasks).

## The figures that exist today

Every figure in this table was measured; none of them is a target.

| Figure | Value | Source |
| --- | --- | --- |
| Phase 2 proof-of-execution payload, `payload.bin` (frozen) | 1,636 bytes | The frozen hash in the [Makefile](../../Makefile) (`PAYLOAD_BIN_SHA256`) and [section 1 of the write-plan draft](../phase-2/write-plan-draft.md#1-what-is-written) |
| The Android boot image around it, `payload.img` | 6,160 bytes | The same section of the write-plan draft |
| Phase 1 heartbeat kernel, code and constants (`.text` 1,484 + `.rodata` 97 + `.ARM.exidx` 8) | 1,589 bytes | `arm-none-eabi-size -A build/qemu-virt-armv7/kernel-heartbeat.elf`, built from `main` at `da1ebae` |
| The same kernel as a flat binary | 1,596 bytes | `arm-none-eabi-objcopy -O binary` of that image |
| The same kernel's reserved stack | 65,536 bytes | `.stack` in [link.ld](../../tests/qemu/virt-armv7/link.ld) |
| Phase 1 negative-test kernels, code and constants: panic, bounds check | 2,060 and 7,692 bytes | `arm-none-eabi-size -B` of `kernel-panic.elf` and `kernel-oob.elf`, the same build. Core's panic-message formatting makes the difference. |
| The heartbeat kernel's ELF file, debug information included | 11,108 bytes | [Phase 1 working notes](../phase-1/rust-foundation.md#binary-sizes-and-sha-256) |
| Usable RAM on the phone | `MemTotal: 1363632 kB` (about 1.3 GiB), as the stock kernel reports it | [Phase 0 hardware evidence](../evidence/phase-0/2026-11-13-hardware-summary.md#actual-device-observations) |
| CPU | Two ARMv7 processors (implementer `0x51`, part `0x04d`); VFPv4 and NEON listed; no integer-divide feature listed | The same evidence |
| The full local suite, `make check` | 61 tests pass in about 13 seconds on the development machine | A clean export of `da1ebae`, 2026-11-14 |

No figure exists yet for the phone's speed, the cost of a task, a context switch or an interrupt, or memory use beyond these images.

## Decision

### The owner's goals

1. **Very small.** One of the smallest operating systems that does real work. The owner named tiny assembly-language systems as the inspiration.
2. **Very fast and efficient.** High performance on old hardware.
3. **Secure.**
4. **Scalable.** Many pieces of work at once, from dozens up to thousands of tasks or threads, and able to move to other devices.
5. **Maintainable.** A codebase that stays simple to understand and to change.
6. **Built from the ground up, with room to invent.** Original ideas from the project's own research are welcome when they serve goals 1 to 5.
7. **The memory rule of ADR 0001.** The stack first, a heap only when it is necessary, in the bounded-arena style studied in Goose.
8. **A real-world system, not a demo.** It ends up doing a real job on real hardware.

### What each goal means here, and how it is measured

#### 1. Very small

- **In engineering terms:** the image the phone runs is as few bytes as the job allows, and every byte has a reason. Size is counted as the loadable bytes of the image (code, constants and initialised data, as `arm-none-eabi-size` reports them) and as the flat binary that is flashed. Statically reserved memory (`.bss`, stacks) is counted separately, under goal 7.
- **What implements it today:** `#![no_std]` Rust with no C library and no allocator; the link checks that reject a C-library or `std` symbol (`make test-build`, `make test-rust`, `make test-payload`); `--gc-sections`; the frozen 1,636-byte payload ([boot/samsung-serranolte/payload.rs](../../boot/samsung-serranolte/payload.rs)) and the 1,589-byte heartbeat kernel ([tests/qemu/virt-armv7/kernel.rs](../../tests/qemu/virt-armv7/kernel.rs)).
- **How it is measured:** the image's loadable bytes and flat-binary bytes, recorded with the commit that produced them, and a breakdown by symbol (`arm-none-eabi-nm --size-sort`) when a change adds more than it should.
- **Where its number is set:** the payload is frozen by hash, which is stricter than a budget. A size budget for the kernel image is set before Phase 3 starts, from the Phase 2 image (roadmap rule 5).

#### 2. Very fast and efficient

- **In engineering terms:** the time and energy each operation costs on the GT-I9195, measured on the GT-I9195. "Fast" is a figure per operation: boot to first output, a context switch, an interrupt's latency, a system call later. "Efficient" means work per joule, and memory per task (goal 4).
- **What implements it today:** nothing measures speed or energy yet. The [engineering standard "measured performance"](../../ARCHITECTURE.md#engineering-standards) requires latency, throughput, memory, CPU, energy and storage figures to be measured on the device and recorded with their commit; the release build is optimised (`-C opt-level=2`, [Makefile](../../Makefile)).
- **How it is measured:** time on the phone, by a cycle counter or a timer read before and after the operation, repeated, with the spread recorded; boot-to-output latency from video, as the write-plan draft records it ("key release to picture", [section 11](../phase-2/write-plan-draft.md#11-evidence)). Energy on the phone, as the power drawn from the battery supply, measured externally, at idle and under a named load, with the work done under that load (for example frames recorded per second), so that the figure is work per joule ([ROADMAP Phase 9](../../ROADMAP.md#phase-9--hardening-and-portability) already plans "measured idle and recording power"). In QEMU, only instruction counts and code bytes are measured. **Emulator timing is not phone timing** ([TESTING.md](../TESTING.md#test-tiers)).
- **Where its number is set:** each time budget comes from that operation's first measurement on the phone, and is set before the next phase starts (roadmap rule 5). Boot latency is first measured in Phase 2 and budgeted before Phase 3 starts. Switch time is first measured on the phone in 3g and budgeted before Phase 4 starts; emulator runs may come first, inside Phase 3, but give instruction counts only. Interrupt latency is not yet a planned measurement (3d plans the timer interrupt, not its latency), so its budget waits until a phase measures it. This roadmap sets no energy budget: Phase 9, its last phase, measures and records idle and recording power. A budget would need an earlier power measurement (for example in Phase 6, once recording runs); adding one is the reviewer's decision.

#### 3. Secure

- **In engineering terms:** the system does only what it was built to do, and a fault in one part cannot silently corrupt another. That means memory safety by default (Rust, bounds checks), every `unsafe` block justified and tested, stack overflows detected rather than silent, no unauthenticated control interface, least privilege between parts once there is more than one, and builds that can be reproduced from a commit.
- **What implements it today:** the [hardware-safety contract](../../AGENTS.md#hardware-safety-contract); Rust's bounds check reaching the panic handler (`qemu-rust-bounds`); the corrupted-image check (`build-rust-corrupt-image-rejected`); the link checks; reproducible builds (`repro-identical`, `payload-repro-identical`); the [engineering standard "security by default"](../../ARCHITECTURE.md#engineering-standards).
- **How it is measured:** as properties, each checked by a test that can fail: a negative test for every check (bounds, stack overrun, corrupted image, refused input), and the count of `unsafe` blocks, each with its safety comment and its negative test. The cost of each check is measured too, because it trades against goal 2.
- **Where its number is set:** security has no single figure. Each check's test is added with the feature that needs it; the stack-overflow check is ROADMAP 3b (MMU guard regions).

#### 4. Scalable

- **In engineering terms:** two kinds of growth. **Work:** one more task costs a small, fixed amount of memory, with no general heap: its stack, the guard region below that stack, its control block, and its arena if it has one (none unless a concrete requirement justifies it, as [ADR 0001](0001-rust-and-arm-assembly.md#memory-strategy) decides). These are its **bytes per task**. Running out of tasks is an error that is reported, never undefined behaviour. **Devices:** a second device means a new port, not a rewrite ([ARCHITECTURE.md](../../ARCHITECTURE.md#portability)).
- **What implements it today:** for work, nothing; there is no task or scheduler code. For devices, the layering of `arch/`, `soc/` and `board/` and the platform contract ([ARCHITECTURE.md](../../ARCHITECTURE.md#layers-and-dependency-rules)), still a proposal.
- **How it is measured:** bytes per task (as defined above); the largest task count, which is the memory reserved for tasks divided by that figure, shown by a run; and the cost of one switch. Each comes from a test that can fail. For devices: what a second port has to change (Phase 9).
- **Where its number is set:** the owner's target is thousands of tasks. The reviewer proposes **1,000 tasks on this phone** as the first proof point, shown by measurement: that is the task-count criterion of ROADMAP 3g (provisional), confirmed or changed when Phase 3 is refined. Of this goal's figures, only the build-time ones can be set before Phase 3 starts (rule 5): the task count, and a bytes-per-task budget, which a build measures the same way whether it runs in QEMU or on the phone. The switch's time on the phone is first measured in 3g and budgeted before Phase 4 starts (goal 2).

#### 5. Maintainable

- **In engineering terms:** a new contributor can find where a thing lives, change it, and know from the tests whether the change is right. Small modules with documented interfaces, one logical change per commit, assembly only where Rust cannot work (each file says why), and documentation that is checked.
- **What implements it today:** `make check` (lint, documentation links and anchors, every test) before every push ([AGENTS.md](../../AGENTS.md#git)); the proposed [module boundaries](../../ARCHITECTURE.md#layers-and-dependency-rules) (not yet code); `-D warnings` ([Makefile](../../Makefile)); the documentation checker ([tests/docs/check_docs.py](../../tests/docs/check_docs.py)); each assembly file's statement of why it is not Rust ([kstart.S](../../tests/qemu/virt-armv7/kstart.S)).
- **How it is measured:** `make check` passes on a clean export, and how long it takes; lines of Rust and of assembly per module, and the count of `unsafe` blocks, recorded with each phase's evidence.
- **Where its number is set:** these counts are recorded with each phase's evidence, starting from the Phase 1 and Phase 2 code; a budget, if one is wanted, is set from those records before Phase 4 starts.

#### 6. Built from the ground up, with room to invent

- **In engineering terms:** no Linux, Android or hosted C library at run time ([ARCHITECTURE.md](../../ARCHITECTURE.md#goals)), and the project's own research may produce its own designs. An original idea is welcome when it serves goals 1 to 5 and survives an experiment that could have shown it wrong.
- **What implements it today:** the `-nostdlib` link in the [Makefile](../../Makefile) (`RUST_LINK_BASE`), so the Rust images contain only the project's code and Rust's `core` and `compiler_builtins`. The negative tests `build-rust-rejects-std`, `build-rust-rejects-libc`, `payload-rejects-std` and `payload-rejects-libc` show that a `std` or C-library reference is rejected, and `build-rust-symbols` and `payload-symbols` require zero undefined symbols. The exact-inputs check (`build-link-map`, [tests/build/check_link.py](../../tests/build/check_link.py)) covers the probe and allocator images, not yet the Rust images. And this decision-record process ([the index](README.md)).
- **How it is measured:** each original idea gets **its own decision record** that names the research it comes from, the goal it serves, and an **experiment that can fail**, with the experiment's result. Nothing is called novel without a source check: a search of prior work, cited in that record.
- **Where its number is set:** in that record, as the experiment's own pass or fail criterion.

#### 7. The memory rule: the stack first, a heap only when necessary

- **In engineering terms:** as [ADR 0001](0001-rust-and-arm-assembly.md#memory-strategy) decides: the native Rust stack for calls and locals, statically reserved fixed-capacity regions for lasting data, no general-purpose heap allocator, and bounded arenas (bump allocation with a capacity check before every advance) only when a concrete requirement justifies them. The idea comes from Goose's separate data region; the unchecked advance does not ([what not to inherit](0001-rust-and-arm-assembly.md#what-to-learn-from-goose-and-what-not-to-inherit)).
- **What implements it today:** the Phase 1 kernel ([kernel.rs](../../tests/qemu/virt-armv7/kernel.rs)) and the Phase 2 payload ([payload.rs](../../boot/samsung-serranolte/payload.rs)) use only the stack and static data, and both link scripts reserve a fixed 64 KiB stack ([link.ld](../../tests/qemu/virt-armv7/link.ld), [boot/samsung-serranolte/link.ld](../../boot/samsung-serranolte/link.ld)). Neither crate uses `alloc` or defines a `#[global_allocator]`, and `arm-none-eabi-nm` lists no allocator symbol (`__rust_alloc`, `__rdl_alloc`, `malloc`) in either image.
- **How it is measured:** statically reserved bytes per image (`.data`, `.bss`, stacks); stack depth per task, by painting the stack and finding the deepest overwritten word; and that no allocator symbol is defined in the image (a check of defined symbols; `nm -u` lists only undefined ones).
- **Where its number is set:** a memory budget per image is set before Phase 3 starts, inside the RAM the phone reports (about 1.3 GiB).

#### 8. A real-world system, not a demo

- **In engineering terms:** the measure of success is a job done on the real phone: the standalone camera of ROADMAP Phase 7, capturing, storing and serving video to the iPhone app with no server. Emulator results never count as hardware results ([roadmap rule 1](../../ROADMAP.md#rules-for-every-phase)).
- **What implements it today:** the phases of [ROADMAP.md](../../ROADMAP.md), each with pass criteria, physical verification and recovery evidence; the Phase 0 baseline on the owner's GT-I9195 ([hardware evidence](../evidence/phase-0/2026-11-13-hardware-summary.md), [addendum](../evidence/phase-0/2026-11-13-linux-retest.md)).
- **How it is measured:** each phase's pass criteria, on the device, with recorded evidence ([TESTING.md](../TESTING.md#recording-evidence)).
- **Where its number is set:** in each phase's criteria, refined before that phase starts (roadmap rule 5).

### Rules for the numbers

- **Only measured figures.** A size, memory or performance figure in this project is a measurement with its source, or a budget derived from one. Where no measurement exists, the record says "budget set before Phase N starts" and names the measurement (roadmap rule 5). Where no phase plans that measurement yet, the record says so (interrupt latency and energy, goal 2). Trial counts and other test parameters are set in review under rule 5, as the roadmap's criteria already are.
- **A budget is enforced where it is measured.**
  - **Build-time budgets** (an image's loadable and flat bytes, statically reserved bytes, bytes per task): each becomes a test under `make check` that fails when it is exceeded, in the style of `payload-frozen` ([Makefile](../../Makefile), `test-payload` part (f)): for example, a check that fails when the image's loadable bytes grow past the budget.
  - **Phone-measured budgets** (latency, switch and interrupt time, and energy if a budget is ever set): checked in the device procedure of the phase whose rule-5 refinement sets the budget, which reports expected and measured values (as Phase 3's observable test already does), measured again in each later phase that changes that path, and recorded as evidence in the device tier of [TESTING.md](../TESTING.md#recording-evidence).
  - **Emulator guards:** an instruction-count check, if one is added to `make check`, is labelled as an emulator figure and never stands for a phone time.
  - Raising any budget is a reviewed change with its reason.
- **Each figure names its tier.** Emulator figures and phone figures are kept apart and labelled.

### Tasks: one more task costs a small, fixed amount

A task's cost must be known before it is created: its bytes per task (stack, guard region, control block, and an arena only if a requirement justifies one), sized when the system is built, so that the largest task count is a division and not a guess. The owner's target is thousands of tasks. The first proof point proposed by the reviewer is 1,000 tasks on the phone, shown by measurement. Which kinds of work need a stack of their own and which can be cheaper (run-to-completion jobs, stackless state machines) is an open question for the task-model experiment and its own record.

### Room to invent

An original idea enters the design through its own decision record, which states:

1. the research it comes from, with sources;
2. the goal it serves (1 to 5);
3. an experiment that can fail, its pass criterion set beforehand, and its result;
4. the source check: what prior work was searched and what was found.

Nothing is called novel until that check is done.

### The tensions, stated plainly

- **Small against fast.** Inlining, unrolling and lookup tables make code faster and bigger. Each such change records both its size and its speed, and the trade is decided by the numbers.
- **Thousands of tasks against no general heap.** Without a heap, every task's memory is reserved in advance, so the task count is bounded by the memory set aside. Per-task cost must be small, and the cheapest kind of task that does the job is preferred.
- **Security checks against speed.** Bounds checks, stack guards, MMU guard pages and privilege changes cost cycles and memory. An MMU guard page also forces stacks to whole 4 KiB pages on ARMv7. Each check's cost is measured, so keeping or dropping it is a decision, not an accident.
- **The hardware bounds all of it.** Two cores and about 1.3 GiB of usable RAM, as measured. Every memory budget fits inside that RAM, and every time and energy budget comes from measurements on this phone.

## Consequences

- [ROADMAP.md](../../ROADMAP.md#phase-3--kernel-foundations) Phase 3 gains a provisional sub-milestone, 3g, for tasks and scheduling, whose task-count target comes from this record.
- [ARCHITECTURE.md](../../ARCHITECTURE.md#goals) "Goals" lists the headline goals, one line each, and links here.
- [README.md](../../README.md) and the [decision index](README.md) link here.
- No code, no budget and no test is added by this record. Each budget arrives with its measurement, and each test with its budget.

## Scope of this pull request

Documentation only. No code was written, no toolchain was changed, no experiment was run for it, and no hardware was touched.
