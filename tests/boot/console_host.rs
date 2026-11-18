//! console_host.rs - host tests for the console image's modules.
//!
//! The console image's `fb.rs`, `console.rs`, `font.rs` and `atags.rs` know
//! nothing of the board, so they also build for the machine that builds the
//! image. This file builds them exactly as they are, with Rust's standard test
//! harness, and runs them against a framebuffer that is ordinary memory with
//! guard bytes on both sides. `make test-console` builds and runs it (test
//! console-host-tests). It is built without optimisation, so an arithmetic
//! overflow in any case tested here stops the test.
//!
//! What this adds to the QEMU tests (tests/boot/run_console.py): the Rust is
//! exercised case by case and not only through whole screens, and `fill_rect`
//! is given rectangles the image never asks for, far outside the panel, to
//! show that it cannot write outside its buffer.
//!
//! Build: rustc --edition 2021 --test tests/boot/console_host.rs

// The modules are built whole; this file does not use every item in them.
#![allow(dead_code)]

#[path = "../../boot/samsung-serranolte/console/atags.rs"]
mod atags;
#[path = "../../boot/samsung-serranolte/console/console.rs"]
mod console;
#[path = "../../boot/samsung-serranolte/console/fb.rs"]
mod fb;
#[path = "../../boot/samsung-serranolte/console/font.rs"]
mod font;

use atags::{Cmdline, Piece, Step, Walk};
use console::Console;
use fb::Framebuffer;

const BPP: usize = 3;
const GUARD: usize = 4096;
/// What the memory holds before anything is drawn. The modules draw only 0x00
/// and 0xFF, so a byte that still holds this was never written.
const NOISE: u8 = 0x55;
/// What a cell reads as when it is not exactly one glyph.
const BAD_CELL: char = '\u{fffd}';

/// Memory standing in for a panel: guard bytes, the pixel rows, guard bytes.
struct Screen {
    memory: Vec<u8>,
    width: usize,
    height: usize,
    stride: usize,
}

impl Screen {
    fn with_stride(width: usize, height: usize, stride: usize) -> Screen {
        Screen { memory: vec![NOISE; GUARD + stride * height + GUARD], width, height, stride }
    }

    fn new(width: usize, height: usize) -> Screen {
        Screen::with_stride(width, height, width * BPP)
    }

    /// A panel that is exactly `columns` by `lines` character cells.
    fn of_cells(columns: usize, lines: usize) -> Screen {
        Screen::new(columns * console::CELL_W, lines * console::CELL_H)
    }

    fn framebuffer(&mut self) -> Framebuffer {
        let base = self.memory.as_mut_ptr() as usize + GUARD;
        // SAFETY: `base` is the first of stride * height bytes inside `memory`.
        // This Screen owns that memory and never resizes it, and each test
        // keeps its Screen alive for as long as it uses the Framebuffer.
        unsafe { Framebuffer::new(base, self.width, self.height, self.stride, BPP) }
    }

    fn pixels(&self) -> &[u8] {
        &self.memory[GUARD..GUARD + self.stride * self.height]
    }

    fn guards_intact(&self) -> bool {
        let end = GUARD + self.stride * self.height;
        self.memory[..GUARD].iter().all(|&b| b == NOISE)
            && self.memory[end..].iter().all(|&b| b == NOISE)
    }
}

/// The character in one cell, read back from the pixels.
fn read_cell(screen: &Screen, line: usize, col: usize) -> char {
    let scale = console::CELL_W / (font::GLYPH_COLS + 1);
    let pixels = screen.pixels();
    let mut rows = [0u8; font::GLYPH_ROWS];
    for gy in 0..font::GLYPH_ROWS + 1 {
        for gx in 0..font::GLYPH_COLS + 1 {
            // One glyph pixel is a scale x scale block, all bytes alike.
            let x0 = col * console::CELL_W + gx * scale;
            let y0 = line * console::CELL_H + gy * scale;
            let first = pixels[y0 * screen.stride + x0 * BPP];
            for y in y0..y0 + scale {
                let start = y * screen.stride + x0 * BPP;
                if pixels[start..start + scale * BPP].iter().any(|&b| b != first) {
                    return BAD_CELL;
                }
            }
            let lit = match first {
                0xFF => true,
                0x00 => false,
                _ => return BAD_CELL,
            };
            if lit {
                // The spacing column and the spacing row are never lit.
                if gx == font::GLYPH_COLS || gy == font::GLYPH_ROWS {
                    return BAD_CELL;
                }
                rows[gy] |= 1 << (font::GLYPH_COLS - 1 - gx);
            }
        }
    }
    match font::GLYPHS.iter().position(|glyph| *glyph == rows) {
        Some(index) => (font::FIRST_CODE + index as u8) as char,
        None => BAD_CELL,
    }
}

