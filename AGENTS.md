# Agent operating contract: Revival OS

Coding agents work on this repository under one orchestrated workflow. This file is the rulebook. Development details are in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Roles

- **Owner:** decides product direction, approves hardware writes, installs system packages and controls spending.
- **Orchestrator** (currently ChatGPT): decomposes tasks, reviews pull requests, and is the only one who merges.
- **Implementer** (for example Claude Code on Ubuntu): implements one task at a time on a task branch, tests locally, opens pull requests, and reports evidence. It never merges.

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

## Hardware safety contract

The first device is the owner's Samsung GT-I9195. These rules apply to every agent and every phase:

1. **No write to the device without an approved write plan.** The plan is a GitHub issue naming the phase, the exact partition, the image and its SHA-256, the method, and an emergency rescue procedure, approved by the owner and the orchestrator. Recovery must restore a safe route for further Revival OS testing; restoring Android is not the success criterion.
2. **Never written, under any plan:** the bootloader chain (`sbl1`, `sbl2`, `sbl3`, `aboot`, `rpm`, `tz` and any other boot-firmware partition), `efs`, `persist` and `modem`.
3. **Dedicated experimental phone; no Android retention requirement.** The owner permits eventual removal of Android and personal data. Phase 0 remains read-only. Do not erase Android or any partition merely for cleanup: first prove independent Revival OS execution, verify an emergency rescue path, and obtain a separate approved, partition-specific write plan. Phase 2+ boot/reboot results are for Revival OS, never for the Android lock screen.
4. **No bootloader unlocking, Knox or security-setting changes,** and no exploits or rooting.
5. **Read-only commands only** outside an approved write plan. The Phase 0 checklist lists which commands those are ([docs/phase-0/hardware-verification-checklist.md](docs/phase-0/hardware-verification-checklist.md#rules-for-this-checklist)).
6. **The owner performs physical steps.** An agent prepares the procedure and reads the results.
7. **No vendor firmware, Samsung firmware packages or device identifiers in the repository.**
8. **Stop on anything unexpected:** a wrong model, an unexpected screen, a write prompt, or failing recovery. Report it, and do not retry blindly.
