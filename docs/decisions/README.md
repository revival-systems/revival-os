# Architecture decision records

Permanent, discoverable records of decisions that shape Revival OS. Each is numbered, dated and kept even after it is superseded (a later record supersedes an earlier one; the earlier one is not deleted).

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-rust-and-arm-assembly.md) | Rust (`#![no_std]`) and ARM Assembly for the kernel; Rust native stack and static memory first; bounded Rust arenas only when justified; Goose retained as a studied reference | Accepted 2026-11-09 (pull request pending review) |
| [0002](0002-design-goals.md) | The owner's eight design goals (small, fast, secure, scalable, maintainable, built from the ground up with room to invent, the memory rule, a real-world system), what each means here, how each is measured and where its number is set | Proposed 2026-11-14 (draft pull request) |
| [0003](0003-task-model.md) | The task model, from an emulator experiment: stackful tasks with a cooperative switch cost 8 bytes of table plus one stack slot (264 bytes at 256-byte stacks) and 48 instructions per yield; 12,000,000 ran in QEMU; jobs and stackless state machines compared, not yet measured | Proposed 2026-11-14 (draft pull request) |

Related planning document: the [Goose reference preservation plan](../goose-reference-preservation-plan.md).
