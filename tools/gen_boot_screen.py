#!/usr/bin/env python3
"""gen_boot_screen.py - make the stored pictures of the Phase 2 boot screen.

The boot screen image (boot/samsung-serranolte/screen/) shows the owner's
console design on the GT-I9195's 540x960 panel. The phone does not compute
that design. It copies stored pictures:

  - one BACKGROUND picture of everything that never changes: the panels, their
    glow, the logo, the icons, the titles and the fixed labels;
  - LETTERS, each a small picture with sixteen levels of coverage, for the
    values that the phone finds out when it runs;
  - a few small MASKS (the chips, and words such as OK).

This tool draws all of that on the host and writes three files next to the
image's sources:

  assets.bin   the pictures, packed (the image includes this file as bytes)
  assets.rs    where each picture is in assets.bin, the layout and the colours,
               as Rust constants for the image
  assets.json  the same facts for the host oracle (tests/boot/screen_v3.py)

The three files are COMMITTED and are the source of truth for the build and
the tests. A build never runs this tool, and `make check` does not need it:
its output depends on the Pillow version and on the fonts installed, so it is
not reproducible from machine to machine. Run it only to change the design,
and commit all three files together. tests/boot/test_screen_v3.py checks that
the three files agree with each other. After a run, two more things show the
new design and are renewed in the same commit: the picture in the document
(`make screen-sample`, copied to docs/phase-2/screen-sample.png) and the
pinned hash of the phone's screen in that test file.

Needs: Pillow; the fonts DejaVu Sans Mono, DejaVu Sans Condensed (Bitstream
Vera licence, docs/licenses/) and Poppins (SIL Open Font License 1.1,
docs/licenses/); and art.png / art.json in the image's directory, the logo and
icons cut from the owner's design picture.

Every position is the design's own position (a picture 999 x 1280), mapped
onto the panel: x by 540/999 and y by 960/1280. Letters are not stretched with
it; they are made tall and narrow so that they fill the taller panel.

Usage: gen_boot_screen.py [--preview FILE.png]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "boot/samsung-serranolte/screen"

W, H = 540, 960
SX = W / 999.0
SY = H / 1280.0
SS = 4
TALL = 1.36

F_MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
F_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
F_COND_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
F_POP_B = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"

BG = (2, 11, 20)
BODY = (3, 14, 25)
STRIP = (7, 27, 40)
ROW1_BODY = (9, 30, 42)
CFG_BODY = (4, 22, 24)
CFG_STRIP = (8, 34, 36)
STATUS_BODY = (6, 34, 50)
CYAN = (84, 214, 232)
LABEL = (104, 222, 230)
NAME = (112, 214, 222)
AMBER = (246, 206, 92)
WHITE = (226, 232, 238)
GREEN = (118, 222, 136)
MINT = (160, 234, 196)
PURPLE = (196, 178, 240)
GREY = (150, 164, 180)
RED = (244, 104, 104)
BAR = (40, 232, 250)
DIM = (126, 138, 160)

HEX = "0123456789ABCDEF"


def X(v):
    return round(v * SX)


def Y(v):
    return round(v * SY)


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def q16(mask):
    """Coverage in sixteen levels (4 bits a pixel), still stored 0..255."""
    return mask.point(lambda v: ((v + 8) // 17) * 17)


def rr(w, h, r, width=None, pad=0):
    """Mask of a rounded rectangle, filled or as an outline `width` wide."""
    big = Image.new("L", ((w + 2 * pad) * SS, (h + 2 * pad) * SS), 0)
    d = ImageDraw.Draw(big)
    box = (pad * SS, pad * SS, (pad + w) * SS - 1, (pad + h) * SS - 1)
    if width is None:
        d.rounded_rectangle(box, r * SS, fill=255)
    else:
        d.rounded_rectangle(box, r * SS, outline=255, width=round(width * SS))
    return big.resize((w + 2 * pad, h + 2 * pad), Image.BOX)


def fit_w(path, sample, width, tall=TALL):
    """(font, squeeze) in which `sample` is `width` design pixels wide."""
    probe = ImageFont.truetype(path, 100)
    size = 100.0 * (width * SX) / probe.getlength(sample) * tall
    return ImageFont.truetype(path, size), 1.0 / tall


def fit_p(path, pitch, fill=0.92, tall=TALL):
    """(font, squeeze) whose digits fill `fill` of a cell `pitch` design pixels wide."""
    probe = ImageFont.truetype(path, 100)
    size = 100.0 * (pitch * SX * fill) / probe.getlength("0") * tall
    return ImageFont.truetype(path, size), 1.0 / tall


class Canvas:
    """The background picture while it is being drawn."""

    def __init__(self):
        self.img = Image.new("RGB", (W, H), BG)
        self.sheet = Image.open(OUT / "art.png").convert("L")
        self.art_index = {a["name"]: a for a in json.loads((OUT / "art.json").read_text())}

    def blend(self, colour, x, y, mask):
        self.img.paste(colour, (x, y), q16(mask))

    def rect(self, colour, x, y, w, h):
        self.img.paste(colour, (x, y, x + w, y + h))

    def panel(self, x0, y0, x1, y1, accent, strip_to=None, r=9, body=BODY, strip=STRIP, glow=0.55):
        x, y, w, h = X(x0), Y(y0), X(x1) - X(x0), Y(y1) - Y(y0)
        pad = 7
        line = rr(w, h, r, 1.6, pad)
        halo = line.filter(ImageFilter.GaussianBlur(2.6)).point(lambda v: min(255, int(v * 2.3 * glow)))
        self.blend(accent, x - pad, y - pad, halo)
        self.blend(body, x, y, rr(w, h, r))
        if strip_to is not None:
            sh = Y(strip_to) - y
            cut = Image.new("L", (w, h), 0)
            cut.paste(255, (0, 0, w, sh))
            self.blend(mix(strip, accent, 0.05), x, y, ImageChops.multiply(rr(w, h, r), cut))
            self.rect(mix(body, accent, 0.5), x + 6, y + sh, w - 12, 1)
        inner = rr(w, h, r, 1.6).filter(ImageFilter.GaussianBlur(1.8)).point(lambda v: int(v * 0.42))
        self.blend(accent, x, y, ImageChops.multiply(inner, rr(w, h, r)))
        self.blend(mix(accent, WHITE, 0.12), x, y, rr(w, h, r, 1.0).point(lambda v: int(v * 0.92)))

    def text(self, x, yc, s, colour, fx, anchor="lm", glow=0.0, tracking=0.0):
        m, origin, total = text_mask(s, fx, tracking)
        ox = {"l": 0, "m": total / 2, "r": total}[anchor[0]]
        px, py = round(x - ox - origin), round(yc - m.height / 2)
        if glow:
            g = m.filter(ImageFilter.GaussianBlur(2.0)).point(lambda v: min(255, int(v * glow)))
            self.blend(colour, px, py, g)
        self.blend(colour, px, py, m)
        return round(x - ox + total)

    def grid(self, x, yc, s, colour, fx, pitch):
        for i, ch in enumerate(s):
            if ch != " ":
                m = glyph_mask(ch, fx)
                self.blend(colour, round(x + i * pitch + pitch / 2 - m.width / 2), round(yc - m.height / 2), m)
        return round(x + len(s) * pitch)

    def art(self, name, colour):
        a = self.art_index[name]
        m = self.sheet.crop((a["x"], 0, a["x"] + a["w"], a["h"]))
        x0, y0, x1, y1 = a["from"]
        cx, cy = (x0 + x1) / 2 * SX, (y0 + y1) / 2 * SY
        self.blend(colour, round(cx - a["w"] / 2), round(cy - a["h"] / 2), m)


def text_mask(s, fx, tracking=0.0):
    """Proportional text as a mask. Returns (mask, x of the text's left edge
    inside the mask, the text's width); the text's middle is the mask's middle row."""
    font, xs = fx
    m = Image.new("L", (int(font.getlength(s) + tracking * len(s)) + 24, int(font.size * 2 + 8)), 0)
    d = ImageDraw.Draw(m)
    cx = 12.0
    for ch in s:
        d.text((cx, m.height / 2), ch, font=font, fill=255, anchor="lm")
        cx += font.getlength(ch) + tracking
    total = (cx - 12) * xs
    if xs != 1.0:
        m = m.resize((max(1, round(m.width * xs)), m.height), Image.LANCZOS)
    return m, 12 * xs, total


def glyph_mask(ch, fx):
    """One character, centred in its mask in both directions."""
    font, xs = fx
    m = Image.new("L", (int(font.size * 1.4) + 14, int(font.size * 2 + 8)), 0)
    ImageDraw.Draw(m).text((m.width / 2, m.height / 2), ch, font=font, fill=255, anchor="mm")
    if xs != 1.0:
        m = m.resize((max(1, round(m.width * xs)), m.height), Image.LANCZOS)
    return m


# --- packing -----------------------------------------------------------------

def pack_mask(mask):
    """A mask as bytes: rows top to bottom, two pixels a byte, left pixel in the
    high four bits, each pixel a coverage level 0..15."""
    w, h = mask.size
    px = q16(mask).load()
    out = bytearray()
    for y in range(h):
        for x in range(0, w, 2):
            hi = px[x, y] // 17
            lo = px[x + 1, y] // 17 if x + 1 < w else 0
            out.append((hi << 4) | lo)
    return bytes(out)


def encode_background(indices):
    """The background's palette indices (W*H of them, row after row) as a
    stream of operations. Each starts with one byte, kind in the top two bits
    and n in the low six:
      00 n        the next n+1 pixels equal the pixel W places earlier
      01 n c      the next n+1 pixels have colour c
      10 n c...   the next n+1 pixels have the n+1 colours that follow
      11 n m      the next (n*256+m)+1 pixels equal the pixel W places earlier
    Pixels before the first row count as colour 0."""
    out = bytearray()
    lit = bytearray()
    total = len(indices)

    def flush():
        for i in range(0, len(lit), 64):
            part = lit[i:i + 64]
            out.append(0x80 | (len(part) - 1))
            out.extend(part)
        lit.clear()

    def above(i):
        return indices[i - W] if i >= W else 0

    i = 0
    while i < total:
        copy = 0
        while i + copy < total and copy < 16384 and indices[i + copy] == above(i + copy):
            copy += 1
        run = 1
        while i + run < total and run < 64 and indices[i + run] == indices[i]:
            run += 1
        if copy >= 2 and copy >= run:
            flush()
            if copy <= 64:
                out.append(copy - 1)
            else:
                out.append(0xC0 | ((copy - 1) >> 8))
                out.append((copy - 1) & 0xFF)
            i += copy
        elif run >= 3:
            flush()
            out.append(0x40 | (run - 1))
            out.append(indices[i])
            i += run
        else:
            lit.append(indices[i])
            i += 1
    flush()
    return bytes(out)


def decode_background(stream):
    """The inverse of encode_background, to check it."""
    out = bytearray()
    i = 0
    while i < len(stream):
        op, n = stream[i] >> 6, stream[i] & 0x3F
        i += 1
        if op == 0 or op == 3:
            if op == 3:
                n = (n << 8) | stream[i]
                i += 1
            for _ in range(n + 1):
                out.append(out[len(out) - W] if len(out) >= W else 0)
        elif op == 1:
            out.extend(bytes([stream[i]]) * (n + 1))
            i += 1
        else:
            out.extend(stream[i:i + n + 1])
            i += n + 1
    return bytes(out)


# --- fonts and masks ---------------------------------------------------------

def ink_box(masks):
    """The union of the ink boxes of several same-sized masks."""
    boxes = [q16(m).getbbox() for m in masks]
    boxes = [b for b in boxes if b]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def grid_font(fx, pitch, chars, strict=False):
    """A fixed-pitch font: every glyph centred in a cell `pitch` wide (pitch in
    panel pixels, may be fractional). With `strict`, all ink must lie inside
    the whole pixels of its own cell, so one glyph can be redrawn alone."""
    raw = {ch: glyph_mask(ch, fx) for ch in chars if ch != " "}
    any_mask = next(iter(raw.values()))
    _, top, _, bottom = ink_box(list(raw.values()))
    # Letters are wider than digits and may reach into the next cell; three
    # pixels of room on each side hold them. A strict font has none.
    pad = 0 if strict else 3
    cell_w = math.floor(pitch) if strict else math.ceil(pitch) + 2 * pad
    left = round(any_mask.width / 2 - pitch / 2) - pad
    glyphs = []
    for ch in chars:
        if ch == " ":
            glyphs.append(Image.new("L", (cell_w, bottom - top), 0))
            continue
        box = q16(raw[ch]).getbbox()
        if box[0] < left or box[2] > left + cell_w:
            raise ValueError(f"glyph {ch!r} has ink outside its {cell_w}-pixel cell: {box}, cell from {left}")
        glyphs.append(raw[ch].crop((left, top, left + cell_w, bottom)))
    return {"chars": chars, "cell_w": cell_w, "cell_h": bottom - top, "up": any_mask.height // 2 - top,
            "pad": pad, "adv16": [round(pitch * 16)] * len(chars), "space16": round(pitch * 16),
            "glyphs": glyphs}


def strict_font(path, pitch_design, chars):
    """The largest font whose every glyph fits inside the whole pixels of a
    cell `pitch_design` design pixels wide."""
    fill = 0.92
    while fill > 0.5:
        try:
            return grid_font(fit_p(path, pitch_design, fill=fill), pitch_design * SX, chars, strict=True)
        except ValueError:
            fill -= 0.02
    raise SystemExit("no font size fits the cell")


def prop_font(fx, chars):
    """A proportional font: each glyph keeps its own advance."""
    font, xs = fx
    pad = 2
    raw, adv = {}, {}
    for ch in chars:
        m, origin, total = text_mask(ch, fx)
        raw[ch] = (m, origin)
        adv[ch] = total
    _, top, _, bottom = ink_box([m for m, _ in raw.values()])
    cell_w = math.ceil(max(adv.values())) + 2 * pad + 1
    glyphs = []
    for ch in chars:
        m, origin = raw[ch]
        left = round(origin) - pad
        box = q16(m).getbbox()
        if box and (box[0] < left or box[2] > left + cell_w):
            raise SystemExit(f"glyph {ch!r} has ink outside its cell")
        glyphs.append(m.crop((left, top, left + cell_w, bottom)))
    any_mask = raw[chars[0]][0]
    return {"chars": chars, "cell_w": cell_w, "cell_h": bottom - top, "up": any_mask.height // 2 - top,
            "pad": pad, "adv16": [round(adv[ch] * 16) for ch in chars],
            "space16": round(font.getlength(" ") * xs * 16), "glyphs": glyphs}


def word_mask(s, fx, tracking=0.0):
    """A whole word as one mask, cut to its ink. `dx` is where the ink starts
    to the right of the word's left edge; `up` is how far its top lies above
    the word's middle line."""
    m, origin, _ = text_mask(s, fx, tracking)
    box = q16(m).getbbox()
    return {"mask": m.crop(box), "w": box[2] - box[0], "h": box[3] - box[1],
            "dx": box[0] - round(origin), "up": m.height // 2 - box[1]}


def shape_mask(mask):
    return {"mask": mask, "w": mask.width, "h": mask.height, "dx": 0, "up": 0}


# --- the design ---------------------------------------------------------------

def build():
    c = Canvas()
    f_brand = fit_w(F_POP_B, "REVIVAL OS", 276, tall=1.30)
    f_title = fit_w(F_POP_B, "CPU REGISTERS", 198, tall=1.32)
    f_row1 = fit_w(F_COND_B, "PHASE 2: IMAGE 2", 228)
    f_val = fit_p(F_COND_B, 16.5)
    f_val2 = fit_p(F_COND_B, 15.25)
    f_lab = fit_w(F_COND_B, "REVISION", 113)
    f_small = fit_p(F_COND_B, 13.6)
    f_par = fit_p(F_MONO_B, 13.55, fill=1.0)
    f_hdr1 = fit_p(F_MONO, 12.8, fill=1.0, tall=1.3)
    f_hdr2 = fit_p(F_MONO, 10.77, fill=1.0, tall=1.3)
    f_chip = fit_w(F_COND_B, "SVC", 38)
    f_ok = fit_w(F_COND_B, "OK", 36)
    f_tick_l = fit_w(F_POP_B, "TICK", 60, tall=1.32)
    f_stat = fit_w(F_COND_B, "STATUS:", 86)
    PP = 13.55 * SX
    L = {}  # the layout: every number the image needs to place what it draws

    # ---- header ----------------------------------------------------------
    c.art("logo", (206, 246, 252))
    c.text(X(165), Y(52), "REVIVAL OS", (224, 246, 252), f_brand, glow=0.55, tracking=1.3)
    c.grid(X(738), Y(33), "Boot Console v0.1", (160, 222, 230), f_hdr1, 12.8 * SX)
    c.grid(X(540), Y(65), "Target: Samsung GT-I9195 (S4 Mini LTE)", (204, 212, 218), f_hdr2, 10.77 * SX)

    # ---- row 1: phase | self-test ---------------------------------------
    c.panel(30, 97, 437, 150, CYAN, body=ROW1_BODY)
    c.art("layers", (196, 226, 234))
    c.text(X(112), Y(124), "PHASE 2: IMAGE 3", WHITE, f_row1, tracking=0.5)
    c.panel(457, 97, 965, 150, CYAN, body=ROW1_BODY)
    c.art("pulse", (60, 226, 180))
    end = c.text(X(530), Y(124), "SELFTEST:", WHITE, f_row1, tracking=0.5)
    L["SELF_X"], L["ROW1_Y"] = end + 5, Y(124)
    L["SELF_CHIP_X"], L["SELF_CHIP_Y"] = X(819), Y(107)
    ok1 = (X(881) - X(819), Y(141) - Y(107))

    # ---- row 2: CPU registers | CPU status ------------------------------
    c.panel(28, 170, 414, 341, CYAN, strip_to=213)
    c.art("chip", CYAN)
    c.text(X(108), Y(190), "CPU REGISTERS", CYAN, f_title, glow=0.4, tracking=0.2)
    L["REG_X"], L["REG_Y"] = X(168), [Y(v) for v in (234, 262, 290, 319)]
    for name, yc in zip(("R0", "R1", "R2", "R3"), L["REG_Y"]):
        c.grid(X(65), yc, name, LABEL, f_val, 16.5 * SX)
    c.panel(428, 170, 967, 341, CYAN, strip_to=213)
    c.art("gear", CYAN)
    c.text(X(514), Y(190), "CPU STATUS", CYAN, f_title, glow=0.4, tracking=0.2)
    L["STAT_X"], L["STAT_Y"] = X(539), [Y(249), Y(299)]
    c.text(X(449), Y(249), "CPSR", LABEL, f_lab)
    c.text(X(450), Y(299), "SCTLR", LABEL, f_lab)
    c.rect(mix(BODY, CYAN, 0.3), X(440), Y(274), X(955) - X(440), 1)
    L["CHIP_X"] = [X(v) for v in (686, 741, 796, 849, 906)]
    bit = (25, 20)
    L["CHIP_W"], L["CHIP_H"] = bit

    # ---- row 3: boot information | memory map ---------------------------
    c.panel(27, 361, 500, 615, PURPLE, strip_to=405)
    c.art("rocket", PURPLE)
    c.text(X(111), Y(381), "BOOT INFORMATION", PURPLE, f_title, glow=0.4, tracking=0.2)
    L["INFO_X"], L["INFO_Y"] = X(203), [Y(v) for v in (427, 454, 481, 509, 537, 564, 592)]
    for name, yc in zip(("MACH", "ENTRY", "ATAGS", "CORE", "INITRD2", "REVISION", "SERIAL"), L["INFO_Y"]):
        c.text(X(58), yc, name, LABEL, f_lab)
    L["ENTRY_CHIP_X"], L["ENTRY_CHIP_Y"] = X(353), Y(441)
    ok2 = (X(405) - X(353), Y(468) - Y(441))
    L["SZ_LABEL_X"], L["SZ_X"] = X(338), X(373)
    warn = (46, 20)
    L["WARN_X"], L["WARN_Y"] = X(353), Y(481) - warn[1] // 2
    c.panel(518, 361, 968, 615, CYAN, strip_to=405)
    c.art("database", CYAN)
    c.text(X(603), Y(381), "MEMORY MAP", CYAN, f_title, glow=0.4, tracking=0.2)
    L["MEM_X"], L["MEM_SIZE_X"], L["MEM_AT_X"], L["MEM_ADDR_X"] = X(542), X(615), X(767), X(819)
    L["MEM_Y"] = [Y(v) for v in (428, 460, 492, 524, 556, 588)]

    # ---- row 4: boot parameters ------------------------------------------
    c.panel(27, 635, 968, 960, PURPLE, strip_to=679)
    c.art("terminal", PURPLE)
    c.text(X(117), Y(656), "BOOT PARAMETERS (CMDLINE)", PURPLE, f_title, glow=0.4, tracking=0.2)
    c.grid(X(57), Y(703), ">", WHITE, f_par, PP)
    c.grid(X(82), Y(703), "CMDLINE", CYAN, f_par, PP)
    c.rect(mix(BODY, WHITE, 0.45), X(509), Y(728), 1, Y(945) - Y(728))
    # Two notes the image writes only when something is wrong, each at the
    # right-hand end of a title strip: what of the list is not on the screen
    # (here), and a command line with no terminating zero (the panel below).
    L["LIST_RIGHT_X"], L["LIST_Y"] = X(955), Y(656)
    L["HEAD_X"], L["HEAD_Y"], L["HEAD_CHARS"] = X(220), Y(703), int((X(955) - X(220)) / PP)
    L["COL_X"] = [X(62), X(547)]
    L["COL_CHARS"] = [int((X(509) - 4 - X(62)) / PP), int((X(957) - X(547)) / PP)]
    L["ROW0_Y"], L["ROW_SPAN"] = Y(738), Y(934) - Y(738)
    # Eight rows as designed. More words than that fit: up to ten rows, closer
    # together. Past ten, the letters of one row would run into the next.
    L["ROWS"], L["ROWS_MAX"] = 8, 10
    # Where each row's middle is, for each number of rows from ROWS to
    # ROWS_MAX: the first row at ROW0_Y, the last ROW_SPAN below it, the others
    # evenly between. A table, so that the image divides by nothing that is
    # not a constant. Entries past a list's last row are not used.
    L["ROW_Y"] = [[L["ROW0_Y"] + (row * L["ROW_SPAN"]) // (rows - 1) if row < rows else 0
                   for row in range(L["ROWS_MAX"])]
                  for rows in range(L["ROWS"], L["ROWS_MAX"] + 1)]

    # ---- row 5: configuration --------------------------------------------
    c.panel(27, 983, 968, 1140, GREEN, strip_to=1032, body=CFG_BODY, strip=CFG_STRIP)
    c.art("wrench", MINT)
    c.text(X(113), Y(1006), "CONFIGURATION", MINT, f_title, glow=0.4, tracking=0.2)
    c.rect(mix(CFG_BODY, MINT, 0.6), X(510), Y(1046), 1, Y(1122) - Y(1046))
    L["TEXT_RIGHT_X"], L["TEXT_Y"] = X(955), Y(1006)
    L["CFG_X"] = [X(62), X(62), X(551)]
    L["CFG_Y"] = [Y(1060), Y(1098), Y(1060)]
    L["CFG_CHARS"] = [L["COL_CHARS"][0], L["COL_CHARS"][0], int((X(957) - X(551)) / PP)]
    end = c.grid(X(551), Y(1098), "MDP4", NAME, f_par, PP)
    L["MDP_X"], L["MDP_Y"] = round(X(551) + 5 * PP), Y(1098)

    # ---- status bar -------------------------------------------------------
    c.panel(28, 1168, 967, 1251, CYAN, r=11, body=STATUS_BODY, glow=0.7)
    c.art("clock", (210, 240, 248))
    c.text(X(105), Y(1210), "TICK", (150, 232, 240), f_tick_l, glow=0.3, tracking=0.3)
    L["TICK_X"], L["TICK_Y"] = X(192), Y(1210)
    c.rect(mix(STATUS_BODY, WHITE, 0.75), X(399), Y(1185), 1, Y(1236) - Y(1185))
    c.text(X(428), Y(1210), "STATUS:", (166, 228, 234), f_stat, tracking=0.3)
    # The word after "STATUS:" is not in the background: the image draws it,
    # so that it says what the image is doing and not what it was built to say.
    L["STATUS_X"], L["STATUS_Y"] = X(530), Y(1210)
    bx, by, bw, bh = X(680), Y(1193), X(940) - X(680), Y(1224) - Y(1193)
    bar_dark = mix(STATUS_BODY, BAR, 0.12)
    c.blend(bar_dark, bx, by, rr(bw, bh, 6))
    c.blend(mix(STATUS_BODY, BAR, 0.75), bx, by, rr(bw, bh, 6, 1.1))
    L["BAR_X"], L["BAR_Y"], L["BAR_W"], L["BAR_H"] = bx + 4, by + 4, bw - 8, bh - 8
    L["BAR_CELLS"] = 16

    fonts = {
        "VAL_REG": grid_font(f_val, 16.5 * SX, HEX + "-+"),
        "VAL": grid_font(f_val2, 15.25 * SX, HEX + "-+"),
        "SMALL": grid_font(f_small, 13.6 * SX, HEX),
        "ROW1": grid_font(f_row1, f_row1[0].getlength("0") * f_row1[1] + 0.5, HEX),
        "TICK": strict_font(F_COND_B, 20.6, HEX),
        "PAR": grid_font(f_par, PP, "".join(chr(v) for v in range(0x20, 0x7F))),
        "CHIP": prop_font(f_chip, "ABCDEFGHIJKLMNOPQRSTUVWXYZ01:?"),
    }
    masks = {
        "OK": word_mask("OK", f_ok), "BAD": word_mask("BAD", f_ok),
        "HIDDEN": word_mask("HIDDEN", f_lab, 0.8), "MEM": word_mask("MEM", f_lab),
        "AT": word_mask("AT", f_lab), "SZ": word_mask("SZ", f_small),
        "BIT_FILL": shape_mask(rr(bit[0], bit[1], 5)), "BIT_LINE": shape_mask(rr(bit[0], bit[1], 5, 1.1)),
        "OK1_FILL": shape_mask(rr(ok1[0], ok1[1], 5)), "OK1_LINE": shape_mask(rr(ok1[0], ok1[1], 5, 1.1)),
        "OK2_FILL": shape_mask(rr(ok2[0], ok2[1], 5)), "OK2_LINE": shape_mask(rr(ok2[0], ok2[1], 5, 1.1)),
        "WARN_FILL": shape_mask(rr(warn[0], warn[1], 5)), "WARN_LINE": shape_mask(rr(warn[0], warn[1], 5, 1.1)),
        "READING": word_mask("Reading", f_stat, 0.3), "RUNNING": word_mask("Running", f_stat, 0.3),
    }
    # The box the image clears before it draws a status word: it holds both words.
    words = (masks["READING"], masks["RUNNING"])
    left = min(m["dx"] for m in words)
    top = max(m["up"] for m in words)
    L["STATUS_BOX_X"], L["STATUS_BOX_Y"] = L["STATUS_X"] + left, L["STATUS_Y"] - top
    L["STATUS_BOX_W"] = max(m["dx"] + m["w"] for m in words) - left
    L["STATUS_BOX_H"] = top + max(m["h"] - m["up"] for m in words)
    colours = {
        "AMBER": AMBER, "AMBER_SOFT": mix(AMBER, WHITE, 0.25), "WHITE": WHITE, "NAME": NAME, "CYAN": CYAN,
        "LABEL": LABEL, "GREEN": GREEN, "PURPLE": PURPLE, "GREY": GREY, "RED": RED, "DIM": DIM,
        "BAR_LIT": BAR,
        # a chip: its fill, its outline and its text, lit and not lit, for each colour it can have
        "CHIP_FILL_LIT": 0.24, "CHIP_FILL_OFF": 0.12, "CHIP_LINE_LIT": 0.95, "CHIP_LINE_OFF": 0.70,
        "CHIP_TEXT_OFF": 0.55,
    }
    # places whose background colour the image must know, read back from the finished picture
    probes = {
        "BG_ROW1": (L["SELF_X"] + 30, L["ROW1_Y"]), "BG_BODY": (L["REG_X"] + 20, L["REG_Y"][1] + 9),
        "BG_LIST": (L["LIST_RIGHT_X"] - 40, L["LIST_Y"]), "BG_CFG": (L["MDP_X"] + 60, L["MDP_Y"]),
        "BG_TEXT": (L["TEXT_RIGHT_X"] - 40, L["TEXT_Y"]),
        "BG_STATUS": (L["TICK_X"] + 20, L["TICK_Y"]), "BAR_DARK": (L["BAR_X"] + 20, L["BAR_Y"] + 4),
    }
    return c.img, L, fonts, masks, colours, probes


def rust_colour(c):
    return f"[{c[0]}, {c[1]}, {c[2]}]"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", metavar="FILE.png", help="also write the background as a PNG")
    args = parser.parse_args(argv)

    img, L, fonts, masks, colours, probes = build()
    pal_img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = bytes(pal_img.getpalette()[:768]).ljust(768, b"\0")
    indices = pal_img.tobytes()
    assert len(indices) == W * H
    stream = encode_background(indices)
    assert decode_background(stream) == indices, "the background does not survive encoding"

    def probe(xy):
        i = indices[xy[1] * W + xy[0]]
        return tuple(palette[3 * i:3 * i + 3])

    for name, xy in probes.items():
        colours[name] = probe(xy)
    body = colours["BG_BODY"]
    for key, t in list(colours.items()):
        if isinstance(t, float):  # the chip colours, worked out here so both sides only copy numbers
            del colours[key]
    for cname in ("GREEN", "PURPLE", "GREY", "RED"):
        base = colours[cname]
        colours[f"CHIP_{cname}_FILL_LIT"] = mix(body, base, 0.24)
        colours[f"CHIP_{cname}_FILL_OFF"] = mix(body, base, 0.12)
        colours[f"CHIP_{cname}_LINE_LIT"] = mix(body, base, 0.95)
        colours[f"CHIP_{cname}_LINE_OFF"] = mix(body, base, 0.70)
        colours[f"CHIP_{cname}_TEXT_OFF"] = mix(base, WHITE, 0.55)

    blob = bytearray(palette)
    index = {"width": W, "height": H, "palette_off": 0, "bg_off": len(blob), "bg_len": len(stream)}
    blob += stream
    index["fonts"] = {}
    for name, f in fonts.items():
        off = len(blob)
        for g in f["glyphs"]:
            blob += pack_mask(g)
        index["fonts"][name] = {k: f[k] for k in ("chars", "cell_w", "cell_h", "up", "pad", "adv16", "space16")}
        index["fonts"][name]["off"] = off
        assert max(f["adv16"]) <= 255 and len(f["chars"]) < 255, f"font {name} does not fit the image's tables"
    index["masks"] = {}
    for name, m in masks.items():
        index["masks"][name] = {"off": len(blob), "w": m["w"], "h": m["h"], "dx": m["dx"], "up": m["up"]}
        blob += pack_mask(m["mask"])
    index["layout"] = L
    index["colours"] = {k: list(v) for k, v in colours.items()}
    index["blob_len"] = len(blob)
    index["blob_sha256"] = hashlib.sha256(blob).hexdigest()

    (OUT / "assets.bin").write_bytes(bytes(blob))
    (OUT / "assets.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="ascii")

    r = ["//! assets.rs - GENERATED by tools/gen_boot_screen.py. Do not edit.",
         "//!",
         "//! Where each stored picture is in assets.bin, the layout and the colours.",
         "//! assets.json holds the same facts for the host oracle; a unit test",
         "//! (tests/boot/test_screen_v3.py) fails if the three files disagree.",
         "",
         "use crate::gfx::{Font, Mask, Rgb};",
         "",
         "/// The stored pictures: palette, background, letters and masks.",
         'pub static BLOB: &[u8] = include_bytes!("assets.bin");',
         f"pub const BLOB_LEN: usize = {len(blob)};",
         f'pub const BLOB_SHA256: &str = "{index["blob_sha256"]}";',
         "",
         f"pub const WIDTH: usize = {W};",
         f"pub const HEIGHT: usize = {H};",
         f"pub const PALETTE_OFF: usize = {index['palette_off']};",
         f"pub const BG_OFF: usize = {index['bg_off']};",
         f"pub const BG_LEN: usize = {index['bg_len']};",
         ""]
    for name, f in index["fonts"].items():
        table = [0xFF] * 96
        for i, ch in enumerate(f["chars"]):
            table[ord(ch) - 0x20] = i
        r.append(f"pub static FONT_{name}: Font = Font {{")
        r.append(f"    off: {f['off']},")
        r.append(f"    cell_w: {f['cell_w']},")
        r.append(f"    cell_h: {f['cell_h']},")
        r.append(f"    up: {f['up']},")
        r.append(f"    pad: {f['pad']},")
        r.append(f"    space16: {f['space16']},")
        r.append("    map: [")
        for i in range(0, 96, 16):
            r.append("        " + ", ".join(str(v) for v in table[i:i + 16]) + ",")
        r.append("    ],")
        r.append("    adv16: &[" + ", ".join(str(v) for v in f["adv16"]) + "],")
        r.append("};")
    r.append("")
    for name, m in index["masks"].items():
        r.append(f"pub const MASK_{name}: Mask = Mask {{ off: {m['off']}, w: {m['w']}, h: {m['h']}, "
                 f"dx: {m['dx']}, up: {m['up']} }};")
    r.append("")
    for name, v in L.items():
        if isinstance(v, list) and isinstance(v[0], list):
            rows = ", ".join("[" + ", ".join(str(n) for n in row) + "]" for row in v)
            r.append(f"pub const {name}: [[usize; {len(v[0])}]; {len(v)}] = [{rows}];")
        elif isinstance(v, list):
            r.append(f"pub const {name}: [usize; {len(v)}] = [{', '.join(str(n) for n in v)}];")
        else:
            r.append(f"pub const {name}: usize = {v};")
    r.append("")
    for name, v in index["colours"].items():
        r.append(f"pub const {name}: Rgb = {rust_colour(v)};")
    (OUT / "assets.rs").write_text("\n".join(r) + "\n", encoding="ascii")

    print(f"background: {len(stream)} bytes for {W * H} pixels, {len(set(indices))} colours")
    for name, f in index["fonts"].items():
        print(f"font {name}: {len(f['chars'])} glyphs, cell {f['cell_w']}x{f['cell_h']}")
    print(f"assets.bin: {len(blob)} bytes, sha256 {index['blob_sha256']}")
    if args.preview:
        pal_img.convert("RGB").save(args.preview)
        print("wrote", args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
