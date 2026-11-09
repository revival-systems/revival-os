# Goose reference preservation plan

Companion to [ADR 0001](decisions/0001-rust-and-arm-assembly.md). Revival OS now implements the kernel in Rust and ARM Assembly, and **keeps the existing Goose work as a studied reference**. This document inventories the Goose-related files, proposes where they move, and sets the rules for the move.

**Status: plan only.** Nothing is moved, renamed or deleted by this document or the pull request that introduces it. The move happens later, in its own reviewed pull request, after the owner and orchestrator approve this plan.

## Principles

1. **Nothing is deleted.** Every Goose source file, test, experiment, research note, script and pin is preserved and kept retrievable, with its Git history and attribution.
2. **Prefer `git mv`** for Goose-only files, so history follows the file. Negative findings and limitations are preserved verbatim, not sanitized.
3. **Do not blindly move whole directories.** `tests/`, `tools/` and the `Makefile` hold both Goose-only and shared/language-agnostic material. Moving a directory wholesale would break working tests and the reusable build plumbing. Each file is classified below.
4. **The Rust kernel build must not depend on Goose.** The reference build stays optional and separate, and is documented so it can still be run.
5. **No pins change here, and Revival Server is not touched.** The shared Goose pin stays equal to Revival Server's until both are changed deliberately.

## Inventory and proposed disposition

Classification: **Goose-only** (move to the reference workspace), **shared/reusable** (stays; the Rust foundation reuses it), **language-agnostic** (stays; not about Goose).

### Research and toolchain notes

| Path | Purpose | Class | Proposed disposition |
| --- | --- | --- | --- |
| `docs/toolchain/goose-freestanding-notes.md` | Goose freestanding feasibility findings | Goose-only | Move under `reference/goose/docs/` |
| `docs/toolchain/goose-runtime-dependency-map.md` | Goose runtime dependency analysis (incl. the data-stack finding) | Goose-only | Move; keep findings verbatim |
| `docs/toolchain/goose-runtime-options.md` | Runtime route options for Goose | Goose-only | Move |
| `docs/toolchain/goose-upstream-questions.md` | Questions for Goose upstream | Goose-only | Move |
| `docs/toolchain/next-runtime-experiment.md` | Proposed next Goose runtime experiment | Goose-only | Move |

### Goose sources and oracles

| Path | Purpose | Class | Proposed disposition |
| --- | --- | --- | --- |
| `tests/goose/probe.goose` | Freestanding Goose probe program | Goose-only | Move under `reference/goose/tests/` |
| `tests/goose/hosted_probe.goose` | Hosted Goose probe | Goose-only | Move |
| `tests/goose/checksum_oracle.py` | Expected-value oracle for the probe | Goose-only | Move |
| `tests/goose/__init__.py` | Package marker | Goose-only | Move with the package |
| `tests/host/probe_host_main.c` | Host driver for the Goose probe | Goose-only | Move |
| `tests/qemu/virt-armv7/probe_main.c` | QEMU entry for the Goose probe | Goose-only | Move |
| `tests/qemu/virt-armv7/alloc_main.c` | Goose-runtime allocator stub test | Goose-only | Move |

### Experiments (currently untracked drafts)

| Path | Purpose | Class | Proposed disposition |
| --- | --- | --- | --- |
| `tests/experiments/arm32-gap-skip/` (8 draft files) | The ARM32 data-stack gap-skip experiment (design, cases, driver, scripts) | Goose-only | **Not touched by this task.** Preserved as-is; to be committed into `reference/goose/experiments/` during the move, by owner decision |

These eight files are present but untracked. They are **left exactly as they are** by this plan. Whether to commit them as history or carry them in as the reference workspace is decided when the move is executed.

### Shared / reusable build and test plumbing (stays in place)

Moving these would break the Rust foundation, which reuses them. They stay where they are; the reference build refers to them.

