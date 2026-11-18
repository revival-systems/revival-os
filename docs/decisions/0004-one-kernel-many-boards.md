# ADR 0004 — One kernel, many boards

- **Status:** Accepted, 2026-11-18. Decided by the owner.

## Decision

Revival OS is one kernel core with two layers beneath it: an architecture layer, today ARMv7-A, and a board layer, today the GT-I9195.

- The kernel core contains nothing specific to a phone, a board or an architecture. It reaches them only through interfaces defined in the kernel tree.
- Drivers are separate from the kernel core and isolated from it.
- The first product is the phone. The design must allow an ARM server and a laptop later, each with a new board or architecture layer and new drivers, and with no change to the core.

## Targets, in order

The order is the owner's plan.

1. The GT-I9195, now.
2. A small, open, documented ARM board, to prove the board seam. It comes after the kernel runs on the phone. Nothing is bought now.
3. x86-64 laptops, as a second architecture, last.

## What the owner wants Revival OS to be

Very small, written in a memory-safe language, with drivers isolated from the kernel, and built for a phone first. The owner knows that no shipped system has all four.

## Consequences

- In Phase 3, every line that is specific to an architecture or a board goes behind an interface, not into the core. The board-facts module of the console image (task R-13) is the first example.
- Cost accepted: more care and some more work in Phase 3. Isolating the drivers costs some speed, and the console image is how that cost is measured on the phone.

## Rejected

- A kernel for this phone only.
- A second architecture before the kernel core is stable.