/// The screen's text, every cell of every line.
fn cells(screen: &Screen) -> Vec<String> {
    let columns = screen.width / console::CELL_W;
    let lines = screen.height / console::CELL_H;
    let mut out = Vec::new();
    for line in 0..lines {
        let text: String = (0..columns).map(|col| read_cell(screen, line, col)).collect();
        out.push(text);
    }
    out
}

/// The screen's text with the spaces at the end of each line removed.
fn text(screen: &Screen) -> Vec<String> {
    cells(screen).iter().map(|line| line.trim_end().to_string()).collect()
}

/// For each text line, whether every byte of it has been written.
fn lines_written(screen: &Screen) -> Vec<bool> {
    let band = console::CELL_H * screen.stride;
    screen.pixels().chunks(band).map(|bytes| !bytes.contains(&NOISE)).collect()
}

// --- fb.rs ---------------------------------------------------------------------

#[test]
fn fill_rect_draws_exactly_the_part_inside_the_panel() {
    let (width, height) = (40, 30);
    let huge = usize::MAX;
    let rectangles: [(usize, usize, usize, usize, u8); 13] = [
        (0, 0, width, height, 0x00),    // the whole panel
        (3, 4, 5, 6, 0xFF),             // inside
        (38, 28, 10, 10, 0x80),         // over the right and bottom edges
        (0, 29, 40, 1, 0x11),           // the last row
        (39, 0, 1, 30, 0x22),           // the last column
        (40, 0, 1, 1, 0x33),            // just outside, to the right
        (0, 30, 1, 1, 0x44),            // just outside, below
        (10, 10, 0, 5, 0x66),           // no width
        (10, 10, 5, 0, 0x77),           // no height
        (5, 5, huge, huge, 0x88),       // sizes that would overflow
        (39, 29, huge, huge, 0x99),     // the last pixel, with such sizes
        (huge, huge, huge, huge, 0xAA), // everything out of range
        (huge, 0, 1, 1, 0xBB),
    ];
    let mut screen = Screen::new(width, height);
    let fb = screen.framebuffer();
    let mut model = vec![NOISE; width * BPP * height];
    for &(x, y, w, h, shade) in rectangles.iter() {
        fb.fill_rect(x, y, w, h, shade);
        for py in 0..height {
            for px in 0..width {
                // Inside the rectangle, said without a sum that could overflow.
                if px >= x && px - x < w && py >= y && py - y < h {
                    for byte in 0..BPP {
                        model[(py * width + px) * BPP + byte] = shade;
                    }
                }
            }
        }
        assert!(screen.pixels() == &model[..], "pixels differ after ({x}, {y}, {w}, {h})");
        assert!(screen.guards_intact(), "guard bytes written by ({x}, {y}, {w}, {h})");
    }
}

#[test]
fn fill_rect_leaves_the_padding_of_a_wider_stride_alone() {
    // 10 pixels of 3 bytes in rows 40 bytes apart: 10 bytes of padding a row.
    let mut screen = Screen::with_stride(10, 4, 40);
    let fb = screen.framebuffer();
    fb.fill_rect(0, 0, usize::MAX, usize::MAX, 0xFF);
    for (row, bytes) in screen.pixels().chunks(40).enumerate() {
        assert!(bytes[..30].iter().all(|&b| b == 0xFF), "pixels of row {row}");
        assert!(bytes[30..].iter().all(|&b| b == NOISE), "padding of row {row}");
    }
    assert!(screen.guards_intact());
}

#[test]
fn fill_rect_stays_inside_even_if_a_row_of_pixels_does_not_fit_the_stride() {
    // 10 pixels of 3 bytes cannot fit in rows 20 bytes apart. The buffer is
    // still only stride * height bytes, and nothing past it may be written.
    let mut screen = Screen::with_stride(10, 4, 20);
    let fb = screen.framebuffer();
    fb.fill_rect(0, 0, 10, 4, 0xFF);
    assert!(screen.pixels().iter().all(|&b| b == 0xFF));
    assert!(screen.guards_intact());
}

