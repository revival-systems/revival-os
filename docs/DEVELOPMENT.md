# Developing Revival OS

Development, builds and tests happen on the local Ubuntu machine. GitHub holds the code and the pull-request reviews. GitHub-hosted CI is started by hand at phase milestones only ([CI-STRATEGY.md](CI-STRATEGY.md)).

The kernel is written in **Rust (`#![no_std]`) and ARM Assembly** ([ADR 0001](decisions/0001-rust-and-arm-assembly.md)). The earlier Goose work is kept as a studied reference ([preservation plan](goose-reference-preservation-plan.md)); its toolchain and probe are not the active build.

## Development cycle

Revival OS is built by observing it run, not by writing design documents ahead of code. Every increment is the smallest capability that can be seen and tested, and it goes through this cycle:

**Build → Boot → Observe → Test → Reboot → Recover → Measure → Document.**

1. **Build** a runnable image for the increment (host/QEMU first).
2. **Boot** it — in QEMU now; on the Samsung only under an approved write plan ([AGENTS.md](../AGENTS.md#hardware-safety-contract)).
3. **Observe** the actual output (serial line, screen, log), not what it "should" do.
4. **Test** a positive case and at least one negative/failure case.
5. **Reboot** / reset repeatedly to show the result is deterministic.
6. **Recover**: confirm the controlled QEMU reset/halt path; on hardware, the approved recovery procedure and a safe return.
7. **Measure** when meaningful (boot time, latency, memory, allocation bounds), with units and repeats.
8. **Document** the exact commands, versions, image hash, output and pass/fail as the increment's evidence.

Rules that do not bend:

- **One increment at a time.** No building future phases ahead of the one in hand.
- **QEMU evidence is not hardware evidence.** A QEMU pass never counts as a Samsung boot ([TESTING.md](TESTING.md)).
- **A phase closes only on its required evidence** ([ROADMAP.md](../ROADMAP.md)), never because code compiles or a document exists.
- **A failure is a result**: record it with its evidence and re-plan; never work around it silently.

## Workspace

```text
~/Developer/revival-systems/
    revival-os/        this repository
    revival-server/    (separate project; not changed by Revival OS work)
    revival-library/
    revival-app/
```

## One-time setup

The reference machine is Ubuntu 26.04 LTS on x86-64. Other Ubuntu releases are expected to work but are not tested locally.

1. System packages (needs sudo):

   ```sh
   sudo apt install make gcc libc6-dev python3 git qemu-system-arm gdb-multiarch shellcheck cppcheck
   ```

   For the Phase 0 phone checklist only: `sudo apt install adb heimdall-flash android-sdk-platform-tools-common`.

2. Pinned toolchains, installed into your home directory with no sudo:

   ```sh
   make install-toolchain
   ```

   This downloads the Goose compiler and the Arm GNU Toolchain, refuses either one unless its SHA-256 matches [tools/pins.env](../tools/pins.env), and re-verifies existing installs. If Revival Server's installer has already put the same Goose release in `~/.local/share/goose/v2026.3`, it is reused.

3. Check the machine:

   ```sh
   make doctor
   ```

   Every required tool must show `ok`. A missing or wrong tool is shown with its fix, and `doctor` exits 1.

## Pinned versions

| Tool | Version | Source | Installed at |
| --- | --- | --- | --- |
| Goose compiler | v2026.3 (`goose runtime 4d3da949e563`) | github.com/aardappel/goose releases | `~/.local/share/goose/v2026.3/` |
| Arm GNU Toolchain | 15.2.Rel1 (`arm-none-eabi-gcc` 15.2.1) | developer.arm.com | `~/.local/share/revival-os/toolchains/` |
| QEMU | Ubuntu package (10.2.1 on 26.04) | Ubuntu archive | system |
| shellcheck, cppcheck, gdb-multiarch | Ubuntu packages (0.11.0, 2.19.0, 17.1 on 26.04) | Ubuntu archive | system |

Goose and the Arm toolchain are pinned by version and SHA-256. Ubuntu packages follow the Ubuntu release, and `make doctor` records their versions. Changing a pin is a reviewed pull request. The Goose pin must stay equal to Revival Server's unless both are changed deliberately.

Since [ADR 0001](decisions/0001-rust-and-arm-assembly.md), the Goose compiler is a **reference** toolchain, not the active one; it is kept and its pin is unchanged. The Arm GNU Toolchain stays (the Rust bare-metal build reuses its linker and utilities). A Rust bare-metal target and any Rust toolchain pin are added in a **later** reviewed pull request, not here.

## Commands

`make help` lists them all.

| Command | What it does |
| --- | --- |
| `make doctor` | Checks every tool and both pins |
| `make build` | Builds every artifact that exists today: the ARMv7-A toolchain probe images and the allocator test image, with their SHA-256 |
| `make test-build` | Validates the freestanding build (link inputs and references, symbols, ELF attributes, no system calls, hosted code rejected) |
| `make test-unit` | Host unit tests, including sanitizer runs |
| `make test-qemu` | Runs the probe and allocator test images in QEMU, including the failure cases |
| `make test-repro` | Two clean builds must be byte-identical |
| `make test` | All four test targets above |
| `make lint` | shellcheck, cppcheck, Python syntax |
| `make check-docs` | Documentation links, anchors and the roadmap template |
| `make check` | Everything: run this before every push |
| `make qemu-run` | Runs the checksum probe in QEMU interactively (Ctrl-A, then X, quits) |
| `make qemu-debug` | Starts QEMU halted with a GDB server; connect with `gdb-multiarch build/qemu-virt-armv7/probe-0.elf -ex 'target remote :1234'` |
| `make clean` | Removes `build/`. Sources are never touched. |

Build output goes to `build/` only. The Goose compiler's cache is redirected to `build/goose-home`, so `~/.goose` is not used.

What each test checks, and what is not tested yet, is in [TESTING.md](TESTING.md).

## Workflow

```text
write Rust (and minimal ARM assembly)  →  make build  →  make test  →  fix
        →  make check  →  review the diff  →  commit  →  push  →  pull request
        →  orchestrator review  →  (at phase milestones) manual CI run  →  merge by the orchestrator
```

- **Branches:** `agent/<machine>/<short-task>`, for example `agent/ubuntu/local-dev-environment`. Never commit to `main` directly.
- **Commits:** one logical change each, with a message that says what changed and why. Unrelated changes go in separate commits and pull requests.
- **Before pushing:** `make check` must pass. If a check cannot pass for a reason outside the change, say so in the pull request. Never skip it silently.
- **Pull requests:** open as drafts until ready. The description lists what changed, the commands run and their results, and anything not verified.
- **Review:** the orchestrator (currently ChatGPT) reviews and merges. Authors never merge their own pull requests.

## Review checklist

- [ ] `make check` passes locally, and the output is quoted in the pull request.
- [ ] New behaviour has a test, including at least one failure case.
- [ ] No test was weakened, skipped or deleted to make a change pass.
- [ ] Pins changed only on purpose, with the reason recorded.
- [ ] Nothing in the change writes to a device. If it does, it follows an approved write plan ([AGENTS.md](../AGENTS.md#hardware-safety-contract)).
- [ ] Documentation matches the behaviour. Claims are labelled implemented or proposed.
- [ ] No vendor firmware, device identifiers or secrets are committed.

## Troubleshooting

- **`sudo` asks for a password in an agent session.** Agents cannot type it. Run the `apt` command yourself.
- **`make doctor` reports `WRONG goose`.** A different Goose build is installed at the pinned path. Move it aside and run `make install-toolchain`.
- **A QEMU test reports "no exit within 20s".** The program hung, or its semihosting exit failed. The full console output is in `build/logs/qemu-<case>.log`.
