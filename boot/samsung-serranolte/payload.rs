//! payload.rs - GT-I9195 Phase 2 proof-of-execution payload (v1.1).
//!
//! `#![no_std]`, ARMv7-A (target `armv7a-none-eabi`, soft-float). DEVICE code:
//! the Rust half of the smallest image that proves Revival OS code runs on the
//! Samsung. Called by `kstart.S` after the stack and `.bss` are set up. It is
//! NOT the Phase 1 QEMU fixture (tests/qemu/virt-armv7/kernel.rs) and NOT the
//! kernel tree (ARCHITECTURE.md places `kernel/` at Phase 3).
//!
//! Memory (ADR 0001, owner's rule): native call stack + statically reserved
//! data only. No heap, no allocator. No `svc`. No timer, no watchdog.
//!
//! v1.1 still LIGHTENS the PR #9 candidate spec (docs/phase-2/boot-payload-research.md,
//! "v1 payload decision"). It reads CPU registers (captured by kstart.S), one
//! guarded word of RAM at *r2, and exactly ONE display-controller register (the
//! MDP4 framebuffer address) which it reads LAST, after a result is already on
//! screen, so a hang there costs nothing already painted. It writes ONLY to
//! framebuffers. The handoff values it paints are whatever the emulator or
//! bootloader supplies; on the phone they are what Phase 2 measures.
//!
//! SIGNAL: both candidate framebuffers are painted (540x960, 3 bytes/pixel,
//! stride 1620), then nine recorded words are drawn as rows of 32 blocks
//! (MSB first, white = 1, black = 0) so a photograph carries the handoff state:
//!   0x88100000 filled bytes FF 00 00  (shows red or blue -> reveals byte order)
//!   0x88300000 filled bytes 00 FF 00  (green in either order)
//! If the MDP4 register names a plausible third framebuffer, that is painted
//! grey (80 80 80) with the same rows. The host oracle tests/boot/serrano_v1.py
//! reproduces the two candidate buffers byte for byte.

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
const FB_BYTES: u64 = STRIDE as u64 * HEIGHT as u64; // 1_555_200

// The guarded read of *r2 is narrowed to the tags page [0x80200000, 0x80208000),
// where the bootloader's ATAGS/DTB pointer (tags_addr 0x80200100) should fall,
// and must be word-aligned. Anything else records the sentinel (e.g. r2 == 0
// under QEMU, which is outside this window).
const R2_READ_LO: u32 = 0x8020_0000;
const R2_READ_HI: u32 = 0x8020_8000;
const R2_OUT_OF_RANGE: u32 = 0xFFFF_FFFF;

// MDP4 DMA_P source-buffer address register (docs/phase-2 section 3). v1.1 reads
// it as the very LAST action, after a-b are painted, to discover the real
// framebuffer address on the device. In QEMU virt this address is flash and
// reads back 0x00000000, which fails the plausibility check (not in RAM).
const MDP_DMA_P_BUF_ADDR: usize = 0x0519_0008;

// Device DRAM and the reserved regions a discovered framebuffer must avoid
// (gt-i9195.md memory map). All half-open [lo, hi); checked by is_plausible_fb.
const DEV_RAM_LO: u64 = 0x8000_0000;
const DEV_RAM_HI: u64 = 0x8000_0000 + 0x6000_0000; // 1.5 GiB -> 0xE000_0000
const RESERVED: [(u64, u64); 6] = [
    (0x8020_0000, 0x8020_8000), // ATAGS / tags page
    (0x8020_8000, 0x8120_8000), // this image + its 64 KiB stack (link.ld, 16 MiB)
    (0x8000_0000, 0x8020_0000), // SMEM (2 MiB)
    (0x8830_0000, 0x8860_0000), // bootloader framebuffer reserved (3 MiB)
    (0x8F00_0000, 0x8F70_0000), // WCNSS (7 MiB)
    (0x8FB0_0000, 0x8FE0_0000), // modem rmtfs (3 MiB)
];
const GREY_PX: [u8; BPP] = [0x80, 0x80, 0x80];

// Block geometry for the encoded word rows. 32 blocks * 16 px = 512 <= 540;
// 9 rows * 16 px = 144 <= 960. White = 0xFF bytes, black = 0x00 bytes (both
// order-independent, so the word rows read the same regardless of RGB/BGR).
const BLOCK_W: usize = 16;
const BLOCK_H: usize = 16;

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
                // SAFETY: as in `fill`; x < 512 <= WIDTH, y < 144 <= HEIGHT.
                unsafe { write_volatile((p + c) as *mut u8, shade) };
                c += 1;
            }
            x += 1;
        }
        y += 1;
    }
}