// --- console.rs ----------------------------------------------------------------

#[test]
fn text_reads_back() {
    let mut screen = Screen::of_cells(12, 3);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 3);
    console.puts(b"REVIVAL OS\nAb1~ !\n");
    console.finish();
    assert_eq!(text(&screen), ["REVIVAL OS", "Ab1~ !", ""]);
    assert_eq!(console.columns(), 12);
    assert!(screen.guards_intact());
}

#[test]
fn every_character_reads_back() {
    // 95 characters in 4 lines of 24.
    let mut screen = Screen::of_cells(24, 4);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 4);
    let all: Vec<u8> = (font::FIRST_CODE..=font::LAST_CODE).collect();
    console.puts(&all);
    console.finish();
    let shown = cells(&screen).concat();
    let want: String = all.iter().map(|&c| c as char).collect();
    assert_eq!(shown.trim_end(), want);
}

#[test]
fn long_text_wraps_at_the_last_column() {
    let mut screen = Screen::of_cells(5, 3);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 3);
    console.puts(b"ABCDEFG");
    assert_eq!(console.column(), 2);
    console.finish();
    assert_eq!(text(&screen), ["ABCDE", "FG", ""]);
}

#[test]
fn a_full_line_then_a_newline_does_not_skip_a_line() {
    let mut screen = Screen::of_cells(5, 3);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 3);
    console.puts(b"ABCDE\nF");
    console.finish();
    assert_eq!(text(&screen), ["ABCDE", "F", ""]);
}

#[test]
fn overflow_marks_the_last_cell_and_drops_the_rest() {
    let mut screen = Screen::of_cells(5, 2);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 2);
    console.puts(b"one\ntwo\nthree\nfour");
    console.finish();
    assert_eq!(text(&screen), ["one", "two +"]);
    assert!(screen.guards_intact());
}

#[test]
fn filling_the_window_exactly_is_not_overflow() {
    let mut screen = Screen::of_cells(5, 2);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 2);
    console.puts(b"ABCDEFGHIJ\n\n");
    console.finish();
    assert_eq!(text(&screen), ["ABCDE", "FGHIJ"]);
}

#[test]
fn numbers() {
    let mut screen = Screen::of_cells(12, 7);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 7);
    console.hex32(0x00C5_487A);
    console.newline();
    console.hex32(0xFFFF_FFFF);
    console.newline();
    console.hex32(0);
    console.newline();
    console.dec(0);
    console.put(b' ');
    console.dec(9);
    console.put(b' ');
    console.dec(10);
    console.newline();
    console.dec(3727);
    console.newline();
    console.dec(4_294_967_295);
    console.finish();
    assert_eq!(
        text(&screen),
        ["00C5487A", "FFFFFFFF", "00000000", "0 9 10", "3727", "4294967295", ""]
    );
    let digits: Vec<u8> = (0..16).map(console::hex_digit).collect();
    assert_eq!(digits, b"0123456789ABCDEF");
}

#[test]
fn characters_outside_printable_ascii_are_question_marks() {
    let mut screen = Screen::of_cells(6, 1);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 1);
    console.puts(&[0x00, 0x1F, 0x7F, 0xFF, b'A']);
    assert_eq!(text(&screen), ["????A"]);
}

#[test]
fn a_line_is_cleared_when_the_cursor_enters_it_and_finish_clears_the_rest() {
    let mut screen = Screen::of_cells(4, 4);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 4);
    // `new` clears the first line; the others still hold what was there.
    assert_eq!(lines_written(&screen), [true, false, false, false]);
    console.puts(b"A\nB");
    assert_eq!(lines_written(&screen), [true, true, false, false]);
    console.finish();
    assert_eq!(text(&screen), ["A", "B", "", ""]);
}

#[test]
fn a_window_draws_only_in_its_own_lines() {
    let mut screen = Screen::of_cells(4, 4);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 1, 2);
    console.puts(b"A\nB\nC\nD");
    console.finish();
    assert_eq!(lines_written(&screen), [false, true, true, false]);
    let shown = text(&screen);
    assert_eq!(shown[1], "A");
    assert_eq!(shown[2], "B  +");
    assert!(screen.guards_intact());
}

