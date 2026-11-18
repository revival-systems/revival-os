# Hardware support matrix

One row per exact model and SoC, not per marketing family ([Revival Server #120](https://github.com/revival-systems/revival-server/issues/120)). "Target" means intended. Only "Verified" columns record achieved results, and each one links to its evidence. An emulator row never counts as hardware support.

| Target | ISA / ABI | SoC | Boot path | Recovery | Debug output | Verified level | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Samsung Galaxy S4 Mini LTE **GT-I9195** (`serranolte`) | ARMv7-A, 32-bit; Qualcomm CPU, NEON/VFPv4 observed | Qualcomm MSM8930AB (research identification); PIT MSM8930; Android platform MSM8960 | Stock Android and ADB observed; historical Download-mode detection and PIT read | Matching stock images verified; earlier physical checks owner-reported; detailed repeated-trial records unavailable here | Bootloader framebuffer **confirmed** at `0x88100000` for a start from `RECOVERY` (measured 2026-11-18, [session record](../evidence/phase-2/2026-11-18-v5-session.md#12-what-this-answers)); UART unconfirmed | Phase 0 **PASS** (owner-directed, 2026-11-13); [addendum](../evidence/phase-0/2026-11-13-linux-retest.md); **Revival OS code has run on the device** from `RECOVERY` (Phase 2 initial proof of execution, 2026-11-18, [session record](../evidence/phase-2/2026-11-18-v5-session.md)); no normal power-on boot of Revival OS yet | [Consolidated hardware evidence](../evidence/phase-0/2026-11-13-hardware-summary.md), [research](gt-i9195.md) |
| QEMU `virt`, `cortex-a15` (**emulator, not hardware**) | ARMv7-A, 32-bit | none (emulated) | `-kernel` ELF | Defined semihosting exit; panic/bounds failure paths tested | PL011 UART, semihosting | **Phase 1 PASS:** Rust + ARM Assembly foundation; 20/20 heartbeat runs, reproducible builds and hosted verification. Goose probe retained as reference | [Phase 1 gate review](../evidence/phase-1/2026-11-13-gate-review.md) |

Support levels, in order: research → boots (Phase 2) → minimal OS (Phase 3–4) → networked (Phase 5) → local camera MVP (Phase 7).

A second hardware target (an accessible, unlockable AArch64 device) is chosen by evidence in Phase 9. None is selected yet.
