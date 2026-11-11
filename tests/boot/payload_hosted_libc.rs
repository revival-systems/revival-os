//! payload_hosted_libc.rs - Phase 2 negative fixture (link-level rejection).
//!
//! A COMPLETE, valid `#![no_std]` payload shaped exactly like the real one
//! (boot/samsung-serranolte/payload.rs): it defines `payload_main` and a
//! `#[panic_handler]`, so it links against the payload's `kstart.S` and
//! `link.ld`. It additionally calls the C standard-library function `puts`.
//! It COMPILES cleanly; only the LINK fails, because `puts` is an unapproved
//! hosted symbol and the image is linked `-nostdlib` with no C library, so
//! `puts` is the SOLE undefined reference.
//!
//! The Makefile check `payload-rejects-libc` links this and requires the
//! failure to name `undefined reference to `puts'`, proving an unapproved
//! hosted dependency cannot slip into the device image. The real payload is the
//! positive control: it links with zero undefined symbols. Never part of
//! `make build`; compiled only by the negative test (mirrors the Phase 1
//! fixture tests/qemu/virt-armv7/hosted_libc.rs).

#![no_std]
#![no_main]

use core::panic::PanicInfo;

extern "C" {
    // The unapproved hosted dependency this fixture exists to reject. With
    // `-nostdlib` and no approved C library, this symbol stays undefined and
    // the link must fail on it.
    fn puts(s: *const u8) -> i32;
}

#[no_mangle]
pub extern "C" fn payload_main(_handoff: *const u32) {
    // SAFETY: deliberately calls an unapproved libc symbol so the link fails;
    // this image is never run.
    unsafe {
        puts(b"revival-os: hosted dependency (phase 2 negative test)\n\0".as_ptr());
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {
        // SAFETY: wfi is a hint; always safe.
        unsafe { core::arch::asm!("wfi") };
    }
}