#[test]
fn replace_redraws_one_cell_and_nothing_else() {
    let mut screen = Screen::of_cells(6, 2);
    let fb = screen.framebuffer();
    let mut console = Console::new(&fb, 0, 2);
    console.puts(b"TICK 0");
    console.replace(5, b'7');
    assert_eq!(text(&screen)[0], "TICK 7");
    console.replace(0, b'K');
    assert_eq!(text(&screen)[0], "KICK 7");
    // A column past the end of the line is ignored, the cursor has not moved,
    // and the second line, which the cursor never entered, is untouched.
    console.replace(6, b'X');
    assert_eq!(text(&screen)[0], "KICK 7");
    assert_eq!(console.column(), 6);
    assert_eq!(lines_written(&screen), [true, false]);
    assert!(screen.guards_intact());
}

// --- font.rs -------------------------------------------------------------------

#[test]
fn glyphs_are_distinct_and_five_columns_wide() {
    for (index, glyph) in font::GLYPHS.iter().enumerate() {
        assert!(glyph.iter().all(|&row| row < 1 << font::GLYPH_COLS), "glyph {index}");
        assert!(font::GLYPHS[..index].iter().all(|other| other != glyph), "glyph {index}");
    }
    assert_eq!(font::GLYPH_COUNT, (font::LAST_CODE - font::FIRST_CODE) as usize + 1);
    assert_eq!(font::GLYPHS[0], [0; font::GLYPH_ROWS], "the space is empty");
}

// --- atags.rs: the walk --------------------------------------------------------

/// One tag: its size and kind words, then `body`.
fn tag(kind: u32, body: &[u32]) -> Vec<u32> {
    let mut words = vec![2 + body.len() as u32, kind];
    words.extend_from_slice(body);
    words
}

/// A walk written out, one line per step.
fn walk(words: &[u32]) -> Vec<String> {
    let mut steps = Vec::new();
    let mut walker = Walk::new(words);
    while let Some(step) = walker.next() {
        steps.push(match step {
            Step::Tag { id, body } => format!("tag {id:08X} +{}", body.len()),
            Step::End { id } => format!("end {id:08X} after {}", walker.seen()),
            Step::BadSize(size) => format!("bad size {size:08X}"),
            Step::PastEnd => "past end".to_string(),
            Step::TooMany => "too many".to_string(),
        });
    }
    assert!(walker.next().is_none(), "a finished walk gives nothing more");
    steps
}

#[test]
fn walk_gives_each_tag_and_the_end() {
    let mut list = tag(atags::ATAG_CORE, &[]);
    list.extend(tag(atags::ATAG_MEM, &[0x0800_0000, 0x8020_0000]));
    list.extend(tag(0x4D53_4D70, &[1, 2, 3]));
    list.extend([0u32, 0]); // the end tag
    list.extend([0xDEAD_BEEFu32; 8]); // after the end: never looked at
    assert_eq!(
        walk(&list),
        ["tag 54410001 +0", "tag 54410002 +2", "tag 4D534D70 +3", "end 00000000 after 3"]
    );
}

#[test]
fn walk_stops_at_what_is_not_a_tag() {
    let none: [u32; 0] = [];
    assert_eq!(walk(&none), ["past end"]);
    // One word: not even a header fits.
    assert_eq!(walk(&[0u32]), ["past end"]);
    assert_eq!(walk(&[0u32, 0]), ["end 00000000 after 0"]);
    // A size of 0 ends the walk whatever the kind word says.
    assert_eq!(walk(&[0u32, 0x1234]), ["end 00001234 after 0"]);
    assert_eq!(walk(&[1u32, atags::ATAG_MEM]), ["bad size 00000001"]);
    assert_eq!(walk(&[2049u32, atags::ATAG_MEM]), ["bad size 00000801"]);
    assert_eq!(walk(&[0xFFFF_FFFFu32, 0]), ["bad size FFFFFFFF"]);
    // A tag that claims one word more than there is.
    assert_eq!(walk(&[4u32, atags::ATAG_MEM, 1]), ["past end"]);
    // A tag that ends exactly where the words end: then no header fits.
    assert_eq!(walk(&[3u32, atags::ATAG_REVISION, 7]), ["tag 54410007 +1", "past end"]);
}

#[test]
fn walk_accepts_the_largest_tag() {
    let mut list: Vec<u32> = vec![2048, 0x1111_1111];
    list.resize(2048, 0xA5A5_A5A5);
    list.extend([0u32, 0]);
    assert_eq!(walk(&list), ["tag 11111111 +2046", "end 00000000 after 1"]);
}

