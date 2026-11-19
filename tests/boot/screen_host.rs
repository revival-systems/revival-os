//! screen_host.rs - host tests for the boot screen image's drawing module.
//!
//! The boot screen image's `gfx.rs` knows nothing of the board, so it also
//! builds for the machine that builds the image. This file builds it exactly
//! as it is, with Rust's standard test harness, and runs it against a
//! framebuffer that is ordinary memory with guard bytes on both sides.
//! `make test-screen` builds and runs it (test screen-host-tests). It is built
//! without optimisation, so an arithmetic overflow in any case tested here
//! stops the test.
//!
//! What this adds to the QEMU tests (tests/boot/run_screen.py): there the
//! image draws only its own, well-formed pictures at its own places. Here the
//! module is given what the image never gives it: rectangles and masks far
//! outside the panel, pictures cut short, a palette that is too small, a font
//! that points outside the stored pictures. Whatever it is given, it must not
//! write outside its buffer.
//!
//! Build: rustc --edition 2021 --test tests/boot/screen_host.rs

// The module is built whole; this file does not use every item in it.
#![allow(dead_code)]

#[path = "../../boot/samsung-serranolte/screen/gfx.rs"]
mod gfx;

use gfx::{Font, Mask, Rgb, Screen};

const GUARD: usize = 4096;
/// What the memory holds before anything is drawn. No test draws this value,
/// so a byte that still holds it was never written.
const NOISE: u8 = 0x55;
const UNDRAWN: Rgb = [NOISE; 3];
const BLACK: Rgb = [0, 0, 0];

/// Memory standing in for a panel: guard bytes, the pixel rows, guard bytes.
struct Panel {
    memory: Vec<u8>,
    width: usize,
    height: usize,
    stride: usize,
}

impl Panel {
    fn with_stride(width: usize, height: usize, stride: usize) -> Panel {
        Panel { memory: vec![NOISE; GUARD + stride * height + GUARD], width, height, stride }
    }

    fn new(width: usize, height: usize) -> Panel {
        Panel::with_stride(width, height, width * 3)
    }

    fn screen(&mut self) -> Screen {
        let base = self.memory.as_mut_ptr() as usize + GUARD;
        // SAFETY: `base` is the first of stride * height bytes inside `memory`.
        // This Panel owns that memory and never resizes it, and each test
        // keeps its Panel alive for as long as it uses the Screen.
        unsafe { Screen::new(base, self.width, self.height, self.stride) }
    }

    /// The colour of a pixel: red, green, blue.
    fn pixel(&self, x: usize, y: usize) -> Rgb {
        let at = GUARD + y * self.stride + x * 3;
        [self.memory[at + 2], self.memory[at + 1], self.memory[at]]
    }

    /// How many pixels have been drawn.
    fn written(&self) -> usize {
        let mut count = 0;
        for y in 0..self.height {
            for x in 0..self.width {
                if self.pixel(x, y) != UNDRAWN {
                    count += 1;
                }
            }
        }
        count
    }

    /// Nothing outside the pixel rows was written.
    fn guards_intact(&self) -> bool {
        let end = GUARD + self.stride * self.height;
        self.memory[..GUARD].iter().all(|&byte| byte == NOISE)
            && self.memory[end..].iter().all(|&byte| byte == NOISE)
    }
}

/// A mask of 3 x 2 pixels. Coverage levels: 15, 0, 8 in the top row and
/// 1, 15, 0 in the bottom row. A row of three pixels takes two bytes.
const MASK_3X2: [u8; 4] = [0xF0, 0x80, 0x1F, 0x00];

/// Two glyphs of 2 x 2 pixels: 'A' is its top row, 'B' is its left column.
const GLYPHS: [u8; 4] = [0xFF, 0x00, 0xF0, 0xF0];

/// A font of those two glyphs. 'A' moves the pen three pixels, 'B' one and a
/// half, a character with no glyph two and a half.
fn font() -> Font {
    let mut map = [0xFFu8; 96];
    map[(b'A' - 0x20) as usize] = 0;
    map[(b'B' - 0x20) as usize] = 1;
    Font { off: 0, cell_w: 2, cell_h: 2, up: 1, pad: 0, space16: 40, map, adv16: &[48, 24] }
}

