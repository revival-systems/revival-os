# Agent operating contract: Revival OS

Coding agents work on this repository under one orchestrated workflow. This file is the rulebook. Development details are in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Roles

- **Owner:** decides product direction, approves hardware writes, installs system packages and controls spending.
- **Reviewer** (a separate Claude session the owner runs): writes each task, reviews each report and pull request independently, and makes the decisions the orchestrator used to make.
- **Implementer** (Claude Code on Ubuntu): implements one task at a time on a task branch, tests locally, pushes, opens pull requests, and reports evidence.
- **Merge rule:** the implementer merges a pull request only when the reviewer's task says so and names the exact head commit the reviewer verified. Never otherwise. Always a merge commit (no squash, no rebase), pinned to that head: `gh pr merge N --merge --match-head-commit <sha>`.

The owner made this change on 2026-11-13. Until then ChatGPT was the orchestrator and the only merger; it is no longer part of the project. Dated records that name ChatGPT or the orchestrator stay as written. Where an older document says "orchestrator", the reviewer now holds that role for tasks, reviews and approvals; merging follows only the merge rule above.

## Scope

- Work only in this repository unless a task names another one. Revival Server, Revival Library and Revival App are separate projects with their own rules.
- Build only what the current milestone needs ([ROADMAP.md](ROADMAP.md)). No speculative kernel code, drivers or placeholder files.
- Stop and report a blocker, rather than inventing a workaround:

  ```text
  BLOCKED
  Dependency: <issue, pull request, tool or decision>
  Reason: <what must be known or done>
  ```

## Git

- Branch: `agent/<machine>/<short-task>`. No direct commits to `main`. No history rewriting of shared branches.
- One logical change per commit. Unrelated changes go in separate pull requests.
- `make check` passes before every push, and its output goes in the pull request.
- Pushes, pull requests, workflow runs and settings changes need the owner's approval in the task, or explicit approval at the time.

## Testing

- Never report a test as passing that was not run. Never weaken, skip or delete a test to make a change pass.
- Every new capability has a test that can fail, and at least one failure case.
- Emulator results are not hardware results ([docs/TESTING.md](docs/TESTING.md)).

## CI and cost rules

- Hosted CI runs only by hand (`workflow_dispatch`), at phase milestones ([docs/CI-STRATEGY.md](docs/CI-STRATEGY.md)). Agents do not start it unless the task says so.
- Adding or changing a workflow trigger, the runner type, caches, artifacts or schedules needs approval.
- No self-hosted runner.
- **Spend in bulk (owner, 2026-11-14).** Whatever costs money on GitHub is done rarely and
  in bulk, never repeatedly. Local `make check` is free and is the default test. A hosted
  run is proposed as one run that covers everything pending, and needs the owner's approval
  each time.
- **Large files.** Do not download the Git LFS firmware again without a reason: fetch,
  clone and check out with `GIT_LFS_SKIP_SMUDGE=1` and use the private local copy. Adding
  large files to Git LFS, artifacts or caches needs approval.
- Merging, pushing and opening pull requests start no workflow here and cost nothing.
  Keep it that way.

## Hardware safety contract

The first device is the owner's Samsung GT-I9195. These rules apply to every agent and every phase:

1. **No write to the device without an approved write plan.** The plan is a GitHub issue naming the phase, the exact partition, the image and its SHA-256, the method, and an emergency rescue procedure, approved by the owner and the reviewer. Recovery must restore a safe route for further Revival OS testing; restoring Android is not the success criterion.
2. **Never written, under any plan:** the bootloader chain (`sbl1`, `sbl2`, `sbl3`, `aboot`, `rpm`, `tz` and any other boot-firmware partition), `efs`, `persist` and `modem`.
3. **Dedicated experimental phone; no Android retention requirement.** The owner permits eventual removal of Android and personal data. Phase 0 remains read-only. Do not erase Android or any partition merely for cleanup: first prove independent Revival OS execution, verify an emergency rescue path, and obtain a separate approved, partition-specific write plan. Phase 2+ boot/reboot results are for Revival OS, never for the Android lock screen.
4. **No bootloader unlocking, Knox configuration or security-setting changes,** and no exploits or rooting. **One exception,** on the owner's GT-I9195 only: the automatic, irreversible change of the Knox warranty bit that a `RECOVERY` image write, or the attempted boot of that image, may cause. It applies only under a write plan approved by the owner and the reviewer under rule 1, which names the exact images and quotes the owner's explicit acceptance of this consequence (given on 2026-11-14). It permits no direct write to a fuse or to Knox, no disabling of a protection, no write to any other partition, and nothing else these rules forbid.
5. **Read-only commands only** outside an approved write plan. The Phase 0 checklist lists which commands those are ([docs/phase-0/hardware-verification-checklist.md](docs/phase-0/hardware-verification-checklist.md#rules-for-this-checklist)).
6. **The owner performs physical steps.** An agent prepares the procedure and reads the results.
7. **No vendor firmware, Samsung firmware packages or device identifiers in the repository,** with two exceptions the owner made on 2026-11-13:
   - the GT-I9195 rescue firmware for the installed build, in Git LFS under [`firmware/GT-I9195/`](firmware/GT-I9195/README.md);
   - redacted photographs of the device and its screens under `docs/evidence/`, with every identifier blacked out and the image metadata stripped ([TESTING.md](docs/TESTING.md#recording-evidence)).

   Everything else stays forbidden: no other vendor files, and never an IMEI, serial number, MAC address, account name, personal photo or unredacted photograph. The repository must never be public while its history or Git LFS storage holds vendor firmware. It is internal on purpose, so that the owner's other agents and machines can read it; the owner decided this on 2026-11-14.
8. **Stop on anything unexpected:** a wrong model, an unexpected screen, a write prompt, or failing recovery. Report it, and do not retry blindly.
