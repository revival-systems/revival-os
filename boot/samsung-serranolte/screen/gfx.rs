//! gfx.rs - a colour framebuffer and the few ways the boot screen draws on it.
//!
//! The boot screen is made of stored pictures (tools/gen_boot_screen.py makes
//! them; assets.rs says where they are). This file copies them to the panel.
//! It computes no shapes, no blur and no fonts:
//!
//!   - `background` unpacks one whole-screen picture, stored as colour
//!     numbers with a palette;
//!   - `mask` draws a small picture of coverage levels (0 to 15, four bits a
//!     pixel) in one colour over a background whose colour is known, so it
//!     never reads the framebuffer back;
//!   - `glyph` and `text` draw characters, each one such mask;
//!   - `fill_rect` paints a rectangle in one colour.
//!
//! Every write goes through `put_at`, which checks the byte offset against
//! the size of the buffer, so nothing here can write outside the buffer
//! whatever it is asked to draw and whatever the stored pictures hold.
//! Nothing here knows the board except the pixel format: three bytes a pixel
//! in the order blue, green, red, as measured on the GT-I9195.
//!
//! The arithmetic is fixed, and the host oracle (tests/boot/screen_v3.py)
//! does exactly the same: a coverage level `a` of colour `fg` over `bg` gives
//! (bg * (15 - a) + fg * a + 7) / 15 for each of red, green and blue.

use core::ptr::write_volatile;

/// A colour: red, green, blue.
pub type Rgb = [u8; 3];

/// Bytes a pixel.
const BPP: usize = 3;

/// The widest background picture `background` can unpack.
const MAX_WIDTH: usize = 1024;

/// A stored font: one mask of `cell_w` x `cell_h` coverage levels for each
/// glyph, one after the other from `off` in the stored pictures.
pub struct Font {
    pub off: usize,
    pub cell_w: usize,
    pub cell_h: usize,
    /// How far the top of a cell lies above the middle of its line of text.
    pub up: usize,
    /// How far the left edge of a cell lies to the left of the pen.
    pub pad: usize,
    /// The pen's step, in sixteenths of a pixel, for a character with no glyph.
    pub space16: usize,
    /// Glyph number for each character code from 0x20 to 0x7F; 255: none.
    pub map: [u8; 96],
    /// The pen's step after each glyph, in sixteenths of a pixel.
    pub adv16: &'static [u8],
}

impl Font {
    /// The glyph number of character `code`, if the font has one.
    pub fn glyph_of(&self, code: u8) -> Option<usize> {
        if code < 0x20 {
            return None;
        }
        match self.map.get((code - 0x20) as usize) {
            Some(&index) if index != 0xFF => Some(index as usize),
            _ => None,
        }
    }

    /// The pen's step for character `code`, in sixteenths of a pixel.
    pub fn advance(&self, code: u8) -> usize {
        let step = match self.glyph_of(code) {
            Some(index) => self.adv16.get(index).copied(),
            None => None,
        };
        match step {
            Some(step) => step as usize,
            None => self.space16,
        }
    }
}

/// A stored mask of `w` x `h` coverage levels at `off` in the stored pictures.
pub struct Mask {
    pub off: usize,
    pub w: usize,
    pub h: usize,
    /// For a word: where its ink starts, relative to the word's left edge.
    pub dx: isize,
    /// For a word: how far its top lies above the middle of its line.
    pub up: usize,
}

/// A framebuffer of three bytes a pixel: blue, green, red.
pub struct Screen {
    base: usize,
    width: usize,
    height: usize,
    stride: usize,
    /// `stride * height`: the size of the buffer in bytes.
    bytes: usize,
}

impl Screen {
    /// # Safety
    ///
    /// `base` must be the first byte of `stride * height` bytes of writable
    /// memory that nothing else uses for as long as the `Screen` exists: not
    /// the image's code, data or stack, and not the bootloader's tag page.
    pub unsafe fn new(base: usize, width: usize, height: usize, stride: usize) -> Self {
        Screen { base, width, height, stride, bytes: stride.saturating_mul(height) }
    }

    /// Pixels across.
    pub fn width(&self) -> usize {
        self.width
    }

    /// Pixel rows.
    pub fn height(&self) -> usize {
        self.height
    }

