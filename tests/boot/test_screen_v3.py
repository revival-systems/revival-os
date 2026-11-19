"""Unit tests for the boot screen image's host oracle (tests/boot/screen_v3.py)
and for the stored pictures it shares with the image.

Pure host tests, discovered by `make test-unit` (unit-python). They check
that the three generated files (assets.bin, assets.rs, assets.json) describe
the same pictures, that the layout the image relies on holds (fixed-pitch
fonts, chip words that fit, values drawn on the background colour the image
assumes), the rules for placing command-line words, the rule that no hidden
value can reach the screen, and the framebuffer round trips. They test the
ORACLE and the DATA; that the image agrees with the oracle is what the QEMU
test (tests/boot/run_screen.py) shows.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import hashlib
import re
import struct
import unittest
import zlib
from pathlib import Path

from tests.boot import console_v2 as con
from tests.boot import screen_v3 as o

ROOT = Path(__file__).resolve().parents[2]
SCREEN_DIR = ROOT / "boot/samsung-serranolte/screen"
SAMPLE_PNG = ROOT / "docs/phase-2/screen-sample.png"
A, L, C = o.A, o.L, o.C

# The oracle's screen for the handoff and tag list the phone gave on
# 2026-11-19, with the counter at 0x56. It changes whenever the stored
# pictures or the drawing rules change; such a change is then a decision, made
# here, and not an accident.
PHONE_SCREEN_SHA256 = "ccb0b113f7e57de2cc116fc174ebbc0c051477865c501a7797203945787f279a"


def parse_assets_rs(text: str) -> dict:
    """The constants of assets.rs, as Python values."""
    rs: dict = {}
    for name, value in re.findall(r"^pub const (\w+): usize = (\d+);", text, re.M):
        rs[name] = int(value)
    for name, value in re.findall(r'^pub const (\w+): &str = "(\w+)";', text, re.M):
        rs[name] = value
    for name, body in re.findall(r"^pub const (\w+): \[usize; \d+\] = \[([^\]]*)\];", text, re.M):
        rs[name] = [int(v) for v in body.split(",")]
    for name, body in re.findall(r"^pub const (\w+): \[\[usize; \d+\]; \d+\] = \[(.*)\];", text, re.M):
        rs[name] = [[int(v) for v in row.split(",")] for row in re.findall(r"\[([^\[\]]*)\]", body)]
    for name, body in re.findall(r"^pub const (\w+): Rgb = \[([^\]]*)\];", text, re.M):
        rs[name] = [int(v) for v in body.split(",")]
    for name, body in re.findall(r"^pub const MASK_(\w+): Mask = Mask \{([^}]*)\};", text, re.M):
        rs["MASK_" + name] = {key.strip(): int(value)
                              for key, value in (item.split(":") for item in body.split(","))}
    for name, body in re.findall(r"^pub static FONT_(\w+): Font = Font \{(.*?)^\};", text, re.M | re.S):
        font = {key: int(value) for key, value in re.findall(r"^    (\w+): (\d+),$", body, re.M)}
        table = re.search(r"map: \[(.*?)\],\n    adv16", body, re.S).group(1)
        font["map"] = [int(v) for v in table.replace("\n", " ").split(",") if v.strip()]
        font["adv16"] = [int(v) for v in re.search(r"adv16: &\[([^\]]*)\]", body).group(1).split(",")]
        rs["FONT_" + name] = font
    return rs


def box_of_difference(a: bytes, b: bytes):
    """The smallest box (x0, y0, x1, y1), x1 and y1 exclusive, that holds every
    pixel in which two framebuffers differ; None if they are equal."""
    rows = [y for y in range(o.H) if a[y * o.STRIDE:(y + 1) * o.STRIDE] != b[y * o.STRIDE:(y + 1) * o.STRIDE]]
    if not rows:
        return None
    xs = []
    for y in rows:
        ra, rb = a[y * o.STRIDE:(y + 1) * o.STRIDE], b[y * o.STRIDE:(y + 1) * o.STRIDE]
        xs += [i // o.BPP for i in range(o.STRIDE) if ra[i] != rb[i]]
    return min(xs), rows[0], max(xs) + 1, rows[-1] + 1


def phone_page(extra=()) -> bytes:
    return con.page_with(o.phone_tags(extra))


def words(n: int) -> bytes:
    """A tag page whose command line has exactly `n` words."""
    text = " ".join(f"w{i}=1" for i in range(n)).encode()
    return con.page_with(con.cmdline_tag(text) + con.end_tag())


PHONE = con.phone_handoff(r3=0x1141)


class AssetsTests(unittest.TestCase):
    """assets.bin, assets.rs and assets.json describe the same pictures."""

    @classmethod
    def setUpClass(cls):
        cls.rs = parse_assets_rs((SCREEN_DIR / "assets.rs").read_text(encoding="ascii"))

    def test_blob_is_the_file_both_indexes_describe(self):
        o.check_assets()
        digest = hashlib.sha256(o.BLOB).hexdigest()
        self.assertEqual((A["blob_len"], A["blob_sha256"]), (len(o.BLOB), digest))
        self.assertEqual((self.rs["BLOB_LEN"], self.rs["BLOB_SHA256"]), (len(o.BLOB), digest))

    def test_rust_header_agrees_with_json(self):
        for rust, key in (("WIDTH", "width"), ("HEIGHT", "height"), ("PALETTE_OFF", "palette_off"),
                          ("BG_OFF", "bg_off"), ("BG_LEN", "bg_len")):
            self.assertEqual(self.rs[rust], A[key], rust)
        self.assertEqual((o.W, o.H, o.STRIDE), (con.WIDTH, con.HEIGHT, con.STRIDE))

    def test_rust_fonts_agree_with_json(self):
        self.assertEqual({name for name in self.rs if name.startswith("FONT_")},
                         {"FONT_" + name for name in A["fonts"]})
        for name, font in A["fonts"].items():
            rust = self.rs["FONT_" + name]
            for key in ("off", "cell_w", "cell_h", "up", "pad", "space16", "adv16"):
                self.assertEqual(rust[key], font[key], f"{name}.{key}")
            table = [0xFF] * 96
            for index, char in enumerate(font["chars"]):
                table[ord(char) - 0x20] = index
            self.assertEqual(rust["map"], table, name)

    def test_rust_masks_layout_and_colours_agree_with_json(self):
        self.assertEqual({name for name in self.rs if name.startswith("MASK_")},
                         {"MASK_" + name for name in A["masks"]})
        for name, mask in A["masks"].items():
            self.assertEqual(self.rs["MASK_" + name], mask, name)
        for name, value in L.items():
            self.assertEqual(self.rs[name], value, name)
        for name, value in A["colours"].items():
            self.assertEqual(self.rs[name], value, name)
        # and nothing in the Rust file that the index does not have
        known = ({"BLOB_LEN", "BLOB_SHA256", "WIDTH", "HEIGHT", "PALETTE_OFF", "BG_OFF", "BG_LEN"}
                 | set(L) | set(A["colours"]) | {"MASK_" + n for n in A["masks"]}
                 | {"FONT_" + n for n in A["fonts"]})
        self.assertEqual(set(self.rs), known)

    def test_pictures_fill_the_blob_exactly(self):
        spans = [(A["palette_off"], 768), (A["bg_off"], A["bg_len"])]
        for font in A["fonts"].values():
            glyph = font["cell_h"] * ((font["cell_w"] + 1) // 2)
            spans.append((font["off"], glyph * len(font["chars"])))
        for mask in A["masks"].values():
            spans.append((mask["off"], mask["h"] * ((mask["w"] + 1) // 2)))
        at = 0
        for off, size in sorted(spans):
            self.assertEqual(off, at, "a gap or an overlap in assets.bin")
            at += size
        self.assertEqual(at, len(o.BLOB))

    def test_background_stream_is_exactly_one_screen(self):
        stream = o.BLOB[A["bg_off"]:A["bg_off"] + A["bg_len"]]
        i = pixels = 0
        while i < len(stream):
            kind, n = stream[i] >> 6, stream[i] & 0x3F
            i += 1
            if kind == 3:
                n = (n << 8) | stream[i]
                i += 1
            i += {0: 0, 1: 1, 2: n + 1, 3: 0}[kind]
            pixels += n + 1
        self.assertEqual((i, pixels), (len(stream), o.W * o.H))
        # every byte of the panel is written by the background alone
        self.assertEqual(len(o.background_fb()), o.FB_BYTES)

    def test_a_pixel_is_blue_green_red(self):
        s = o.Screen()
        s.put(1, 0, (0x11, 0x22, 0x33))
        self.assertEqual(bytes(s.fb[3:6]), bytes([0x33, 0x22, 0x11]))
        s.put(o.W, 0, (1, 2, 3))   # off the panel: ignored
        s.put(0, o.H, (1, 2, 3))
        s.put(-1, 0, (1, 2, 3))
        self.assertEqual(s.fb.count(0), o.FB_BYTES - 3)

    def test_blend_is_the_documented_rounding(self):
        s = o.Screen()
        font = A["fonts"]["TICK"]
        s.glyph(font, 0, font["up"], ord("8"), (255, 255, 255), (0, 0, 0))
        levels = {s.fb[i] for i in range(0, font["cell_h"] * o.STRIDE, 3)}
        self.assertTrue(levels <= {(a * 255 + 7) // 15 for a in range(16)})
        self.assertIn(255, levels)

    def test_fonts_fit_the_images_tables(self):
        for name, font in A["fonts"].items():
            self.assertLess(len(font["chars"]), 255, name)
            self.assertEqual(len(set(font["chars"])), len(font["chars"]), name)
            self.assertTrue(all(0x20 <= ord(c) <= 0x7E for c in font["chars"]), name)
            self.assertLessEqual(max(font["adv16"]), 255, name)
            self.assertEqual(len(font["adv16"]), len(font["chars"]), name)

    def test_grid_fonts_are_fixed_pitch_in_whole_pixels(self):
        # The layout counts characters, not pixels, wherever these are used.
        # A whole-pixel pitch puts every letter on a whole pixel, so the gaps
        # between letters are all the same; with a pitch of 7.3 pixels,
        # `sysscope` read as `syss cope`.
        for name in ("PAR", "TICK", "VAL", "VAL_REG", "SMALL", "ROW1"):
            font = A["fonts"][name]
            self.assertEqual(set(font["adv16"]), {font["space16"]}, name)
            self.assertEqual(font["space16"] % 16, 0, name)
        self.assertEqual(len(A["fonts"]["PAR"]["chars"]), 0x7F - 0x20)

    def test_counter_cells_do_not_overlap(self):
        font = A["fonts"]["TICK"]
        self.assertEqual(font["pad"], 0)
        left = [((L["TICK_X"] << 4) + i * font["space16"]) >> 4 for i in range(8)]
        for a, b in zip(left, left[1:]):
            self.assertGreaterEqual(b - a, font["cell_w"])

    def test_index_says_what_drew_the_pictures(self):
        made = A["made_with"]
        self.assertRegex(made["pillow"], r"^\d+\.\d+")
        self.assertEqual(len(made["fonts"]), 4)
        for name, digest in list(made["fonts"].items()) + [("art.png", made["art_png"])]:
            self.assertRegex(digest, r"^[0-9a-f]{64}$", name)
            self.assertNotIn("/", name)
        self.assertEqual(made["art_png"], hashlib.sha256((SCREEN_DIR / "art.png").read_bytes()).hexdigest())

    def test_chip_words_fit_their_chips(self):
        chip = A["fonts"]["CHIP"]

        def width(text):
            return sum(chip["adv16"][chip["chars"].index(c)] for c in text)

        bits = [f"{letter}:{bit}" for letter in "IFATMCV" for bit in "01"]
        for text in list(con.MODE_NAMES.values()) + ["???"] + bits:
            self.assertLessEqual(width(text), A["masks"]["BIT_FILL"]["w"] << 4, text)
        for text in o.WARN_WORDS.values():
            self.assertLessEqual(width(text), A["masks"]["WARN_FILL"]["w"] << 4, text)
        for word, shape in (("OK", "OK1_FILL"), ("BAD", "OK1_FILL"), ("OK", "OK2_FILL")):
            self.assertLessEqual(A["masks"][word]["w"], A["masks"][shape]["w"])
            self.assertLessEqual(A["masks"][word]["h"], A["masks"][shape]["h"])
        self.assertEqual((A["masks"]["BIT_FILL"]["w"], A["masks"]["BIT_FILL"]["h"]), (L["CHIP_W"], L["CHIP_H"]))

    def test_words_stay_inside_their_places(self):
        step = A["fonts"]["PAR"]["space16"]

        def right(x, chars):
            return ((x << 4) + chars * step) >> 4

        self.assertLess(right(L["HEAD_X"], L["HEAD_CHARS"]), o.W)
        # after the longest first word and two spaces, the second word has room
        self.assertGreaterEqual(L["HEAD_CHARS"] - L["HEAD_FIRST_CHARS"] - 2, 8)
        self.assertGreater(L["HEAD_FIRST_CHARS"], 30)
        self.assertLess(right(L["COL_X"][0], L["COL_CHARS"][0]), L["COL_X"][1])
        self.assertLess(right(L["COL_X"][1], L["COL_CHARS"][1]), o.W)
        self.assertLess(right(L["CFG_X"][0], L["CFG_CHARS"][0]), L["CFG_X"][2])
        self.assertLess(right(L["CFG_X"][2], L["CFG_CHARS"][2]), o.W)
        self.assertLess(right(L["MDP_X"], len("88100000 NOT FB")), o.W)
        self.assertEqual((len(L["COL_X"]), len(L["CFG_X"]), len(L["MEM_Y"]), len(L["INFO_Y"])), (2, 3, 6, 7))
        # rows closer together than this would run the letters of one row into the next
        pitch = L["ROW_SPAN"] // (L["ROWS_MAX"] - 1)
        self.assertGreaterEqual(pitch, A["fonts"]["PAR"]["cell_h"] - 2)


class CheckedScreen(o.Screen):
    """A Screen that notes every pixel drawn on a colour other than the one
    the image assumes is there. The image never reads the framebuffer back, so
    a wrong assumption would show as a halo around a letter."""

    def __init__(self):
        super().__init__()
        self.wrong = []
        self.drawn = set()
        self.outlines = {m["off"] for name, m in A["masks"].items() if name.endswith("_LINE")}

    def mask(self, x, y, w, h, off, fg, bg):
        row_bytes = (w + 1) // 2
        for j in range(h):
            for i in range(w):
                byte = o.BLOB[off + j * row_bytes + i // 2]
                if (byte >> 4 if i % 2 == 0 else byte & 0xF) and 0 <= x + i < o.W and 0 <= y + j < o.H:
                    at = (y + j) * o.STRIDE + (x + i) * o.BPP
                    have = (self.fb[at + 2], self.fb[at + 1], self.fb[at])
                    # An outline lies on the edge of its own chip, and a letter
                    # may touch its neighbour: those pixels were drawn before.
                    if have != tuple(bg) and off not in self.outlines and (x + i, y + j) not in self.drawn:
                        self.wrong.append((x + i, y + j, have, tuple(bg)))
                    self.drawn.add((x + i, y + j))
        super().mask(x, y, w, h, off, fg, bg)

    def fill_rect(self, x, y, w, h, rgb):
        # A box is cleared to the colour that was there before anything was
        # drawn in it.
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                at = yy * o.STRIDE + xx * o.BPP
                have = (self.fb[at + 2], self.fb[at + 1], self.fb[at])
                if have != tuple(rgb) and (xx, yy) not in self.drawn:
                    self.wrong.append((xx, yy, have, tuple(rgb)))
        super().fill_rect(x, y, w, h, rgb)


class BackgroundColourTests(unittest.TestCase):
    def checked(self, *args):
        real = o.Screen
        o.Screen = CheckedScreen
        try:
            return o.draw(*args)
        finally:
            o.Screen = real

    def test_values_are_drawn_on_the_colour_the_image_assumes(self):
        extra = tuple((f"one_more_word_{i}", i + 1) for i in range(8))
        broken = (con.tag(con.ATAG_CORE, 0, 0x1000, 0) + con.tag(con.ATAG_MEM, 1, 2) * 8
                  + struct.pack("<2I", 5, con.ATAG_CMDLINE) + b"key=SECRET12"
                  + con.cmdline_tag(b"n" * 80 + b"=1 second=22 bare " + b"m" * 40 + b"=1")
                  + struct.pack("<2I", 0, 0xABCD_0123))
        cases = (
            (PHONE, phone_page(), o.FB_BASE, 0x56),
            (PHONE, phone_page(extra), 0x1234_5678, 0xFFFF_FFFF),
            (con.Handoff(1, 2, con.PHONE_R2, 4, 0x6000_01D7, 0x00C5_187F), con.page_with(broken), 0, 9),
            (PHONE, phone_page(), None, 0),
        )
        for case in cases:
            screen = self.checked(*case)
            self.assertEqual(screen.wrong[:5], [])


class ScreenTests(unittest.TestCase):
    def test_phone_screen_is_pinned(self):
        fb = o.expected_fb(PHONE, phone_page(), o.FB_BASE, 0x56)
        self.assertEqual(len(fb), o.FB_BYTES)
        self.assertEqual(hashlib.sha256(fb).hexdigest(), PHONE_SCREEN_SHA256)

    def test_a_moved_image_cannot_be_drawn_as_a_screen(self):
        with self.assertRaises(ValueError):
            o.draw(con.Handoff(entry=o.LINK_ENTRY + 0x1000))
        fb = o.moved_fb()
        self.assertEqual(len(fb), o.FB_BYTES)
        self.assertEqual(set(fb), {0x00, 0xFF})
        self.assertEqual(fb[:o.STRIDE], b"\xff" * o.STRIDE)

    def test_each_register_changes_only_its_own_place(self):
        base = o.expected_fb(con.Handoff(r2=con.PHONE_R2))
        for index, name in enumerate(("r0", "r1", "r2", "r3")):
            other = o.expected_fb(con.Handoff(r2=con.PHONE_R2)._replace(**{name: 0x89AB_CDEF}))
            box = box_of_difference(base, other)
            self.assertIsNotNone(box, name)
            if name == "r0" or name == "r3":   # r1 is also MACH; r2 is also ATAGS and the tag list
                self.assertGreaterEqual(box[1], L["REG_Y"][index] - 12, name)
                self.assertLessEqual(box[3], L["REG_Y"][index] + 12, name)

    def test_status_bits_are_chips(self):
        a = o.expected_fb(con.Handoff(sctlr=0))
        b = o.expected_fb(con.Handoff(sctlr=1 << 1))   # SCTLR.A, the fourth chip
        box = box_of_difference(a, b)
        # the value itself changes too; the chip that changes is the fourth one
        self.assertEqual(box[2], L["CHIP_X"][3] + L["CHIP_W"])
        self.assertGreaterEqual(box[1], L["STAT_Y"][1] - L["CHIP_H"] // 2)
        self.assertLessEqual(box[3], L["STAT_Y"][1] + L["CHIP_H"] // 2 + 1)
        # a bit with no chip changes the value only
        c = o.expected_fb(con.Handoff(sctlr=1 << 20))
        self.assertLess(box_of_difference(a, c)[2], L["CHIP_X"][0])

    def test_display_register_states(self):
        page = phone_page()
        reading = o.expected_fb(PHONE, page, None)
        is_fb = o.expected_fb(PHONE, page, o.FB_BASE, 0)
        not_fb = o.expected_fb(PHONE, page, 0, 0)
        self.assertIsNone(o.tick_of(reading))
        self.assertEqual(o.tick_of(is_fb), 0)
        self.assertNotEqual(is_fb, not_fb)
        box = box_of_difference(is_fb, not_fb)
        self.assertGreaterEqual(box[0], L["MDP_X"] - 4)
        self.assertLess(abs((box[1] + box[3]) // 2 - L["MDP_Y"]), 6)
        # before the read: no value, no counter, and another status word
        box = box_of_difference(reading, is_fb)
        self.assertGreaterEqual(box[1], L["MDP_Y"] - 12)

    def test_counter_round_trip_and_reach(self):
        page = phone_page()
        zero = o.expected_fb(PHONE, page, o.FB_BASE, 0)
        for tick in (0, 1, 9, 0xA, 0xF, 0x10, 0xFF, 0x100, 0x89AB_CDEF, 0xFFFF_FFFF):
            fb = o.expected_fb(PHONE, page, o.FB_BASE, tick)
            self.assertEqual(o.tick_of(fb), tick)
            band = fb[o.TICK_TOP * o.STRIDE:(o.TICK_TOP + o.TICK_ROWS) * o.STRIDE]
            self.assertEqual(o.tick_of_band(band), tick)
            if tick:
                cell = A["masks"]["BAR_CELL"]
                box = box_of_difference(zero, fb)
                self.assertGreaterEqual(box[0], L["TICK_X"])
                self.assertLessEqual(box[2], L["BAR_CELL_X"][-1] + cell["w"])
                self.assertGreaterEqual(box[1], min(o.TICK_TOP, L["BAR_CELL_Y"]))
                self.assertLessEqual(box[3], max(o.TICK_TOP + o.TICK_ROWS, L["BAR_CELL_Y"] + cell["h"]))
        self.assertEqual(o.tick_of(o.expected_fb(PHONE, page, o.FB_BASE, 1 << 32)), 0)
        self.assertIsNone(o.tick_of(o.background_fb()))
        self.assertIsNone(o.tick_of(o.moved_fb()))
        with self.assertRaises(ValueError):
            o.tick_of(zero[:-1])

    def test_bar_has_one_lit_cell_and_it_names_the_counters_last_four_bits(self):
        cell = A["masks"]["BAR_CELL"]
        self.assertEqual(len(L["BAR_CELL_X"]), 16)
        for a, b in zip(L["BAR_CELL_X"], L["BAR_CELL_X"][1:]):
            self.assertGreater(b - a, cell["w"])   # cells do not touch
        row = (L["BAR_CELL_Y"] + cell["h"] // 2) * o.STRIDE

        def middles(tick):
            fb = o.expected_fb(con.Handoff(), None, 0, tick)
            return [tuple(reversed(fb[row + (x + cell["w"] // 2) * 3:row + (x + cell["w"] // 2) * 3 + 3]))
                    for x in L["BAR_CELL_X"]]

        for tick in (0, 1, 7, 15, 16, 0x1F, 0x89AB_CDE5):
            want = [C["BAR_DIM"]] * 16
            want[tick % 16] = C["BAR_LIT"]
            self.assertEqual(middles(tick), want, tick)
        self.assertNotEqual(C["BAR_LIT"], C["BAR_DIM"])
        self.assertNotEqual(C["BAR_DIM"], C["BAR_DARK"])

    def test_self_test_sum_and_its_chip(self):
        self.assertEqual(o.table_sum(), o.SELFTEST_SUM)
        self.assertEqual(o.SELFTEST_SUM, con.SELFTEST_SUM)
        changed = list(o.SELFTEST_TABLE)
        changed[-1] ^= 1
        self.assertNotEqual(o.table_sum(changed), o.SELFTEST_SUM)
        good = o.expected_fb(con.Handoff())
        bad = o.expected_fb(con.Handoff(), selftest=o.table_sum(changed))
        box = box_of_difference(good, bad)
        # the sum's last digit and the chip, on the first row of panels
        self.assertGreater(box[0], L["SELF_X"])
        self.assertLessEqual(box[2], L["SELF_CHIP_X"] + A["masks"]["OK1_FILL"]["w"])
        self.assertLess(abs((box[1] + box[3]) // 2 - L["ROW1_Y"]), 6)
        # a wrong sum that happens to print the same digits cannot exist: the sum is what is printed
        self.assertNotEqual(o.expected_fb(con.Handoff(), selftest=0), good)


class TagListTests(unittest.TestCase):
    def screen(self, data: bytes, r2: int = con.PHONE_R2, at: int | None = None) -> bytes:
        return o.expected_fb(con.Handoff(r2=r2), con.page_with(data, r2 if at is None else at))

    def test_word_places(self):
        self.assertEqual([o.word_places(n) for n in (0, 1, 21, 22, 23, 24, 25, 26, 500)],
                         [(8, 0), (8, 1), (8, 21), (9, 22), (9, 23), (10, 24), (10, 25), (10, 25), (10, 25)])
        self.assertEqual((L["ROWS"], L["ROWS_MAX"]), (8, 10))

    def test_row_table_is_the_even_spacing(self):
        # The image looks its rows up; this is the rule the table must follow.
        self.assertEqual(len(L["ROW_Y"]), L["ROWS_MAX"] - L["ROWS"] + 1)
        for rows, table in zip(range(L["ROWS"], L["ROWS_MAX"] + 1), L["ROW_Y"]):
            self.assertEqual(len(table), L["ROWS_MAX"])
            self.assertEqual(table[:rows], [L["ROW0_Y"] + (row * L["ROW_SPAN"]) // (rows - 1)
                                            for row in range(rows)], rows)
            self.assertEqual((table[0], table[rows - 1]), (L["ROW0_Y"], L["ROW0_Y"] + L["ROW_SPAN"]))
            self.assertEqual(sorted(table[:rows]), table[:rows])
        # every list the image can meet gets a row count the table has
        for n in range(0, 300):
            rows, _shown = o.word_places(n)
            self.assertIn(rows, range(L["ROWS"], L["ROWS_MAX"] + 1))

    def test_the_phones_command_line_fits_as_designed(self):
        self.assertEqual(len(o.PHONE_WORDS), 21)
        self.assertEqual(o.word_places(len(o.PHONE_WORDS)), (L["ROWS"], 21))

    def test_note_only_when_something_is_not_shown(self):
        strip = (L["LIST_Y"] - 10) * o.STRIDE, (L["LIST_Y"] + 10) * o.STRIDE
        clean = o.background_fb()[strip[0]:strip[1]]
        for n, noted in ((0, False), (21, False), (25, False), (26, True), (40, True)):
            fb = o.expected_fb(con.Handoff(r2=con.PHONE_R2), words(n))
            self.assertEqual(fb[strip[0]:strip[1]] != clean, noted, n)
        # a seventh memory tag, or a kind with no place, is counted too
        for data in (con.tag(con.ATAG_MEM, 1, 2) * 7, con.tag(0x4D53_4D70, 1), con.tag(con.ATAG_CORE) * 2):
            fb = self.screen(data + con.end_tag())
            self.assertNotEqual(fb[strip[0]:strip[1]], clean)
        fb = self.screen(con.tag(con.ATAG_MEM, 1, 2) * 6 + con.end_tag())
        self.assertEqual(fb[strip[0]:strip[1]], clean)

    def test_every_way_a_list_can_fail_has_its_own_mark(self):
        hi = con.TAGS_PAGE_HI
        screens = {
            None: self.screen(con.tag(con.ATAG_CORE) + con.end_tag()),
            "out": self.screen(b"", r2=hi, at=con.PHONE_R2),
            "odd": self.screen(b"", r2=con.PHONE_R2 + 2, at=con.PHONE_R2),
            "dtb": self.screen(struct.pack(">I", 0xD00D_FEED)),
            "bad-size": self.screen(con.tag(con.ATAG_CORE) + struct.pack("<2I", 1, con.ATAG_MEM)),
            "past-end": self.screen(struct.pack("<2I", 17, con.ATAG_MEM), r2=hi - 64),
            "too-many": self.screen(con.tag(0x3333_3333) * (con.MAX_TAGS + 1) + con.end_tag()),
            "kind": self.screen(con.tag(con.ATAG_CORE) + struct.pack("<2I", 0, 0xABCD_0123)),
        }
        self.assertEqual(set(screens) - {None}, set(o.WARN_WORDS))
        # the chip's place holds the background on a good list, and seven
        # different pictures on the seven bad ones
        chips = {}
        for key, fb in screens.items():
            rows = [fb[(L["WARN_Y"] + j) * o.STRIDE + L["WARN_X"] * 3:
                       (L["WARN_Y"] + j) * o.STRIDE + (L["WARN_X"] + A["masks"]["WARN_FILL"]["w"]) * 3]
                    for j in range(A["masks"]["WARN_FILL"]["h"])]
            chips[key] = b"".join(rows)
        self.assertEqual(len(set(chips.values())), len(chips))
        self.assertEqual(set(chips[None]), set(reversed(C["BG_BODY"])))

    def test_unterminated_command_line_is_marked(self):
        strip = (L["TEXT_Y"] - 10) * o.STRIDE, (L["TEXT_Y"] + 10) * o.STRIDE
        clean = o.background_fb()[strip[0]:strip[1]]
        good = self.screen(con.cmdline_tag(b"key=value") + con.end_tag())
        bad = self.screen(struct.pack("<2I", 5, con.ATAG_CMDLINE) + b"key=value123" + con.end_tag())
        empty = self.screen(con.tag(con.ATAG_CMDLINE) + con.end_tag())
        self.assertEqual(good[strip[0]:strip[1]], clean)
        self.assertNotEqual(bad[strip[0]:strip[1]], clean)
        self.assertNotEqual(empty[strip[0]:strip[1]], clean)

    def test_no_word_is_left_out_of_the_head_line(self):
        # Whatever the first word is, the second is drawn: cut, if it must be.
        # (Until the reviewed build of 2026-11-19 a first word of 52 characters
        # or more left the second one out without a mark.)
        for first in (b"a=1", b"f" * 40 + b"=1", b"f" * 60 + b"=1", b"f" * 500 + b"=1", b"f" * 51):
            one = self.screen(con.cmdline_tag(first) + con.end_tag())
            two = self.screen(con.cmdline_tag(first + b" second=22") + con.end_tag())
            box = box_of_difference(one, two)
            self.assertIsNotNone(box, first[:8])
            self.assertLess(abs((box[1] + box[3]) // 2 - L["HEAD_Y"]), 8)
            self.assertLess(box[2], o.W - 16)
        s = o.Screen()
        long_word = [("f", "NAME")] * 60
        pen, count = o._draw_word(s, L["HEAD_X"] << 4, L["HEAD_Y"], long_word, L["HEAD_FIRST_CHARS"], C["BG_BODY"])
        self.assertEqual(count, L["HEAD_FIRST_CHARS"])

    def test_long_words_are_cut_and_stay_in_their_column(self):
        long_name = b"n" * 200
        fb = self.screen(con.cmdline_tag(b"a=1 b=2 " + long_name + b"=1 short=2") + con.end_tag())
        ref = self.screen(con.cmdline_tag(b"a=1 b=2 c=1 short=2") + con.end_tag())
        box = box_of_difference(fb, ref)
        self.assertGreaterEqual(box[0], L["COL_X"][0] - 4)
        self.assertLess(box[2], L["COL_X"][1])   # the second column is untouched
        s = o.Screen()
        piece = [("x", "NAME")] * 10
        self.assertEqual(o._draw_word(s, 0, 20, piece, 10, C["BG_BODY"])[1], 10)
        self.assertEqual(o._draw_word(s, 0, 20, piece, 9, C["BG_BODY"])[1], 9)
        self.assertEqual(o._draw_word(s, 0, 20, piece, 1, C["BG_BODY"])[1], 1)
        self.assertEqual(o._draw_word(s, 0, 20, piece, 0, C["BG_BODY"]), (0, 0))

    def test_hidden_values_cannot_change_the_screen(self):
        """Every value the image must hide is replaced by another of the same
        length; the screen must stay the same in every byte."""
        data = con.sample_tags()
        other = (data.replace(b"SECRET", b"public").replace(b"5EC2E7", b"A1B2C3")
                 .replace(b"\xe7\xc2\x5e", b"\x11\x22\x33").replace(b"null", b"ttyS").replace(b"qcom", b"abcd")
                 .replace(b"0x3F", b"0x00").replace(b"=31", b"=77").replace(b"=3 ", b"=9 ").replace(b"=4 ", b"=7 "))
        self.assertNotEqual(data, other)
        self.assertEqual(len(data), len(other))
        for secret in con.SAMPLE_SECRETS:
            self.assertIn(secret, data)
            self.assertNotIn(secret, other)
        h = con.Handoff(r1=con.PHONE_R1, r2=con.PHONE_R2)
        self.assertEqual(o.expected_fb(h, con.page_with(data), o.FB_BASE, 3),
                         o.expected_fb(h, con.page_with(other), o.FB_BASE, 3))
        # the names and the lengths, which are shown, do change it
        renamed = data.replace(b"loglevel", b"logLEVEL")
        self.assertNotEqual(o.expected_fb(h, con.page_with(data)), o.expected_fb(h, con.page_with(renamed)))

    def test_only_the_first_of_a_kind_fills_its_place(self):
        one = self.screen(con.tag(con.ATAG_REVISION, 5) + con.end_tag())
        two = self.screen(con.tag(con.ATAG_REVISION, 5) + con.tag(con.ATAG_REVISION, 6) + con.end_tag())
        box = box_of_difference(one, two)
        self.assertLess(abs((box[1] + box[3]) // 2 - L["LIST_Y"]), 8)   # only the note differs

    def test_command_line_tags_are_read_as_one_list(self):
        split = self.screen(con.cmdline_tag(b"a=1 b=22") + con.cmdline_tag(b"c=333") + con.end_tag())
        joined = self.screen(con.cmdline_tag(b"a=1 b=22 c=333") + con.end_tag())
        self.assertEqual(split, joined)


class PngTests(unittest.TestCase):
    def pixels(self, png: bytes) -> bytes:
        """The pixel rows of a PNG file written by the oracle, as the
        framebuffer holds them: blue, green, red."""
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height, depth, colour = struct.unpack(">2I2B", png[16:26])
        self.assertEqual((width, height, depth, colour), (o.W, o.H, 8, 2))
        at, data = 8, b""
        while at < len(png):
            (size,), kind = struct.unpack(">I", png[at:at + 4]), png[at + 4:at + 8]
            body = png[at + 8:at + 8 + size]
            self.assertEqual(struct.unpack(">I", png[at + 8 + size:at + 12 + size])[0],
                             zlib.crc32(kind + body) & 0xFFFF_FFFF)
            if kind == b"IDAT":
                data += body
            at += 12 + size
        raw = zlib.decompress(data)
        self.assertEqual(len(raw), o.H * (1 + o.STRIDE))
        out = bytearray()
        for y in range(o.H):
            self.assertEqual(raw[y * (1 + o.STRIDE)], 0)   # filter 0: the row as it is
            row = bytearray(raw[y * (1 + o.STRIDE) + 1:(y + 1) * (1 + o.STRIDE)])
            row[0::3], row[2::3] = row[2::3], row[0::3]
            out += row
        return bytes(out)

    def test_png_round_trip(self):
        fb = o.expected_fb(PHONE, phone_page(), o.FB_BASE, 0x56)
        self.assertEqual(self.pixels(o.png_bytes(fb)), fb)
        with self.assertRaises(ValueError):
            o.png_bytes(fb[:-1])

    def test_the_documents_picture_is_the_oracles_screen(self):
        # docs/phase-2/screen-payload.md shows this file. Compared pixel by
        # pixel, not byte by byte: two zlib versions may pack the same pixels
        # differently. To renew it: make screen-sample, and copy the file.
        fb = o.expected_fb(PHONE, phone_page(), o.FB_BASE, 0x56)
        self.assertEqual(self.pixels(SAMPLE_PNG.read_bytes()), fb)


if __name__ == "__main__":
    unittest.main()
