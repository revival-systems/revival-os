//! hosted_libc.rs - Phase 1 negative fixture (Test A, link-level rejection).
//!
//! A COMPLETE, valid `#![no_std]` kernel - it defines `kmain`, `kexception`
//! and a `#[panic_handler]`, exactly like kernel.rs, and takes `rt_exit` from
//! kstart.S - that additionally calls one C standard-library function, `puts`.
//! The fixture COMPILES cleanly; only the LINK fails, because `puts` is an
//! unapproved hosted symbol and the image is linked `-nostdlib` with no C
//! library. `puts` is therefore the SOLE undefined reference.
//!
//! Two checks use this file so the rejection is provably the libc dependency
//! and not an unrelated failure (ROADMAP Phase 1, ADR 0001):
//!   - `build-rust-hosted-libc-compiles` first compiles it to an object and
//!     requires success - the fixture is valid Rust;
//!   - `build-rust-rejects-libc` then links it and requires the failure to
//!     name `undefined reference to `puts'`.
//!
//! Never part of `make build`; compiled only by the negative test.

#![no_std]
#![no_main]

use core::panic::PanicInfo;

extern "C" {
    // Provided by kstart.S: the image's semihosting exit.
    fn rt_exit(status: i32) -> !;
    // The unapproved hosted dependency this fixture exists to reject. With
    // `-nostdlib` and no approved C library, this symbol stays undefined and
    // the link must fail on it.
    fn puts(s: *const u8) -> i32;
}

#[no_mangle]
pub extern "C" fn kmain() -> i32 {
    // SAFETY: deliberately calls an unapproved libc symbol so the link fails;
    // this image is never run.
    unsafe { puts(b"revival-os: hosted dependency (negative test)\n\0".as_ptr()) }
}

#[no_mangle]
pub extern "C" fn kexception(_vector: u32) -> ! {
    // SAFETY: rt_exit is the semihosting exit in kstart.S; it never returns.
    unsafe { rt_exit(1) }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    // SAFETY: rt_exit is the semihosting exit in kstart.S; it never returns.
    unsafe { rt_exit(1) }
}
