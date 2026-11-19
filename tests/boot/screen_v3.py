"""screen_v3.py - host oracle for the GT-I9195 Phase 2 boot screen image.

Works out, on the host and without the image, the exact bytes the boot screen
image (boot/samsung-serranolte/screen/) must leave in the framebuffer for a
given handoff, tag page, display-register value and counter value. The QEMU
test (tests/boot/run_screen.py) compares real framebuffer dumps with
expected_fb(...) byte for byte.

The image and this oracle share DATA, not code: both read the stored pictures
(assets.bin) and the layout numbers that tools/gen_boot_screen.py wrote
(assets.rs for the image, assets.json for this file). What is drawn where, and
from which value, is written twice: in Rust there and in Python here, from the
description in docs/phase-2/screen-payload.md. Where the two disagree, one of
them is wrong.

The drawing rules, which the image follows exactly:

  pixel      three bytes in the framebuffer: blue, green, red
  blend      a stored coverage level a (0..15) of colour fg over a known
             background colour bg gives, for each of red, green and blue,
             (bg * (15 - a) + fg * a + 7) // 15; a level of 0 draws nothing
  text       a pen position in sixteenths of a pixel; a glyph is drawn with
             its cell's left edge at (pen >> 4) - pad and its top at the
             line's middle minus the font's `up`; then the pen moves by the
             glyph's advance

Python standard library only. Nothing here touches a device or a network.

  python3 -m tests.boot.screen_v3 --png build/boot-screen-sample.png
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

from tests.boot import console_v2 as con  # the tag-list reader's oracle, and the tag builders

DIR = Path(__file__).resolve().parents[2] / "boot/samsung-serranolte/screen"
A = json.loads((DIR / "assets.json").read_text(encoding="ascii"))
BLOB = (DIR / "assets.bin").read_bytes()

W, H = A["width"], A["height"]
BPP = 3
STRIDE = W * BPP
FB_BYTES = STRIDE * H
FB_BASE = con.FB_BASE
LINK_ENTRY = con.LINK_ENTRY
L = A["layout"]
C = {name: tuple(rgb) for name, rgb in A["colours"].items()}
SELFTEST_SUM = con.SELFTEST_SUM
MOVED_STRIPES = 20


def check_assets() -> None:
    """The stored pictures are the ones the index describes."""
    if len(BLOB) != A["blob_len"] or hashlib.sha256(BLOB).hexdigest() != A["blob_sha256"]:
        raise ValueError("assets.bin is not the file assets.json describes")


class Screen:
    """A framebuffer, and the image's few ways of drawing into it."""

    def __init__(self):
        self.fb = bytearray(FB_BYTES)

    def put(self, x: int, y: int, rgb) -> None:
        if 0 <= x < W and 0 <= y < H:
            at = y * STRIDE + x * BPP
            self.fb[at], self.fb[at + 1], self.fb[at + 2] = rgb[2], rgb[1], rgb[0]

    def fill_rect(self, x: int, y: int, w: int, h: int, rgb) -> None:
        if x < 0 or y < 0:
            raise ValueError("the image never starts a rectangle off the panel")
        for yy in range(y, min(H, y + h)):
            for xx in range(x, min(W, x + w)):
                self.put(xx, yy, rgb)

    def background(self) -> None:
        """Unpack the stored background picture over the whole screen."""
        stream = BLOB[A["bg_off"]:A["bg_off"] + A["bg_len"]]
        pal = BLOB[A["palette_off"]:A["palette_off"] + 768]
        line = bytearray(W)  # the colour numbers of the row above, then of this row
        i = at = 0
        total = W * H
        while at < total and i < len(stream):
            kind, n = stream[i] >> 6, stream[i] & 0x3F
            i += 1
            if kind == 3:
                n = (n << 8) | stream[i]
                i += 1
            if kind == 1:
                colour = stream[i]
                i += 1
            for _ in range(n + 1):
                if at >= total:
                    break
                x = at % W
                if kind == 1:
                    line[x] = colour
                elif kind == 2:
                    line[x] = stream[i]
                    i += 1
                c = line[x]
                self.put(x, at // W, pal[3 * c:3 * c + 3])
                at += 1

    def mask(self, x: int, y: int, w: int, h: int, off: int, fg, bg) -> None:
        """Draw a stored mask of w x h coverage levels in colour fg over bg."""
        lut = [tuple((bg[k] * (15 - a) + fg[k] * a + 7) // 15 for k in range(3)) for a in range(16)]
        row_bytes = (w + 1) // 2
        for j in range(h):
            for i in range(w):
                byte = BLOB[off + j * row_bytes + i // 2]
                a = byte >> 4 if i % 2 == 0 else byte & 0xF
                if a:
                    self.put(x + i, y + j, lut[a])

    def glyph(self, font: dict, pen: int, yc: int, code: int, fg, bg) -> int:
        """Draw one character; returns the pen after it."""
        index = font["chars"].find(chr(code)) if 0x20 <= code < 0x80 else -1
        if index < 0:
            return pen + font["space16"]
        glyph_bytes = font["cell_h"] * ((font["cell_w"] + 1) // 2)
        self.mask((pen >> 4) - font["pad"], yc - font["up"], font["cell_w"], font["cell_h"],
                  font["off"] + index * glyph_bytes, fg, bg)
        return pen + font["adv16"][index]

    def text(self, font: dict, x: int, yc: int, s: str, fg, bg) -> int:
        pen = x << 4
        for ch in s:
            pen = self.glyph(font, pen, yc, ord(ch), fg, bg)
        return pen

    def text_right(self, right: int, yc: int, s: str, fg, bg) -> None:
        """Text in the command-line font that ends at pixel `right`."""
        font = A["fonts"]["PAR"]
        self.text(font, right - ((len(s) * font["space16"]) >> 4), yc, s, fg, bg)

    def status(self, name: str, fg) -> None:
        """The word after "STATUS:": its box is cleared, then the word drawn."""
        self.fill_rect(L["STATUS_BOX_X"], L["STATUS_BOX_Y"], L["STATUS_BOX_W"], L["STATUS_BOX_H"],
                       C["BG_STATUS"])
        self.word(A["masks"][name], L["STATUS_X"], L["STATUS_Y"], fg, C["BG_STATUS"])

    def tick_digit(self, i: int, digit: str) -> None:
        """Digit `i` (0 is the leftmost) of the counter: its cell is cleared,
        then the digit drawn, so a cell shows one digit whatever it showed."""
        font = A["fonts"]["TICK"]
        pen = (L["TICK_X"] << 4) + i * font["space16"]
        self.fill_rect((pen >> 4) - font["pad"], L["TICK_Y"] - font["up"], font["cell_w"],
                       font["cell_h"], C["BG_STATUS"])
        self.glyph(font, pen, L["TICK_Y"], ord(digit), C["AMBER"], C["BG_STATUS"])

    def word(self, m: dict, x: int, yc: int, fg, bg) -> None:
        """A stored word, its left edge at x and its middle line at yc."""
        self.mask(x + m["dx"], yc - m["up"], m["w"], m["h"], m["off"], fg, bg)

    def chip(self, x: int, y: int, shape: str, colour: str, lit: bool, under) -> tuple:
        """A chip's filled shape and outline; returns its fill colour, the
        background of whatever is then written on it."""
        state = "LIT" if lit else "OFF"
        fill = C[f"CHIP_{colour}_FILL_{state}"]
        f, ln = A["masks"][f"{shape}_FILL"], A["masks"][f"{shape}_LINE"]
        self.mask(x, y, f["w"], f["h"], f["off"], fill, under)
        self.mask(x, y, ln["w"], ln["h"], ln["off"], C[f"CHIP_{colour}_LINE_{state}"], fill)
        return fill

    def chip_text(self, x: int, y: int, shape: str, s: str, colour: str, lit: bool, under) -> None:
        """A chip with text from the chip font, centred."""
        fill = self.chip(x, y, shape, colour, lit, under)
        font, f = A["fonts"]["CHIP"], A["masks"][f"{shape}_FILL"]
        width = sum(font["adv16"][font["chars"].index(ch)] for ch in s)
        pen = (x << 4) + ((f["w"] << 4) - width) // 2
        fg = C[colour] if lit else C[f"CHIP_{colour}_TEXT_OFF"]
        for ch in s:
            pen = self.glyph(font, pen, y + f["h"] // 2, ord(ch), fg, fill)

    def chip_word(self, x: int, y: int, shape: str, name: str, colour: str, under) -> None:
        """A lit chip with a stored word centred on it."""
        fill = self.chip(x, y, shape, colour, True, under)
        f, m = A["masks"][f"{shape}_FILL"], A["masks"][name]
        self.mask(x + (f["w"] - m["w"]) // 2, y + (f["h"] - m["h"]) // 2, m["w"], m["h"], m["off"],
                  C[colour], fill)


# --- what is drawn ------------------------------------------------------------

MODE_NAMES = con.MODE_NAMES


def _words(page: bytes, r2: int):
    """Read the tag list. Returns (problem, tags, how_it_ended): problem is
    a key of WARN_WORDS, or None for a list that was read to a proper end."""
    if not con.TAGS_PAGE_LO <= r2 < con.TAGS_PAGE_HI:
        return "out", [], None
    if r2 % 4:
        return "odd", [], None
    words = con._words(page, r2)
    if words[0] == con.DEVICE_TREE_MAGIC:
        return "dtb", [], None
    tags, ended = con.parse_tags(words)
    if ended[0] != "end":
        return ended[0], tags, ended
    return ("kind" if ended[1] != 0 else None), tags, ended


def _piece_text(name: bytes, value_length, word_length) -> list:
    """A command-line word as (character, colour name) pairs."""
    out = []
    if value_length is not None:
        out += [(chr(b) if 0x20 <= b <= 0x7E else "?", "NAME") for b in name]
        out.append(("=", "WHITE"))
        number = str(value_length)
    else:
        number = str(word_length)
    out.append(("<", "AMBER"))
    out += [(d, "AMBER_SOFT") for d in number]
    out.append((">", "AMBER"))
    return out


def _draw_word(s: Screen, pen: int, yc: int, piece: list, limit: int, bg) -> tuple:
    """Draw a word from pen position `pen` (in sixteenths), at most `limit`
    characters: a longer word is cut, and its last character is then `~`.
    Returns (the pen after it, how many characters were drawn)."""
    font = A["fonts"]["PAR"]
    if len(piece) > limit:
        piece = piece[:limit - 1] + [("~", "WHITE")] if limit > 0 else []
    for ch, colour in piece:
        pen = s.glyph(font, pen, yc, ord(ch), C[colour], bg)
    return pen, len(piece)


def word_places(n: int) -> tuple:
    """Where `n` command-line words go. Returns (rows, shown): how many rows
    the two columns have, and how many of the words have a place. Two words go
    on the head line and three in the lower panel; the rest fill the columns,
    row by row. The columns have L["ROWS"] rows; a list with more words than
    that holds gets just enough rows, closer together, up to L["ROWS_MAX"]."""
    rows = L["ROWS"]
    if n > 2 + 2 * rows + 3:
        rows = min(L["ROWS_MAX"], (n - 4) // 2)
    return rows, min(n, 2 + 2 * rows + 3)


# One word for why a tag list was not read, or not read to its end.
WARN_WORDS = {"out": "OUT",        # r2 does not point into the tag page
              "odd": "ODD",        # r2 is not a multiple of four
              "dtb": "DTB",        # a device tree is there, not a tag list
              "bad-size": "SIZE",  # a tag's size word is 1, or too large
              "past-end": "PAST",  # a tag runs past the end of the page
              "too-many": "MANY",  # more tags than the image reads
              "kind": "KIND"}      # the tag that ends the list has a kind


def draw(handoff: con.Handoff, page: bytes | None = None, mdp: int | None = 0,
         tick: int = 0) -> Screen:
    """The screen for this handoff, tag page, display-register value and
    counter value. mdp None: the screen as it stands while that register has
    not been read: the status word is "Reading", and there is no register
    value and no counter."""
    if handoff.entry != LINK_ENTRY:
        raise ValueError("an image entered at another address draws stripes: moved_fb()")
    if page is None:
        page = bytes(con.TAGS_PAGE_BYTES)
    h = handoff
    f = A["fonts"]
    m = A["masks"]
    s = Screen()
    s.fb[:] = background_fb()
    body = C["BG_BODY"]

    # self-test
    s.text(f["ROW1"], L["SELF_X"], L["ROW1_Y"], f"{SELFTEST_SUM:08X}", C["WHITE"], C["BG_ROW1"])
    s.chip_word(L["SELF_CHIP_X"], L["SELF_CHIP_Y"], "OK1", "OK", "GREEN", C["BG_ROW1"])

    # registers
    for value, yc in zip((h.r0, h.r1, h.r2, h.r3), L["REG_Y"]):
        s.text(f["VAL_REG"], L["REG_X"], yc, f"{value:08X}", C["AMBER"], body)

    # processor state: the value, then one chip for the mode and one for each bit
    def bits(word, row, chips):
        yc = L["STAT_Y"][row]
        s.text(f["VAL"], L["STAT_X"], yc, f"{word:08X}", C["AMBER"], body)
        for x, (text, colour, lit) in zip(L["CHIP_X"], chips):
            s.chip_text(x, yc - L["CHIP_H"] // 2, "BIT", text, colour, lit, body)

    def bit(letter, word, n):
        on = (word >> n) & 1
        return (f"{letter}:{on}", "GREEN" if on else "GREY", bool(on))

    bits(h.cpsr, 0, [(MODE_NAMES.get(h.cpsr & 0x1F, "???"), "PURPLE", True),
                     bit("I", h.cpsr, 7), bit("F", h.cpsr, 6), bit("A", h.cpsr, 8), bit("T", h.cpsr, 5)])
    bits(h.sctlr, 1, [bit("M", h.sctlr, 0), bit("C", h.sctlr, 2), bit("I", h.sctlr, 12),
                      bit("A", h.sctlr, 1), bit("V", h.sctlr, 13)])

    # boot information
    info_y = L["INFO_Y"]
    val = f["VAL"]
    s.text(val, L["INFO_X"], info_y[0], str(h.r1), C["WHITE"], body)
    s.text(val, L["INFO_X"], info_y[1], f"{h.entry:08X}", C["WHITE"], body)
    s.chip_word(L["ENTRY_CHIP_X"], L["ENTRY_CHIP_Y"], "OK2", "OK", "GREEN", body)
    s.text(val, L["INFO_X"], info_y[2], f"{h.r2:08X}", C["WHITE"], body)

    problem, tags, ended = _words(page, h.r2)
    seen = set()
    mem_rows = 0
    not_shown = 0
    pieces = []          # every command-line word, in order
    unterminated = False
    for kind, tag_body in tags:
        first = kind not in seen
        seen.add(kind)
        if kind == con.ATAG_CORE and first:
            s.text(val, L["INFO_X"], info_y[3], f"{tag_body[1]:08X}" if len(tag_body) >= 2 else "-",
                   C["WHITE"], body)
        elif kind == con.ATAG_INITRD2 and first:
            if len(tag_body) >= 2:
                s.text(val, L["INFO_X"], info_y[4], f"{tag_body[0]:08X}", C["WHITE"], body)
                s.word(m["SZ"], L["SZ_LABEL_X"], info_y[4], C["LABEL"], body)
                s.text(f["SMALL"], L["SZ_X"], info_y[4], f"{tag_body[1]:08X}", C["WHITE"], body)
            else:
                s.text(val, L["INFO_X"], info_y[4], "-", C["WHITE"], body)
        elif kind == con.ATAG_REVISION and first:
            s.text(val, L["INFO_X"], info_y[5], f"{tag_body[0]:08X}" if tag_body else "-", C["WHITE"], body)
        elif kind == con.ATAG_SERIAL and first:
            # The serial number is an identifier: the tag is there, no more.
            s.word(m["HIDDEN"], L["INFO_X"], info_y[6], C["WHITE"], body)
        elif kind == con.ATAG_MEM and mem_rows < len(L["MEM_Y"]):
            yc = L["MEM_Y"][mem_rows]
            mem_rows += 1
            s.word(m["MEM"], L["MEM_X"], yc, C["CYAN"], body)
            if len(tag_body) >= 2:
                s.text(val, L["MEM_SIZE_X"], yc, f"{tag_body[0]:08X}", C["AMBER"], body)
                s.word(m["AT"], L["MEM_AT_X"], yc, C["CYAN"], body)
                s.text(val, L["MEM_ADDR_X"], yc, f"{tag_body[1]:08X}", C["WHITE"], body)
            else:
                s.text(val, L["MEM_SIZE_X"], yc, "-", C["AMBER"], body)
        elif kind == con.ATAG_CMDLINE:
            pieces += [_piece_text(*w) for w in con.split_cmdline(tag_body)]
            if b"\0" not in struct.pack(f"<{len(tag_body)}I", *tag_body):
                unterminated = True
        else:
            not_shown += 1   # a kind with no place on this screen, or one more than fits

    # the command line: two words on the head line, then two columns, then
    # the three free cells of the lower panel
    n = len(pieces)
    rows, shown = word_places(n)
    pen = L["HEAD_X"] << 4
    left = L["HEAD_CHARS"]
    for i, piece in enumerate(pieces[:shown]):
        if i < 2:
            if i == 1:
                pen += 2 * f["PAR"]["space16"]
                left = max(0, left - 2)
            pen, count = _draw_word(s, pen, L["HEAD_Y"], piece, left, body)
            left -= count
        elif i < 2 + 2 * rows:
            row, col = divmod(i - 2, 2)
            yc = L["ROW_Y"][rows - L["ROWS"]][row]
            _draw_word(s, L["COL_X"][col] << 4, yc, piece, L["COL_CHARS"][col], body)
        else:
            cell = i - 2 - 2 * rows
            _draw_word(s, L["CFG_X"][cell] << 4, L["CFG_Y"][cell], piece, L["CFG_CHARS"][cell], C["BG_CFG"])

    # why the list was not read to a proper end: one word on a red chip
    if problem:
        s.chip_text(L["WARN_X"], L["WARN_Y"], "WARN", WARN_WORDS[problem], "RED", True, body)
    # what of the list is not on the screen
    if not_shown or n > shown:
        note = "NOT SHOWN:" + (f" {not_shown} TAGS" if not_shown else "") + \
               (f" {n - shown} WORDS" if n > shown else "")
        s.text_right(L["LIST_RIGHT_X"], L["LIST_Y"], note, C["RED"], C["BG_LIST"])
    # a command line whose text has no terminating zero
    if unterminated:
        s.text_right(L["TEXT_RIGHT_X"], L["TEXT_Y"], "CMDLINE UNTERMINATED", C["RED"], C["BG_TEXT"])

    if mdp is None:
        s.status("READING", C["AMBER"])
        return s
    pen = s.text(f["PAR"], L["MDP_X"], L["MDP_Y"], f"{mdp:08X}", C["WHITE"], C["BG_CFG"])
    verdict, colour = (" IS FB", "LABEL") if mdp == FB_BASE else (" NOT FB", "RED")
    for ch in verdict:
        pen = s.glyph(f["PAR"], pen, L["MDP_Y"], ord(ch), C[colour], C["BG_CFG"])
    s.status("RUNNING", C["GREEN"])

    tick &= 0xFFFF_FFFF
    for i, digit in enumerate(f"{tick:08X}"):
        s.tick_digit(i, digit)
    lit = L["BAR_W"] * ((tick & 15) + 1) // L["BAR_CELLS"]
    s.fill_rect(L["BAR_X"], L["BAR_Y"], lit, L["BAR_H"], C["BAR_LIT"])
    s.fill_rect(L["BAR_X"] + lit, L["BAR_Y"], L["BAR_W"] - lit, L["BAR_H"], C["BAR_DARK"])
    return s


def expected_fb(handoff: con.Handoff, page: bytes | None = None, mdp: int | None = 0,
                tick: int = 0) -> bytes:
    return bytes(draw(handoff, page, mdp, tick).fb)


_BACKGROUND: list = []


def background_fb() -> bytes:
    """The stored background alone: what the image draws first."""
    if not _BACKGROUND:
        s = Screen()
        s.background()
        _BACKGROUND.append(bytes(s.fb))
    return _BACKGROUND[0]


def moved_fb() -> bytes:
    """An image entered at another address than it is linked for: stripes,
    white first, exactly as the console image draws them."""
    return con.moved_fb()


# The pixel rows the counter's digits are in: the first row, and how many.
TICK_TOP = L["TICK_Y"] - A["fonts"]["TICK"]["up"]
TICK_ROWS = A["fonts"]["TICK"]["cell_h"]
_DIGIT_CELLS: list = []


def _digit_cells() -> list:
    """The pixels of a counter cell for each of the sixteen digits."""
    if not _DIGIT_CELLS:
        font = A["fonts"]["TICK"]
        x = L["TICK_X"] - font["pad"]
        for digit in "0123456789ABCDEF":
            s = Screen()
            s.tick_digit(0, digit)
            _DIGIT_CELLS.append(b"".join(
                bytes(s.fb[(TICK_TOP + j) * STRIDE + x * BPP:(TICK_TOP + j) * STRIDE + (x + font["cell_w"]) * BPP])
                for j in range(TICK_ROWS)))
    return _DIGIT_CELLS


def tick_of_band(band: bytes) -> int | None:
    """The counter value shown in `band`, the TICK_ROWS whole pixel rows from
    row TICK_TOP, or None if its eight cells are not exactly eight digits."""
    if len(band) != TICK_ROWS * STRIDE:
        raise ValueError(f"the counter's band is {TICK_ROWS * STRIDE} bytes, not {len(band)}")
    font = A["fonts"]["TICK"]
    cells = _digit_cells()
    value = 0
    for i in range(8):
        x = (((L["TICK_X"] << 4) + i * font["space16"]) >> 4) - font["pad"]
        block = b"".join(bytes(band[j * STRIDE + x * BPP:j * STRIDE + (x + font["cell_w"]) * BPP])
                         for j in range(TICK_ROWS))
        if block not in cells:
            return None
        value = (value << 4) | cells.index(block)
    return value


def tick_of(fb: bytes) -> int | None:
    """The counter value the framebuffer shows, or None."""
    if len(fb) != FB_BYTES:
        raise ValueError(f"a framebuffer is {FB_BYTES} bytes, not {len(fb)}")
    return tick_of_band(fb[TICK_TOP * STRIDE:(TICK_TOP + TICK_ROWS) * STRIDE])


def png_bytes(fb: bytes) -> bytes:
    """The framebuffer (blue, green, red) as a PNG file."""
    if len(fb) != FB_BYTES:
        raise ValueError(f"a framebuffer is {FB_BYTES} bytes, not {len(fb)}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFF_FFFF))

    rows = []
    for y in range(H):
        row = bytearray(fb[y * STRIDE:(y + 1) * STRIDE])
        row[0::3], row[2::3] = row[2::3], row[0::3]
        rows.append(b"\0" + bytes(row))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


# The tag list the phone passed on 2026-11-19, as far as the console image
# showed it (docs/evidence/phase-2/2026-11-19-console-session.md). The values
# of the command-line words are made up; only their names and lengths are real.
PHONE_WORDS = (
    ("mem", 4), ("console", 4), ("sec_log", 18), ("sec_dbg", 18), ("sec_debug.reset_reason", 10),
    ("normal_off", 1), ("lcd_attached", 1), ("etb_buf", 17), ("androidboot.debug_level", 6),
    ("sec_debug.enable", 1), ("sec_debug.enable_user", 1), ("msm_rtb.enabled", 1),
    ("androidboot.cp_debug_level", 6), ("sec_debug.enable_cp_debug", 1), ("cordon", 32),
    ("connie", 50), ("sysscope", 10), ("loglevel", 1), ("samsung.hardware", 8),
    ("androidboot.emmc_checksum", 1), ("androidboot.warranty_bit", 1))


def phone_tags(extra_words=()) -> bytes:
    words = PHONE_WORDS + tuple(extra_words)
    cmdline = " ".join(f"{name}={'x' * length}" for name, length in words).encode()
    return b"".join((
        con.tag(con.ATAG_CORE), con.tag(con.ATAG_INITRD2, 0x8120_0000, 1), con.tag(con.ATAG_REVISION, 5),
        con.tag(con.ATAG_SERIAL, 0x5EC2_E700, 0x5EC2_E701),
        con.tag(con.ATAG_MEM, 0x2000_0000, 0xC000_0000), con.tag(con.ATAG_MEM, 0x07E0_0000, 0x8020_0000),
        con.tag(con.ATAG_MEM, 0x0080_0000, 0x8E80_0000), con.tag(con.ATAG_MEM, 0x0030_0000, 0x8F80_0000),
        con.tag(con.ATAG_MEM, 0x0010_0000, 0x8FE0_0000), con.tag(con.ATAG_MEM, 0x3000_0000, 0x9000_0000),
        con.cmdline_tag(cmdline), con.end_tag()))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--png", metavar="FILE", required=True,
                        help="write the screen for the phone's measured handoff and tag list")
    parser.add_argument("--tick", type=lambda v: int(v, 0), default=0x56)
    args = parser.parse_args(argv)
    check_assets()
    fb = expected_fb(con.phone_handoff(r3=0x1141), con.page_with(phone_tags()), FB_BASE, args.tick)
    Path(args.png).write_bytes(png_bytes(fb))
    print(f"wrote {args.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
