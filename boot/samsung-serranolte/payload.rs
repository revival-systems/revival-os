//! payload.rs - GT-I9195 Phase 2 proof-of-execution payload (v1).
//!
//! `#![no_std]`, ARMv7-A (target `armv7a-none-eabi`, soft-float). DEVICE code:
//! the Rust half of the smallest image that proves Revival OS code runs on the
//! Samsung. Called by `kstart.S` after the stack and `.bss` are set up. It is
//! NOT the Phase 1 QEMU fixture (tests/qemu/virt-armv7/kernel.rs) and NOT the
//! kernel tree (ARCHITECTURE.md places `kernel/` at Phase 3).
//!
//! Memory (ADR 0001, owner's rule): native call stack + statically reserved
//! data only. No heap, no allocator. No `svc`.
//!
//! v1 LIGHTENS the PR #9 candidate spec (docs/phase-2/boot-payload-research.md,
//! "v1 payload decision"): it performs NO MMIO reads of the display controller,
//! timer or watchdog. It reads only CPU registers (captured by kstart.S) and,
//! conditionally, one word of RAM at r2. Its only writes are to the two
//! candidate framebuffers, which are RAM. The handoff values it paints are
//! whatever the emulator/bootloader supplies; on the phone they are what
//! Phase 2 measures.
//!
//! SIGNAL: both candidate framebuffers are painted (540x960, 3 bytes/pixel,
//! stride 1620), then eight recorded words are drawn as rows of 32 blocks
//! (MSB first, white = 1, black = 0) so a photograph carries the handoff state:
//!   0x88100000 filled bytes FF 00 00  (shows red or blue -> reveals byte order)
//!   0x88300000 filled bytes 00 FF 00  (green in either order)
//! The host oracle tests/boot/serrano_v1.py reproduces this byte for byte.

#![no_std]
#![no_main]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

// --- GT-I9195 board facts (docs/hardware/gt-i9195.md, PR #9) -----------------
// Inlined here rather than in a board/ module: v1 has a single native consumer,
// and ARCHITECTURE.md adds board/ dirs only when a milestone needs them. The
// host oracle holds the same constants; the byte-for-byte QEMU compare is what
// guarantees they agree (docs/phase-2 "v1 payload decision").
const FB_RED: usize = 0x8810_0000; // contested address from the Jan 2026 LKML report
const FB_GREEN: usize = 0x8830_0000; // the mainline-fork / reserved framebuffer
const WIDTH: usize = 540;
const HEIGHT: usize = 960;
const BPP: usize = 3;
const STRIDE: usize = 1620; // WIDTH * BPP, no padding

// Device RAM window for the conditional read of *r2. Start 0x80000000, size
// ~1.5 GiB (gt-i9195.md). r2 is read only if it lies here and is word-aligned;
// otherwise the recorded word is the sentinel below (e.g. r2 == 0 under QEMU).
const RAM_START: u32 = 0x8000_0000;
const RAM_END: u32 = 0x8000_0000 + 0x6000_0000; // 1.5 GiB -> 0xE000_0000
const R2_NOT_IN_RAM: u32 = 0xFFFF_FFFF;

// Completion marker: the payload's final write, one word to a scratch cell in
// the unreserved gap between the two framebuffers (0x8827_BB00..0x8830_0000).
// An external observer (the QEMU harness now; any future on-device probe) can
// poll it to know painting finished before reading the framebuffers, instead
// of racing a fixed delay. It is in RAM on both QEMU and the phone and touches
// nothing else. See docs/phase-2 "v1 payload decision".
const DONE_ADDR: usize = 0x8829_0000;
const DONE_VALUE: u32 = 0xD09E_D09E;

// Block geometry for the encoded word rows. 32 blocks * 16 px = 512 <= 540;
// 8 rows * 16 px = 128 <= 960. White = 0xFF bytes, black = 0x00 bytes (both
// order-independent, so the word rows read the same regardless of RGB/BGR).
const BLOCK_W: usize = 16;
const BLOCK_H: usize = 16;
const WORDS: usize = 8;

// --- checksum: reused verbatim from the Phase 1 fixture (trivial) ------------
// Same table and algorithm as tests/qemu/virt-armv7/kernel.rs, so the value is
// the same known constant and the host oracle can recompute it independently.
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

