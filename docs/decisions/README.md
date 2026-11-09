# Architecture decision records

Permanent, discoverable records of decisions that shape Revival OS. Each is numbered, dated and kept even after it is superseded (a later record supersedes an earlier one; the earlier one is not deleted).

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-rust-and-arm-assembly.md) | Rust (`#![no_std]`) and ARM Assembly for the kernel; Rust native stack and static memory first; bounded Rust arenas only when justified; Goose retained as a studied reference | Accepted 2026-11-09 (pull request pending review) |

Related planning document: the [Goose reference preservation plan](../goose-reference-preservation-plan.md).
