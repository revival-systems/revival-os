//! hosted_std.rs - Phase 1 negative fixture (Test A, build-level rejection).
//!
//! A kernel source that DELIBERATELY omits `#![no_std]`, so it pulls in the
//! Rust standard library. `std` has no build for the bare-metal target
//! `armv7a-none-eabi`, so the compiler rejects it before anything is linked.
//! The Makefile check `build-rust-rejects-std` builds this file and REQUIRES
//! the build to fail with the standard-library-unavailable diagnostic
//! ("... target may not support the standard library"). Matching that exact
//! message means the check cannot pass because of an unrelated error.
//!
//! This proves an unapproved hosted (std) dependency cannot slip into a
//! Revival OS image unnoticed. The real kernel (kernel.rs) is the control: it
//! declares `#![no_std]` and builds clean. This file is never part of
//! `make build`; it is compiled only by the negative test, and is expected to
//! fail (ADR 0001, ROADMAP Phase 1).

// No `#![no_std]` here: that omission is the whole point of this fixture.

fn main() {
    // Touch `std` explicitly so the hosted dependency is unmistakable in the
    // source, not just implied by the missing `#![no_std]`.
    let mut v = std::vec::Vec::<u32>::new();
    v.push(0x00C0_FFEE);
    core::hint::black_box(&v);
}