#[test]
fn a_pixel_is_blue_green_red() {
    let mut panel = Panel::new(4, 2);
    let screen = panel.screen();
    screen.fill_rect(1, 0, 1, 1, [0x11, 0x22, 0x33]);
    assert_eq!(panel.memory[GUARD + 3..GUARD + 6], [0x33u8, 0x22, 0x11]);
    assert_eq!(panel.written(), 1);
    assert_eq!((screen.width(), screen.height()), (4, 2));
}

#[test]
fn fill_rect_never_leaves_the_panel() {
    let mut panel = Panel::new(8, 6);
    let screen = panel.screen();
    let big = usize::MAX;
    let rectangles: [(usize, usize, usize, usize); 8] = [
        (8, 0, 1, 1),
        (0, 6, 1, 1),
        (big, big, big, big),
        (big, 0, 2, 2),
        (0, big, 2, 2),
        (0, 0, 0, 5),
        (0, 0, 5, 0),
        (9, 9, big, big),
    ];
    for (x, y, w, h) in rectangles {
        screen.fill_rect(x, y, w, h, [1, 2, 3]);
    }
    assert_eq!(panel.written(), 0);
    screen.fill_rect(6, 4, 100, 100, [1, 2, 3]);
    assert_eq!(panel.written(), 4);
    screen.fill_rect(3, 2, big, big, [1, 2, 3]);
    assert_eq!(panel.written(), 20);
    screen.fill_rect(0, 0, 8, 6, [4, 5, 6]);
    assert_eq!(panel.written(), 48);
    assert_eq!(panel.pixel(7, 5), [4, 5, 6]);
    assert!(panel.guards_intact());
}

#[test]
fn row_padding_is_never_written() {
    // Four pixels a row, but fourteen bytes from one row to the next.
    let mut panel = Panel::with_stride(4, 3, 14);
    let screen = panel.screen();
    screen.fill_rect(0, 0, 4, 3, [9, 9, 9]);
    screen.background(&[0x7F, 0x01], &[0, 0, 0, 7, 7, 7]);
    assert_eq!(panel.written(), 12);
    for row in 0..3 {
        let padding = GUARD + row * 14 + 12;
        assert_eq!(panel.memory[padding..padding + 2], [NOISE, NOISE]);
    }
    assert!(panel.guards_intact());
}

#[test]
fn mask_blends_over_the_background_it_is_told() {
    let mut panel = Panel::new(5, 4);
    let screen = panel.screen();
    let ink: Rgb = [255, 150, 0];
    let paper: Rgb = [0, 30, 90];
    screen.mask(1, 1, 3, 2, &MASK_3X2, ink, paper);
    // (paper * (15 - level) + ink * level + 7) / 15, worked out by hand.
    assert_eq!(panel.pixel(1, 1), ink); // level 15
    assert_eq!(panel.pixel(2, 1), UNDRAWN); // level 0 draws nothing
    assert_eq!(panel.pixel(3, 1), [136, 94, 42]); // level 8
    assert_eq!(panel.pixel(1, 2), [17, 38, 84]); // level 1
    assert_eq!(panel.pixel(2, 2), ink);
    assert_eq!(panel.pixel(3, 2), UNDRAWN);
    assert_eq!(panel.written(), 4);
    assert!(panel.guards_intact());
}

#[test]
fn mask_is_clipped_on_every_side() {
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    let ink: Rgb = [9, 9, 9];
    // Over the right and bottom edges: only its top left pixel is on the panel.
    screen.mask(3, 2, 3, 2, &MASK_3X2, ink, BLACK);
    assert_eq!(panel.pixel(3, 2), ink);
    assert_eq!(panel.written(), 1);
    // A corner at (-1, -1), given the way the image gives it: wrapped. Its
    // bottom row lands on row 0, and of that row the middle pixel on column 0.
    screen.mask(usize::MAX, usize::MAX, 3, 2, &MASK_3X2, ink, BLACK);
    assert_eq!(panel.pixel(0, 0), ink);
    assert_eq!(panel.written(), 2);
    // Nowhere near the panel.
    screen.mask(1000, 1000, 3, 2, &MASK_3X2, ink, BLACK);
    screen.mask(usize::MAX - 100, 1, 3, 2, &MASK_3X2, ink, BLACK);
    screen.mask(1, usize::MAX - 100, 3, 2, &MASK_3X2, ink, BLACK);
    assert_eq!(panel.written(), 2);
    assert!(panel.guards_intact());
}

