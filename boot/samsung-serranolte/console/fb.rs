//! fb.rs - a framebuffer, and the only code in the image that writes to it.
//!
//! One operation: fill a rectangle with a grey level. Every pixel the image
//! ever draws goes through `fill_rect`, which clips the rectangle to the panel,
//! so no caller can write outside the buffer whatever coordinates it passes.
//!
//! Nothing here knows the board. The address and the geometry are given when
//! the `Framebuffer` is made, so the same code serves any linear framebuffer.
//!
//! Writes are single bytes and volatile. Bytes, so that nothing here depends on
//! alignment (the phone enters with alignment checking on) or on the order of
//! the colour bytes (measured on the GT-I9195: blue, green, red); every byte of
//! a pixel gets the same value, so only greys can be drawn. Volatile, so that
//! the compiler keeps every write and keeps it in order with the image's one
//! register read. This is the simple form, not the fast one: a later image can
//! write words.

use core::ptr::write_volatile;

/// A linear framebuffer: `height` rows, `stride` bytes from one row to the
/// next, `width` pixels of `bytes_per_pixel` bytes at the start of each row.
pub struct Framebuffer {
    base: usize,
    width: usize,
    height: usize,
    stride: usize,
    bytes_per_pixel: usize,
}

impl Framebuffer {
    /// # Safety
    ///
    /// `base` must be the first byte of `stride * height` bytes of writable
    /// memory that nothing else uses for as long as the `Framebuffer` exists:
    /// not the image's code, data or stack, and not the bootloader's tag page.
    pub unsafe fn new(
        base: usize,
        width: usize,
        height: usize,
        stride: usize,
        bytes_per_pixel: usize,
    ) -> Self {
        Framebuffer { base, width, height, stride, bytes_per_pixel }
    }

    /// Pixels across.
    pub fn width(&self) -> usize {
        self.width
    }

    /// Pixel rows.
    pub fn height(&self) -> usize {
        self.height
    }

    /// Set every byte of every pixel in the rectangle to `shade`. The part of
    /// the rectangle that lies outside the panel is not drawn.
    pub fn fill_rect(&self, x: usize, y: usize, w: usize, h: usize, shade: u8) {
        if x >= self.width || y >= self.height {
            return;
        }
        let x_end = x.saturating_add(w).min(self.width);
        let y_end = y.saturating_add(h).min(self.height);
        // Byte offsets inside a row. Held to `stride`, so that the bound below
        // does not depend on `width` and `bytes_per_pixel` fitting in a row.
        let first = x.saturating_mul(self.bytes_per_pixel);
        let last = x_end.saturating_mul(self.bytes_per_pixel).min(self.stride);
        let mut row = y;
        while row < y_end {
            let line = self.base + row * self.stride;
            let mut offset = first;
            while offset < last {
                // SAFETY: row < height and offset < stride (both held above),
                // so the address is below base + stride * height: inside the
                // memory that `new`'s caller vouched for. A byte write needs
                // no alignment.
                unsafe { write_volatile((line + offset) as *mut u8, shade) };
                offset += 1;
            }
            row += 1;
        }
    }
}
