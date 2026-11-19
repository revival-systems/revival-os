//! main.rs - GT-I9195 Phase 2 image 3: the boot screen.
//!
//! `#![no_std]`, ARMv7-A (target `armv7a-none-eabi`, soft-float). DEVICE code,
//! built into build/boot-serrano-screen/screen.bin. It is entered through the
//! first image's own `kstart.S` and laid out by its `link.ld`, both used
//! unchanged, so everything that runs before Rust is the code that has already
//! run on the phone. docs/phase-2/screen-payload.md is the full description.
//!
//! What it does: shows what the console image (image 2) shows, in the owner's
//! design: panels, colours and smooth letters instead of white text on black.
//! The design is not computed here. It is stored pictures (assets.rs says
//! where they are): one background of everything that never changes, and
//! letters and small shapes for the values the phone finds out. This file
//! decides which value goes where; gfx.rs copies the pictures to the panel.
//!
//! What it touches: exactly what the console image touches. Outside its own
//! stack it WRITES only to the framebuffer at `board::FB_BASE`. It READS the
//! seven words kstart.S captured, the tag list (only inside the tag page, only
//! word-aligned), and exactly one register, the MDP4 framebuffer address,
//! after everything else is on screen. No heap, no allocator, no `svc`, no
//! timer, no watchdog, no interrupts, no `core::fmt`, and no path that can
//! panic (`make test-screen` checks the last one in the linked image).
//!
//! What it never shows: a value from the kernel command line, the serial tag's
//! words, or the content of a tag it does not know. Those hold the phone's
//! identifiers, and a photograph of this screen is evidence that gets shared.
//! The tag-list reader is the console image's own file, which cannot give a
//! value's bytes at all.
//!
//! A fault lands in kstart.S's halt-only vectors: what was drawn stays.

#![no_std]
#![no_main]

// The tag-list reader and the board's facts are the console image's own
// files, used unchanged; both have run on the phone. This image does not use
// every item in them.
#[allow(dead_code)]
#[path = "../console/atags.rs"]
mod atags;
#[allow(dead_code)]
#[path = "../console/board.rs"]
mod board;
// Generated tables. Not every number in them is used.
#[allow(dead_code)]
mod assets;
mod gfx;

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

use atags::{Cmdline, Piece, Step, Walk};
use gfx::{Font, Mask, Rgb, Screen};

// The stored pictures were made for this panel and this pixel format.
const _: () = assert!(assets::WIDTH == board::FB_WIDTH && assets::HEIGHT == board::FB_HEIGHT);
const _: () = assert!(board::FB_BYTES_PER_PIXEL == 3);

/// Loop turns between two steps of the counter: the console image's number.
const TICK_TURNS: u32 = 4_194_304;

/// Stripes drawn instead of the screen when the image runs at the wrong
/// address: the console image's pattern.
const MOVED_STRIPES: usize = 20;

/// The background the values of the upper panels are drawn on.
const BODY: Rgb = assets::BG_BODY;

/// Cells in the bar beside the counter.
const BAR_CELLS: usize = assets::BAR_CELL_X.len();

// --- self-test: the first image's table and sum ------------------------------
// Same table and algorithm as boot/samsung-serranolte/payload.rs, so the sum is
// the value the phone has already shown twice: 0x22BECBA4.
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

/// The three colours of a chip: its filled shape, its outline, and what is
/// written on it.
struct Chip {
    fill: Rgb,
    line: Rgb,
    text: Rgb,
}

/// A bit that is 1, and "OK".
const CHIP_GREEN: Chip = Chip {
    fill: assets::CHIP_GREEN_FILL_LIT,
    line: assets::CHIP_GREEN_LINE_LIT,
    text: assets::GREEN,
};
/// A bit that is 0.
const CHIP_GREY: Chip = Chip {
    fill: assets::CHIP_GREY_FILL_OFF,
    line: assets::CHIP_GREY_LINE_OFF,
    text: assets::CHIP_GREY_TEXT_OFF,
};
/// The processor mode.
const CHIP_PURPLE: Chip = Chip {
    fill: assets::CHIP_PURPLE_FILL_LIT,
    line: assets::CHIP_PURPLE_LINE_LIT,
    text: assets::PURPLE,
};
/// Something wrong.
const CHIP_RED: Chip = Chip {
    fill: assets::CHIP_RED_FILL_LIT,
    line: assets::CHIP_RED_LINE_LIT,
    text: assets::RED,
};