#[test]
fn walk_gives_at_most_max_tags() {
    let one: [u32; 2] = [2, 0x3333_3333];
    let mut list: Vec<u32> = Vec::new();
    for _ in 0..atags::MAX_TAGS {
        list.extend(one);
    }
    let mut exactly = list.clone();
    exactly.extend([0u32, 0]);
    let steps = walk(&exactly);
    assert_eq!(steps.len(), atags::MAX_TAGS + 1);
    assert_eq!(steps[atags::MAX_TAGS], "end 00000000 after 64");

    list.extend(one);
    list.extend([0u32, 0]);
    let steps = walk(&list);
    assert_eq!(steps.len(), atags::MAX_TAGS + 1);
    assert_eq!(steps[atags::MAX_TAGS], "too many");
}

// --- atags.rs: the command line ------------------------------------------------

/// The body of a command-line tag holding `text`: with `terminate`, the text,
/// a zero byte and zeros up to a whole word; without, the text alone, which
/// must then be whole words.
fn text_words(text: &[u8], terminate: bool) -> Vec<u32> {
    let mut bytes = text.to_vec();
    if terminate {
        bytes.push(0);
        while bytes.len() % 4 != 0 {
            bytes.push(0);
        }
    }
    assert!(bytes.len() % 4 == 0, "an unterminated text must be whole words");
    bytes.chunks(4).map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]])).collect()
}

/// A command line as the image shows it: `name=<n>` or `<n>` for each word.
fn shown(body: &[u32]) -> String {
    let mut out = String::new();
    for piece in Cmdline::new(body) {
        match piece {
            Piece::Name(c) => out.push(c as char),
            Piece::Value(length) => out.push_str(&format!("=<{length}> ")),
            Piece::Bare(length) => out.push_str(&format!("<{length}> ")),
        }
    }
    out.trim_end().to_string()
}

fn shown_text(text: &[u8]) -> String {
    shown(&text_words(text, true))
}

#[test]
fn cmdline_gives_names_and_lengths() {
    assert_eq!(shown_text(b"a=1 bb=22 ccc=333"), "a=<1> bb=<2> ccc=<3>");
    assert_eq!(shown_text(b"quiet ro SECRET"), "<5> <2> <6>");
    assert_eq!(shown_text(b"a= =SECRET b==x"), "a=<0> =<6> b=<2>");
    assert_eq!(shown_text(b""), "");
    assert_eq!(shown_text(b"   "), "");
    assert_eq!(shown_text(b"  a=1\tb=2\nc=3\r\x0b\x0cd=4  "), "a=<1> b=<1> c=<1> d=<1>");
}

#[test]
fn cmdline_keeps_a_quoted_value_whole() {
    assert_eq!(shown_text(b"a=\"SECRET one two\" b=1"), "a=<16> b=<1>");
    // An unclosed quote takes the rest of the text into the value.
    assert_eq!(shown_text(b"a=\"SECRET b=1 c=2"), "a=<15>");
}

#[test]
fn cmdline_text_ends_at_its_zero_byte_or_at_the_end_of_the_body() {
    assert_eq!(shown_text(b"a=1\0b=SECRET"), "a=<1>");
    let cut = text_words(b"key=SECRET12", false);
    assert_eq!(shown(&cut), "key=<8>");
    assert!(!Cmdline::new(&cut).is_terminated());
    assert!(Cmdline::new(&text_words(b"key=1", true)).is_terminated());
    let none: [u32; 0] = [];
    assert!(!Cmdline::new(&none).is_terminated());
    assert_eq!(shown(&none), "");
}

#[test]
fn cmdline_never_gives_a_byte_of_a_value_or_of_a_word_without_equals() {
    let text = b"console=null serialno=SECRET5EC2E7 quiet label=\"SECRET with spaces\" \
                 SECRET5EC2E7 =SECRET";
    let body = text_words(text, true);
    let mut names: Vec<u8> = Vec::new();
    let mut lengths: Vec<u32> = Vec::new();
    for piece in Cmdline::new(&body) {
        match piece {
            Piece::Name(c) => names.push(c),
            Piece::Value(length) | Piece::Bare(length) => lengths.push(length),
        }
    }
    // Every byte the splitter gave out: the three names, and nothing else.
    assert_eq!(names, b"consoleserialnolabel");
    assert_eq!(lengths, [4u32, 12, 5, 20, 12, 6]);
}
