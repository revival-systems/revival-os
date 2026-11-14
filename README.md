# Revival OS

A lightweight, independent operating system written in **Rust and ARM Assembly** (`#![no_std]`, ARMv7-A), intended to run directly on repurposed phone hardware and, later, on cameras, robots and other embedded devices. It began as a [Goose](https://github.com/aardappel/goose)-based prototype; that work is kept as a studied reference ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)).

**Status: Phase 0 — research and hardware verification. A QEMU-only Rust + ARM Assembly kernel exists (the Phase 1 foundation); no Revival OS code has run on the phone yet.** That kernel boots only in the QEMU emulator ([working notes](docs/phase-1/rust-foundation.md)), which is not a hardware result, and no hardware milestone has been passed. This repository also holds the architecture, the milestone plan and the first target's research and test procedure.

## First target

**Samsung Galaxy S4 Mini LTE, GT-I9195** (codename `serranolte` / `serranoltexx`): Qualcomm MSM8930AB (Snapdragon 400), two Krait cores, 32-bit ARMv7-A, 1.5 GB RAM, removable battery.

These facts come from public sources and **have not yet been confirmed on the owner's physical device**. See [docs/hardware/gt-i9195.md](docs/hardware/gt-i9195.md) for the research and its sources, and the [Phase 0 hardware verification checklist](docs/phase-0/hardware-verification-checklist.md) for the confirmation procedure.

## What "replacing Android" means here

On this phone, early boot is fixed vendor firmware: the SoC boot ROM, Qualcomm's signed secondary bootloaders, TrustZone, the RPM firmware and Samsung's bootloader. Those stay. Revival OS replaces what that chain loads from the `boot` (or `recovery`) partition: today, the Linux kernel and the Android userspace above it. **The owner intends the final device to boot Revival OS, not Android; personal data are disposable.** Some peripherals (Wi-Fi, modem, video, GPU) also run vendor firmware, which Revival OS would load rather than replace. These essential firmware components must not be erased just because Android is being replaced. Details: [ARCHITECTURE.md](ARCHITECTURE.md#what-stays-vendor-firmware).

There is no PC BIOS or UEFI on this device.

## How the work proceeds

Every milestone adds the smallest capability that can be observed and tested on the real phone, with a recorded rescue path. Emulator results never count as hardware results. **The Samsung is dedicated to Revival OS experiments; Android and personal data need not be preserved.** Phase 0 stock boot/reboot checks are only a one-time hardware baseline; after that, *boot* and *reboot* milestones measure **Revival OS itself**, one tiny capability at a time: first our code executing, then a normal power-on boot path, then a logo/console and individual drivers. Android removal is eventual and controlled, not a prerequisite for the first experiments. See [ROADMAP.md](ROADMAP.md).

| Phase | Capability | State |
| --- | --- | --- |
| 0 | One-time stock hardware baseline; identify the boot chain and emergency rescue path | Research documented; physical verification evidence pending review |
| 1 | Freestanding Rust + ARM Assembly foundation for ARMv7-A | QEMU foundation implemented ([PR #5](https://github.com/revival-systems/revival-os/pull/5) merged; [working notes](docs/phase-1/rust-foundation.md)); formal gate review pending; not yet run on the Samsung. Goose feasibility kept as reference ([findings](docs/toolchain/goose-freestanding-notes.md)) |
| 2 | First bare-metal boot with observable output | Not started |
| 3–9 | Kernel foundations → hardware → networking → camera → standalone camera → internet → hardening | Not started |

## Quick start

Development and testing happen on the local Ubuntu machine ([docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)):

```sh
sudo apt install make gcc libc6-dev python3 git qemu-system-arm gdb-multiarch shellcheck cppcheck
make install-toolchain   # pinned Goose compiler and Arm toolchain, SHA-256 verified, no sudo
make doctor              # every required tool must be "ok"
make check               # lint, docs and every test; run before each push
```

The buildable artifacts today are QEMU-only test fixtures. The **Phase 1 Rust + ARM Assembly kernel image** boots on QEMU's `virt` board and prints a heartbeat and a checksum ([working notes](docs/phase-1/rust-foundation.md), [ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)); it has not run on the Samsung. The **Goose toolchain probe** is now a reference artifact: a tiny Goose program cross-compiled for ARMv7-A and run in QEMU with no Linux and no C library. It tests the toolchain and is not part of the operating system.

## Repository map

| Path | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Proposed module boundaries, dependency rules and vendor-firmware boundaries |
| [ROADMAP.md](ROADMAP.md) | Phases 0–9, each with a capability, tests, pass/fail criteria and recovery evidence |
| [AGENTS.md](AGENTS.md) | Rules for coding agents, including the hardware safety contract |
| [docs/decisions/](docs/decisions/README.md) | Architecture decision records; [ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md) adopts Rust + ARM Assembly; [ADR 0002](docs/decisions/0002-design-goals.md) records the owner's design goals and how each is measured |
| [docs/goose-reference-preservation-plan.md](docs/goose-reference-preservation-plan.md) | Inventory and plan for keeping Goose as a `reference/goose/` study workspace |
| [Makefile](Makefile) | The local build and test entry points (`make help`) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, pinned versions, commands, workflow and review checklist |
| [docs/TESTING.md](docs/TESTING.md) | Test tiers, what each test checks, what is not tested yet, evidence rules |
| [docs/CI-STRATEGY.md](docs/CI-STRATEGY.md) | Local-first CI: the manual-only workflow and its cost controls |
| [docs/hardware/](docs/hardware/gt-i9195.md) | GT-I9195 research and the [support matrix](docs/hardware/support-matrix.md) |
| [docs/phase-0/](docs/phase-0/hardware-verification-checklist.md) | The Phase 0 hardware verification checklist |
| [docs/toolchain/](docs/toolchain/goose-freestanding-notes.md) | Goose **reference** research: freestanding feasibility findings, and the runtime research: [dependency map](docs/toolchain/goose-runtime-dependency-map.md), [runtime routes](docs/toolchain/goose-runtime-options.md), [upstream questions](docs/toolchain/goose-upstream-questions.md), [next experiment](docs/toolchain/next-runtime-experiment.md) |
| [tools/](tools/pins.env) | Pinned versions and the installers |
| [tests/](tests/qemu/virt-armv7/minirt.c) | Test fixtures: the Goose probe, the QEMU harness, host tests and the docs checker |

The source directories in [ARCHITECTURE.md](ARCHITECTURE.md#proposed-source-layout) are a proposal. They are created only when a milestone needs them.

## Related projects

Revival Systems has four independent repositories:

- **Revival OS** (this repository): the device operating system. Primary priority.
- [Revival Server](https://github.com/revival-systems/revival-server): the existing Linux-hosted Goose runtime, Edge, GF1, networking and security work. Optional for Revival OS.
- [Revival Library](https://github.com/revival-systems/revival-library): portable, reusable Goose components.
- [Revival App](https://github.com/revival-systems/revival-app): the iPhone viewing and control client.

The architecture decisions behind this split are recorded in Revival Server issues [#120](https://github.com/revival-systems/revival-server/issues/120), [#121](https://github.com/revival-systems/revival-server/issues/121), [#123](https://github.com/revival-systems/revival-server/issues/123) and [#125](https://github.com/revival-systems/revival-server/issues/125).

A phone running Revival OS must capture, store and serve video to the app on the local network with no server and no internet. Revival Server adds optional remote features later.
