# ADR 0001 — Rust and ARM Assembly for the Revival OS kernel

- **Status:** Accepted by the owner on 2026-11-09. This documentation pull request is pending orchestrator review ([AGENTS.md](../../AGENTS.md)).
- **Supersedes:** the earlier working assumption, recorded in the first drafts of [README.md](../../README.md), [ARCHITECTURE.md](../../ARCHITECTURE.md) and [ROADMAP.md](../../ROADMAP.md), that Goose would be the active kernel implementation language.
- **Does not change:** the hardware target, the phase-by-phase method, or the hardware-safety contract.

## Context

Revival OS set out to be written primarily in Goose (compiled to C, cross-compiled for ARMv7-A). A Phase 1 feasibility experiment in QEMU showed that a small Goose subset can be compiled freestanding, but it also surfaced two problems in the pinned compiler's output:

1. A **QEMU-reproduced unaligned-access fault** on ARMv7-A (the generated C emitted unaligned wide stores).
2. A **source-level data-stack concern**: the generated data-stack code advances a stack pointer by a run-time-dependent amount without writing the skipped range, and leans on an unmapped guard gap whose bound is not established for a 32-bit address space. This was a **source-analysis concern, not a reproduced memory-corruption result**, and investigating it further repeatedly ran into tooling limits.

Rather than continue an open-ended investigation of the Goose toolchain's low-level code generation, the owner has decided to implement the operating system in languages whose freestanding behaviour and memory model Revival OS controls directly.

## Decision

### Languages

- **Rust (`#![no_std]`)** is the active implementation language for the kernel.
- **ARM Assembly** is used only for what Rust cannot express: the entry stub, exception vector table, CPU-mode and special-register setup, barriers, and the context switch. Each assembly file states why it cannot be Rust.
- No other language enters the active kernel build without a demonstrated technical need and owner approval.

### Target (unchanged)

- **ARMv7-A, 32-bit ARM.** First hardware target: **Samsung Galaxy S4 Mini LTE, GT-I9195**.
- Initial development and testing in **QEMU** (an ARMv7-A machine such as `virt` with `-cpu cortex-a15`). Emulator success is never evidence that the kernel boots on the phone.

### Memory strategy

Initial design, for the first kernel milestones:

- Use the **native Rust call stack** for functions and local variables.
- Use **statically reserved memory** (fixed-capacity, compile-time-sized regions) for persistent kernel data and fixed structures.
- **No general-purpose heap allocator.** No dynamic allocation that is not required.
- Keep memory usage **explicit and bounded**.

Later design to evaluate, **only when a concrete kernel requirement justifies it**:

- Independent **bounded Rust arenas** backed by statically reserved regions, using bump allocation, with:
  - checked size, alignment and offset arithmetic;
  - a **capacity check before every pointer/offset advance**;
  - explicit lifetimes so a reference cannot outlive the arena or its reset;
  - controlled reset points.
- Arenas are not implemented prematurely, and any `unsafe` in them requires negative tests (overflow, exhaustion) and review before a memory-safety claim is made.

This borrows the *idea* of a separate data-oriented region and fast bump allocation from Goose, but reimplements it in Rust with bounds and alignment checks the previous Goose work lacked. See [what to learn, and what not to inherit](#what-to-learn-from-goose-and-what-not-to-inherit).

## Goose is retained as a reference, not deleted

The existing Goose prototype, experiments, research documents, test fixtures, scripts and toolchain pins are **preserved in this repository as a studied reference**, not discarded. They are valuable material for how Goose approaches separate data stacks and bump allocation.

- Proposed future location: a `reference/goose/` workspace (a living reference, not an archive). The exact move is **not performed by this decision** — it is planned, inventoried and executed through a separate reviewed pull request. See the [Goose reference preservation plan](../goose-reference-preservation-plan.md).
- The Rust kernel build **must not depend** on the Goose compiler, its runtime, or its generated C.
- Historical Goose results stay clearly labelled as Goose results. They are never presented as evidence that the Rust kernel works.

## What to learn from Goose, and what not to inherit

**Concepts worth studying and reimplementing in Rust:** separating a data-oriented region from the normal call stack; bump allocation; fixed-capacity regions; explicit lifetime and reset points; fast, predictable allocation for bounded kernel tasks.

**Not inherited without independent, tested safety:** Goose's compiler-generated data-stack arithmetic; advancing a stack or offset without writing the skipped range; reliance on a guard gap whose bound is not established; 32-bit pointer-wrap assumptions; and the belief that a static region alone makes code memory-safe. A Rust arena must bound and align-check every advance, carry negative tests for overflow and exhaustion, and enforce lifetimes; any `unsafe` is reviewed.

## Development method (unchanged in spirit, restated)

Every increment follows the cycle recorded in [docs/DEVELOPMENT.md](../DEVELOPMENT.md#development-cycle):

**Build → Boot → Observe → Test → Reboot → Recover → Measure → Document.**

A phase closes only on the evidence that phase requires — never because code compiles or a design document exists. QEMU evidence and physical-device evidence stay separate.

## Consequences

- README, ARCHITECTURE, ROADMAP and docs/DEVELOPMENT are updated so they no longer describe Goose as the active or future kernel language, while keeping the historical facts and the Goose research intact.
- Phase 1 changes from "freestanding Goose toolchain" to a **freestanding Rust + ARM Assembly foundation** that boots in QEMU and prints a deterministic heartbeat from Rust. The Goose feasibility result is kept as historical reference.
- A Rust bare-metal toolchain (target, pins) will be added in a **later, separate, reviewed pull request**. The Goose and Arm GNU Toolchain pins are **not** changed by this decision, and the shared Goose pin with Revival Server is untouched.
- Phase 0 hardware verification remains a separate, unmet requirement. No phase is marked complete by this decision.

## Scope of this pull request

Documentation only. No source files were moved or deleted, no toolchain was installed or changed, no experiment was run, and no hardware was touched. The Goose migration and the first Rust kernel milestone are separate, later, reviewed pull requests.
