//! exc.rs - emulator-only step toward ROADMAP 3a: exception vectors that say
//! which exception happened and where, then halt.
//!
//! QEMU `virt` test fixture (ARMv7-A, `armv7a-none-eabi`, soft-float), next to
//! the Phase 1 kernel. Not OS code, not Samsung code, and no claim about the
//! phone: ROADMAP 3a is tested on the device, and an emulator result never
//! replaces that (docs/TESTING.md).
//!
//! exc_vectors.S holds the vector table and calls `exc_report` with the
//! vector number, the address of the instruction that caused the exception
//! and, for the two aborts, the fault status and fault address registers.
//! `exc_report` names the exception, decodes the status, compares the report
//! with what the case expected, prints both, and halts (semihosting exit 1:
//! an exception always ends the run as a failure of the program).
//!
//! One image per case, chosen by a cfg (as kernel.rs's kmode_*):
//!   ecase_undef  an undefined instruction at a known address (exc_udf)
//!   ecase_dabt   a load from an address with nothing behind it (exc_load)
//!   ecase_pabt   a jump to that address
//! Memory (ADR 0001): stack and static data only.

#![no_std]
#![no_main]

use core::cell::UnsafeCell;
use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

// PL011 UART0 of QEMU `virt` (as in kernel.rs).
const UART0_DR: *mut u32 = 0x0900_0000 as *mut u32;
const UART0_FR: *const u32 = 0x0900_0018 as *const u32;
const UART_FR_TXFF: u32 = 1 << 5;

/// Nothing is behind this address on QEMU `virt` with the 64 MiB the test
/// runner gives it: above the RAM (0x40000000 to 0x44000000), below 4 GiB.
/// QEMU answers an access there with a synchronous external abort.
#[cfg(any(ecase_dabt, ecase_pabt))]
const UNMAPPED: usize = 0x4800_0000;

extern "C" {
    /// kstart.S: Arm semihosting SYS_EXIT (the image's only `svc`).
    fn rt_exit(status: i32) -> !;
    /// exc_vectors.S: VBAR = the reporting vector table.
    fn install_exc_vectors();
    /// exc_vectors.S: an undefined instruction at the symbol's address.
    #[cfg(ecase_undef)]
    fn exc_udf();
    /// exc_vectors.S: a load, at the symbol's address, from `addr`.
    #[cfg(ecase_dabt)]
    fn exc_load(addr: usize) -> u32;
}

fn putc(b: u8) {
    // SAFETY: fixed MMIO registers of the QEMU `virt` PL011; one core.
    unsafe {
        while read_volatile(UART0_FR) & UART_FR_TXFF != 0 {}
        write_volatile(UART0_DR, b as u32);
    }
}

fn puts(s: &str) {
    for &b in s.as_bytes() {
        putc(b);
    }
}

fn put_hex(v: u32) {
    puts("0x");
    let mut shift = 28i32;
    while shift >= 0 {
        let nib = ((v >> shift) & 0xf) as u8;
        putc(if nib < 10 { b'0' + nib } else { b'a' + (nib - 10) });
        shift -= 4;
    }
}

/// The eight ARMv7-A vectors, by number.
const NAMES: [&str; 8] = [
    "reset",
    "undefined instruction",
    "supervisor call",
    "prefetch abort",
    "data abort",
    "unused vector",
    "IRQ",
    "FIQ",
];
const PREFETCH_ABORT: u32 = 3;
const DATA_ABORT: u32 = 4;
/// Short-descriptor fault status of a synchronous external abort.
const FS_SYNC_EXTERNAL: u32 = 0b01000;

/// The 5-bit fault status of a DFSR or IFSR value (short-descriptor format:
/// FS[4] is bit 10, FS[3:0] are bits 3 to 0).
fn fault_status(fsr: u32) -> u32 {
    ((fsr >> 6) & 0x10) | (fsr & 0xf)
}

fn fault_status_name(fs: u32) -> &'static str {
    match fs {
        0b00001 => "alignment fault",
        0b00010 => "debug event",
        0b00011 => "access flag fault, section",
        0b00101 => "translation fault, section",
        0b00110 => "access flag fault, page",
        0b00111 => "translation fault, page",
        0b01000 => "synchronous external abort",
        0b01001 => "domain fault, section",
        0b01011 => "domain fault, page",
        0b01101 => "permission fault, section",
        0b01111 => "permission fault, page",
        0b10110 => "asynchronous external abort",
        _ => "other fault status",
    }
}

/// What the case expects the vectors to report. Written once, before the
/// fault; read once, by exc_report.
#[derive(Clone, Copy)]
struct Expect {
    kind: u32,
    pc: usize,
    /// The fault address, for an abort.
    far: Option<usize>,
    /// The 5-bit fault status, for an abort.
    status: Option<u32>,
}

struct Global<T>(UnsafeCell<T>);
// SAFETY: one core, interrupts masked (kstart.S); written before the fault
// and read only by exc_report after it.
unsafe impl<T> Sync for Global<T> {}

