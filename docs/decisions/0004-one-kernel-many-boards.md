# ADR 0004 — One kernel, many boards

- **Status:** Accepted, 2026-11-18. Decided by the owner.

## Decision

Revival OS is one kernel core with two layers beneath it: an architecture layer, today ARMv7-A, and a board layer, today the GT-I9195.

- The kernel core contains nothing specific to a phone, a board or an architecture. It reaches them only through interfaces defined in the kernel tree.
- Drivers are separate from the kernel core and isolated from it. How they are isolated is not decided here: by the language's safety inside one address space, by separate address spaces, or by both. Phase 3 decides it in its own record, with measurements on the phone.
- The first product is the phone. The design must allow an ARM server and a laptop later, each with a new board or architecture layer and new drivers, and with no change to the core.

## Targets, in order

The order is the owner's plan.

1. The GT-I9195, now.
2. A small, open, documented ARM board, to prove the board seam. It comes after the kernel runs on the phone. Nothing is bought now.
3. x86-64 laptops, as a second architecture, last.

## First intended product

The owner decided on 2026-11-18 that the first product built on Revival OS is a fixed camera device for a restaurant, running on the GT-I9195. It counts the people at each table, tells whether each table is occupied, and times how long guests stay.

It is an appliance: one program, running unattended all day, with no touch interface and no calls.

What it needs after the kernel core, in this order:

1. the display;
2. the camera;
3. networking, to send its results;
4. enough performance to run a person detector.

The owner's requirement is that it runs smoothly, with no lag and no stalls.

**Unknown:** whether the person detector can use this phone's GPU or its DSP.

## Later goal: continuity between devices

The owner's wish, stated on 2026-11-18: work begun on one Revival OS device can be seen and continued on another of the owner's devices, for example on a phone and a laptop.

Nothing is built for it now. It depends on networking, on the secure pairing of the device protocol ([ARCHITECTURE.md, contract 4](../../ARCHITECTURE.md#contracts-to-define)), and on a second device.

Its one consequence today: when the application model is designed, an application's state must be separable from the device it runs on.

## What the owner wants Revival OS to be

Very small, written in a memory-safe language, with drivers isolated from the kernel, and built for a phone first. Whether any shipped system has all four is not established: the reviewer said so from memory, unchecked. A survey of comparable systems is due before Phase 3 is designed ([ADR 0002, room to invent](0002-design-goals.md#room-to-invent)).

## Consequences

- In Phase 3, every line that is specific to an architecture or a board goes behind an interface, not into the core. The board-facts module of the console image is the first example.
- Cost accepted: more care and some more work in Phase 3. Isolating the drivers may cost speed, depending on the method; the cost is measured on the phone in Phase 3. The console image gives the first speed figure for our code on the phone.

## Rejected

- A kernel for this phone only.
- A second architecture before the kernel core is stable.