#[test]
fn mask_stops_where_its_data_ends() {
    let mut panel = Panel::new(4, 4);
    let screen = panel.screen();
    // Only the first row's two bytes are there: levels 15, 0, 8.
    screen.mask(0, 0, 3, 2, &MASK_3X2[..2], [1, 2, 3], BLACK);
    assert_eq!(panel.written(), 2);
    screen.mask(0, 2, 3, 2, &[], [1, 2, 3], BLACK);
    assert_eq!(panel.written(), 2);
    assert!(panel.guards_intact());
}

#[test]
fn stored_mask_and_word() {
    let mut panel = Panel::new(6, 5);
    let screen = panel.screen();
    let ink: Rgb = [50, 60, 70];
    // The mask is the last four bytes of these six.
    let blob: [u8; 6] = [0xAA, 0xAA, 0xF0, 0x80, 0x1F, 0x00];
    let mask = Mask { off: 2, w: 3, h: 2, dx: -1, up: 1 };
    // As a word at x = 2 on the row whose middle is y = 2: its ink starts one
    // pixel to the left and one row up, so its corner is (1, 1).
    screen.word(&blob, &mask, 2, 2, ink, BLACK);
    assert_eq!(panel.pixel(1, 1), ink);
    assert_eq!(panel.pixel(2, 2), ink);
    assert_eq!(panel.written(), 4);
    // The same mask by its corner.
    screen.stored(&blob, &mask, 3, 3, ink, BLACK);
    assert_eq!(panel.pixel(3, 3), ink);
    assert_eq!(panel.pixel(4, 4), ink);
    assert_eq!(panel.written(), 8);
    // A mask that is not wholly inside the stored pictures is not drawn.
    let outside = Mask { off: 3, w: 3, h: 2, dx: 0, up: 0 };
    screen.stored(&blob, &outside, 0, 0, [1, 1, 1], BLACK);
    let far = Mask { off: usize::MAX / 2, w: 3, h: 2, dx: 0, up: 0 };
    screen.stored(&blob, &far, 0, 0, [1, 1, 1], BLACK);
    assert_eq!(panel.written(), 8);
    assert!(panel.guards_intact());
}

#[test]
fn text_moves_the_pen_in_sixteenths_of_a_pixel() {
    let mut panel = Panel::new(12, 4);
    let screen = panel.screen();
    let font = font();
    let ink: Rgb = [7, 8, 9];
    // From x = 1, on the row whose middle is y = 2; a cell's top is one row up.
    //   'A' at pen 16, x = 1; the pen moves 48 to 64
    //   'B' at pen 64, x = 4; the pen moves 24 to 88
    //   '?' has no glyph: nothing is drawn; the pen moves 40 to 128
    //   'B' at pen 128, x = 8; the pen moves 24 to 152
    let pen = screen.text(&GLYPHS, &font, 1, 2, b"AB?B", ink, BLACK);
    assert_eq!(pen, 152);
    assert_eq!((panel.pixel(1, 1), panel.pixel(2, 1)), (ink, ink));
    assert_eq!((panel.pixel(4, 1), panel.pixel(4, 2)), (ink, ink));
    assert_eq!((panel.pixel(8, 1), panel.pixel(8, 2)), (ink, ink));
    assert_eq!(panel.written(), 6);
    assert!(panel.guards_intact());
}

#[test]
fn a_character_with_no_glyph_only_moves_the_pen() {
    let font = font();
    for code in [0u8, 0x1F, b' ', b'C', 0x7F, 0x80, 0xFF] {
        assert_eq!(font.glyph_of(code), None);
        assert_eq!(font.advance(code), 40);
    }
    assert_eq!((font.glyph_of(b'A'), font.advance(b'A')), (Some(0), 48));
    assert_eq!((font.glyph_of(b'B'), font.advance(b'B')), (Some(1), 24));
}

#[test]
fn a_glyph_cell_may_start_left_of_the_pen() {
    let mut panel = Panel::new(4, 4);
    let screen = panel.screen();
    let padded = Font { pad: 1, ..font() };
    // 'A' at pen 0 with one pixel of padding: its cell starts at x = -1, so
    // only the second pixel of its top row is on the panel.
    let pen = screen.glyph(&GLYPHS, &padded, 0, 1, b'A', [3, 3, 3], BLACK);
    assert_eq!(pen, 48);
    assert_eq!(panel.pixel(0, 0), [3, 3, 3]);
    assert_eq!(panel.written(), 1);
    assert!(panel.guards_intact());
}