| Path | Purpose | Class | Note |
| --- | --- | --- | --- |
| `tests/qemu/virt-armv7/start.S` | Minimal ARMv7-A entry stub | Shared | The Rust foundation needs an equivalent entry path; reuse or adapt rather than move |
| `tests/qemu/virt-armv7/link.ld` | Freestanding linker script | Shared | Reusable for the Rust image |
| `tests/qemu/virt-armv7/minirt.c`, `minirt.h` | Minimal freestanding runtime/semihosting for QEMU | Shared | Reusable; some pieces were added for the Goose probe |
| `tests/qemu/run.sh` | QEMU run harness | Shared | Language-agnostic runner |
| `tests/build/check_link.py`, `tests/build/link-negative/*`, `tests/build/test_check_link.py` | Freestanding link/symbol checker and its negative fixtures | Shared | Directly reusable to prove the Rust image pulls in no hosted C library |
| `tools/install-arm-toolchain.sh` | Installs Arm GNU Toolchain (linker, objcopy, nm) | Shared | The Rust bare-metal build uses the Arm GNU linker/utilities |
| `tools/doctor.sh` | Environment check | Shared/mixed | Checks both Goose and Arm tools; split out the Goose checks when the move happens, do not move wholesale |
| `tools/pins.env` | Pinned versions and SHA-256 | Shared/mixed | Holds **both** the Goose pin (reference) and the Arm pin (reusable). Not edited here; partitioned, not moved, at migration time |
| `Makefile` | Build and test entry points | Shared/mixed | Has Goose-probe targets and reusable targets (`lint`, `check-docs`, the link check). Partition the Goose targets behind a clearly labelled reference section; do not move |

### Language-agnostic (stays; not about Goose)

`tests/__init__.py`, `tests/expect.sh`, `tests/docs/check_docs.py`, `tests/docs/test_check_docs.py`, `tests/build/__init__.py`, and everything under `docs/hardware/`, `docs/phase-0/`, `docs/CI-STRATEGY.md`, `docs/TESTING.md` (its Goose-probe descriptions stay accurate as reference). These are unaffected.

## Proposed `reference/goose/` layout

A living reference workspace, not an archive:

```text
reference/goose/
    README.md            index of the reference: what each experiment showed,
                         the open data-stack/arena questions to study, and how
                         to run the reference build; distinguishes reproduced
                         findings, source-only analysis, and untested hypotheses
    docs/                the five toolchain research notes
    tests/               probe.goose, hosted_probe.goose, checksum_oracle.py,
                         the probe host/QEMU drivers, the allocator stub test
    experiments/         the arm32-gap-skip experiment (by owner decision)
    BUILD.md             exact, labelled commands to run the reference build,
                         and any test that can no longer run, with the reason
```

The Rust kernel never includes this tree in its build graph.

## Migration sequence

1. **This pull request — documentation and plan only.** ADR 0001, this plan, and the consistency edits to README, ARCHITECTURE, ROADMAP and docs/DEVELOPMENT. No files moved. Owner and orchestrator review.
2. **Migration pull request (after approval).** Perform the `git mv`s above, split the mixed-purpose `Makefile`/`doctor.sh`/`pins.env` along the Goose/shared line, add `reference/goose/README.md` and `BUILD.md`, and keep the reference build runnable (or record precisely what no longer runs and why). Show that an ordinary Rust build does not touch `reference/goose/`.
3. **First Rust kernel milestone (separate pull request).** Independent of the move; see [ROADMAP.md](../ROADMAP.md) Phase 1.

## Preservation checklist for the migration pull request

- [ ] Every Goose-only file moved with `git mv`; history and attribution intact.
- [ ] No negative finding, limitation or defect note deleted or softened.
- [ ] `reference/goose/README.md` indexes the experiments and the open study questions, labelling reproduced vs source-only vs hypothesis.
- [ ] The reference build is documented and, where feasible, runnable; anything that cannot run is recorded with the reason.
- [ ] The Rust build demonstrably does not depend on `reference/goose/`.
- [ ] Mixed-purpose `Makefile`, `doctor.sh` and `pins.env` partitioned, not moved wholesale; working tests still pass.
- [ ] No pin changed; Revival Server untouched; no device written.
