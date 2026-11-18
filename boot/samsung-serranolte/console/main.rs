//! main.rs - GT-I9195 Phase 2 image 2: a text console.
//!
//! `#![no_std]`, ARMv7-A (target `armv7a-none-eabi`, soft-float). DEVICE code,
//! built into build/boot-serrano-console/console.bin. It is entered through
//! the first image's own `kstart.S` and laid out by its `link.ld`, both used
//! unchanged, so everything that runs before Rust is the code that has already
//! run on the phone. docs/phase-2/console-payload.md is the full description.
//!
//! What it does: writes what the bootloader handed over as readable text
//! instead of rows of bits. The CPU registers, the bootloader's tag list
//! (ATAGS) and the display controller's framebuffer register, then a counter
//! that keeps counting to show the CPU is still running.
//!
//! What it touches: it WRITES only to the framebuffer at `board::FB_BASE`. It
//! READS the seven words kstart.S captured, the tag list (only inside the tag
//! page, only word-aligned), and exactly one register, the MDP4 framebuffer
//! address, after the rest is on screen. No heap, no allocator, no `svc`, no
//! timer, no watchdog, no interrupts, no `core::fmt`, and no path that can
//! panic (`make test-console` checks the last one in the linked image).
//!
//! What it never shows: a value from the kernel command line, the serial tag's
//! words, or the content of a tag it does not know. Those hold the phone's
//! identifiers, and a photograph of this screen is evidence that gets shared.
//!
//! A fault lands in kstart.S's halt-only vectors: what was drawn stays.

#![no_std]
#![no_main]

mod atags;
mod board;
mod console;
mod fb;
mod font;

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

use atags::{Cmdline, Piece, Step, Walk};
use console::Console;
use fb::Framebuffer;

// --- screen layout -----------------------------------------------------------
// The report gets every line but the last two, which are fixed: one for the
// display register and one for the counter. Whatever the report does, those
// two lines are always drawn in the same place.
const REPORT_LINES: usize = console::LINES - 2;
const MDP_LINE: usize = console::LINES - 2;
const TICK_LINE: usize = console::LINES - 1;

/// Loop turns between two steps of the counter. How long that takes on the
/// phone is not known; the session measures it.
const TICK_TURNS: u32 = 4_194_304;

/// Stripes drawn instead of text when the image runs at the wrong address.
const MOVED_STRIPES: usize = 20;

// --- self-test: the first image's table and sum ------------------------------
// Same table and algorithm as boot/samsung-serranolte/payload.rs, so the sum is
// the value the phone has already shown: 0x22BECBA4.
static TABLE: [u32; 8] = [
    0x5245_5649, 0x414c_204f, 0x5350_4841, 0x5345_3120, 0x0000_0001, 0x0000_0002, 0x0000_0003,
    0x0000_0004,
];
const TABLE_SUM: u32 = 0x22BE_CBA4;

fn table_sum() -> u32 {
    let mut acc: u32 = 0x1234_5678;
    for (i, entry) in TABLE.iter().enumerate() {
        // SAFETY: `entry` is a reference to a word of TABLE: valid and aligned.
        // The read is volatile so that the sum is worked out on the device from
        // the bytes the bootloader loaded, not folded to a constant when the
        // image is built.
        let word = unsafe { read_volatile(entry) };
        acc = acc.rotate_left(5) ^ word.wrapping_add(i as u32);
    }
    acc
}