#[test]
fn a_font_that_points_outside_the_pictures_draws_nothing() {
    let mut panel = Panel::new(8, 4);
    let screen = panel.screen();
    // 'B' would be two bytes from offset 3 of a four-byte blob.
    let shifted = Font { off: 1, ..font() };
    let pen = screen.text(&GLYPHS, &shifted, 0, 1, b"B", [3, 3, 3], BLACK);
    assert_eq!((pen, panel.written()), (24, 0));
    // A table that names a glyph the step table does not have.
    let short = Font { adv16: &[48], ..font() };
    assert_eq!(short.advance(b'B'), 40);
    assert!(panel.guards_intact());
}

/// Three colours, and a picture of 4 x 3 pixels that uses every operation:
///   row 0: four pixels of colour 1                 (01, n = 3)
///   row 1: colours 2 and 0                         (10, n = 1)
///          then two pixels equal to the row above  (00, n = 1)
///   row 2: four pixels equal to the row above      (11, n = 0, m = 3)
const PALETTE: [u8; 9] = [10, 11, 12, 20, 21, 22, 30, 31, 32];
const PICTURE: [u8; 8] = [0x43, 0x01, 0x81, 0x02, 0x00, 0x01, 0xC0, 0x03];
const C0: Rgb = [10, 11, 12];
const C1: Rgb = [20, 21, 22];
const C2: Rgb = [30, 31, 32];

fn rows(panel: &Panel) -> Vec<Vec<Rgb>> {
    (0..panel.height).map(|y| (0..panel.width).map(|x| panel.pixel(x, y)).collect()).collect()
}

#[test]
fn background_unpacks_every_operation() {
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    screen.background(&PICTURE, &PALETTE);
    assert_eq!(
        rows(&panel),
        vec![vec![C1, C1, C1, C1], vec![C2, C0, C1, C1], vec![C2, C0, C1, C1]]
    );
    assert!(panel.guards_intact());
}

#[test]
fn background_counts_colour_0_above_the_first_row() {
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    // Twelve pixels equal to the row above.
    screen.background(&[0xC0, 0x0B], &PALETTE);
    assert_eq!(rows(&panel), vec![vec![C0; 4]; 3]);
}

#[test]
fn background_stops_at_a_picture_cut_short() {
    for (cut, drawn) in [(0usize, 0usize), (1, 0), (2, 4), (3, 4), (4, 5), (5, 6), (6, 8), (7, 8)] {
        let mut panel = Panel::new(4, 3);
        let screen = panel.screen();
        screen.background(&PICTURE[..cut], &PALETTE);
        assert_eq!(panel.written(), drawn, "picture cut to {cut} bytes");
        assert!(panel.guards_intact());
    }
}

#[test]
fn background_stops_at_a_colour_the_palette_lacks() {
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    // Two colours only: the picture's fifth pixel has colour 2.
    screen.background(&PICTURE, &PALETTE[..6]);
    assert_eq!(panel.written(), 4);
    // A palette cut inside a colour does not have that colour.
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    screen.background(&PICTURE, &PALETTE[..5]);
    assert_eq!(panel.written(), 0);
    assert!(panel.guards_intact());
}

#[test]
fn background_never_draws_more_than_the_panel() {
    // A picture of 64 + 16384 pixels for a panel of twelve.
    let mut panel = Panel::new(4, 3);
    let screen = panel.screen();
    screen.background(&[0x7F, 0x02, 0xFF, 0xFF], &PALETTE);
    assert_eq!(rows(&panel), vec![vec![C2; 4]; 3]);
    assert!(panel.guards_intact());
    // A panel wider than the row the module keeps is not drawn at all.
    let mut wide = Panel::new(1025, 1);
    let screen = wide.screen();
    screen.background(&[0x7F, 0x01], &PALETTE);
    assert_eq!(wide.written(), 0);
    // A panel of no pixels.
    let mut none = Panel::new(0, 0);
    let screen = none.screen();
    screen.background(&PICTURE, &PALETTE);
    screen.fill_rect(0, 0, 9, 9, [1, 1, 1]);
    screen.mask(0, 0, 3, 2, &MASK_3X2, [1, 1, 1], BLACK);
    assert!(none.guards_intact());
}
