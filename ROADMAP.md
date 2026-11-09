# Revival OS roadmap

Each phase adds the smallest capability that can be observed and tested, on the real Samsung where hardware is involved. A phase is complete only when its pass criteria are met **and** recorded as evidence ([docs/TESTING.md](docs/TESTING.md#recording-evidence)), and the orchestrator has reviewed that evidence.

The kernel is written in Rust and ARM Assembly ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)); the earlier Goose work is kept as a studied reference. Every increment follows the development cycle — **Build → Boot → Observe → Test → Reboot → Recover → Measure → Document** ([docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#development-cycle)).

Sources: Revival Server issues [#120](https://github.com/revival-systems/revival-server/issues/120) (phone-first decision and test strategy) and [#121](https://github.com/revival-systems/revival-server/issues/121) (milestone ladder and engineering requirements).

## Rules for every phase

1. **No hardware milestone is complete on a design or an emulator result.** Emulators prove code generation and architecture-level logic only.
2. **Every phase that runs on the device records boot, reboot and recovery evidence**: the image hash, the device state before and after, the number of trials, and the recovery action taken.
3. **No write to the device without an approved write plan.** The plan is a GitHub issue that names the exact partition, image, hash and recovery procedure, approved by the owner and the orchestrator. Bootloader-chain partitions are never written ([AGENTS.md](AGENTS.md#hardware-safety-contract)).
4. **Android is not erased** until independent boot has been proved and the owner decides to. No phase below requires erasing it.
5. **Later-phase criteria are provisional.** They are refined in a reviewed pull request before the phase starts, using what earlier phases measured.
6. **A failed phase is a result.** It is recorded with its evidence, and the next step is re-planned. It is never worked around silently.

## Phase summary

| Phase | Capability | Runs on | State |
| --- | --- | --- | --- |
| 0 | Hardware identity, stock boot/reboot, recovery paths | Device (read-only) | Research done; physical checks not started |
| 1 | Rust + ARM Assembly freestanding foundation (ARMv7-A) | Host + emulator | Not started; Goose feasibility kept as reference |
| 2 | First bare-metal boot with observable output | Device (first write) | Not started |
| 3 | Exceptions, MMU, memory, interrupts, timer, watchdog | Device + emulator | Not started |
| 4 | Buttons, display console, storage reads | Device | Not started |
| 5 | Local networking with another device | Device | Not started |
| 6 | Camera frames and local recording | Device | Not started |
| 7 | Standalone camera served to the iPhone app | Device + iPhone | Not started |
| 8 | Internet access and optional Revival Server | Device + network | Not started |
| 9 | Hardening, updates and a second hardware target | Device(s) | Not started |

---

### Phase 0 — Samsung identification, boot, reboot and recovery

**Entry gate:** None. **No write to the device at any point in this phase.**

**Capability:** A verified record of the exact device, its firmware versions, its partition names, and its boot, recovery and Download-mode paths, made using only stock software and read-only commands. Plus a verified restore source (the matching stock firmware) for later phases.

**Observable test:** The [Phase 0 hardware verification checklist](docs/phase-0/hardware-verification-checklist.md), sections A to H.

**Pass criteria:** All of:

- The label under the battery and the software both report GT-I9195. `/proc/cpuinfo` reports an ARMv7 processor with Qualcomm's implementer code (`0x51`).
- The bootloader version, build, baseband and Android version are recorded.
- Stock cold boot succeeds 3 of 3 times, and `adb reboot` 3 of 3.
- Stock recovery is entered and left without selecting any action, 3 of 3.
- Download mode is entered and cancelled from its warning screen 3 of 3, and entered and left by removing the battery 3 of 3.
- Heimdall detects the phone in Download mode. If the PIT read is performed, it lists `BOOT` and `RECOVERY` partitions.
- The Download-mode status lines (binary and system status, Knox warranty bit, Qualcomm secure boot, reactivation lock, if shown) are photographed and transcribed.
- The baseline is recorded: rear and front photo and video, Wi-Fi joined and pinged from Ubuntu, buttons, display, battery health.
- A stock firmware package matching the installed build is identified and its checksum verified, or its absence is recorded as a blocker.
- The owner confirms that no write was performed.

**Fail criteria (stop and re-plan):** The model is not GT-I9195 (for example GT-I9195I, which has a different SoC). Download mode cannot be reached. A reactivation lock is on and its account is unknown. The battery is swollen or the device is unstable. Any unexpected write happens. A missing stock firmware package does not fail Phase 0, but it **blocks Phase 2**.

**Negative and failure tests:**

- With the phone booted into Android, `heimdall detect` finds no device.
- Before USB debugging is authorized on the phone, `adb devices` shows `unauthorized`.
- The Download-mode warning screen's cancel button restarts the phone normally.
- Removing the battery while Download mode is idle (no transfer) leaves the next normal boot unaffected.
- Leaving stock recovery without selecting anything leaves the user data intact.

**Physical verification:** Required for every step. All of it is on the owner's device.

**Boot, reboot and recovery evidence:** The time from power-on to the lock screen for each cold boot, the reboot count, and photographs of the recovery and Download-mode screens. A final normal boot shows the same build and the same user data as before.

**Next safe milestone:** Phase 1 (host and emulator only, no device writes). Phase 0's results feed the separate Phase 2 write-plan decision.

---

### Phase 1 — Rust + ARM Assembly freestanding foundation

**Entry gate:** Phase 0 has confirmed the instruction set (ARMv7-A, VFP/NEON), and the Rust bare-metal target and any toolchain pin have been chosen in review ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)). Adding the Rust target is a separate reviewed pull request; the Goose and Arm GNU Toolchain pins are unchanged.

**Supersedes:** Phase 1 was formerly "freestanding Goose toolchain." The implementation language is now Rust and ARM Assembly ([ADR 0001](docs/decisions/0001-rust-and-arm-assembly.md)). The Goose freestanding feasibility result (2026-11-08, QEMU only: `make test-qemu` ran a Goose-generated function on emulated ARMv7-A with no C library) is **kept as reference**, not as a passed phase ([findings](docs/toolchain/goose-freestanding-notes.md), [preservation plan](docs/goose-reference-preservation-plan.md)).

**Capability:** A reproducible build that turns a tiny `#![no_std]` Rust program, linked with a minimal ARM Assembly entry stub, into an ARMv7-A binary with no hosted C library and no operating-system calls. It includes the entry stub, a linker script, initial stack and static-memory setup, and a panic path, plus a written list of what the freestanding build supports and does not.

**Observable test:** Under `qemu-system-arm` (an ARMv7-A machine such as `virt` with `-cpu cortex-a15`), the image boots through the Assembly entry into Rust, prints a fixed heartbeat line, prints a value computed in Rust (for example a checksum of a static table), then halts or exits through a defined path.

**Pass criteria:**

- Two clean builds of the same commit produce byte-identical binaries, and the SHA-256 is recorded.
- Undefined symbols (`arm-none-eabi-nm -u`) are only those of the documented support layer, and none is a C-library or `std` symbol.
- No supervisor call (`svc`) appears in the disassembly unless documented.
- The ELF attributes (`readelf -A`) report ARMv7-A.
- The heartbeat line comes from Rust, after Assembly has established the stack, and appears in 20 of 20 runs.

**Fail criteria:** The freestanding Rust build needs hosted facilities (threads, `mmap`, signals, stdio) that a small documented support layer cannot replace, or success would require changing a pinned toolchain without approval. The blocker is recorded and the phase stops for a decision.

**Negative and failure tests:**

- A test program that pulls in a C-library or `std` symbol fails the link/symbol check that detects it.
- A Rust panic reaches the panic handler, which reports its location, rather than continuing into undefined behaviour.
- A corrupted binary is rejected by hash comparison.
- A deliberate stack-limit overrun faults observably, not silently corrupting memory.

**Physical verification:** None. This phase is host and emulator only, and its results are **not** hardware results.

**Boot, reboot and recovery evidence:** Not applicable to the device. Emulator start, halt and reset behaviour is recorded across repeated runs.

**Next safe milestone:** Phase 2, only after Phase 0 has passed without a recovery blocker and a write plan has been approved.

---

### Phase 2 — First bare-metal boot

**Entry gate:** All of:

- Phase 0 has passed, with stock `boot` and `recovery` images for the installed build verified and Download mode shown to be reliable.
- Phase 1 has passed.
- A write plan issue names the method, partition, image hash and recovery steps.
- The owner has explicitly accepted that flashing a non-Samsung image is reported to trip the irreversible Knox warranty bit ([gt-i9195.md](docs/hardware/gt-i9195.md#bootloader-lock-and-knox)).
- The orchestrator has approved the plan.

**Capability:** The smallest boot image the stock bootloader accepts, whose payload (entry stub plus Rust-originated code) produces one observable effect and then halts or resets deterministically.

**Method options (chosen in the write-plan review, not here):**

- **A. Payload in `recovery` only.** Android's `boot` partition stays untouched. The payload runs when the phone is started with the recovery key combination, and a normal power-on still boots Android. Each iteration costs one Download-mode flash of `recovery`.
- **B. lk2nd as an intermediate bootloader.** [lk2nd](https://github.com/msm8916-mainline/lk2nd) lists the GT-I9195. It is installed once (to `boot` or `recovery`), then offers fastboot. With fastboot, `fastboot boot` runs each test payload from RAM with no further flash. This option adds a third-party component to the chain and needs its own review.

**Observable test:** The payload fills the framebuffer that the stock bootloader appears to leave running (`0x88300000`, 540×960, 24-bit RGB, per a [community mainline device tree](https://github.com/msm8227-mainline/linux/blob/msm8227-6.19/arch/arm/boot/dts/qcom/qcom-msm8930-samsung-serranolte.dts); **unconfirmed on this device**) with a fixed pattern. It keeps it for 10 seconds, then resets or halts. If a 1.8 V UART cable through the micro-USB JIG mode is available and verified, a heartbeat line on the UART is an alternative or additional test. The entry register values are encoded into the pattern so that the handoff state can be read off a photograph.

**Pass criteria:**

- The pattern appears in 5 of 5 cold boots of the same image, whose hash is recorded.
- After every trial, a normal power-on boots Android unchanged, 5 of 5.
- Download mode stays reachable throughout.
- The entry state is recorded: `r0`–`r2`, the CPU mode, and whether the MMU and caches are on.
- The watchdog's behaviour while the payload runs is recorded (the device resets on its own or not, and after how long).

**Fail criteria:** No observable output after the image is accepted, an unrecoverable state, or any change to a partition outside the write plan. A failure is recorded together with its recovery.

**Negative and failure tests:**

- A deliberately invalid image (bad header) shows how the bootloader rejects images, and recovery is proven afterwards.
- A payload that hangs forever is recovered by removing the battery.
- A payload that triggers an exception before any handler exists shows its observable behaviour.
- Each test is followed by a full Download-mode restore of the stock image to the written partition, with a boot check.

**Physical verification:** Required. This milestone is defined on the hardware.

**Boot, reboot and recovery evidence:** A photograph or video of each trial with its timestamp and image hash, the reboot counts, every recovery action, and the state of the partitions after the phase.

**Next safe milestone:** Phase 3, with the measured handoff state written into the boot handoff contract ([ARCHITECTURE.md](ARCHITECTURE.md#contracts-to-define)).

---

### Phase 3 — Kernel foundations

**Entry gate:** Phase 2 has passed. A reliable output channel (framebuffer or UART) and a repeatable flash or RAM-boot loop exist.

**Capability:** One sub-milestone at a time, each tested on the device:

- **3a.** Exception vectors: a deliberate undefined instruction and a data abort are reported, then the device resets.
- **3b.** MMU with an identity map, then caches enabled.
- **3c.** A physical-frame allocator built from the memory map that the bootloader passes, which honours reserved regions (shared memory at `0x80000000`, the WCNSS region at `0x8f000000`, the framebuffer).
- **3d.** A periodic timer interrupt through the QGIC2 interrupt controller.
- **3e.** Watchdog petting, plus a crash record that survives a watchdog reset.
- **3f.** Bounded pools and arenas with exhaustion handling.

**Observable test:** A test screen or UART log reports each sub-milestone's checks with expected and measured values. Timer accuracy is compared against host time over at least 10 minutes.

**Pass criteria:** Each sub-milestone passes in 10 of 10 boots. Timer drift stays within a stated bound, set from Phase 2 measurements before the phase starts. Allocator tests show no leak over 10,000 allocate/free cycles, and exhaustion is reported. A crash record is recovered after a forced watchdog reset in 5 of 5 trials.

**Fail criteria:** Any silent memory corruption, any write to a reserved region, unrecoverable lockups, or a sub-milestone that needs undocumented bootloader state.

**Negative and failure tests:** Fault injection: undefined instruction, data and prefetch aborts, stack overflow, allocator exhaustion, an interrupt storm, and a deliberately starved watchdog.

**Physical verification:** Required for every sub-milestone. Emulator runs may precede the device test but never replace it.

**Boot, reboot and recovery evidence:** The boot count per sub-milestone, the reset causes observed, and confirmation that Android and Download mode are unaffected.

**Next safe milestone:** Phase 4.

---

### Phase 4 — Basic hardware: buttons, display, storage

**Entry gate:** Phase 3 has passed. Storage work starts **read-only**. Writes are allowed only to a test microSD card or an explicitly approved scratch area, never to `efs`, `persist`, `modem` or the bootloader chain.

**Capability:**

- **4a.** Volume Up, Volume Down and Home are read through GPIO. The public sources give them as GPIO 50, 81 and 35, which is to be confirmed.
- **4b.** A text console on the display.
- **4c.** Read-only eMMC access: the partition table and a partition's contents.
- **4d.** microSD read, then write.

**Observable test:** Button presses show on screen. The eMMC partition table is compared with Phase 0's PIT listing. File contents read from microSD are hashed on the device and compared with `sha256sum` of the same file on Ubuntu.

**Pass criteria:** 100 of 100 presses of each button are registered with no phantom events. The partition table matches Phase 0. The eMMC `boot` partition read back hashes equal to the verified stock `boot.img`, padded to the partition size as documented. microSD read and write hashes match in 100 of 100 files.

**Fail criteria:** Any eMMC write outside the plan, mismatched reads, or button events lost or invented.

**Negative and failure tests:** The card is removed mid-read, an unreadable block is simulated, power is lost during a microSD write and the filesystem is checked on Ubuntu afterwards, and buttons are held down or bounced.

**Physical verification:** Required.

**Boot, reboot and recovery evidence:** Android still boots from the untouched `boot` partition (method A) or is restored (method B). Download mode is reachable. The partition hashes before and after the phase are recorded.

**Next safe milestone:** Phase 5.

---

### Phase 5 — Networking

**Entry gate:** Phase 4 has passed. The networking route (Wi-Fi through the WCNSS core, or USB networking) is chosen in review from Phase 0–4 evidence. The device protocol is drafted jointly with Revival App. No listening service is exposed before authentication exists.

**Capability:** Join the owner's WPA2 LAN, obtain an address, answer ping, and complete an authenticated message exchange with the Ubuntu machine, then with an iPhone.

**Observable test:** Ping from Ubuntu, and a test client that pairs, sends a request and verifies the authenticated response.

**Pass criteria:** 1,000 pings with less than 1 % loss on the LAN. An authenticated exchange succeeds 100 of 100 times. The device reconnects after an access-point restart without a reboot. Memory and connection counts stay bounded under a 100-client connection flood.

**Fail criteria:** An unauthenticated peer is accepted, there is unbounded resource growth, or the radio is operated outside the device's regulatory configuration.

**Negative and failure tests:** A wrong Wi-Fi password, the access point disappearing, malformed and oversized packets, an unauthenticated or replayed request, and the connection limit being reached.

**Physical verification:** Required, on the owner's LAN. No cloud is involved.

**Boot, reboot and recovery evidence:** Network start after a cold boot and after a watchdog reset, and recovery of the device afterwards.

**Next safe milestone:** Phase 6.

---

### Phase 6 — Camera

**Entry gate:** Phase 5 has passed. The camera route is reviewed: the rear sensor is the Sony IMX175 or the Samsung S5K3H5XA (Phase 0 identifies which), and Qualcomm's image processing is partly proprietary. **This is the highest-risk phase.** A blocker here is recorded and re-planned, not worked around.

**Capability:** One sub-milestone at a time:

- **6a.** Read the sensor's ID register over its control bus.
- **6b.** Capture one raw frame.
- **6c.** Save it to storage and retrieve it on Ubuntu.
- **6d.** Stream at a fixed resolution and frame rate.
- **6e.** Record locally with encoding (software first; the hardware encoder needs its own firmware).

**Observable test:** The sensor ID is shown on screen. A retrieved frame opens on Ubuntu and shows the scene. A recorded clip plays on Ubuntu.

**Pass criteria:** The sensor ID matches in 5 of 5 boots. A raw frame is recognizable. Frame rate, CPU, memory and temperature are measured and recorded. A 10-minute recording has no more dropped frames than a threshold agreed before the phase.

**Fail criteria:** Sensor or regulator programming outside documented values, thermal limits exceeded, or recording corrupting storage.

**Negative and failure tests:** The sensor is left unpowered (an error, not a hang), the storage fills (recording stops cleanly), the device is thermally stressed, and the camera is opened and closed 100 times.

**Physical verification:** Required.

**Boot, reboot and recovery evidence:** Camera start after a cold boot and after a reset. A recording interrupted by power loss is checked for recoverable content.

**Next safe milestone:** Phase 7.

---

### Phase 7 — Standalone Revival OS camera

**Entry gate:** Phase 6 has passed. A Revival App build exists that implements the reviewed device protocol (built on macOS).

**Capability:** The phone boots by itself, records, and serves live and recorded video to the iPhone app over the local network, with no internet and no server.

**Observable test:** An offline LAN demonstration: the router has no upstream connection, the iPhone pairs, views live video, and browses and plays recordings.

**Pass criteria:**

- Cold boot to live view within a time set from Phase 6 measurements.
- A one-hour continuous live view.
- 20 of 20 app disconnects and reconnects.
- Phone reboots during a session recover without user action beyond reopening the app.
- Only paired devices are accepted.

**Fail criteria:** Any dependency on internet or a server, unpaired access, or recording loss beyond the agreed bound.

**Negative and failure tests:** An unpaired client, revoked pairing, network loss, a full storage, power loss during recording, and the app killed during playback.

**Physical verification:** Required: the Samsung and an iPhone.

**Boot, reboot and recovery evidence:** Unattended start after power restoration, and update and rollback of the OS image (manual at this stage).

**Next safe milestone:** Phase 8. Whether to remove Android from the phone becomes an owner decision from this point. It is not required.

---

### Phase 8 — Internet and optional Revival Server

**Entry gate:** Phase 7 has passed. A threat model for remote access has been reviewed. Revival Server's security issue [#96](https://github.com/revival-systems/revival-server/issues/96) is resolved before any Edge/GF1 production exposure.

**Capability:** Secure remote viewing from another network (which, depending on NAT, may need a relay, VPN or reachable endpoint), and opt-in backup to Revival Server.

**Observable test:** The iPhone on a cellular network views the phone's live video. A backup appears on the server and its checksum is verified.

**Pass criteria:** Remote viewing works where connectivity permits. Losing internet or the server never interrupts local recording or LAN viewing (tested by disconnecting both during recording). Backups match their checksums.

**Fail criteria:** Plaintext or unauthenticated remote access, or any local feature depending on the server.

**Negative and failure tests:** A wrong server certificate, the server down, credentials revoked, a slow or lossy link, and a backup interrupted mid-transfer.

**Physical verification:** Required: the device on a real network, with a client on a different network.

**Boot, reboot and recovery evidence:** The device reconnects to the server after reboots and outages without manual action.

**Next safe milestone:** Phase 9.

---

### Phase 9 — Hardening and portability

**Entry gate:** Phase 8 has passed.

**Capability:** Signed updates with rollback, a reviewed threat model, soak and power measurements, and a second hardware target (an accessible, unlockable AArch64 device chosen by evidence) through its own Phase 0–3.

**Observable test:** Update and rollback cycles, a multi-day soak run, power measurements, and the second device's Phase 2 boot evidence.

**Pass criteria:** 20 of 20 update and rollback cycles, including a power cut mid-update. A 72-hour soak with no unbounded resource growth. Measured idle and recording power. The second target passes its own Phase 2 and Phase 3.

**Fail criteria:** An update that can leave the device unbootable with no automatic rollback, or a second port that needs changes to architecture-independent code beyond its interfaces.

**Negative and failure tests:** Tampered and downgraded update images rejected, power loss at every update step, storage exhaustion, and clock changes.

**Physical verification:** Required on every supported device.

**Boot, reboot and recovery evidence:** Recovery from every injected update failure.

**Next safe milestone:** Further devices, each with its own Phase 0 and support-matrix entry.