/// Image entry, called by kstart.S with the address of the seven words it
/// captured: r0, r1, r2, r3, CPSR, SCTLR and the address it was entered at.
///
/// Order: everything that only reads memory comes first. The one register read
/// comes after the report is complete, so that if it hangs or faults the
/// report is already on screen, with "MDP4 READ PENDING" under it.
///
/// It does not return, except in the wrong-address case below; then, as after
/// any fault, kstart.S halts.
#[no_mangle]
pub extern "C" fn payload_main(handoff: *const u32) {
    // SAFETY: kstart.S passes the address of eight words it has just pushed on
    // the stack (the seven captured values, then one word of padding). They
    // are word-aligned and stay in place for as long as this function runs.
    let captured: &[u32; 7] = unsafe { &*(handoff as *const [u32; 7]) };
    let [_, _, r2, _, _, _, entry] = *captured;

    // SAFETY: board::FB_BASE is the start of the panel's framebuffer, which
    // lies outside this image, its stack and the tag page (the overlap table
    // in docs/phase-2/console-payload.md). Nothing else here uses that memory.
    let fb = unsafe { Framebuffer::new(board::FB_BASE) };

    // The image is linked for one address and uses absolute addresses for its
    // text and its font. If the bootloader put it somewhere else, those would
    // point at memory that is not this image, so no text can be trusted. Draw
    // stripes, which need neither, and stop.
    if entry != board::LINK_ENTRY {
        draw_moved(&fb);
        return;
    }

    let mut report = Console::new(&fb, 0, REPORT_LINES);
    report.puts(b"REVIVAL OS\nPHASE 2 IMAGE 2\n");
    report_selftest(&mut report);
    report_cpu(&mut report, captured);
    report_tags(&mut report, r2);
    report.finish();

    // Both fixed lines are put in a known state before the register is read.
    let mut mdp_line = Console::new(&fb, MDP_LINE, 1);
    mdp_line.puts(b"MDP4 READ PENDING");
    let _ = Console::new(&fb, TICK_LINE, 1);

    // SAFETY: one volatile read of a fixed, word-aligned register address; the
    // register is never written. Reading it on the phone has been measured.
    let mdp = unsafe { read_volatile(board::MDP_DMA_P_BUF_ADDR as *const u32) };
    let mut mdp_line = Console::new(&fb, MDP_LINE, 1);
    mdp_line.puts(b"MDP4 ");
    mdp_line.hex32(mdp);
    let verdict: &[u8] = if mdp as usize == board::FB_BASE { b" IS FB" } else { b" NOT FB" };
    mdp_line.puts(verdict);

    let mut tick: u32 = 0;
    loop {
        let mut tick_line = Console::new(&fb, TICK_LINE, 1);
        tick_line.puts(b"TICK ");
        tick_line.hex32(tick);
        console_tick_wait();
        tick = tick.wrapping_add(1);
    }
}

/// Wait between two steps of the counter by counting, with nothing else going
/// on: no timer and no `wfi`, because no interrupt would ever end one.
///
/// A function of its own, never inlined and with a fixed name, so that the
/// test harness can find it in the ELF: while the CPU is in here the screen is
/// complete, never half-drawn.
#[no_mangle]
#[inline(never)]
pub extern "C" fn console_tick_wait() {
    let mut turns: u32 = 0;
    let slot: *mut u32 = &mut turns;
    loop {
        // SAFETY: `slot` points at `turns`, a live local of this function that
        // nothing else refers to. The accesses are volatile so that the
        // compiler keeps the loop instead of working out its result.
        let now = unsafe { read_volatile(slot) };
        if now >= TICK_TURNS {
            break;
        }
        // SAFETY: as above.
        unsafe { write_volatile(slot, now + 1) };
    }
}

/// White and black stripes across the whole panel. Uses no text and no table,
/// so it is right wherever the image was loaded.
fn draw_moved(fb: &Framebuffer) {
    let height = board::FB_HEIGHT / MOVED_STRIPES;
    let mut stripe: usize = 0;
    while stripe < MOVED_STRIPES {
        let shade: u8 = if stripe & 1 == 0 { 0xFF } else { 0x00 };
        fb.fill_rect(0, stripe * height, board::FB_WIDTH, height, shade);
        stripe += 1;
    }
}

fn report_selftest(report: &mut Console) {
    let sum = table_sum();
    report.puts(b"SELFTEST ");
    report.hex32(sum);
    let verdict: &[u8] = if sum == TABLE_SUM { b" OK\n" } else { b" BAD\n" };
    report.puts(verdict);
}

