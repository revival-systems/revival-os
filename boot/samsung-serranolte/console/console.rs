//! console.rs - text on the framebuffer: white characters on black.
//!
//! The panel is a grid of 30 columns by 40 lines. A `Console` owns a run of
//! whole lines (its window) and writes characters into it from the top left.
//! It never scrolls. When the window is full, further characters are dropped
//! and a `+` is drawn in the window's last cell, so a photograph shows that
//! something is missing.
//!
//! Nothing clears the whole screen first. A line is cleared (painted black) at
//! the moment the cursor enters it, so each line shows the bootloader's picture
//! until it is replaced, and `finish` clears the lines the text did not reach.
//!
//! No heap and no `core::fmt`: numbers are written by the two small routines
//! here. Characters outside ASCII 0x20 to 0x7E are drawn as `?`.

use crate::board;
use crate::fb::Framebuffer;
use crate::font;

/// Screen pixels per glyph pixel.
const SCALE: usize = 3;
/// One character cell: the glyph plus one glyph pixel of spacing on the right
/// and below.
const CELL_W: usize = (font::GLYPH_COLS + 1) * SCALE;
const CELL_H: usize = (font::GLYPH_ROWS + 1) * SCALE;

/// Characters per line, and lines on the panel.
pub const COLUMNS: usize = board::FB_WIDTH / CELL_W;
pub const LINES: usize = board::FB_HEIGHT / CELL_H;

// The grid covers the panel exactly: 30 x 18 = 540 and 40 x 24 = 960.
const _: () = assert!(COLUMNS == 30 && COLUMNS * CELL_W == board::FB_WIDTH);
const _: () = assert!(LINES == 40 && LINES * CELL_H == board::FB_HEIGHT);

const INK: u8 = 0xFF;
const PAPER: u8 = 0x00;
const UNKNOWN_CHAR: u8 = b'?';
const OVERFLOW_MARK: u8 = b'+';

/// A window of whole text lines on the framebuffer, with a cursor.
pub struct Console<'a> {
    fb: &'a Framebuffer,
    /// The screen line the window starts at.
    top: usize,
    /// How many lines the window has.
    lines: usize,
    /// Cursor line inside the window; equal to `lines` once the window is full.
    line: usize,
    /// Cursor column; may equal `COLUMNS` until the next character wraps.
    col: usize,
    /// Whether the `+` has been drawn.
    overflowed: bool,
}

impl<'a> Console<'a> {
    /// A console over `lines` screen lines starting at screen line `top`, with
    /// the cursor at its top left. Clears the first line.
    pub fn new(fb: &'a Framebuffer, top: usize, lines: usize) -> Self {
        let console = Console { fb, top, lines, line: 0, col: 0, overflowed: false };
        console.clear_line(0);
        console
    }

    /// Write one character. `\n` starts the next line; a character that would
    /// pass the last column starts the next line first.
    pub fn put(&mut self, c: u8) {
        if c == b'\n' {
            self.newline();
            return;
        }
        if self.col >= COLUMNS {
            self.newline();
        }
        if self.line >= self.lines {
            self.mark_overflow();
            return;
        }
        self.glyph(self.line, self.col, c);
        self.col += 1;
    }

    /// Write each character of `text`.
    pub fn puts(&mut self, text: &[u8]) {
        for &c in text {
            self.put(c);
        }
    }

    /// Move to the start of the next line and clear it. In a full window this
    /// does nothing.
    pub fn newline(&mut self) {
        if self.line < self.lines {
            self.line += 1;
            self.col = 0;
            self.clear_line(self.line);
        }
    }

    /// Write `value` as eight hexadecimal digits, capitals, leading zeros kept.
    pub fn hex32(&mut self, value: u32) {
        let mut shift: u32 = 32;
        while shift > 0 {
            shift -= 4;
            let digit = ((value >> shift) & 0xF) as u8;
            self.put(if digit < 10 { b'0' + digit } else { b'A' + (digit - 10) });
        }
    }

    /// Write `value` in decimal, without leading zeros.
    pub fn dec(&mut self, value: u32) {
        // A u32 has at most ten decimal digits; they are produced last first.
        let mut digits = [b'0'; 10];
        let mut count: usize = 0;
        let mut rest = value;
        loop {
            if let Some(slot) = digits.get_mut(count) {
                *slot = b'0' + (rest % 10) as u8;
            }
            count += 1;
            rest /= 10;
            if rest == 0 {
                break;
            }
        }
        while count > 0 {
            count -= 1;
            if let Some(&digit) = digits.get(count) {
                self.put(digit);
            }
        }
    }

    /// The cursor's column: how many characters the current line holds.
    pub fn column(&self) -> usize {
        self.col
    }

    /// Clear every line of the window below the cursor's line.
    pub fn finish(&self) {
        let mut line = self.line + 1;
        while line < self.lines {
            self.clear_line(line);
            line += 1;
        }
    }

    /// Paint one line of the window black. Lines outside the window are left
    /// alone.
    fn clear_line(&self, line: usize) {
        if line < self.lines {
            self.fb.fill_rect(0, (self.top + line) * CELL_H, board::FB_WIDTH, CELL_H, PAPER);
        }
    }

    /// Draw the lit pixels of one character in the cell at `line`, `col`.
    fn glyph(&self, line: usize, col: usize, c: u8) {
        let code = if c < font::FIRST_CODE || c > font::LAST_CODE { UNKNOWN_CHAR } else { c };
        let rows = match font::GLYPHS.get((code - font::FIRST_CODE) as usize) {
            Some(rows) => rows,
            None => return,
        };
        let x0 = col * CELL_W;
        let y0 = (self.top + line) * CELL_H;
        for (row, &bits) in rows.iter().enumerate() {
            let mut pixel: usize = 0;
            while pixel < font::GLYPH_COLS {
                if (bits >> (font::GLYPH_COLS - 1 - pixel)) & 1 != 0 {
                    self.fb.fill_rect(x0 + pixel * SCALE, y0 + row * SCALE, SCALE, SCALE, INK);
                }
                pixel += 1;
            }
        }
    }

    /// Draw the `+` in the window's last cell, once.
    fn mark_overflow(&mut self) {
        if self.overflowed || self.lines == 0 {
            return;
        }
        self.overflowed = true;
        let line = self.lines - 1;
        let col = COLUMNS - 1;
        self.fb.fill_rect(col * CELL_W, (self.top + line) * CELL_H, CELL_W, CELL_H, PAPER);
        self.glyph(line, col, OVERFLOW_MARK);
    }
}
