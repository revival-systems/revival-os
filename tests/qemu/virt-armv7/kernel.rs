//! kernel.rs - Phase 1 freestanding Rust foundation for Revival OS.
//!
//! `#![no_std]`, ARMv7-A (target `armv7a-none-eabi`, soft-float). Phase 1
//! fixture that boots in QEMU's `virt` board and prints a deterministic
//! heartbeat from Rust. It is NOT Samsung code and NOT yet the kernel tree
//! (ARCHITECTURE.md places `kernel/` at Phase 3). Pairs with `kstart.S`
//! (entry, vectors, semihosting exit) and reuses `link.ld`.
//!
//! Memory (ADR 0001): native Rust call stack + statically reserved data only.
//! No general-purpose heap and no dynamic allocation.
//!
//! BUILD: `make build` and `make test-rust` compile this file and boot it in
//! QEMU; docs/phase-1/rust-foundation.md records the exact commands, the
//! observed serial output, the binary sizes and their SHA-256. rustc drives
//! the link with its own `core` and `compiler_builtins`, which also supply
//! `mem*` and the ARM EABI helpers, so the Arm GNU `bfd` linker is only the
//! backend and no C library and no `-lgcc` are added. The build, per image:
//!
//!   rustc --target armv7a-none-eabi --edition 2021 --crate-type bin \
//!         -C panic=abort -C opt-level=2 -C relocation-model=static \
//!         -C linker=arm-none-eabi-gcc -C linker-flavor=gcc \
//!         -C link-arg=-fuse-ld=bfd -C link-arg=-nostartfiles \
//!         -C link-arg=-nostdlib -C link-arg=-Wl,-T,link.ld \
//!         -C link-arg=kstart.o --emit link -o kernel.elf kernel.rs
//!   # heartbeat is the default; add --cfg kmode_panic or --cfg kmode_oob
//!   # for the two negative-test images. The mem module below stays off
//!   # (compiler_builtins already supplies mem*); see its note.

#![no_std]
#![no_main]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

// QEMU `virt` PL011 UART0 (identical to the probe fixture, minirt.c).
const UART0_DR: *mut u32 = 0x0900_0000 as *mut u32;
const UART0_FR: *mut u32 = 0x0900_0018 as *mut u32;
const UART_FR_TXFF: u32 = 1 << 5;

// Provided by kstart.S: Arm semihosting SYS_EXIT (the image's only `svc`).
extern "C" {
    fn rt_exit(status: i32) -> !;
}

fn uart_putc(b: u8) {
    // SAFETY: fixed MMIO register of the QEMU `virt` PL011, single-threaded.
    unsafe {
        while read_volatile(UART0_FR) & UART_FR_TXFF != 0 {}
        write_volatile(UART0_DR, b as u32);
    }
}

fn uart_puts(s: &str) {
    for &b in s.as_bytes() {
        uart_putc(b);
    }
}

fn uart_put_hex32(v: u32) {
    uart_puts("0x");
    let mut shift = 28i32;
    while shift >= 0 {
        let nib = ((v >> shift) & 0xf) as u8;
        uart_putc(if nib < 10 { b'0' + nib } else { b'a' + (nib - 10) });
        shift -= 4;
    }
}

fn uart_put_u32(v: u32) {
    let mut buf = [0u8; 10];
    let mut n = 0usize;
    let mut u = v;
    loop {
        buf[n] = b'0' + (u % 10) as u8;
        n += 1;
        u /= 10;
        if u == 0 {
            break;
        }
    }
    while n > 0 {
        n -= 1;
        uart_putc(buf[n]);
    }
}

// A fixed, statically reserved table. The heartbeat prints a checksum computed
// over it in Rust, so a correct boot is observable and deterministic.
static TABLE: [u32; 8] = [
    0x5245_5649, 0x414c_204f, 0x5350_4841, 0x5345_3120, 0x0000_0001, 0x0000_0002, 0x0000_0003,
    0x0000_0004,
];

fn checksum() -> u32 {
    let mut acc: u32 = 0x1234_5678;
    let mut i = 0usize;
    while i < TABLE.len() {
        acc = acc.rotate_left(5) ^ TABLE[i].wrapping_add(i as u32);
        i += 1;
    }
    acc
}