/// The registers as kstart.S captured them, with the bits that matter spelled
/// out: 1 means the bit is set.
fn report_cpu(report: &mut Console, captured: &[u32; 7]) {
    let [r0, r1, r2, r3, cpsr, sctlr, entry] = *captured;

    report.puts(b"R0 ");
    report.hex32(r0);
    report.puts(b" R1 ");
    report.hex32(r1);
    report.puts(b"\nR2 ");
    report.hex32(r2);
    report.puts(b" R3 ");
    report.hex32(r3);
    // r1 is the machine number the bootloader passes; in decimal, as it is
    // listed.
    report.puts(b"\nMACH ");
    report.dec(r1);

    // CPSR: mode, then the IRQ, FIQ and abort masks and the Thumb bit.
    report.puts(b"\nCPSR ");
    report.hex32(cpsr);
    report.put(b' ');
    report.puts(mode_name(cpsr));
    report_bit(report, b" I", cpsr, 7);
    report_bit(report, b" F", cpsr, 6);
    report_bit(report, b" A", cpsr, 8);
    report_bit(report, b" T", cpsr, 5);

    // SCTLR: MMU, data cache, instruction cache, alignment checking, high
    // vectors.
    report.puts(b"\nSCTLR ");
    report.hex32(sctlr);
    report_bit(report, b" M", sctlr, 0);
    report_bit(report, b" C", sctlr, 2);
    report_bit(report, b" I", sctlr, 12);
    report_bit(report, b" A", sctlr, 1);
    report_bit(report, b" V", sctlr, 13);

    // Reached only when the entry address is the linked one.
    report.puts(b"\nENTRY ");
    report.hex32(entry);
    report.puts(b" OK\n");
}

fn report_bit(report: &mut Console, name: &[u8], word: u32, bit: u32) {
    report.puts(name);
    report.put(if (word >> bit) & 1 != 0 { b'1' } else { b'0' });
}

fn mode_name(cpsr: u32) -> &'static [u8] {
    match cpsr & 0x1F {
        0x10 => b"USR",
        0x11 => b"FIQ",
        0x12 => b"IRQ",
        0x13 => b"SVC",
        0x16 => b"MON",
        0x17 => b"ABT",
        0x1A => b"HYP",
        0x1B => b"UND",
        0x1F => b"SYS",
        _ => b"???",
    }
}

/// The bootloader's tag list, if r2 points at one inside the tag page.
fn report_tags(report: &mut Console, r2: u32) {
    report.puts(b"ATAGS ");
    report.hex32(r2);
    if r2 < board::TAGS_PAGE_LO || r2 >= board::TAGS_PAGE_HI {
        report.puts(b" OUT OF PAGE\n");
        return;
    }
    if r2 & 3 != 0 {
        report.puts(b" UNALIGNED\n");
        return;
    }
    let count = ((board::TAGS_PAGE_HI - r2) / 4) as usize;
    // SAFETY: r2 is word-aligned and inside the tag page (both checked just
    // above), and `count` words from it end exactly at the end of that page.
    // The page is ordinary memory that the bootloader wrote before it started
    // this image; nothing writes it now, and this image never does.
    let words = unsafe { core::slice::from_raw_parts(r2 as *const u32, count) };
    if words.first().copied() == Some(atags::DEVICE_TREE_MAGIC) {
        report.puts(b" DEVICE TREE\n");
        return;
    }
    report.newline();

    let mut walk = Walk::new(words);
    while let Some(step) = walk.next() {
        match step {
            Step::Tag { id, body } => report_tag(report, id, body),
            Step::End { id } => {
                report.puts(b" END ");
                report.dec(walk.seen() as u32);
                report.puts(b" TAGS\n");
                if id != 0 {
                    report.puts(b" END KIND ");
                    report.hex32(id);
                    report.newline();
                }
            }
            Step::BadSize(size) => {
                report.puts(b" STOP SIZE ");
                report.hex32(size);
                report.newline();
            }
            Step::PastEnd => report.puts(b" STOP PAST PAGE END\n"),
            Step::TooMany => {
                report.puts(b" STOP AT ");
                report.dec(atags::MAX_TAGS as u32);
                report.puts(b" TAGS\n");
            }
        }
    }
}

