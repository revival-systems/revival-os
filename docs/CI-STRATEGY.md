# CI strategy: local first, hosted CI at milestones

**Decision (owner, 2026-11-08):** develop and test on the local Ubuntu machine. Run GitHub-hosted CI only by hand, at each phase milestone, for independent verification. Do not configure a self-hosted runner at this stage.

## What exists

Inspected on 2026-11-08:

| Item | State |
| --- | --- |
| Workflows in `revival-systems/revival-os` before this change | None. The repository held only its empty initial commit. |
| Workflow runs | 0 |
| Actions setting for the repository | Enabled; all actions allowed (repository default) |
| Organization `.github` repository | Profile README and images only; no workflow templates |
| Organization rulesets and required workflows | **Not inspected.** The GitHub token lacks the `admin:org` scope. |
| Actions spending limit | **Not inspected.** The billing API needs `admin:org`. |

## The one workflow

[`.github/workflows/verify.yml`](../.github/workflows/verify.yml):

| Property | Value | Why |
| --- | --- | --- |
| Trigger | `workflow_dispatch` only | Pushes and pull requests never start it, so it costs nothing until someone chooses to run it |
| Runner | `ubuntu-24.04`, standard GitHub-hosted Linux | Cheapest hosted runner class. A pinned image, so the environment does not change silently. |
| Time limit | 30 minutes | Bounds the cost of a hung job |
| Concurrency | One run per branch; a new run cancels the old one | No duplicate runs |
| Permissions | `contents: read`, and the checkout keeps no credentials | Least privilege |
| Third-party code | `actions/checkout` pinned to a full commit SHA (v7.0.1) | A moved tag cannot change what runs |
| Steps | Install packages, `make install-toolchain`, `make doctor`, `make check` | The same entry points as local development |
| Caches, artifacts | None | No storage cost. Each run downloads the pinned toolchains (about 170 MB) and verifies their SHA-256. |

**Historical results verified on 2026-11-13:** the [2026-11-09 run](https://github.com/revival-systems/revival-os/actions/runs/42661958874) failed at `qemu-checksum`. After the default-NIC fix, the [2026-11-10 run](https://github.com/revival-systems/revival-os/actions/runs/42757111224) on `3f1130a` passed every step, including `make check` (36 PASS / 0 FAIL). The hosted runner used Ubuntu 24.04.5 and QEMU 8.2.2, distinct from the local Ubuntu/QEMU 10.2.1 environment. These historical results support the [Phase 1 gate review](evidence/phase-1/2026-11-13-gate-review.md); no new run was started to write that review.

## When to run it

At each phase milestone, on the pull request that claims the milestone, after `make check` passes locally:

```sh
gh workflow run verify.yml --repo revival-systems/revival-os --ref <branch>
gh run list --repo revival-systems/revival-os --workflow verify.yml --limit 3
```

GitHub lists and runs a `workflow_dispatch` workflow only once the file exists on the default branch (`main`). Until this file is merged, the workflow cannot be started at all.

Ordinary pull requests rely on the local `make check`, with its output quoted in the pull request.

## Cost risks and controls

| Risk | Control |
| --- | --- |
| Someone adds a `push` or `pull_request` trigger | Changing triggers needs approval ([AGENTS.md](../AGENTS.md#ci-and-cost-rules)). A push trigger would run on every commit of every branch. |
| Larger, macOS or GPU runners | Not used. macOS minutes cost more than Linux minutes. Any runner change needs approval. |
| A hung job | `timeout-minutes: 30`; QEMU tests have their own time limits |
| Repeated manual runs | Concurrency cancels the older run on the same branch |
| Scheduled (cron) workflows | None, and none to be added without approval |
| Artifact and cache storage | None configured |
| Internal and private repositories use the plan's Actions minutes | The repository is `internal`. Its minutes come from the organization's plan, and use beyond the plan is billed when the spending limit allows it. |
| Workflow settings alone do not guarantee zero cost | **The organization's Actions spending limit must be checked in GitHub's billing settings by an owner.** It could not be checked from here. |

## Security checks that stay

- Everything security-relevant in `make check` also runs locally: shellcheck, cppcheck, sanitizer runs, SHA-256 verification of both toolchains, and the freestanding-link checks.
- The workflow uses no secrets and has read-only repository access.
- Branch protection and required checks for `main` are not configured by this change. Configuring them is a separate, approved repository-settings change. A required check that only runs by hand would block merges, so required checks should be chosen deliberately.

## Not done, by decision

- No self-hosted runner.
- No hosted CI on every push or pull request.
- No change to repository or organization settings.