/// Image entry, called by kstart.S with the address of the seven words it
/// captured: r0, r1, r2, r3, CPSR, SCTLR and the address it was entered at.
///
/// Order: everything that only reads memory comes first. The one register read
/// comes after all of that is on screen, so that if it hangs or faults the
/// screen is complete except for the register's value and the counter, and its
/// status word still says "Reading".
///
/// It does not return, except in the wrong-address case below; then, as after
/// any fault, kstart.S halts.
#[no_mangle]
pub extern "C" fn payload_main(handoff: *const u32) {
    // SAFETY: kstart.S passes the address of eight words it has just pushed on
    // the stack (the seven captured values, then one word of padding). They
    // are word-aligned and stay in place for as long as this function runs.
    let captured: &[u32; 7] = unsafe { &*(handoff as *const [u32; 7]) };
    let [r0, r1, r2, r3, cpsr, sctlr, entry] = *captured;

    // SAFETY: board::FB_BASE is the start of the panel's framebuffer, which is
    // FB_STRIDE * FB_HEIGHT bytes and lies outside this image, its stack and
    // the tag page (the overlap table in docs/phase-2/screen-payload.md).
    // Nothing else here uses that memory.
    let screen = unsafe {
        Screen::new(board::FB_BASE, board::FB_WIDTH, board::FB_HEIGHT, board::FB_STRIDE)
    };

    // The image is linked for one address and uses absolute addresses for its
    // stored pictures. If the bootloader put it somewhere else, those would
    // point at memory that is not this image, so nothing stored can be
    // trusted. Draw stripes, which need nothing stored, and stop.
    if entry != board::LINK_ENTRY {
        draw_moved(&screen);
        return;
    }

    let ui = Ui { screen: &screen, blob: assets::BLOB };
    ui.background();
    ui.selftest();
    ui.registers([r0, r1, r2, r3]);
    ui.cpu_state(cpsr, sctlr);
    ui.boot_info(r1, entry, r2);
    ui.tags(r2);

    // The status word is put in a known state before the register is read.
    ui.status(&assets::MASK_READING, assets::AMBER);
    // SAFETY: one volatile read of a fixed, word-aligned register address; the
    // register is never written. Reading it on the phone has been measured.
    let mdp = unsafe { read_volatile(board::MDP_DMA_P_BUF_ADDR as *const u32) };
    ui.mdp(mdp);
    ui.status(&assets::MASK_RUNNING, assets::GREEN);

    // The counter. All eight digits are drawn once; after that only the
    // digits that change are redrawn, one cell each. The bar beside it has
    // sixteen cells, one of them lit: the one the counter's last four bits
    // name. It moves one cell at each step, so that a step can be seen from
    // further away than a digit can be read.
    let mut digit: usize = 0;
    while digit < 8 {
        ui.tick_digit(digit, 0);
        digit += 1;
    }
    let mut cell: usize = 0;
    while cell < BAR_CELLS {
        ui.bar_cell(cell, cell == 0);
        cell += 1;
    }
    let mut tick: u32 = 0;
    loop {
        screen_tick_wait();
        let next = tick.wrapping_add(1);
        let mut digit: usize = 0;
        while digit < 8 {
            let shift = 28 - 4 * digit as u32;
            let nibble = (next >> shift) & 0xF;
            if nibble != (tick >> shift) & 0xF {
                ui.tick_digit(digit, nibble);
            }
            digit += 1;
        }
        ui.bar_cell(tick as usize % BAR_CELLS, false);
        ui.bar_cell(next as usize % BAR_CELLS, true);
        tick = next;
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
pub extern "C" fn screen_tick_wait() {
    let mut turns: u32 = 0;
    let slot: *mut u32 = &mut turns;
    loop {
        // SAFETY: `slot` points at `turns`, which is live until this function
        // returns and which nothing else reads or writes. The accesses are
        // volatile so that the compiler keeps the loop instead of working
        // out its result.
        let now = unsafe { read_volatile(slot) };
        if now >= TICK_TURNS {
            break;
        }
        // SAFETY: `slot` points at `turns`, which is live until this function
        // returns and which nothing else reads or writes.
        unsafe { write_volatile(slot, now + 1) };
    }
}

/// White and black stripes across the whole panel. Uses nothing stored, so it
/// is right wherever the image was loaded.
fn draw_moved(screen: &Screen) {
    let height = screen.height() / MOVED_STRIPES;
    let mut stripe: usize = 0;
    while stripe < MOVED_STRIPES {
        let shade: u8 = if stripe & 1 == 0 { 0xFF } else { 0x00 };
        screen.fill_rect(0, stripe * height, screen.width(), height, [shade, shade, shade]);
        stripe += 1;
    }
}

/// The panel and the stored pictures: what every drawing function needs.
struct Ui<'a> {
    screen: &'a Screen,
    blob: &'a [u8],
}

/// What has been found in the tag list so far, and where the next
/// command-line word goes.
struct List {
    // A tag kind that has one place on the screen fills it once.
    core: bool,
    initrd: bool,
    revision: bool,
    serial: bool,
    /// Rows of the memory map used so far.
    mem_rows: usize,
    /// Tags that are not on the screen: a kind with no place on it, or one
    /// more of a kind than it has places for.
    not_shown: u32,
    /// A command-line tag's text had no terminating zero.
    unterminated: bool,
    /// Command-line words in the whole list.
    total: usize,
    /// Command-line words dealt with so far.
    placed: usize,
    /// Rows of the two columns: `assets::ROWS`, or more, closer together,
    /// when the list has more words than that holds.
    rows: usize,
    /// The pen on the head line, in sixteenths of a pixel, and how many
    /// characters still fit there.
    head_pen: usize,
    head_room: usize,
}

/// Words on the head line, and cells in the lower panel.
const HEAD_WORDS: usize = 2;
const CELLS: usize = 3;

impl List {
    fn new(total: usize) -> List {
        let rows = if total > HEAD_WORDS + 2 * assets::ROWS + CELLS {
            // Just enough rows for all the words, up to the most that fit.
            ((total - HEAD_WORDS - CELLS + 1) / 2).min(assets::ROWS_MAX)
        } else {
            assets::ROWS
        };
        List {
            core: false,
            initrd: false,
            revision: false,
            serial: false,
            mem_rows: 0,
            not_shown: 0,
            unterminated: false,
            total,
            placed: 0,
            rows,
            head_pen: assets::HEAD_X << 4,
            head_room: assets::HEAD_CHARS,
        }
    }

    /// How many command-line words the screen has places for.
    fn places(&self) -> usize {
        HEAD_WORDS + 2 * self.rows + CELLS
    }
}

/// A run of characters in the command-line font: where the pen is, and how
/// many more characters may be drawn. Characters past that are dropped.
struct Run {
    pen: usize,
    yc: usize,
    room: usize,
    bg: Rgb,
}

impl Run {
    fn put(&mut self, ui: &Ui, code: u8, colour: Rgb) {
        if self.room == 0 {
            return;
        }
        self.room -= 1;
        let font = &assets::FONT_PAR;
        self.pen = ui.screen.glyph(ui.blob, font, self.pen, self.yc, code, colour, self.bg);
    }

    /// A length, as `<123>`.
    fn length(&mut self, ui: &Ui, length: u32) {
        let mut digits = [0u8; 10];
        self.put(ui, b'<', assets::AMBER);
        for &digit in dec(length, &mut digits) {
            self.put(ui, digit, assets::AMBER_SOFT);
        }
        self.put(ui, b'>', assets::AMBER);
    }
}

/// A short line of text put together before it is drawn, so that its length
/// is known and it can be drawn to end at a given place.
struct Line {
    text: [u8; 48],
    len: usize,
}

impl Line {
    fn new() -> Line {
        Line { text: [b' '; 48], len: 0 }
    }

    /// Add `text`. What does not fit is dropped.
    fn push(&mut self, text: &[u8]) {
        for &code in text {
            if let Some(slot) = self.text.get_mut(self.len) {
                *slot = code;
                self.len += 1;
            }
        }
    }

    fn push_dec(&mut self, value: u32) {
        let mut digits = [0u8; 10];
        self.push(dec(value, &mut digits));
    }

    fn bytes(&self) -> &[u8] {
        match self.text.get(..self.len) {
            Some(text) => text,
            None => &[],
        }
    }
}

impl<'a> Ui<'a> {
    // --- the pieces everything is drawn with ---------------------------------

    /// `text` in `font` from pixel `x`; returns the pen after it.
    fn text(&self, font: &Font, x: usize, yc: usize, text: &[u8], fg: Rgb, bg: Rgb) -> usize {
        self.screen.text(self.blob, font, x, yc, text, fg, bg)
    }

    /// `text` in the command-line font, ending at pixel `right`.
    fn text_right(&self, right: usize, yc: usize, text: &[u8], fg: Rgb, bg: Rgb) {
        let width = (text.len() * assets::FONT_PAR.space16) >> 4;
        self.text(&assets::FONT_PAR, right.wrapping_sub(width), yc, text, fg, bg);
    }

    /// A value of the boot-information panel, on the row whose middle is `yc`.
    fn info(&self, yc: usize, text: &[u8]) {
        self.text(&assets::FONT_VAL, assets::INFO_X, yc, text, assets::WHITE, BODY);
    }

    /// A stored word, its left edge at `x`, on the row whose middle is `yc`.
    fn word(&self, mask: &Mask, x: usize, yc: usize, fg: Rgb, bg: Rgb) {
        self.screen.word(self.blob, mask, x, yc, fg, bg);
    }

    /// A chip with its top left corner at (x, y): its filled shape over
    /// `under`, then its outline. What is written on it goes over `chip.fill`.
    fn chip(&self, x: usize, y: usize, fill: &Mask, line: &Mask, chip: &Chip, under: Rgb) {
        self.screen.stored(self.blob, fill, x, y, chip.fill, under);
        self.screen.stored(self.blob, line, x, y, chip.line, chip.fill);
    }

    /// A chip with a stored word in its middle.
    fn chip_word(
        &self,
        x: usize,
        y: usize,
        fill: &Mask,
        line: &Mask,
        word: &Mask,
        chip: &Chip,
        under: Rgb,
    ) {
        self.chip(x, y, fill, line, chip, under);
        let word_x = x + fill.w.saturating_sub(word.w) / 2;
        let word_y = y + fill.h.saturating_sub(word.h) / 2;
        self.screen.stored(self.blob, word, word_x, word_y, chip.text, chip.fill);
    }

    /// A chip with `text` in the chip font in its middle.
    fn chip_text(
        &self,
        x: usize,
        y: usize,
        fill: &Mask,
        line: &Mask,
        text: &[u8],
        chip: &Chip,
        under: Rgb,
    ) {
        self.chip(x, y, fill, line, chip, under);
        let font = &assets::FONT_CHIP;
        let mut width: usize = 0;
        for &code in text {
            width += font.advance(code);
        }
        let mut pen = (x << 4) + (fill.w << 4).saturating_sub(width) / 2;
        let yc = y + fill.h / 2;
        for &code in text {
            pen = self.screen.glyph(self.blob, font, pen, yc, code, chip.text, chip.fill);
        }
    }

    // --- what is drawn, top to bottom ----------------------------------------

    /// Everything that never changes: one stored picture, the whole panel.
    fn background(&self) {
        let stream = self.blob.get(assets::BG_OFF..assets::BG_OFF + assets::BG_LEN);
        let palette = self.blob.get(assets::PALETTE_OFF..assets::PALETTE_OFF + 768);
        if let (Some(stream), Some(palette)) = (stream, palette) {
            self.screen.background(stream, palette);
        }
    }

    fn selftest(&self) {
        let sum = table_sum();
        self.text(
            &assets::FONT_ROW1,
            assets::SELF_X,
            assets::ROW1_Y,
            &hex8(sum),
            assets::WHITE,
            assets::BG_ROW1,
        );
        let good = sum == TABLE_SUM;
        let word = if good { &assets::MASK_OK } else { &assets::MASK_BAD };
        let chip = if good { &CHIP_GREEN } else { &CHIP_RED };
        self.chip_word(
            assets::SELF_CHIP_X,
            assets::SELF_CHIP_Y,
            &assets::MASK_OK1_FILL,
            &assets::MASK_OK1_LINE,
            word,
            chip,
            assets::BG_ROW1,
        );
    }

    /// r0 to r3 as kstart.S captured them.
    fn registers(&self, values: [u32; 4]) {
        for (&value, &yc) in values.iter().zip(assets::REG_Y.iter()) {
            self.text(&assets::FONT_VAL_REG, assets::REG_X, yc, &hex8(value), assets::AMBER, BODY);
        }
    }

    /// CPSR and SCTLR, each with the bits that matter as chips: green and 1
    /// when the bit is set, grey and 0 when it is not.
    fn cpu_state(&self, cpsr: u32, sctlr: u32) {
        let [cpsr_y, sctlr_y] = assets::STAT_Y;
        let [x0, x1, x2, x3, x4] = assets::CHIP_X;

        // CPSR: mode, then the IRQ, FIQ and abort masks and the Thumb bit.
        self.text(&assets::FONT_VAL, assets::STAT_X, cpsr_y, &hex8(cpsr), assets::AMBER, BODY);
        let top = cpsr_y - assets::CHIP_H / 2;
        self.chip_text(
            x0,
            top,
            &assets::MASK_BIT_FILL,
            &assets::MASK_BIT_LINE,
            mode_name(cpsr),
            &CHIP_PURPLE,
            BODY,
        );
        self.bit(x1, top, b'I', cpsr, 7);
        self.bit(x2, top, b'F', cpsr, 6);
        self.bit(x3, top, b'A', cpsr, 8);
        self.bit(x4, top, b'T', cpsr, 5);

        // SCTLR: MMU, data cache, instruction cache, alignment checking, high
        // vectors.
        self.text(&assets::FONT_VAL, assets::STAT_X, sctlr_y, &hex8(sctlr), assets::AMBER, BODY);
        let top = sctlr_y - assets::CHIP_H / 2;
        self.bit(x0, top, b'M', sctlr, 0);
        self.bit(x1, top, b'C', sctlr, 2);
        self.bit(x2, top, b'I', sctlr, 12);
        self.bit(x3, top, b'A', sctlr, 1);
        self.bit(x4, top, b'V', sctlr, 13);
    }

    /// One bit of `word` as a chip: its letter, a colon, and 1 or 0.
    fn bit(&self, x: usize, y: usize, letter: u8, word: u32, bit: u32) {
        let on = (word >> bit) & 1 != 0;
        let text = [letter, b':', if on { b'1' } else { b'0' }];
        let chip = if on { &CHIP_GREEN } else { &CHIP_GREY };
        self.chip_text(x, y, &assets::MASK_BIT_FILL, &assets::MASK_BIT_LINE, &text, chip, BODY);
    }

    /// The machine number (r1, in decimal, as it is listed), the entry address
    /// and the tag list's address (r2).
    fn boot_info(&self, r1: u32, entry: u32, r2: u32) {
        let [mach_y, entry_y, atags_y, ..] = assets::INFO_Y;
        let mut digits = [0u8; 10];
        self.info(mach_y, dec(r1, &mut digits));
        // Reached only when the entry address is the linked one.
        self.info(entry_y, &hex8(entry));
        self.chip_word(
            assets::ENTRY_CHIP_X,
            assets::ENTRY_CHIP_Y,
            &assets::MASK_OK2_FILL,
            &assets::MASK_OK2_LINE,
            &assets::MASK_OK,
            &CHIP_GREEN,
            BODY,
        );
        self.info(atags_y, &hex8(r2));
    }

    /// One word on a red chip beside the tag list's address: why the list was
    /// not read, or not read to a proper end.
    fn warn(&self, word: &[u8]) {
        self.chip_text(
            assets::WARN_X,
            assets::WARN_Y,
            &assets::MASK_WARN_FILL,
            &assets::MASK_WARN_LINE,
            word,
            &CHIP_RED,
            BODY,
        );
    }

    /// The bootloader's tag list, if r2 points at one inside the tag page.
    fn tags(&self, r2: u32) {
        if r2 < board::TAGS_PAGE_LO || r2 >= board::TAGS_PAGE_HI {
            self.warn(b"OUT");
            return;
        }
        if r2 & 3 != 0 {
            self.warn(b"ODD");
            return;
        }
        let count = ((board::TAGS_PAGE_HI - r2) / 4) as usize;
        // SAFETY: r2 is word-aligned and inside the tag page (both checked just
        // above), and `count` words from it end exactly at the end of that page.
        // The page is ordinary memory that the bootloader wrote before it started
        // this image; nothing writes it now, and this image never does.
        let words = unsafe { core::slice::from_raw_parts(r2 as *const u32, count) };
        if words.first().copied() == Some(atags::DEVICE_TREE_MAGIC) {
            self.warn(b"DTB");
            return;
        }

        // The list is read twice. The first time only counts the command
        // line's words: how many there are decides how they are laid out.
        let mut list = List::new(count_words(words));
        let mut stopped: &[u8] = b"";
        for step in Walk::new(words) {
            match step {
                Step::Tag { id, body } => self.tag(&mut list, id, body),
                Step::End { id: 0 } => {}
                // A tag of size 0 ends the walk whatever its kind, as it does
                // in the Linux kernel; a kind other than 0 is still a
                // malformed list.
                Step::End { .. } => stopped = b"KIND",
                Step::BadSize(_) => stopped = b"SIZE",
                Step::PastEnd => stopped = b"PAST",
                Step::TooMany => stopped = b"MANY",
            }
        }
        if !stopped.is_empty() {
            self.warn(stopped);
        }

        // What of the list is not on the screen. Nothing is said when all of
        // it is.
        let words_left = list.total.saturating_sub(list.places());
        if list.not_shown != 0 || words_left != 0 {
            let mut note = Line::new();
            note.push(b"NOT SHOWN:");
            if list.not_shown != 0 {
                note.push(b" ");
                note.push_dec(list.not_shown);
                note.push(b" TAGS");
            }
            if words_left != 0 {
                note.push(b" ");
                note.push_dec(words_left as u32);
                note.push(b" WORDS");
            }
            self.text_right(
                assets::LIST_RIGHT_X,
                assets::LIST_Y,
                note.bytes(),
                assets::RED,
                assets::BG_LIST,
            );
        }
        if list.unterminated {
            self.text_right(
                assets::TEXT_RIGHT_X,
                assets::TEXT_Y,
                b"CMDLINE UNTERMINATED",
                assets::RED,
                assets::BG_TEXT,
            );
        }
    }

    /// One tag. A kind that has no place on this screen is only counted: its
    /// words could be anything.
    fn tag(&self, list: &mut List, id: u32, body: &[u32]) {
        let [_, _, _, core_y, initrd_y, revision_y, serial_y] = assets::INFO_Y;
        match id {
            atags::ATAG_CORE if !list.core => {
                list.core = true;
                // flags, page size, root device; only the page size says anything.
                match body.get(1) {
                    Some(&page) => self.info(core_y, &hex8(page)),
                    None => self.info(core_y, b"-"),
                }
            }
            atags::ATAG_INITRD2 if !list.initrd => {
                list.initrd = true;
                match body {
                    [start, size, ..] => {
                        self.info(initrd_y, &hex8(*start));
                        let label = &assets::MASK_SZ;
                        self.word(label, assets::SZ_LABEL_X, initrd_y, assets::LABEL, BODY);
                        self.text(
                            &assets::FONT_SMALL,
                            assets::SZ_X,
                            initrd_y,
                            &hex8(*size),
                            assets::WHITE,
                            BODY,
                        );
                    }
                    _ => self.info(initrd_y, b"-"),
                }
            }
            atags::ATAG_REVISION if !list.revision => {
                list.revision = true;
                match body.first() {
                    Some(&revision) => self.info(revision_y, &hex8(revision)),
                    None => self.info(revision_y, b"-"),
                }
            }
            atags::ATAG_SERIAL if !list.serial => {
                list.serial = true;
                // The serial number is an identifier: say the tag is there, no
                // more.
                self.word(&assets::MASK_HIDDEN, assets::INFO_X, serial_y, assets::WHITE, BODY);
            }
            atags::ATAG_MEM if list.mem_rows < assets::MEM_Y.len() => {
                let yc = match assets::MEM_Y.get(list.mem_rows) {
                    Some(&yc) => yc,
                    None => return,
                };
                list.mem_rows += 1;
                self.word(&assets::MASK_MEM, assets::MEM_X, yc, assets::CYAN, BODY);
                let font = &assets::FONT_VAL;
                match body {
                    [size, address, ..] => {
                        self.text(font, assets::MEM_SIZE_X, yc, &hex8(*size), assets::AMBER, BODY);
                        self.word(&assets::MASK_AT, assets::MEM_AT_X, yc, assets::CYAN, BODY);
                        let start = hex8(*address);
                        self.text(font, assets::MEM_ADDR_X, yc, &start, assets::WHITE, BODY);
                    }
                    _ => {
                        self.text(font, assets::MEM_SIZE_X, yc, b"-", assets::AMBER, BODY);
                    }
                }
            }
            atags::ATAG_CMDLINE => self.cmdline(list, body),
            _ => list.not_shown += 1,
        }
    }

    /// The words of one command-line tag, each to the next free place.
    fn cmdline(&self, list: &mut List, body: &[u32]) {
        let mut pieces = Cmdline::new(body);
        if !pieces.is_terminated() {
            list.unterminated = true;
        }
        loop {
            let width = word_width(pieces);
            if width == 0 {
                break;
            }
            self.place_word(list, &mut pieces, width);
        }
    }

    /// Put the next word of `pieces`, which takes `width` characters, in the
    /// next free place: the first two words on the head line, then the two
    /// columns row by row, then the three cells of the lower panel. A word
    /// that has a place is always drawn, cut if it is too long for it. A word
    /// with no place left is read past and not drawn; `tags` says how many
    /// those were. Either way exactly one word of `pieces` is used up.
    fn place_word(&self, list: &mut List, pieces: &mut Cmdline, width: usize) {
        let index = list.placed;
        list.placed += 1;
        let in_columns = 2 * list.rows;

        // Where the word goes: pen, row middle, characters that fit, background.
        let place: Option<(usize, usize, usize, Rgb)> = if index < HEAD_WORDS {
            let room = if index == 0 {
                // The first word may not take the whole line: what it leaves
                // is enough for the second to show at least how it starts.
                assets::HEAD_FIRST_CHARS
            } else {
                // Two spaces between the words of the head line.
                list.head_pen += 2 * assets::FONT_PAR.space16;
                list.head_room = list.head_room.saturating_sub(2);
                list.head_room
            };
            Some((list.head_pen, assets::HEAD_Y, room, BODY))
        } else if index < HEAD_WORDS + in_columns {
            let row = (index - HEAD_WORDS) / 2;
            let col = (index - HEAD_WORDS) % 2;
            // The middle of this row, looked up for this number of rows.
            let yc = match assets::ROW_Y.get(list.rows.wrapping_sub(assets::ROWS)) {
                Some(rows_y) => rows_y.get(row).copied(),
                None => None,
            };
            match (assets::COL_X.get(col), assets::COL_CHARS.get(col), yc) {
                (Some(&x), Some(&room), Some(yc)) => Some((x << 4, yc, room, BODY)),
                _ => None,
            }
        } else {
            let cell = index - HEAD_WORDS - in_columns;
            match (assets::CFG_X.get(cell), assets::CFG_Y.get(cell), assets::CFG_CHARS.get(cell)) {
                (Some(&x), Some(&yc), Some(&room)) => Some((x << 4, yc, room, assets::BG_CFG)),
                _ => None,
            }
        };

        match place {
            Some((pen, yc, room, bg)) => {
                let (pen, drawn) = self.draw_word(pieces, width, pen, yc, room, bg);
                if index < HEAD_WORDS {
                    list.head_pen = pen;
                    list.head_room = list.head_room.saturating_sub(drawn);
                }
            }
            None => skip_word(pieces),
        }
    }

    /// Draw the next word of `pieces`: `NAME=<length>`, or `<length>` alone
    /// for a word with no `=`. At most `room` characters are drawn: a word
    /// that takes more (`width`) is cut, and its last character is then `~`.
    /// Returns the pen after the word and how many characters were drawn.
    fn draw_word(
        &self,
        pieces: &mut Cmdline,
        width: usize,
        pen: usize,
        yc: usize,
        room: usize,
        bg: Rgb,
    ) -> (usize, usize) {
        let cut = width > room;
        let mut run = Run { pen, yc, room: if cut { room.saturating_sub(1) } else { room }, bg };
        loop {
            match pieces.next() {
                Some(Piece::Name(code)) => run.put(self, printable(code), assets::NAME),
                Some(Piece::Value(length)) => {
                    run.put(self, b'=', assets::WHITE);
                    run.length(self, length);
                    break;
                }
                Some(Piece::Bare(length)) => {
                    run.length(self, length);
                    break;
                }
                None => break,
            }
        }
        if cut && room > 0 {
            run.room = 1;
            run.put(self, b'~', assets::WHITE);
        }
        (run.pen, if cut { room } else { width })
    }

    /// The display register's value, and whether it is the framebuffer's
    /// address.
    fn mdp(&self, value: u32) {
        let bg = assets::BG_CFG;
        let font = &assets::FONT_PAR;
        let digits = hex8(value);
        let mut pen = self.text(font, assets::MDP_X, assets::MDP_Y, &digits, assets::WHITE, bg);
        let is_fb = value as usize == board::FB_BASE;
        let verdict: &[u8] = if is_fb { b" IS FB" } else { b" NOT FB" };
        let colour = if is_fb { assets::LABEL } else { assets::RED };
        for &code in verdict {
            pen = self.screen.glyph(self.blob, font, pen, assets::MDP_Y, code, colour, bg);
        }
    }

    /// The word after "STATUS:". Its box is cleared first, so that the new
    /// word replaces the old one.
    fn status(&self, word: &Mask, colour: Rgb) {
        self.screen.fill_rect(
            assets::STATUS_BOX_X,
            assets::STATUS_BOX_Y,
            assets::STATUS_BOX_W,
            assets::STATUS_BOX_H,
            assets::BG_STATUS,
        );
        self.word(word, assets::STATUS_X, assets::STATUS_Y, colour, assets::BG_STATUS);
    }

    /// Digit `digit` of the counter (0 is the leftmost). Its cell is cleared
    /// first, so that a cell shows one digit whatever it showed before.
    fn tick_digit(&self, digit: usize, nibble: u32) {
        let font = &assets::FONT_TICK;
        let pen = (assets::TICK_X << 4) + digit * font.space16;
        self.screen.fill_rect(
            (pen >> 4).wrapping_sub(font.pad),
            assets::TICK_Y.wrapping_sub(font.up),
            font.cell_w,
            font.cell_h,
            assets::BG_STATUS,
        );
        self.screen.glyph(
            self.blob,
            font,
            pen,
            assets::TICK_Y,
            hex_digit(nibble),
            assets::AMBER,
            assets::BG_STATUS,
        );
    }

    /// One cell of the bar beside the counter, lit or dim. A cell's pixels
    /// are the same pixels either way, so drawing it replaces what it showed.
    /// The bar is not a progress bar: the image has nothing to be part-way
    /// through. Its lit cell only shows that the counter stepped.
    fn bar_cell(&self, cell: usize, lit: bool) {
        if let Some(&x) = assets::BAR_CELL_X.get(cell) {
            let colour = if lit { assets::BAR_LIT } else { assets::BAR_DIM };
            let shape = &assets::MASK_BAR_CELL;
            self.screen.stored(self.blob, shape, x, assets::BAR_CELL_Y, colour, assets::BAR_DARK);
        }
    }
}

/// How many words the command lines of the tag list in `words` hold.
fn count_words(words: &[u32]) -> usize {
    let mut total: usize = 0;
    for step in Walk::new(words) {
        if let Step::Tag { id: atags::ATAG_CMDLINE, body } = step {
            for piece in Cmdline::new(body) {
                // Every word ends with exactly one of these two.
                if matches!(piece, Piece::Value(_) | Piece::Bare(_)) {
                    total += 1;
                }
            }
        }
    }
    total
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

/// Read past the next word of the command line without drawing it.
fn skip_word(pieces: &mut Cmdline) {
    while let Some(Piece::Name(_)) = pieces.next() {}
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

/// `value` in decimal, written at the end of `digits`; returns the digits.
fn dec(value: u32, digits: &mut [u8; 10]) -> &[u8] {
    let mut at = digits.len();
    let mut rest = value;
    loop {
        at = at.saturating_sub(1);
        if let Some(slot) = digits.get_mut(at) {
            *slot = b'0' + (rest % 10) as u8;
        }
        rest /= 10;
        if rest == 0 {
            break;
        }
    }
    match digits.get(at..) {
        Some(text) => text,
        None => &[],
    }
}

/// `value` as eight hexadecimal digits.
fn hex8(value: u32) -> [u8; 8] {
    let mut text = [b'0'; 8];
    for (i, slot) in text.iter_mut().enumerate() {
        *slot = hex_digit((value >> (28 - 4 * i as u32)) & 0xF);
    }
    text
}

/// The character for one hexadecimal digit, 0 to 15.
fn hex_digit(nibble: u32) -> u8 {
    let nibble = (nibble & 0xF) as u8;
    if nibble < 10 {
        b'0' + nibble
    } else {
        b'A' + (nibble - 10)
    }
}

/// A byte of a command-line name as the character drawn for it: itself if it
/// is printable ASCII, `?` if it is not.
fn printable(code: u8) -> u8 {
    if (0x20..=0x7E).contains(&code) {
        code
    } else {
        b'?'
    }
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

/// Nothing in this image can panic; the handler exists because `#![no_std]`
/// requires one. `make test-screen` checks that the linked image contains no
/// panic code at all.
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}