/// One tag. A kind that is not listed here is shown as its number and its
/// length only: its words could be anything.
fn report_tag(report: &mut Console, id: u32, body: &[u32]) {
    match id {
        atags::ATAG_CORE => {
            // flags, page size, root device; only the page size says anything.
            report.puts(b" CORE");
            if let Some(&page) = body.get(1) {
                report.puts(b" PAGE ");
                report.hex32(page);
            }
            report.newline();
        }
        atags::ATAG_MEM => report_pair(report, b" MEM ", b" AT ", body),
        atags::ATAG_INITRD2 => report_pair(report, b" INITRD2 ", b" SZ ", body),
        atags::ATAG_REVISION => {
            report.puts(b" REVISION");
            if let Some(&revision) = body.first() {
                report.put(b' ');
                report.hex32(revision);
            }
            report.newline();
        }
        // The serial number is an identifier: say the tag is there, no more.
        atags::ATAG_SERIAL => report.puts(b" SERIAL HIDDEN\n"),
        atags::ATAG_CMDLINE => report_cmdline(report, body),
        _ => {
            report.puts(b" TAG ");
            report.hex32(id);
            report.puts(b" W");
            report.dec(body.len() as u32);
            report.newline();
        }
    }
}

/// A tag whose body starts with two words: `name`, the first, `between`, the
/// second.
fn report_pair(report: &mut Console, name: &[u8], between: &[u8], body: &[u32]) {
    report.puts(name);
    match body {
        [first, second, ..] => {
            report.hex32(*first);
            report.puts(between);
            report.hex32(*second);
        }
        _ => report.puts(b"SHORT"),
    }
    report.newline();
}

/// The kernel command line: each word's name and the length of its value,
/// `NAME=<length>`, or `<length>` alone for a word with no `=`. Words are kept
/// whole where they fit: one that would pass the end of the line starts a new
/// line, indented.
fn report_cmdline(report: &mut Console, body: &[u32]) {
    report.puts(b" CMDLINE");
    let mut pieces = Cmdline::new(body);
    loop {
        let width = word_width(pieces);
        if width == 0 {
            break;
        }
        if report.column() + 1 + width > console::COLUMNS {
            report.puts(b"\n  ");
        } else {
            report.put(b' ');
        }
        // Draw this one word: the pieces up to its `Value` or `Bare`.
        loop {
            match pieces.next() {
                Some(Piece::Name(c)) => report.put(c),
                Some(Piece::Value(length)) => {
                    report.puts(b"=<");
                    report.dec(length);
                    report.put(b'>');
                    break;
                }
                Some(Piece::Bare(length)) => {
                    report.put(b'<');
                    report.dec(length);
                    report.put(b'>');
                    break;
                }
                None => break,
            }
        }
    }
    report.newline();
}

/// How many characters the next word of the command line takes on screen, or
/// 0 if there is no next word. Works on a copy; the caller's place is kept.
fn word_width(mut pieces: Cmdline) -> usize {
    let mut name = 0;
    loop {
        match pieces.next() {
            Some(Piece::Name(_)) => name += 1,
            Some(Piece::Value(length)) => return name + 3 + dec_width(length),
            Some(Piece::Bare(length)) => return 2 + dec_width(length),
            None => return 0,
        }
    }
}

/// How many digits `value` has in decimal.
fn dec_width(value: u32) -> usize {
    let mut width = 1;
    let mut rest = value;
    while rest >= 10 {
        rest /= 10;
        width += 1;
    }
    width
}

/// Nothing in this image can panic; the handler exists because `#![no_std]`
/// requires one. `make test-console` checks that the linked image contains no
/// panic code at all.
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}