fn heartbeat() {
    uart_puts("revival-os: phase 1 rust heartbeat\n");
    uart_puts("revival-os: checksum=");
    uart_put_hex32(checksum());
    uart_putc(b'\n');
}

/// Kernel entry, called by kstart.S after the stack and .bss are set up.
/// Returns an exit status that kstart.S passes to the semihosting exit.
#[no_mangle]
pub extern "C" fn kmain() -> i32 {
    heartbeat();

    // Negative-test modes, selected at build time (one image each), mirroring
    // the probe fixture's PROBE_CASE. The default build just prints and exits 0.
    #[cfg(kmode_panic)]
    panic!("deliberate panic (phase 1 negative test)");

    #[cfg(kmode_oob)]
    {
        // Runtime out-of-bounds index: Rust's bounds check must panic into the
        // handler instead of reading past the end. `black_box` keeps the index
        // opaque so it is a runtime check, not a compile-time error.
        let idx = core::hint::black_box(TABLE.len() + 3);
        uart_put_u32(TABLE[idx]);
    }

    #[cfg(not(kmode_panic))]
    {
        0
    }
}

/// Fault handler, called from the kstart.S vector stubs. Reports the vector
/// number and exits with a failure status.
#[no_mangle]
pub extern "C" fn kexception(vector: u32) -> ! {
    uart_puts("revival-os: unexpected exception, vector ");
    uart_put_u32(vector);
    uart_putc(b'\n');
    // SAFETY: rt_exit is the semihosting exit in kstart.S; it never returns.
    unsafe { rt_exit(1) }
}

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    uart_puts("panic: ");
    if let Some(loc) = info.location() {
        uart_puts(loc.file());
        uart_putc(b':');
        uart_put_u32(loc.line());
    } else {
        uart_puts("<unknown location>");
    }
    uart_putc(b'\n');
    // SAFETY: rt_exit is the semihosting exit in kstart.S; it never returns.
    unsafe { rt_exit(1) }
}

/// Freestanding `mem*` the compiler may emit (for example via the bounds-check
/// panic's formatting path). The pinned target's own `compiler_builtins`
/// already supplies `memcpy`/`memmove`/`memset`/`memcmp` - the images link with
/// zero undefined symbols without this module - so it is built only under
/// `--cfg kprovide_mem` and is off by default. Kept as a documented fallback,
/// like the probe fixture's C versions; unused copies drop out at `--gc-sections`.
#[cfg(kprovide_mem)]
mod mem {
    use core::ptr;

    #[no_mangle]
    pub unsafe extern "C" fn memcpy(dst: *mut u8, src: *const u8, n: usize) -> *mut u8 {
        let mut i = 0usize;
        while i < n {
            ptr::write(dst.add(i), ptr::read(src.add(i)));
            i += 1;
        }
        dst
    }

    #[no_mangle]
    pub unsafe extern "C" fn memmove(dst: *mut u8, src: *const u8, n: usize) -> *mut u8 {
        if (dst as usize) < (src as usize) {
            let mut i = 0usize;
            while i < n {
                ptr::write(dst.add(i), ptr::read(src.add(i)));
                i += 1;
            }
        } else {
            let mut i = n;
            while i > 0 {
                i -= 1;
                ptr::write(dst.add(i), ptr::read(src.add(i)));
            }
        }
        dst
    }

    #[no_mangle]
    pub unsafe extern "C" fn memset(dst: *mut u8, c: i32, n: usize) -> *mut u8 {
        let mut i = 0usize;
        while i < n {
            ptr::write(dst.add(i), c as u8);
            i += 1;
        }
        dst
    }

    #[no_mangle]
    pub unsafe extern "C" fn memcmp(a: *const u8, b: *const u8, n: usize) -> i32 {
        let mut i = 0usize;
        while i < n {
            let x = ptr::read(a.add(i));
            let y = ptr::read(b.add(i));
            if x != y {
                return if x < y { -1 } else { 1 };
            }
            i += 1;
        }
        0
    }
}
