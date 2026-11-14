# Revival OS architecture

**Status: proposal.** Nothing described here is implemented. Module boundaries are set now so that the first code lands in the right place. Each boundary is revisited when the milestone that needs it starts ([ROADMAP.md](ROADMAP.md)).

## Goals

The owner's headline goals, each with what it means here, how it is measured and where its number is set, in [ADR 0002](docs/decisions/0002-design-goals.md):

- **Very small:** one of the smallest operating systems that does real work.
- **Very fast and efficient:** high performance on old hardware.
- **Secure.**
- **Scalable:** from dozens up to thousands of tasks at once, and able to move to other devices.
- **Maintainable:** a codebase that stays simple to understand and to change.
- **Built from the ground up, with room to invent:** original ideas from the project's own research, when they serve the goals above.
- **The stack first, a heap only when necessary:** bounded arenas, as [ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md#memory-strategy) decides.
- **A real-world system, not a demo:** it ends up doing a real job on real hardware.

The engineering goals that serve them:

- Run on supported hardware with no Linux, Android or hosted C library at run time.
- Keep architecture-independent code separate from CPU-architecture code, SoC code and board code, so that a second device means a new port and not a rewrite.
- Bound every resource: memory, queues, connections, storage, time. Overload must degrade predictably.
- Recover by design: a failed boot, crash or watchdog reset leaves the device recoverable and, where possible, leaves a record of what happened.
- Implement only what the current milestone needs, behind an interface that can grow.

## Layers and dependency rules

```text
            services/          system services (device, camera, recording, pairing, update)
                │
   ┌────────────┼──────────────────────────────┐
 net/        storage/        drivers/ (class interfaces: display, input, block, net, camera)
   └────────────┼──────────────────────────────┘
                │
   kernel/  ── mm/ ── sched/        architecture-independent core
                │
         platform contract           the only way the core reaches hardware
                │
   ┌────────────┼───────────────┐
 arch/arm32   soc/<soc>     board/<board>
 (arch/arm64 later)
                │
              boot/                  entry stub and boot-image packaging, per board
```

| Module | May depend on | Must not depend on |
| --- | --- | --- |
| `kernel/`, `mm/`, `sched/` | the platform contract; Revival Library portable modules | `arch/*`, `soc/*` or `board/*` directly; Linux; libc |
| `drivers/` class interfaces | `kernel/` interfaces | any particular SoC or board |
| `drivers/` implementations | the class interface, `soc/` primitives (clocks, GPIO, interrupts) | other drivers' internals |
| `storage/`, `net/` | `kernel/`, driver class interfaces, Revival Library | a specific driver implementation |
| `services/` | `kernel/`, `storage/`, `net/`, class interfaces, Revival Library | hardware registers |
| `arch/arm32/` | nothing above it | `soc/`, `board/` |
| `soc/<soc>/` | `arch/` primitives | `board/`; anything above the platform contract |
| `board/<board>/` | `soc/`, `arch/` | anything above the platform contract |
| `boot/` | the board's handoff facts | everything else |

Code that needs a fact about one board (a GPIO number, a memory address, a regulator) gets it from `board/`. If such a fact is found in `kernel/`, `drivers/` class code or `services/`, that is a defect.

## Proposed source layout

These directories do not exist yet. Each is created by the first milestone that puts real, tested code in it. Placeholder files are not added.

| Path | Responsibility | First needed |
| --- | --- | --- |
| `boot/` | Entry stub (minimal assembly), boot-image packaging, the handoff contract per board | Phase 2 |
| `arch/arm32/` | ARMv7-A: exception vectors, CPU modes, CP15, MMU (short-descriptor tables), caches, barriers, atomics (`LDREX`/`STREX`), VFP/NEON enable, context switch | Phase 2–3 |
| `arch/arm64/` | AArch64 equivalents, for a later 64-bit target | Phase 9 |
| `soc/qcom-msm8930/` | MSM8930: UART-DM, TLMM (GPIO), QGIC2 setup, KPSS timer and watchdog, SDCC, clock controller, RPM and SMD, TrustZone (SCM) calls, peripheral firmware loading | Phase 2 onward |
| `board/samsung-serranolte/` | GT-I9195: memory map, bootloader framebuffer, key GPIOs, PMIC rails, boot-image parameters | Phase 2 |
| `kernel/` | Init sequence, panic and crash records, resource accounting, events and IPC, the platform contract | Phase 3 |
| `mm/` | Physical frame allocator, address-space interface (implemented by `arch/`), bounded arenas and pools | Phase 3 |
| `sched/` | Tasks, scheduling policy, timers and deadlines (context switch lives in `arch/`) | Phase 3 |
| `drivers/` | Device-class interfaces and their implementations | Phase 4 |
| `storage/` | Block layer, partition table reading, filesystem, wear and power-loss safety | Phase 4 |
| `net/` | Network interfaces, IP stack, transport, local service protocol | Phase 5 |
| `services/` | Device, camera, recording, pairing and authentication, update and recovery services | Phase 6–7 |
| `tools/` | Host tools: image packaging, evidence collection, log decoding | Phase 2 |
| `tests/host/` | Portable code run on the development machine. **Exists:** the probe's host driver. | Phase 1 |
| `tests/qemu/` | QEMU runs of architecture-level code. **Exists:** the toolchain probe harness for `virt` (ARMv7-A). Test fixture, not OS code. | Phase 1 |
| `docs/evidence/` | Redacted device results ([TESTING.md](docs/TESTING.md#recording-evidence)); procedures live in `docs/phase-*` | Phase 0 |

## Contracts to define

Interfaces are written down before the code that uses them, and each one changes only through a reviewed pull request.

1. **Boot handoff contract (per board).** The CPU state the bootloader leaves at entry: load address, entry registers (`r0`–`r2` under the ARM Linux boot convention), CPU mode, MMU and cache state, which cores run, and what the bootloader leaves set up (display, watchdog, clocks). For the GT-I9195 the public sources give a load address and a probable framebuffer, but the entry state is **unmeasured**. Phase 2 measures it ([gt-i9195.md](docs/hardware/gt-i9195.md#boot-image-format-and-handoff)).
2. **Platform contract.** What the core needs from a board, at first only: emit a byte or pixel, read a monotonic time, arm and service an interrupt, reset the device, report the memory map. It grows one function per milestone.
3. **Driver class interfaces.** Display, input, block, network and camera, each with explicit buffer ownership, bounded queues and an error model.
4. **Device protocol (with Revival App).** Discovery, pairing, control and media transport. It is defined jointly with [Revival App](https://github.com/revival-systems/revival-app) at Phase 5, and versioned from its first draft.

## Implementation languages and memory

- **Rust (`#![no_std]`) is the implementation language.** Assembly is limited to what Rust cannot express: the entry stub, exception vectors, CPU-mode and special-register setup, barriers and the context switch. Each assembly file states why it cannot be Rust. This supersedes the project's earlier Goose-based plan ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)).
- **Memory, initially:** the native Rust call stack plus statically reserved, fixed-capacity regions. No general-purpose heap allocator, and no dynamic allocation that is not required. `mm/` appears only when a milestone needs it.
- **Memory, later:** bounded arenas backed by static regions (bump allocation) are added only when a concrete requirement justifies them, with checked size/alignment/offset arithmetic, a capacity check before every advance, explicit lifetimes and controlled reset. The *idea* is borrowed from Goose; its unchecked advance and guard-gap assumptions are not ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md#what-to-learn-from-goose-and-what-not-to-inherit)).
- **Goose is retained as a studied reference, not a dependency.** The Rust kernel build must not depend on the Goose compiler, runtime or generated C. The Goose feasibility work stays available: a first QEMU experiment compiled a small Goose subset freestanding (its generated C needed only four runtime entry points, and the upstream runtime itself was not freestanding), recorded in the [findings](docs/toolchain/goose-freestanding-notes.md) and carried forward under the [preservation plan](docs/goose-reference-preservation-plan.md).
- Linux system calls, `epoll`, `signalfd` and similar facilities used by Revival Server's runtime do not exist here. Server code is reused only after a dependency audit, through [Revival Library](https://github.com/revival-systems/revival-library).

## What stays vendor firmware

On the GT-I9195, Revival OS sits on a fixed vendor boot chain and depends on several vendor firmware images. The public evidence for this is in [docs/hardware/gt-i9195.md](docs/hardware/gt-i9195.md).

| Component | Role | Revival OS stance |
| --- | --- | --- |
| SoC boot ROM (PBL) | First code; verifies the next stage | Immutable. Not touched. |
| Secondary bootloaders, TrustZone, RPM firmware | Signed early boot, secure monitor, shared-resource manager | Never written. Revival OS calls TrustZone and talks to the RPM where hardware needs it. |
| Samsung bootloader (`aboot`) | Loads `boot` or `recovery`; provides Download mode | Never written. It is the device's recovery anchor. |
| Wi-Fi/Bluetooth (WCNSS), modem, video and GPU microcode | Peripheral firmware | Loaded at run time from the device's own partitions when a driver needs it. Not committed for use by Revival OS; the only copy in this repository is inside the rescue firmware package under `firmware/GT-I9195/` ([AGENTS.md](AGENTS.md#hardware-safety-contract), rule 7). |

"Replacing Android" means replacing the contents of `boot`, and later `system` and `userdata`. It does not mean replacing this chain.

## Portability

- **CPU architecture:** `arch/arm32` now; `arch/arm64` for the second target. AArch32 and AArch64 differ in startup, exceptions, page tables and atomics, so they are separate ports that share only the core.
- **SoC and board:** each new device adds a `soc/` package (if the SoC is new) and a `board/` package. Sharing an Arm ISA does not remove driver work. Display, camera, Wi-Fi, storage, clocks, regulators and power are board- or SoC-specific.
- **Beyond phones:** robots, cameras and other devices reuse the core and the class interfaces, and add their own `board/` and drivers. Real-time guarantees, if a device needs them, are a scheduler property introduced deliberately, not assumed.
- The support matrix records each target's verified state: [docs/hardware/support-matrix.md](docs/hardware/support-matrix.md).

## Engineering standards

These apply to every module ([Revival Server #121](https://github.com/revival-systems/revival-server/issues/121)):

- **Bounded resources.** Every queue, buffer, table and connection has a fixed or configured limit, a defined behaviour when full, and a test for that behaviour.
- **Failure isolation and recovery.** A failing driver or service is reported and contained, not silently retried forever. A watchdog covers the whole system.
- **Security by default.** No unauthenticated control interface. No network service before pairing and encryption exist. Least privilege between services once there is more than one.
- **Measured performance.** Latency, throughput, memory, CPU, energy and storage figures are measured on the device and recorded with the commit that produced them. No figure is claimed without a measurement.
- **Clear interfaces.** Each module has a documented interface, an owner and tests at that interface.
- **Reproducibility.** Every image that runs on hardware is built reproducibly from a commit, and its hash is recorded with the test result.

## Non-goals for now

- Supporting more than one device before the GT-I9195 reaches the local camera milestone (Phase 7).
- Cellular modem, telephony, GPU acceleration, Bluetooth and NFC.
- Running Android or Linux applications.
- Promising universal Android-phone support. Each model must be researched and verified on its own.