    /// Write one pixel at byte offset `at` of the buffer. An offset whose
    /// three bytes are not all inside the buffer is ignored.
    fn put_at(&self, at: usize, colour: Rgb) {
        if at >= self.bytes || self.bytes - at < BPP {
            return;
        }
        let [red, green, blue] = colour;
        let address = self.base + at;
        // SAFETY: at + 3 <= bytes (checked just above), and `new`'s caller
        // vouched for `bytes` bytes from `base`, so the three bytes written
        // are inside that memory. Byte writes need no alignment.
        unsafe {
            write_volatile(address as *mut u8, blue);
            write_volatile((address + 1) as *mut u8, green);
            write_volatile((address + 2) as *mut u8, red);
        }
    }

    /// Set the pixel at column `x` of row `y`. Coordinates outside the panel
    /// are ignored.
    fn put(&self, x: usize, y: usize, colour: Rgb) {
        if x >= self.width || y >= self.height {
            return;
        }
        // x < width and y < height, so neither product can overflow for any
        // panel whose buffer fits in memory.
        self.put_at(y * self.stride + x * BPP, colour);
    }

    /// Paint the rectangle in one colour. The part outside the panel is not
    /// drawn.
    pub fn fill_rect(&self, x: usize, y: usize, w: usize, h: usize, colour: Rgb) {
        let x_end = x.saturating_add(w).min(self.width);
        let y_end = y.saturating_add(h).min(self.height);
        let mut row = y;
        while row < y_end {
            let mut col = x;
            while col < x_end {
                self.put(col, row, colour);
                col += 1;
            }
            row += 1;
        }
    }

    /// Unpack a stored background picture over the whole panel, row by row
    /// from the top.
    ///
    /// `stream` is a run of operations, each one byte with its kind in the
    /// top two bits and n in the low six:
    ///
    ///   00 n        the next n+1 pixels equal the pixel one row up
    ///   01 n c      the next n+1 pixels have colour number c
    ///   10 n c...   the next n+1 pixels have the n+1 colour numbers that follow
    ///   11 n m      the next (n*256+m)+1 pixels equal the pixel one row up
    ///
    /// `palette` holds red, green, blue for each colour number. Above the
    /// first row every pixel counts as colour number 0. A stream that ends
    /// early, or names a colour the palette does not have, stops the picture
    /// there. The framebuffer is never read: the row above is kept here, as
    /// colour numbers.
    pub fn background(&self, stream: &[u8], palette: &[u8]) {
        if self.width == 0 || self.width > MAX_WIDTH {
            return;
        }
        // The colour numbers of the row above, replaced as this row is drawn.
        let mut line = [0u8; MAX_WIDTH];
        let mut bytes = stream.iter();
        let total = self.width.saturating_mul(self.height);
        // What a row's end adds to the byte offset: the row's padding.
        let skip = self.stride.saturating_sub(self.width * BPP);
        let mut done: usize = 0;
        let mut x: usize = 0;
        let mut at: usize = 0;
        while done < total {
            let op = match bytes.next() {
                Some(&op) => op,
                None => return,
            };
            let kind = op >> 6;
            let mut count = (op & 0x3F) as usize;
            if kind == 3 {
                match bytes.next() {
                    Some(&low) => count = (count << 8) | low as usize,
                    None => return,
                }
            }
            let mut run_colour: u8 = 0;
            if kind == 1 {
                match bytes.next() {
                    Some(&colour) => run_colour = colour,
                    None => return,
                }
            }
            count += 1;
            while count > 0 && done < total {
                let slot = match line.get_mut(x) {
                    Some(slot) => slot,
                    None => return,
                };
                if kind == 1 {
                    *slot = run_colour;
                } else if kind == 2 {
                    match bytes.next() {
                        Some(&colour) => *slot = colour,
                        None => return,
                    }
                }
                let entry = *slot as usize * 3;
                match palette.get(entry..entry + 3) {
                    Some(&[red, green, blue]) => self.put_at(at, [red, green, blue]),
                    _ => return,
                }
                at += BPP;
                x += 1;
                if x == self.width {
                    x = 0;
                    at += skip;
                }
                done += 1;
                count -= 1;
            }
        }
    }