static EXPECT: Global<Expect> = Global(UnsafeCell::new(Expect { kind: u32::MAX, pc: 0, far: None, status: None }));

fn expect(e: Expect) {
    // SAFETY: see Global.
    unsafe { *EXPECT.0.get() = e };
}

/// Called by exc_vectors.S on the main stack. Reports the exception, checks
/// it against the case's expectation, and halts.
#[no_mangle]
pub extern "C" fn exc_report(kind: u32, pc: usize, fsr: u32, far: usize) -> ! {
    let name = NAMES.get(kind as usize).copied().unwrap_or("unknown vector");
    let is_abort = kind == PREFETCH_ABORT || kind == DATA_ABORT;
    puts("exception: ");
    puts(name);
    puts(" at pc ");
    put_hex(pc as u32);
    if is_abort {
        puts(", fault address ");
        put_hex(far as u32);
        puts(", status ");
        put_hex(fsr);
        puts(" (");
        puts(fault_status_name(fault_status(fsr)));
        if kind == DATA_ABORT {
            puts(if fsr & (1 << 11) != 0 { ", a write" } else { ", a read" });
        }
        puts(")");
    }
    putc(b'\n');

    // SAFETY: see Global.
    let e = unsafe { *EXPECT.0.get() };
    let far_ok = match e.far {
        Some(a) => far == a,
        None => true,
    };
    let status_ok = match e.status {
        Some(fs) => fault_status(fsr) == fs,
        None => true,
    };
    if kind == e.kind && pc == e.pc && far_ok && status_ok {
        // The decoded status is part of the line the tests check, so a wrong
        // decode fails them too.
        puts("exception: as expected (");
        puts(name);
        puts(" at the expected pc");
        if is_abort {
            puts(", fault address and status: ");
            puts(fault_status_name(fault_status(fsr)));
            if kind == DATA_ABORT {
                puts(if fsr & (1 << 11) != 0 { ", a write" } else { ", a read" });
            }
        }
        puts("); halted\n");
    } else {
        puts("exception: NOT as expected: wanted ");
        puts(NAMES.get(e.kind as usize).copied().unwrap_or("no exception"));
        puts(" at pc ");
        put_hex(e.pc as u32);
        if let Some(a) = e.far {
            puts(", fault address ");
            put_hex(a as u32);
        }
        if let Some(fs) = e.status {
            puts(", status ");
            puts(fault_status_name(fs));
        }
        puts("; halted\n");
    }
    // SAFETY: semihosting exit; the run ends here.
    unsafe { rt_exit(1) }
}

#[cfg(ecase_undef)]
fn case() -> i32 {
    expect(Expect { kind: 1, pc: exc_udf as *const () as usize, far: None, status: None });
    // SAFETY: deliberate fault; exc_report does not return.
    unsafe { exc_udf() };
    puts("exception: FAIL the undefined instruction did not trap\n");
    1
}

#[cfg(ecase_dabt)]
fn case() -> i32 {
    expect(Expect { kind: DATA_ABORT, pc: exc_load as *const () as usize, far: Some(UNMAPPED), status: Some(FS_SYNC_EXTERNAL) });
    // SAFETY: deliberate fault; exc_report does not return.
    let v = unsafe { exc_load(UNMAPPED) };
    puts("exception: FAIL the load from nothing returned ");
    put_hex(v);
    putc(b'\n');
    1
}

#[cfg(ecase_pabt)]
fn case() -> i32 {
    expect(Expect { kind: PREFETCH_ABORT, pc: UNMAPPED, far: Some(UNMAPPED), status: Some(FS_SYNC_EXTERNAL) });
    // SAFETY: deliberate fault: a call to an address with nothing behind it;
    // exc_report does not return.
    let nowhere: extern "C" fn() = unsafe { core::mem::transmute::<usize, extern "C" fn()>(UNMAPPED) };
    nowhere();
    puts("exception: FAIL the jump to nothing returned\n");
    1
}

/// Called by kstart.S after the stack and .bss are set up.
#[no_mangle]
pub extern "C" fn kmain() -> i32 {
    // The decode of FS[4] (bit 10) cannot be seen in QEMU's 0x8, so check it
    // on known values first: 0x406 is an asynchronous external abort.
    if fault_status(0x406) != 0b10110 || fault_status(0x8) != FS_SYNC_EXTERNAL || fault_status(0x40f) != 0b11111 {
        puts("exception: FAIL the fault-status decode\n");
        return 1;
    }
    // SAFETY: writes VBAR; interrupts are masked (kstart.S).
    unsafe { install_exc_vectors() };
    case()
}

/// kstart.S's own vectors call this. After install_exc_vectors they are not
/// in use, so reaching it means the reporting vectors were not installed.
#[no_mangle]
pub extern "C" fn kexception(vector: u32) -> ! {
    puts("exception: FAIL reached the Phase 1 vectors (vector ");
    putc(b'0' + (vector & 7) as u8);
    puts("): the reporting vectors are not installed\n");
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    puts("panic\n");
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}
