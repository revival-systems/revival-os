//! fb.rs - the framebuffer, and the only code in the image that writes to it.
//!
//! One operation: fill a rectangle with a grey level. Every pixel the image
//! ever draws goes through `fill_rect`, which clips the rectangle to the panel,
//! so no caller can write outside the buffer whatever coordinates it passes.
//!
//! Writes are single bytes and volatile. Bytes, so that nothing here depends on
//! alignment (the phone enters with alignment checking on) or on the order of
//! the colour bytes (measured: blue, green, red); every byte of a pixel gets
//! the same value, so only greys can be drawn. Volatile, so that the compiler
//! keeps every write and keeps it in order with the image's one register read.
//! This is the simple form, not the fast one: a later image can write words.

use core::ptr::write_volatile;

use crate::board;

/// The panel's framebuffer: `board::FB_STRIDE * board::FB_HEIGHT` bytes.
pub struct Framebuffer {
    base: usize,
}

impl Framebuffer {
    /// # Safety
    ///
    /// `base` must be the first byte of `board::FB_STRIDE * board::FB_HEIGHT`
    /// bytes of writable memory that nothing else in the image uses: not its
    /// code, data or stack, and not the bootloader's tag page.
    pub unsafe fn new(base: usize) -> Self {
        Framebuffer { base }
    }

    /// Set every byte of every pixel in the rectangle to `shade`. The part of
    /// the rectangle that lies outside the panel is not drawn.
    pub fn fill_rect(&self, x: usize, y: usize, w: usize, h: usize, shade: u8) {
        if x >= board::FB_WIDTH || y >= board::FB_HEIGHT {
            return;
        }
        let x_end = clip(x, w, board::FB_WIDTH);
        let y_end = clip(y, h, board::FB_HEIGHT);
        let first = x * board::FB_BYTES_PER_PIXEL;
        let last = x_end * board::FB_BYTES_PER_PIXEL;
        let mut row = y;
        while row < y_end {
            let line = self.base + row * board::FB_STRIDE;
            let mut offset = first;
            while offset < last {
                // SAFETY: row < FB_HEIGHT and offset < FB_WIDTH * FB_BYTES_PER_PIXEL
                // = FB_STRIDE (both ends were clipped above), so the address is
                // below base + FB_STRIDE * FB_HEIGHT: inside the buffer that
                // `new`'s caller vouched for. A byte write needs no alignment.
                unsafe { write_volatile((line + offset) as *mut u8, shade) };
                offset += 1;
            }
            row += 1;
        }
    }
}

/// `start + len`, held to `limit`. Never overflows.
fn clip(start: usize, len: usize, limit: usize) -> usize {
    let end = start.saturating_add(len);
    if end < limit {
        end
    } else {
        limit
    }
}