/// Fill a framebuffer with one 3-byte pixel value, every pixel.
fn fill(base: usize, px: [u8; BPP]) {
    let mut y = 0usize;
    while y < HEIGHT {
        let row = base + y * STRIDE;
        let mut x = 0usize;
        while x < WIDTH {
            let p = row + x * BPP;
            let mut c = 0usize;
            while c < BPP {
                // SAFETY: p is within [base, base + STRIDE*HEIGHT), the
                // framebuffer region, which does not overlap the image, its
                // stack, ATAGS or any reserved region (overlap table in
                // docs/phase-2/boot-payload-research.md). Single-threaded.
                unsafe { write_volatile((p + c) as *mut u8, px[c]) };
                c += 1;
            }
            x += 1;
        }
        y += 1;
    }
}

/// Draw one block (BLOCK_W x BLOCK_H) at block-column `bx`, block-row `by`.
/// `on` selects white (0xFF) or black (0x00); both are order-independent.
fn draw_block(base: usize, bx: usize, by: usize, on: bool) {
    let shade: u8 = if on { 0xFF } else { 0x00 };
    let x0 = bx * BLOCK_W;
    let y0 = by * BLOCK_H;
    let mut y = y0;
    while y < y0 + BLOCK_H {
        let row = base + y * STRIDE;
        let mut x = x0;
        while x < x0 + BLOCK_W {
            let p = row + x * BPP;
            let mut c = 0usize;
            while c < BPP {
                // SAFETY: as in `fill`; x < 512 <= WIDTH, y < 128 <= HEIGHT.
                unsafe { write_volatile((p + c) as *mut u8, shade) };
                c += 1;
            }
            x += 1;
        }
        y += 1;
    }
}

/// Draw the eight recorded words as rows of 32 blocks, MSB first.
fn draw_words(base: usize, words: &[u32; WORDS]) {
    let mut row = 0usize;
    while row < WORDS {
        let w = words[row];
        let mut bit = 0usize;
        while bit < 32 {
            let on = (w >> (31 - bit)) & 1 != 0;
            draw_block(base, bit, row, on);
            bit += 1;
        }
        row += 1;
    }
}

/// Payload entry, called by kstart.S with a pointer to the 7 captured words
/// [r0, r1, r2, r3, cpsr, sctlr, entry]. Returns after painting; kstart.S then
/// halts in a masked wfi loop.
#[no_mangle]
pub extern "C" fn payload_main(handoff: *const u32) {
    // SAFETY: kstart.S passes a 7-word array on the stack; it is valid and
    // aligned for the duration of this call.
    let h = unsafe { core::slice::from_raw_parts(handoff, 7) };
    let r0 = h[0];
    let r1 = h[1];
    let r2 = h[2];
    // h[3] (r3) is captured but not among the eight painted words (the spec
    // lists r0, r1, r2, CPSR, SCTLR, entry, *r2, checksum).
    let cpsr = h[4];
    let sctlr = h[5];
    let entry = h[6];

    // Conditional single read of *r2 (the only non-framebuffer memory access),
    // guarded so it never faults: r2 must be in device RAM and word-aligned.
    let at_r2 = if r2 >= RAM_START && r2 < RAM_END && (r2 & 3) == 0 {
        // SAFETY: r2 is within the device RAM window and word-aligned.
        unsafe { read_volatile(r2 as *const u32) }
    } else {
        R2_NOT_IN_RAM
    };

    let words: [u32; WORDS] = [r0, r1, r2, cpsr, sctlr, entry, at_r2, checksum()];

    fill(FB_RED, [0xFF, 0x00, 0x00]);
    fill(FB_GREEN, [0x00, 0xFF, 0x00]);
    draw_words(FB_RED, &words);
    draw_words(FB_GREEN, &words);

    // Final write: publish the completion marker. Must be last.
    // SAFETY: DONE_ADDR is a single word in RAM, in the scratch gap between the
    // framebuffers; it overlaps nothing else. Single-threaded.
    unsafe { write_volatile(DONE_ADDR as *mut u32, DONE_VALUE) };
}

/// This payload has no reachable panic in v1; the handler exists because
/// `#![no_std]` requires one. It halts (interrupts are already masked), with no
/// `svc` and no output. Structure mirrors the Phase 1 fixture's handler.
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {
        // SAFETY: wfi is a hint; always safe. Matches kstart.S's halt.
        unsafe { core::arch::asm!("wfi") };
    }
}
