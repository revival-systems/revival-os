#!/usr/bin/env python3
"""gen_boot_screen.py - make the stored pictures of the Phase 2 boot screen.

The boot screen image (boot/samsung-serranolte/screen/) shows the owner's
console design on the GT-I9195's 540x960 panel. The phone does not compute
that design. It copies stored pictures:

  - one BACKGROUND picture of everything that never changes: the panels, their
    glow and gloss, the logo, the icons, the titles and the fixed labels;
  - small COLOUR PICTURES: each chip with its letters, and the inside of the
    bar at each of its sixteen lengths, in the design's gel look;
  - LETTERS, each a small picture with sixteen levels of coverage, for the
    values that the phone finds out when it runs, and a few whole WORDS of
    the same kind.

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

import PIL
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


def whole(pitch):
    """The design pitch nearest to `pitch` (in design pixels) that is a whole
    number of panel pixels. Every fixed-pitch text uses one, so that each
    letter starts on a whole pixel and the gaps between letters are all the
    same: with a pitch of 7.3 pixels every third or fourth gap is a pixel
    wider, and `sysscope` reads as `syss cope`."""
    return round(pitch * SX) / SX


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


def fade_mask(size, weight):
    """A mask whose value at (x, y) is 255 * weight(x, y), weight in 0..1."""
    w, h = size
    m = Image.new("L", size, 0)
    m.putdata([int(255 * min(1.0, max(0.0, weight(x, y)))) for y in range(h) for x in range(w)])
    return m


def gel_plate(w, h, r, accent, strength, bg, glow):
    """A chip's plate in the design's gel look: a soft glow around it, a body
    that is darker at the top, light along the inside of its rim, a faint
    gloss over its upper half and a rim that is brightest at the top left.
    `strength` is 1 for a lit chip, less for an unlit one. Returns the plate
    already laid over `bg`, with `glow` pixels of room on every side, and its
    coverage (0 where the plate and its glow do not reach)."""
    S = SS
    tw, th = (w + 2 * glow) * S, (h + 2 * glow) * S
    box = (glow * S, glow * S, (glow + w) * S - 1, (glow + h) * S - 1)

    def rounded(inset=0.0, **how):
        m = Image.new("L", (tw, th), 0)
        b = (box[0] + inset * S, box[1] + inset * S, box[2] - inset * S, box[3] - inset * S)
        ImageDraw.Draw(m).rounded_rectangle(b, max(1.0, r - inset) * S, **how)
        return m

    shape = rounded(fill=255)
    out = Image.new("RGB", (tw, th), bg)
    halo = shape.filter(ImageFilter.GaussianBlur(1.3 * S)).point(lambda v: int(v * 0.60 * strength))
    out.paste(accent, (0, 0), halo)
    fill = mix(bg, accent, 0.16 + 0.16 * strength)
    top, bottom = mix(fill, (0, 0, 0), 0.34), mix(fill, accent, 0.10)
    grad = Image.new("RGB", (1, th))
    for y in range(th):
        grad.putpixel((0, y), mix(top, bottom, min(1.0, max(0.0, (y - glow * S) / (h * S - 1)))))
    out.paste(grad.resize((tw, th)), (0, 0), shape)
    inner = rounded(outline=255, width=round(2.4 * S)).filter(ImageFilter.GaussianBlur(1.2 * S))
    out.paste(accent, (0, 0), ImageChops.multiply(inner, shape).point(lambda v: int(v * 0.42 * strength)))
    cap = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(cap).ellipse((box[0] - w * S * 0.25, box[1] - h * S * 0.80,
                                 box[2] + w * S * 0.25, box[1] + h * S * 0.48), fill=255)
    cap = ImageChops.multiply(cap, rounded(1.6, fill=255)).filter(ImageFilter.GaussianBlur(0.5 * S))
    out.paste((255, 255, 255), (0, 0), cap.point(lambda v: int(v * 0.11)))
    rim = rounded(outline=255, width=round(1.5 * S))
    out.paste(mix(bg, accent, 0.62 + 0.38 * strength), (0, 0), rim)
    shine = fade_mask((tw, th), lambda x, y: 1.0 - ((x - box[0]) + 1.6 * (y - box[1])) / (0.75 * w * S))
    out.paste(mix(accent, WHITE, 0.75), (0, 0), ImageChops.multiply(rim, shine).point(lambda v: int(v * 0.8)))
    size = (w + 2 * glow, h + 2 * glow)
    return out.resize(size, Image.LANCZOS), ImageChops.lighter(shape, halo).resize(size, Image.BOX)


def chip_sprite(text, fx, size, accent, strength, ink, bg, glow, tracking=0.5):
    """A chip with its text, as a picture laid over `bg`."""
    w, h = size
    rgb, alpha = gel_plate(w, h, 5.5, accent, strength, bg, glow)
    m, origin, total = text_mask(text, fx, tracking)
    px, py = round(rgb.width / 2 - total / 2 - origin), round(rgb.height / 2 - m.height / 2)
    soft = m.filter(ImageFilter.GaussianBlur(1.0)).point(lambda v: int(v * 0.45))
    rgb.paste(ink, (px, py), soft)
    rgb.paste(ink, (px, py), m)
    return {"rgb": rgb, "alpha": alpha, "hole_below": 10}


def bar_sprite(w, h, lit, cells, dark):
    """The inside of the bar's track with `lit` of `cells` parts of it filled:
    one piece, rounded, lighter at the top. The whole inside is drawn, filled
    or dark, so that one picture replaces another."""
    S = SS
    shape = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, w * S - 1, h * S - 1), 3.2 * S, fill=255)
    out = Image.new("RGB", (w * S, h * S), dark)
    length = round(w * lit / cells)
    fill = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(fill).rounded_rectangle((0, 0, length * S - 1, h * S - 1), min(3.2, length / 2) * S, fill=255)
    top, mid, low = mix(BAR, WHITE, 0.52), mix(BAR, WHITE, 0.10), mix(BAR, (20, 110, 190), 0.42)
    grad = Image.new("RGB", (1, h * S))
    for y in range(h * S):
        t = y / (h * S - 1)
        grad.putpixel((0, y), mix(top, mid, t / 0.4) if t < 0.4 else mix(mid, low, (t - 0.4) / 0.6))
    out.paste(grad.resize((w * S, h * S)), (0, 0), fill)
    gloss = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(gloss).rounded_rectangle((2 * S, 1.6 * S, max(2 * S + 1, (length - 2) * S), 4.2 * S), 1.2 * S, fill=255)
    gloss = ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(0.7 * S)), fill)
    out.paste((255, 255, 255), (0, 0), gloss.point(lambda v: int(v * 0.36)))
    return {"rgb": out.resize((w, h), Image.LANCZOS), "alpha": shape.resize((w, h), Image.BOX), "hole_below": 128,
            "exact": dark}


def clean_icon(m):
    """An icon without what came with it from the design picture. The icons
    were cut out of that picture as brightness, so each carries a little of
    what was around it: a piece of its panel's top border as a line above it,
    and the panel's own brightness as a haze. Rows above the first and below
    the last row with real ink are emptied, the haze (the brightest pixel of
    the outer ring of what is left) is taken off everything, and what is left
    of it below one coverage level is dropped."""
    w, h = m.size
    px = [[m.getpixel((x, y)) for x in range(w)] for y in range(h)]

    def drawn(row):
        # Real ink is strong somewhere and absent somewhere else. A row that
        # is about equally bright from end to end is a piece of border.
        return max(row) >= 128 and max(row) - min(row) >= 0.45 * max(row)

    inked = [y for y in range(h) if drawn(px[y])]
    for y in range(h):
        if y < inked[0] or y > inked[-1]:
            px[y] = [0] * w
    ring = px[inked[0]] + px[inked[-1]] + [row[0] for row in px] + [row[-1] for row in px]
    haze = min(64, max(ring))
    out = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            v = (px[y][x] - haze) * 255 // (255 - haze)
            out.putpixel((x, y), v if v >= 17 else 0)
    return out


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
        # Gloss: the corner where the title is catches the light. It lies on
        # the upper part of the title strip (or, with no strip, on a narrow
        # band under the top edge) and has faded out before half the panel's
        # width, so that everything the image draws lands on a flat colour.
        band = (sh if strip_to is not None else 12) * 0.62
        gloss = fade_mask((w, h), lambda px, py: (1.0 - py / band) * (1.0 - px / (w * 0.44)) ** 1.4
                          if px < w * 0.44 and py < band else 0.0)
        self.img.paste(mix(accent, WHITE, 0.55), (x, y),
                       ImageChops.multiply(gloss, rr(w, h, r)).point(lambda v: int(v * 0.38)))
        inner = rr(w, h, r, 1.6).filter(ImageFilter.GaussianBlur(1.8)).point(lambda v: int(v * 0.42))
        self.blend(accent, x, y, ImageChops.multiply(inner, rr(w, h, r)))
        self.blend(mix(accent, WHITE, 0.12), x, y, rr(w, h, r, 1.0).point(lambda v: int(v * 0.92)))
        # and the border itself is brightest at that corner
        shine = fade_mask((w, h), lambda px, py: 1.0 - (px + 2.2 * py) / (w * 0.36))
        self.img.paste(mix(accent, WHITE, 0.82), (x, y),
                       ImageChops.multiply(rr(w, h, r, 1.3), shine).point(lambda v: int(v * 0.9)))

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
        if name != "logo":
            m = clean_icon(m)
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


def encode_picture(indices, width):
    """A picture's colour numbers (`width` a row, row after row) as a stream
    of operations. Each starts with one byte, kind in the top two bits and n
    in the low six:
      00 n        the next n+1 pixels equal the pixel one row up
      01 n c      the next n+1 pixels have colour c
      10 n c...   the next n+1 pixels have the n+1 colours that follow
      11 n m      the next (n*256+m)+1 pixels equal the pixel one row up
    Pixels above the first row count as colour 0."""
    W = width
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


def decode_picture(stream, width):
    """The inverse of encode_picture, to check it."""
    W = width
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
    if abs(pitch - round(pitch)) > 1e-6:
        raise ValueError(f"a fixed-pitch font needs a whole-pixel pitch, not {pitch}")
    pitch = round(pitch)
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


def word_mask(s, fx, tracking=0.0):
    """A whole word as one mask, cut to its ink. `dx` is where the ink starts
    to the right of the word's left edge; `up` is how far its top lies above
    the word's middle line."""
    m, origin, _ = text_mask(s, fx, tracking)
    box = q16(m).getbbox()
    return {"mask": m.crop(box), "w": box[2] - box[0], "h": box[3] - box[1],
            "dx": box[0] - round(origin), "up": m.height // 2 - box[1]}


# --- the design ---------------------------------------------------------------

def build():
    c = Canvas()
    f_brand = fit_w(F_POP_B, "REVIVAL OS", 276, tall=1.30)
    f_title = fit_w(F_POP_B, "CPU REGISTERS", 198, tall=1.32)
    f_row1 = fit_w(F_COND_B, "PHASE 2: IMAGE 2", 228)
    # The design's pitches, each moved to the nearest whole panel pixel.
    p_val, p_val2, p_small, p_par = whole(16.5), whole(15.25), whole(13.6), whole(13.55)
    p_hdr1, p_hdr2, p_tick = whole(12.8), whole(10.77), whole(20.6)
    f_val = fit_p(F_COND_B, p_val)
    f_val2 = fit_p(F_COND_B, p_val2)
    f_lab = fit_w(F_COND_B, "REVISION", 113)
    f_small = fit_p(F_COND_B, p_small)
    f_par = fit_p(F_MONO_B, p_par, fill=1.0)
    f_hdr1 = fit_p(F_MONO, p_hdr1, fill=1.0, tall=1.3)
    f_hdr2 = fit_p(F_MONO, p_hdr2, fill=1.0, tall=1.3)
    f_chip = fit_w(F_COND_B, "SVC", 41, tall=1.45)   # not the monospace font: its zero has a dot in it
    f_ok = fit_w(F_COND_B, "OK", 36)
    f_tick_l = fit_w(F_POP_B, "TICK", 60, tall=1.32)
    f_stat = fit_w(F_COND_B, "STATUS:", 86)
    PP = round(p_par * SX)   # the command line's pitch, in panel pixels
    L = {}  # the layout: every number the image needs to place what it draws

    # ---- header ----------------------------------------------------------
    c.art("logo", (206, 246, 252))
    c.text(X(165), Y(52), "REVIVAL OS", (224, 246, 252), f_brand, glow=0.55, tracking=1.3)
    c.grid(X(738), Y(33), "Boot Console v0.1", (160, 222, 230), f_hdr1, p_hdr1 * SX)
    c.grid(X(540), Y(65), "Target: Samsung GT-I9195 (S4 Mini LTE)", (204, 212, 218), f_hdr2, p_hdr2 * SX)

    # ---- row 1: phase | self-test ---------------------------------------
    c.panel(30, 97, 437, 150, CYAN, body=ROW1_BODY)
    c.art("layers", (196, 226, 234))
    c.text(X(112), Y(124), "PHASE 2: IMAGE 3", WHITE, f_row1, tracking=0.5)
    c.panel(457, 97, 965, 150, CYAN, body=ROW1_BODY)
    c.art("pulse", (60, 226, 180))
    end = c.text(X(530), Y(124), "SELFTEST:", WHITE, f_row1, tracking=0.5)
    L["SELF_X"], L["ROW1_Y"] = end + 5, Y(124)
    glow = 3   # room around every chip for its glow
    ok1 = (X(881) - X(819), Y(141) - Y(107))
    L["SELF_CHIP_X"], L["SELF_CHIP_Y"] = X(819) - glow, Y(107) - glow

    # ---- row 2: CPU registers | CPU status ------------------------------
    c.panel(28, 170, 414, 341, CYAN, strip_to=213)
    c.art("chip", CYAN)
    c.text(X(108), Y(190), "CPU REGISTERS", CYAN, f_title, glow=0.4, tracking=0.2)
    L["REG_X"], L["REG_Y"] = X(168), [Y(v) for v in (234, 262, 290, 319)]
    for name, yc in zip(("R0", "R1", "R2", "R3"), L["REG_Y"]):
        c.grid(X(65), yc, name, LABEL, f_val, p_val * SX)
    c.panel(428, 170, 967, 341, CYAN, strip_to=213)
    c.art("gear", CYAN)
    c.text(X(514), Y(190), "CPU STATUS", CYAN, f_title, glow=0.4, tracking=0.2)
    L["STAT_X"], L["STAT_Y"] = X(539), [Y(249), Y(299)]
    c.text(X(449), Y(249), "CPSR", LABEL, f_lab)
    c.text(X(450), Y(299), "SCTLR", LABEL, f_lab)
    c.rect(mix(BODY, CYAN, 0.3), X(440), Y(274), X(955) - X(440), 1)
    bit = (26, 24)
    L["CHIP_X"] = [X(v) - glow for v in (686, 741, 796, 849, 906)]
    L["CHIP_Y"] = [yc - bit[1] // 2 - glow for yc in L["STAT_Y"]]

    # ---- row 3: boot information | memory map ---------------------------
    c.panel(27, 361, 500, 615, PURPLE, strip_to=405)
    c.art("rocket", PURPLE)
    c.text(X(111), Y(381), "BOOT INFORMATION", PURPLE, f_title, glow=0.4, tracking=0.2)
    L["INFO_X"], L["INFO_Y"] = X(203), [Y(v) for v in (427, 454, 481, 509, 537, 564, 592)]
    for name, yc in zip(("MACH", "ENTRY", "ATAGS", "CORE", "INITRD2", "REVISION", "SERIAL"), L["INFO_Y"]):
        c.text(X(58), yc, name, LABEL, f_lab)
    ok2 = (X(405) - X(353), Y(468) - Y(441))
    L["ENTRY_CHIP_X"], L["ENTRY_CHIP_Y"] = X(353) - glow, Y(441) - glow
    L["SZ_LABEL_X"], L["SZ_X"] = X(338), X(373)
    # The red chip that says why a tag list was not read to its end: at the
    # right-hand end of this panel's title, where nothing else is.
    warn = (46, 20)
    L["WARN_X"], L["WARN_Y"] = X(500) - 8 - warn[0] - glow, Y(381) + 1 - warn[1] // 2 - glow
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
    # The first word may take this much of the head line and no more, so that
    # after it and two spaces the second word still has eight characters:
    # enough for a cut word to show how it starts. No word is left out.
    L["HEAD_FIRST_CHARS"] = L["HEAD_CHARS"] - 2 - 8
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
    # The inside of the track is the image's: one of sixteen stored pictures,
    # each the whole inside with so many sixteenths of it filled.
    L["BAR_X"], L["BAR_Y"] = bx + 3, by + 3
    bar_size = (bw - 6, bh - 6)

    fonts = {
        "VAL_REG": grid_font(f_val, p_val * SX, HEX + "-+"),
        "VAL": grid_font(f_val2, p_val2 * SX, HEX + "-+"),
        "SMALL": grid_font(f_small, p_small * SX, HEX),
        "ROW1": grid_font(f_row1, round(f_row1[0].getlength("0") * f_row1[1] + 0.5), HEX),
        "TICK": strict_font(F_COND_B, p_tick, HEX),
        "PAR": grid_font(f_par, PP, "".join(chr(v) for v in range(0x20, 0x7F))),
    }
    masks = {
        "HIDDEN": word_mask("HIDDEN", f_lab, 0.8), "MEM": word_mask("MEM", f_lab),
        "AT": word_mask("AT", f_lab), "SZ": word_mask("SZ", f_small),
        "READING": word_mask("Reading", f_stat, 0.3), "RUNNING": word_mask("Running", f_stat, 0.3),
    }

    def sprites(colours):
        """The chips and the bar as colour pictures, laid over the colours
        that the finished background really has where they go."""
        body, row1, title = colours["BG_BODY"], colours["BG_ROW1"], colours["BG_WARN"]
        green_ink, grey_ink = mix(GREEN, WHITE, 0.62), (226, 230, 238)
        out = {}
        for name in ("USR", "FIQ", "IRQ", "SVC", "MON", "ABT", "HYP", "UND", "SYS"):
            out[f"MODE_{name}"] = chip_sprite(name, f_chip, bit, PURPLE, 1.0, (240, 234, 248), body, glow)
        out["MODE_UNKNOWN"] = chip_sprite("???", f_chip, bit, PURPLE, 1.0, (240, 234, 248), body, glow)
        for letter in "IFATMCV":
            out[f"BIT_{letter}0"] = chip_sprite(f"{letter}:0", f_chip, bit, GREY, 0.45, grey_ink, body, glow)
            out[f"BIT_{letter}1"] = chip_sprite(f"{letter}:1", f_chip, bit, GREEN, 1.0, green_ink, body, glow)
        for word in ("OUT", "ODD", "DTB", "SIZE", "PAST", "MANY", "KIND"):
            out[f"WARN_{word}"] = chip_sprite(word, f_chip, warn, RED, 1.0, mix(RED, WHITE, 0.75), title, glow)
        out["OK_ROW1"] = chip_sprite("OK", f_ok, ok1, GREEN, 1.0, green_ink, row1, glow)
        out["BAD_ROW1"] = chip_sprite("BAD", f_ok, ok1, RED, 1.0, mix(RED, WHITE, 0.75), row1, glow)
        out["OK_BODY"] = chip_sprite("OK", f_ok, ok2, GREEN, 1.0, green_ink, body, glow)
        for lit in range(1, 17):
            out[f"BAR_{lit:02d}"] = bar_sprite(bar_size[0], bar_size[1], lit, 16, colours["BAR_DARK"])
        return out
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
    }
    # places whose background colour the image must know, read back from the finished picture
    probes = {
        "BG_ROW1": (L["SELF_X"] + 30, L["ROW1_Y"]), "BG_BODY": (L["REG_X"] + 20, L["REG_Y"][1] + 9),
        "BG_LIST": (L["LIST_RIGHT_X"] - 40, L["LIST_Y"]), "BG_CFG": (L["MDP_X"] + 60, L["MDP_Y"]),
        "BG_TEXT": (L["TEXT_RIGHT_X"] - 40, L["TEXT_Y"]),
        "BG_WARN": (L["WARN_X"] + glow + warn[0] // 2, L["WARN_Y"] + glow + warn[1] // 2),
        "BG_STATUS": (L["TICK_X"] + 20, L["TICK_Y"]), "BAR_DARK": (L["BAR_X"] + 60, L["BAR_Y"] + 8),
    }
    return c.img, L, fonts, masks, colours, probes, sprites


def sprite_palette(pics):
    """One palette for all the small colour pictures, and each picture as
    colour numbers. Colour 0 means "no pixel here": the image leaves such a
    pixel as it is. A picture's `exact` colour gets a palette entry of its
    own, so that it comes out as exactly that colour."""
    exact = sorted({pic["exact"] for pic in pics.values() if "exact" in pic})
    shown = []
    for pic in pics.values():
        rgb, alpha = pic["rgb"].load(), pic["alpha"].load()
        w, h = pic["rgb"].size
        shown += [rgb[x, y] for y in range(h) for x in range(w) if alpha[x, y] >= pic["hole_below"]]
    strip = Image.new("RGB", (len(shown), 1))
    strip.putdata(shown)
    room = 255 - len(exact)
    q = strip.quantize(colors=room, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    found = q.getpalette()[:3 * room]
    palette = [(0, 0, 0)] + exact + [tuple(found[i:i + 3]) for i in range(0, len(found), 3)]
    numbers = iter(q.tobytes())
    out = {}
    for name, pic in pics.items():
        rgb, alpha = pic["rgb"].load(), pic["alpha"].load()
        w, h = pic["rgb"].size
        idx = bytearray()
        for y in range(h):
            for x in range(w):
                if alpha[x, y] < pic["hole_below"]:
                    idx.append(0)
                    continue
                n = next(numbers)
                idx.append(1 + exact.index(rgb[x, y]) if rgb[x, y] in exact else 1 + len(exact) + n)
        out[name] = bytes(idx)
    flat = bytes(v for colour in palette for v in colour)
    return flat.ljust(768, b"\0"), out


def rust_colour(c):
    return f"[{c[0]}, {c[1]}, {c[2]}]"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", metavar="FILE.png", help="also write the background as a PNG")
    args = parser.parse_args(argv)

    img, L, fonts, masks, colours, probes, sprites = build()
    pal_img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = bytes(pal_img.getpalette()[:768]).ljust(768, b"\0")
    indices = pal_img.tobytes()
    assert len(indices) == W * H
    stream = encode_picture(indices, W)
    assert decode_picture(stream, W) == indices, "the background does not survive encoding"

    def probe(xy):
        i = indices[xy[1] * W + xy[0]]
        return tuple(palette[3 * i:3 * i + 3])

    for name, xy in probes.items():
        colours[name] = probe(xy)
    pics = sprites(colours)
    del colours["BAR_DARK"]   # only the bar's pictures needed it
    sprite_pal, sprite_idx = sprite_palette(pics)

    blob = bytearray(palette)
    index = {"width": W, "height": H, "palette_off": 0, "bg_off": len(blob), "bg_len": len(stream)}
    blob += stream
    index["sprite_palette_off"] = len(blob)
    blob += sprite_pal
    index["sprites"] = {}
    for name, pic in pics.items():
        w, h = pic["rgb"].size
        packed = encode_picture(sprite_idx[name], w)
        assert decode_picture(packed, w) == sprite_idx[name], f"picture {name} does not survive encoding"
        index["sprites"][name] = {"off": len(blob), "len": len(packed), "w": w, "h": h}
        blob += packed
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
    # What drew the pictures. The same tool with another Pillow or another
    # font file may draw them differently; this says what to install to get
    # these bytes again.
    index["made_with"] = {
        "pillow": PIL.__version__,
        "fonts": {Path(path).name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                  for path in (F_MONO, F_MONO_B, F_COND_B, F_POP_B)},
        "art_png": hashlib.sha256((OUT / "art.png").read_bytes()).hexdigest(),
    }
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
         "use crate::gfx::{Font, Mask, Picture, Rgb};",
         "",
         "/// The stored pictures: palettes, background, chips, bar, letters and masks.",
         'pub static BLOB: &[u8] = include_bytes!("assets.bin");',
         f"pub const BLOB_LEN: usize = {len(blob)};",
         f'pub const BLOB_SHA256: &str = "{index["blob_sha256"]}";',
         "",
         f"pub const WIDTH: usize = {W};",
         f"pub const HEIGHT: usize = {H};",
         f"pub const PALETTE_OFF: usize = {index['palette_off']};",
         f"pub const BG_OFF: usize = {index['bg_off']};",
         f"pub const BG_LEN: usize = {index['bg_len']};",
         f"pub const SPRITE_PALETTE_OFF: usize = {index['sprite_palette_off']};",
         ""]

    def picture(name):
        v = index["sprites"][name]
        return f"Picture {{ off: {v['off']}, len: {v['len']}, w: {v['w']}, h: {v['h']} }}"

    for name in index["sprites"]:
        if name.startswith("BIT_") and name.endswith("0"):
            letter = name[4]
            r.append(f"/// Bit {letter}: [0] when it is clear, [1] when it is set.")
            r.append(f"pub const CHIP_BIT_{letter}: [Picture; 2] = [")
            r.append(f"    {picture(name)},")
            r.append(f"    {picture(f'BIT_{letter}1')},")
            r.append("];")
        elif not name.startswith(("BIT_", "BAR_")):
            r.append(f"pub const CHIP_{name}: Picture = {picture(name)};")
    r.append("/// The bar: BAR[n] has n + 1 sixteenths of it filled.")
    r.append("pub static BAR: [Picture; 16] = [")
    for lit in range(1, 17):
        r.append(f"    {picture(f'BAR_{lit:02d}')},")
    r.append("];")
    r.append("")
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
    chips = sum(v["len"] for k, v in index["sprites"].items() if not k.startswith("BAR_"))
    bars = sum(v["len"] for k, v in index["sprites"].items() if k.startswith("BAR_"))
    print(f"pictures: {len(index['sprites'])} ({chips} bytes of chips, {bars} bytes of bar)")
    print(f"assets.bin: {len(blob)} bytes, sha256 {index['blob_sha256']}")
    if args.preview:
        pal_img.convert("RGB").save(args.preview)
        print("wrote", args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