/// Draw one 32-bit word as a row of 32 blocks (MSB first) at block-row `row`.
fn draw_row(base: usize, row: usize, value: u32) {
    let mut bit = 0usize;
    while bit < 32 {
        let on = (value >> (31 - bit)) & 1 != 0;
        draw_block(base, bit, row, on);
        bit += 1;
    }
}

/// Is `fb` a plausible real framebuffer to also paint? It must be word-aligned,
/// hold the whole 1620x960 buffer inside device RAM, differ from both candidate
/// addresses, and not overlap this image, its stack, ATAGS or any reserved
/// region (gt-i9195.md). Pure arithmetic; it performs no memory access.
fn is_plausible_fb(fb: u32) -> bool {
    if fb & 3 != 0 {
        return false;
    }
    let lo = fb as u64;
    let hi = lo + FB_BYTES;
    if lo < DEV_RAM_LO || hi > DEV_RAM_HI {
        return false;
    }
    if fb as usize == FB_RED || fb as usize == FB_GREEN {
        return false;
    }
    let mut i = 0usize;
    while i < RESERVED.len() {
        let (rlo, rhi) = RESERVED[i];
        if lo < rhi && rlo < hi {
            return false;
        }
        i += 1;
    }
    true
}

/// Payload entry, called by kstart.S with a pointer to the 7 captured words
/// [r0, r1, r2, r3, cpsr, sctlr, entry]. Returns after painting; kstart.S then
/// halts in a masked wfi loop. The image writes ONLY to framebuffers.
///
/// Order (v1.1): the risky steps run LAST, after a visible result is on screen.
///   a. fill both candidate framebuffers;
///   b. read *r2 (guarded) and draw the 8 handoff word rows in both;
///   c. read the MDP4 framebuffer-address register (the one display-controller
///      access, done last so a hang costs nothing already painted); draw it as
///      a 9th row, and if it names a plausible framebuffer, paint that grey and
///      draw all 9 rows there too.
#[no_mangle]
pub extern "C" fn payload_main(handoff: *const u32) {
    // SAFETY: kstart.S passes a 7-word array on the stack; valid for this call.
    let h = unsafe { core::slice::from_raw_parts(handoff, 7) };
    let r0 = h[0];
    let r1 = h[1];
    let r2 = h[2];
    // h[3] (r3) is captured but not painted.
    let cpsr = h[4];
    let sctlr = h[5];
    let entry = h[6];

    // Guarded single read of *r2: only inside the tags page and word-aligned.
    let at_r2 = if r2 >= R2_READ_LO && r2 < R2_READ_HI && (r2 & 3) == 0 {
        // SAFETY: r2 is inside the tags page and word-aligned.
        unsafe { read_volatile(r2 as *const u32) }
    } else {
        R2_OUT_OF_RANGE
    };

    // The 8 handoff words (the 9th, below, is the display register, read last).
    let words8: [u32; 8] = [r0, r1, r2, cpsr, sctlr, entry, at_r2, checksum()];

    // a. fill both candidate framebuffers.
    fill(FB_RED, [0xFF, 0x00, 0x00]);
    fill(FB_GREEN, [0x00, 0xFF, 0x00]);

    // b. draw the 8 handoff rows in both (visible before any risky read).
    let mut row = 0usize;
    while row < 8 {
        draw_row(FB_RED, row, words8[row]);
        draw_row(FB_GREEN, row, words8[row]);
        row += 1;
    }

    // c. the single display-controller read, done last. In QEMU virt it returns
    // 0 (flash); on the device it names the live framebuffer.
    // SAFETY: a single volatile read of a fixed MMIO/flash address; no write.
    let mdp = unsafe { read_volatile(MDP_DMA_P_BUF_ADDR as *const u32) };
    draw_row(FB_RED, 8, mdp);
    draw_row(FB_GREEN, 8, mdp);

    if is_plausible_fb(mdp) {
        let third = mdp as usize;
        fill(third, GREY_PX);
        let mut row = 0usize;
        while row < 8 {
            draw_row(third, row, words8[row]);
            row += 1;
        }
        draw_row(third, 8, mdp);
    }
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
