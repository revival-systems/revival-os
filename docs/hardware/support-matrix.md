# Hardware support matrix

One row per exact model and SoC, not per marketing family ([Revival Server #120](https://github.com/revival-systems/revival-server/issues/120)). "Target" means intended. Only "Verified" columns record achieved results, and each one links to its evidence. An emulator row never counts as hardware support.

| Target | ISA / ABI | SoC | Boot path | Recovery | Debug output | Verified level | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Samsung Galaxy S4 Mini LTE **GT-I9195** (`serranolte`) | ARMv7-A, 32-bit | Qualcomm MSM8930AB | Stock Samsung bootloader loads an Android boot image from `boot` or `recovery`; Download mode (Odin protocol, Heimdall) | Battery removal; Download mode + stock images | Bootloader framebuffer (unconfirmed); micro-USB JIG UART (unconfirmed) | **Research only.** Phase 0 not yet performed. | [gt-i9195.md](gt-i9195.md) |
| QEMU `virt`, `cortex-a15` (**emulator, not hardware**) | ARMv7-A, 32-bit | none (emulated) | `-kernel` ELF | n/a | PL011 UART, semihosting | Goose toolchain probe runs (pre-Phase 1 feasibility) | [goose-freestanding-notes.md](../toolchain/goose-freestanding-notes.md) |

Support levels, in order: research → boots (Phase 2) → minimal OS (Phase 3–4) → networked (Phase 5) → local camera MVP (Phase 7).

A second hardware target (an accessible, unlockable AArch64 device) is chosen by evidence in Phase 9. None is selected yet.