    /// Draw a mask of `w` x `h` coverage levels, packed in `data` two pixels
    /// a byte (rows from the top, each row starting a new byte, the left
    /// pixel in the high four bits), in colour `fg` over a background known
    /// to be `bg`. Level 0 draws nothing. `x` and `y` are the mask's top left
    /// corner; they may have wrapped below zero for a mask that starts left
    /// of or above the panel.
    pub fn mask(&self, x: usize, y: usize, w: usize, h: usize, data: &[u8], fg: Rgb, bg: Rgb) {
        let table = blend_table(fg, bg);
        let row_bytes = (w + 1) / 2;
        let mut row: usize = 0;
        while row < h {
            let mut col: usize = 0;
            while col < w {
                let byte = match data.get(row * row_bytes + col / 2) {
                    Some(&byte) => byte,
                    None => return,
                };
                let level = if col & 1 == 0 { byte >> 4 } else { byte & 0x0F };
                if level != 0 {
                    if let Some(&colour) = table.get(level as usize) {
                        // Adding wraps a corner that was below zero back into
                        // range; `put` drops whatever is still outside.
                        self.put(x.wrapping_add(col), y.wrapping_add(row), colour);
                    }
                }
                col += 1;
            }
            row += 1;
        }
    }

    /// Draw a stored mask with its top left corner at (x, y).
    pub fn stored(&self, blob: &[u8], mask: &Mask, x: usize, y: usize, fg: Rgb, bg: Rgb) {
        let bytes = ((mask.w + 1) / 2) * mask.h;
        if let Some(data) = blob.get(mask.off..mask.off + bytes) {
            self.mask(x, y, mask.w, mask.h, data, fg, bg);
        }
    }

    /// Draw a stored word with its left edge at `x` and the middle of its
    /// line at `yc`.
    pub fn word(&self, blob: &[u8], mask: &Mask, x: usize, yc: usize, fg: Rgb, bg: Rgb) {
        // `dx` may be negative; as a `usize` it wraps, and adding wraps back.
        self.stored(blob, mask, x.wrapping_add(mask.dx as usize), yc.wrapping_sub(mask.up), fg, bg);
    }

    /// Draw one character. `pen` is the position in sixteenths of a pixel and
    /// `yc` the middle of the line; returns the pen after the character. A
    /// character the font has no glyph for only moves the pen.
    pub fn glyph(
        &self,
        blob: &[u8],
        font: &Font,
        pen: usize,
        yc: usize,
        code: u8,
        fg: Rgb,
        bg: Rgb,
    ) -> usize {
        if let Some(index) = font.glyph_of(code) {
            let bytes = font.cell_h * ((font.cell_w + 1) / 2);
            let start = font.off + index * bytes;
            if let Some(data) = blob.get(start..start + bytes) {
                let x = (pen >> 4).wrapping_sub(font.pad);
                self.mask(x, yc.wrapping_sub(font.up), font.cell_w, font.cell_h, data, fg, bg);
            }
        }
        pen + font.advance(code)
    }

    /// Draw `text` from pixel `x`; returns the pen after it, in sixteenths of
    /// a pixel.
    pub fn text(
        &self,
        blob: &[u8],
        font: &Font,
        x: usize,
        yc: usize,
        text: &[u8],
        fg: Rgb,
        bg: Rgb,
    ) -> usize {
        let mut pen = x << 4;
        for &code in text {
            pen = self.glyph(blob, font, pen, yc, code, fg, bg);
        }
        pen
    }
}

/// The colour for each coverage level 0..15 of `fg` over `bg`.
fn blend_table(fg: Rgb, bg: Rgb) -> [Rgb; 16] {
    let [fore_r, fore_g, fore_b] = fg;
    let [back_r, back_g, back_b] = bg;
    let mut table = [[0u8; 3]; 16];
    for (level, slot) in table.iter_mut().enumerate() {
        let a = level as u32;
        *slot = [blend(fore_r, back_r, a), blend(fore_g, back_g, a), blend(fore_b, back_b, a)];
    }
    table
}

/// One colour channel at coverage level `a` (0..15), rounded to nearest.
fn blend(fg: u8, bg: u8, a: u32) -> u8 {
    ((bg as u32 * (15 - a) + fg as u32 * a + 7) / 15) as u8
}
