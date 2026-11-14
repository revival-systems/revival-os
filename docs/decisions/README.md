# Architecture decision records

Permanent, discoverable records of decisions that shape Revival OS. Each is numbered, dated and kept even after it is superseded (a later record supersedes an earlier one; the earlier one is not deleted).

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-rust-and-arm-assembly.md) | Rust (`#![no_std]`) and ARM Assembly for the kernel; Rust native stack and static memory first; bounded Rust arenas only when justified; Goose retained as a studied reference | Accepted 2026-11-09 |
| [0002](0002-design-goals.md) | The owner's eight design goals (small, fast, secure, scalable, maintainable, built from the ground up with room to invent, the memory rule, a real-world system), what each means here, how each is measured and where its number is set | Accepted by the reviewer 2026-11-14 |
| [0003](0003-task-model.md) | The task model, from emulator experiments on three models: a stackful task costs 264 bytes (256-byte stack) and 57 instructions per step (48 of them the yield), and 12,000,000 ran in QEMU; a run-to-completion job costs 12 bytes and 93 instructions per step, and 10,000,000 ran; a stackless task (Rust `async`, no heap) costs 16 bytes and 75 instructions per step, and 200,000,000 ran | Accepted by the reviewer 2026-11-14 |

Related planning document: the [Goose reference preservation plan](../goose-reference-preservation-plan.md).
