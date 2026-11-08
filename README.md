# Revival OS

A lightweight, independent operating system written primarily in the [Goose programming language](https://github.com/aardappel/goose), intended to run directly on repurposed phone hardware and, later, on cameras, robots and other embedded devices.

**Status: Phase 0 — research and hardware verification. No operating-system code exists yet.** Nothing in this repository boots, and no hardware milestone has been passed. This repository currently holds the architecture, the milestone plan and the first target's research and test procedure.

## First target

**Samsung Galaxy S4 Mini LTE, GT-I9195** (codename `serranolte` / `serranoltexx`): Qualcomm MSM8930AB (Snapdragon 400), two Krait cores, 32-bit ARMv7-A, 1.5 GB RAM, removable battery.

These facts come from public sources and **have not yet been confirmed on the owner's physical device**. See [docs/hardware/gt-i9195.md](docs/hardware/gt-i9195.md) for the research and its sources, and the [Phase 0 hardware verification checklist](docs/phase-0/hardware-verification-checklist.md) for the confirmation procedure.

## What "replacing Android" means here

On this phone, early boot is fixed vendor firmware: the SoC boot ROM, Qualcomm's signed secondary bootloaders, TrustZone, the RPM firmware and Samsung's bootloader. Those stay. Revival OS replaces what that chain loads from the `boot` (or `recovery`) partition: today, the Linux kernel and the Android userspace above it. The finished OS must not need Linux or Android to run. Some peripherals (Wi-Fi, modem, video, GPU) also run vendor firmware, which Revival OS would load rather than replace. Details: [ARCHITECTURE.md](ARCHITECTURE.md#what-stays-vendor-firmware).

There is no PC BIOS or UEFI on this device.

## How the work proceeds

Every milestone adds the smallest capability that can be observed and tested on the real phone, with a recorded recovery path. Emulator results never count as hardware results. Android is not erased until independent boot has been proved and the owner decides to. See [ROADMAP.md](ROADMAP.md).

| Phase | Capability | State |
| --- | --- | --- |
| 0 | Identify the hardware, boot chain and recovery paths; stock boot, reboot and recovery | Research documented; **physical checks not started** |
| 1 | Freestanding Goose toolchain for ARMv7-A | Feasibility shown **in QEMU only** ([findings](docs/toolchain/goose-freestanding-notes.md)); phase not passed |
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

The only buildable artifact today is the **Goose toolchain probe**: a tiny Goose program cross-compiled for ARMv7-A and run in QEMU with no Linux and no C library. It is a test of the toolchain, not part of the operating system.

## Repository map

| Path | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Proposed module boundaries, dependency rules and vendor-firmware boundaries |
| [ROADMAP.md](ROADMAP.md) | Phases 0–9, each with a capability, tests, pass/fail criteria and recovery evidence |
| [AGENTS.md](AGENTS.md) | Rules for coding agents, including the hardware safety contract |
| [Makefile](Makefile) | The local build and test entry points (`make help`) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, pinned versions, commands, workflow and review checklist |
| [docs/TESTING.md](docs/TESTING.md) | Test tiers, what each test checks, what is not tested yet, evidence rules |
| [docs/CI-STRATEGY.md](docs/CI-STRATEGY.md) | Local-first CI: the manual-only workflow and its cost controls |
| [docs/hardware/](docs/hardware/gt-i9195.md) | GT-I9195 research and the [support matrix](docs/hardware/support-matrix.md) |
| [docs/phase-0/](docs/phase-0/hardware-verification-checklist.md) | The Phase 0 hardware verification checklist |
| [docs/toolchain/](docs/toolchain/goose-freestanding-notes.md) | Goose freestanding feasibility findings, and the runtime research: [dependency map](docs/toolchain/goose-runtime-dependency-map.md), [runtime routes](docs/toolchain/goose-runtime-options.md), [upstream questions](docs/toolchain/goose-upstream-questions.md), [next experiment](docs/toolchain/next-runtime-experiment.md) |
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
