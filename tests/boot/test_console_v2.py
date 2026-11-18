"""Unit tests for the console image's host oracle (tests/boot/console_v2.py).

Pure host tests, discovered by `make test-unit` (unit-python). They pin the
screen's wording and layout, the rules for reading a tag list, the rule that
no hidden value can reach the screen, the font and its generated Rust table,
and the framebuffer round trip. They test the ORACLE; that the image agrees
with the oracle is what the QEMU test (tests/boot/run_console.py) shows.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import re
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

from tests.boot import console_v2 as o

ROOT = Path(__file__).resolve().parents[2]
CONSOLE_DIR = ROOT / "boot/samsung-serranolte/console"


def report(page=None, **regs):
    """The report lines for a handoff, right-stripped, without empty tails."""
    lines = [line.rstrip() for line in o.report_text(o.Handoff(**regs), page)]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def tags_report(data: bytes, address: int = o.PHONE_R2):
    """The report lines from the ATAGS line on, for `data` stored at r2."""
    lines = report(o.page_with(data, address), r2=address)
    return lines[9:]


class GridTests(unittest.TestCase):
    def test_grid_covers_the_panel_exactly(self):
        self.assertEqual((o.CELL_W, o.CELL_H), (18, 24))
        self.assertEqual((o.COLUMNS, o.LINES), (30, 40))
        self.assertEqual(o.COLUMNS * o.CELL_W, o.WIDTH)
        self.assertEqual(o.LINES * o.CELL_H, o.HEIGHT)
        self.assertEqual(o.FB_BYTES, 1_555_200)

    def test_fixed_lines_are_the_last_two(self):
        self.assertEqual((o.REPORT_LINES, o.MDP_LINE, o.TICK_LINE), (38, 38, 39))

    def test_framebuffer_clear_of_image_stack_and_tags(self):
        fb = (o.FB_BASE, o.FB_BASE + o.FB_BYTES)
        image_and_stack = (o.LINK_ENTRY, o.LINK_ENTRY + (16 << 20))  # link.ld: 16 MiB
        tags = (o.TAGS_PAGE_LO, o.TAGS_PAGE_HI)
        for lo, hi in (image_and_stack, tags):
            self.assertFalse(fb[0] < hi and lo < fb[1])


class FontTests(unittest.TestCase):
    def setUp(self):
        self.font = o.load_font()

    def test_every_printable_ascii_code_once(self):
        self.assertEqual(sorted(self.font), list(range(0x20, 0x7F)))

    def test_glyphs_are_distinct_and_only_space_is_empty(self):
        self.assertEqual(len(set(self.font.values())), 95)
        for code, art in self.font.items():
            lit = sum(row.count("#") for row in art)
            self.assertEqual(lit == 0, code == 0x20, f"glyph {code:#04x}")

    def test_hex_digits_differ_by_at_least_three_pixels(self):
        digits = [self.font[ord(c)] for c in "0123456789ABCDEF"]
        for i, a in enumerate(digits):
            for b in digits[i + 1:]:
                differ = sum(x != y for ra, rb in zip(a, b) for x, y in zip(ra, rb))
                self.assertGreaterEqual(differ, 3)

    def test_generated_rust_table_matches_the_art(self):
        # Read font.rs here, independently of the generator: one row byte per
        # art row, bit 4 the leftmost pixel.
        source = (CONSOLE_DIR / "font.rs").read_text(encoding="ascii")
        rows = re.findall(r"^    \[((?:0x[0-9A-F]{2}(?:, )?){7})\], // 0x([0-9A-F]{2})",
                          source, flags=re.M)
        self.assertEqual(len(rows), 95)
        for values, code in rows:
            art = self.font[int(code, 16)]
            want = [sum((cell == "#") << (4 - i) for i, cell in enumerate(row)) for row in art]
            self.assertEqual([int(v, 16) for v in values.split(", ")], want, f"glyph 0x{code}")

    def test_generator_check_passes(self):
        done = subprocess.run([sys.executable, "-I", str(ROOT / "tools/gen_console_font.py"),
                               "--check"], capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)


class WindowTests(unittest.TestCase):
    def test_wraps_after_the_last_column(self):
        win = o.Window(3)
        win.puts("A" * 31)
        self.assertEqual(win.text(), ["A" * 30, "A".ljust(30), " " * 30])
        self.assertFalse(win.overflow)

    def test_a_full_line_then_newline_does_not_skip_a_line(self):
        win = o.Window(3)
        win.puts("A" * 30 + "\nB")
        self.assertEqual(win.text()[1], "B".ljust(30))

    def test_overflow_marks_the_last_cell_and_drops_the_rest(self):
        win = o.Window(2)
        win.puts("one\ntwo\nthree")
        self.assertTrue(win.overflow)
        self.assertEqual(win.text(), ["one".ljust(30), "two".ljust(29) + "+"])

    def test_filling_the_window_exactly_is_not_overflow(self):
        win = o.Window(2)
        win.puts("A" * 60 + "\n\n")
        self.assertFalse(win.overflow)
        self.assertEqual(win.text(), ["A" * 30, "A" * 30])

    def test_codes_outside_printable_ascii_show_as_question_mark(self):
        win = o.Window(1)
        win.puts(bytes([0x00, 0x1F, 0x7F, 0xFF, 0x41]))
        self.assertEqual(win.text(), ["????A".ljust(30)])


class ReportTests(unittest.TestCase):
    def test_phone_handoff_wording(self):
        # The registers measured on the phone on 2026-11-18, with no tag list.
        lines = [line.rstrip() for line in o.report_text(o.phone_handoff())][:10]
        self.assertEqual(lines, [
            "REVIVAL OS",
            "PHASE 2 IMAGE 2",
            "SELFTEST 22BECBA4 OK",
            "R0 00000000 R1 00000E8F",
            "R2 80200100 R3 00000000",
            "MACH 3727",
            "CPSR 60000193 SVC I1 F0 A1 T0",
            "SCTLR 00C5487A M0 C0 I0 A1 V0",
            "ENTRY 80208000 OK",
            "ATAGS 80200100",
        ])

    def test_qemu_reset_wording(self):
        lines = report(cpsr=0x4000_01D3, sctlr=0x00C5_0078)
        self.assertEqual(lines[5:], [
            "MACH 0",
            "CPSR 400001D3 SVC I1 F1 A1 T0",
            "SCTLR 00C50078 M0 C0 I0 A0 V0",
            "ENTRY 80208000 OK",
            "ATAGS 00000000 OUT OF PAGE",
        ])

    def test_every_mode_and_bit(self):
        for mode, name in o.MODE_NAMES.items():
            self.assertIn(f" {name} ", report(cpsr=mode)[6])
        self.assertIn(" ??? ", report(cpsr=0x14)[6])
        self.assertTrue(report(cpsr=0x1F | 0x20)[6].endswith("I0 F0 A0 T1"))
        self.assertTrue(report(sctlr=0x3007)[7].endswith("M1 C1 I1 A1 V1"))

    def test_lines_fit_the_screen(self):
        full = o.Handoff(*([0xFFFF_FFFF] * 6), o.LINK_ENTRY)
        for line in o.report_text(full):
            self.assertEqual(len(line), o.COLUMNS)
        # Nothing wrapped: the nine register lines are still nine lines.
        self.assertTrue(o.report_text(full)[8].startswith("ENTRY "))

    def test_screen_states(self):
        h = o.phone_handoff()
        pending = o.screen_text(h, None, None)
        self.assertEqual((pending[38].rstrip(), pending[39].rstrip()), ("MDP4 READ PENDING", ""))
        live = o.screen_text(h, None, o.FB_BASE, 0x1F)
        self.assertEqual((live[38].rstrip(), live[39].rstrip()),
                         ("MDP4 88100000 IS FB", "TICK 0000001F"))
        other = o.screen_text(h, None, 0x8830_0000, 0)
        self.assertEqual(other[38].rstrip(), "MDP4 88300000 NOT FB")
        self.assertEqual(len(live), o.LINES)

    def test_moved_image_has_no_text_screen(self):
        with self.assertRaises(ValueError):
            o.screen_text(o.Handoff(entry=0x80A0_8000))


class TagTests(unittest.TestCase):
    def test_sample_list(self):
        self.assertEqual(tags_report(o.sample_tags()), [
            "ATAGS 80200100",
            " CORE",
            " MEM 08000000 AT 80200000",
            " MEM 10000000 AT 90000000",
            " INITRD2 82200000 SZ 00000000",
            " REVISION 0000000B",
            " SERIAL HIDDEN",
            " TAG 4D534D70 W12",
            " CMDLINE console=<4>",
            "  androidboot.hardware=<4>",
            "  user_debug=<2>",
            "  msm_rtb.filter=<4>",
            "  ehci-hcd.park=<1>",
            "  androidboot.bootloader=<12>",
            "  androidboot.serialno=<12>",
            "  loglevel=<1> <5> label=<20>",
            "  <12>",
            " END 8 TAGS",
        ])

    def test_r2_outside_the_page_or_unaligned_is_not_read(self):
        marker = o.tag(o.ATAG_REVISION, 0x1234_5678) + o.end_tag()
        for r2, why in ((0, "OUT OF PAGE"), (o.TAGS_PAGE_LO - 4, "OUT OF PAGE"),
                        (o.TAGS_PAGE_HI, "OUT OF PAGE"), (0xFFFF_FFFC, "OUT OF PAGE"),
                        (o.PHONE_R2 + 1, "UNALIGNED"), (o.PHONE_R2 + 2, "UNALIGNED")):
            lines = report(o.page_with(marker), r2=r2)
            self.assertEqual(lines[9:], [f"ATAGS {r2:08X} {why}"])

    def test_first_and_last_word_of_the_page(self):
        self.assertEqual(tags_report(o.end_tag(), o.TAGS_PAGE_LO),
                         ["ATAGS 80200000", " END 0 TAGS"])
        # One word left: not even a tag header fits.
        self.assertEqual(report(r2=o.TAGS_PAGE_HI - 4)[9:],
                         ["ATAGS 80207FFC", " STOP PAST PAGE END"])

    def test_device_tree_is_named_and_skipped(self):
        blob = struct.pack(">I", 0xD00D_FEED) + b"SECRET" * 4
        self.assertEqual(tags_report(blob), ["ATAGS 80200100 DEVICE TREE"])

    def test_core_with_a_body_shows_the_page_size(self):
        data = o.tag(o.ATAG_CORE, 0, 0x1000, 0) + o.end_tag()
        self.assertEqual(tags_report(data)[1:], [" CORE PAGE 00001000", " END 1 TAGS"])

    def test_short_bodies(self):
        data = (o.tag(o.ATAG_MEM, 0x10) + o.tag(o.ATAG_INITRD2) + o.tag(o.ATAG_REVISION)
                + o.end_tag())
        self.assertEqual(tags_report(data)[1:],
                         [" MEM SHORT", " INITRD2 SHORT", " REVISION", " END 3 TAGS"])

    def test_bad_sizes_stop_the_walk(self):
        for size in (1, o.MAX_TAG_WORDS + 1, 0xFFFF_FFFF):
            data = o.tag(o.ATAG_CORE) + struct.pack("<2I", size, o.ATAG_MEM)
            self.assertEqual(tags_report(data)[1:], [" CORE", f" STOP SIZE {size:08X}"])

    def test_largest_tag_is_accepted(self):
        data = o.tag(0x1111_1111, *([0] * (o.MAX_TAG_WORDS - 2))) + o.end_tag()
        self.assertEqual(tags_report(data)[1:], [" TAG 11111111 W2046", " END 1 TAGS"])

    def test_tag_running_past_the_page_end_stops_the_walk(self):
        # 16 words before the end of the page, a tag that claims 17.
        address = o.TAGS_PAGE_HI - 64
        data = struct.pack("<2I", 17, o.ATAG_MEM)
        self.assertEqual(tags_report(data, address),
                         ["ATAGS 80207FC0", " STOP PAST PAGE END"])
        # The same tag claiming exactly 16 fits, and then the page is over.
        data = struct.pack("<2I", 16, 0x2222_2222)
        self.assertEqual(tags_report(data, address),
                         ["ATAGS 80207FC0", " TAG 22222222 W14", " STOP PAST PAGE END"])

    def test_tag_limit(self):
        # More lines than the screen has, so read them from a taller window.
        def all_lines(data):
            win = o.Window(100)
            o._report_tags(win, o.PHONE_R2, o.page_with(data))
            return [line.rstrip() for line in win.text() if line.strip()]

        exactly = all_lines(o.tag(0x3333_3333) * o.MAX_TAGS + o.end_tag())
        self.assertEqual(len(exactly), 1 + o.MAX_TAGS + 1)
        self.assertEqual(exactly[-1], " END 64 TAGS")
        over = all_lines(o.tag(0x3333_3333) * (o.MAX_TAGS + 1) + o.end_tag())
        self.assertEqual(len(over), 1 + o.MAX_TAGS + 1)
        self.assertEqual(over[-1], " STOP AT 64 TAGS")

    def test_end_tag_with_a_kind_is_reported(self):
        data = o.tag(o.ATAG_CORE) + struct.pack("<2I", 0, 0xABCD_0123)
        self.assertEqual(tags_report(data)[1:], [" CORE", " END 1 TAGS", " END KIND ABCD0123"])

    def test_report_overflow_marks_the_last_report_cell(self):
        data = o.tag(o.ATAG_MEM, 1, 2) * 40 + o.end_tag()
        lines = o.report_text(o.Handoff(r2=o.PHONE_R2), o.page_with(data))
        self.assertEqual(len(lines), o.REPORT_LINES)
        self.assertEqual(lines[-1], " MEM 00000001 AT 00000002".ljust(29) + "+")


class CmdlineTests(unittest.TestCase):
    def shown(self, text: bytes):
        data = o.cmdline_tag(text) + o.end_tag()
        return " ".join(line.strip() for line in tags_report(data)[1:-1])

    def test_names_and_lengths_only(self):
        self.assertEqual(self.shown(b"a=1 bb=22 ccc=333"), "CMDLINE a=<1> bb=<2> ccc=<3>")

    def test_words_without_equals_show_only_their_length(self):
        self.assertEqual(self.shown(b"quiet ro SECRET"), "CMDLINE <5> <2> <6>")

    def test_empty_value_and_empty_name(self):
        self.assertEqual(self.shown(b"a= =SECRET b==x"), "CMDLINE a=<0> =<6> b=<2>")

    def test_quotes_keep_a_value_with_spaces_whole(self):
        self.assertEqual(self.shown(b'a="SECRET one two" b=1'), "CMDLINE a=<16> b=<1>")
        # An unclosed quote takes the rest of the line into the value.
        self.assertEqual(self.shown(b'a="SECRET b=1 c=2'), "CMDLINE a=<15>")

    def test_all_white_space_separates(self):
        self.assertEqual(self.shown(b"  a=1\tb=2\nc=3\r\x0b\x0cd=4  "),
                         "CMDLINE a=<1> b=<1> c=<1> d=<1>")

    def test_empty_command_line(self):
        self.assertEqual(self.shown(b""), "CMDLINE")
        self.assertEqual(self.shown(b"   "), "CMDLINE")

    def test_text_stops_at_the_first_zero_byte(self):
        self.assertEqual(self.shown(b"a=1\0b=SECRET"), "CMDLINE a=<1>")

    def test_text_without_a_zero_byte_stops_at_the_end_of_the_tag(self):
        body = b"key=SECRET12"  # three whole words, no terminator
        data = struct.pack("<2I", 2 + len(body) // 4, o.ATAG_CMDLINE) + body
        data += o.tag(o.ATAG_REVISION, 7) + o.end_tag()
        self.assertEqual(tags_report(data)[1:],
                         [" CMDLINE key=<8>", " REVISION 00000007", " END 2 TAGS"])

    def test_words_are_kept_whole_at_the_line_end(self):
        data = o.cmdline_tag(b"aaaaaaaaaa=1 bbbbbbbbbb=2 cccccccccc=3") + o.end_tag()
        self.assertEqual(tags_report(data)[1:-1],
                         [" CMDLINE aaaaaaaaaa=<1>", "  bbbbbbbbbb=<1>", "  cccccccccc=<1>"])
        # A word that exactly reaches the last column stays on its line.
        data = o.cmdline_tag(b"k" * 17 + b"=1") + o.end_tag()
        self.assertEqual(tags_report(data)[1], " CMDLINE " + "k" * 17 + "=<1>")
        data = o.cmdline_tag(b"k" * 18 + b"=1") + o.end_tag()
        self.assertEqual(tags_report(data)[1:3], [" CMDLINE", "  " + "k" * 18 + "=<1>"])

    def test_a_name_longer_than_a_line_wraps(self):
        data = o.cmdline_tag(b"n" * 40 + b"=1") + o.end_tag()
        self.assertEqual(tags_report(data)[1:-1],
                         [" CMDLINE", "  " + "n" * 28, "n" * 12 + "=<1>"])

    def test_unprintable_name_bytes_show_as_question_marks(self):
        self.assertEqual(self.shown(b"a\x01\xffb=1"), "CMDLINE a??b=<1>")


class PrivacyTests(unittest.TestCase):
    """Nothing the image must hide may be readable on the screen."""

    def test_sample_screen_shows_no_hidden_value(self):
        lines = o.screen_text(o.phone_handoff(), o.page_with(o.sample_tags()), o.FB_BASE, 3)
        screen = "\n".join(lines)
        for secret in o.SAMPLE_SECRETS:
            self.assertNotIn(secret.decode(), screen)
        self.assertNotIn("5EC2E7", screen.replace(" ", ""))

    def test_decoded_framebuffer_shows_no_hidden_value(self):
        fb = o.expected_fb(o.phone_handoff(), o.page_with(o.sample_tags()), o.FB_BASE, 3)
        screen = "\n".join(o.decode(fb))
        for secret in o.SAMPLE_SECRETS:
            self.assertNotIn(secret.decode(), screen)

    def test_split_cmdline_returns_no_value_bytes(self):
        body = o.cmdline_tag(o.SAMPLE_CMDLINE)[8:]
        words = o.split_cmdline(list(struct.unpack(f"<{len(body) // 4}I", body)))
        self.assertEqual(len(words), 11)
        for name, value_length, _word_length in words:
            self.assertEqual(name == b"", value_length is None)
            for secret in o.SAMPLE_SECRETS:
                self.assertNotIn(secret, name)

    def test_serial_and_unknown_tag_words_are_never_formatted(self):
        data = (o.tag(o.ATAG_SERIAL, 0xDEAD_BEEF, 0xFEED_F00D)
                + o.tag(0x7777_7777, 0xDEAD_BEEF, 0xFEED_F00D) + o.end_tag())
        screen = "\n".join(tags_report(data))
        for hidden in ("DEADBEEF", "FEEDF00D"):
            self.assertNotIn(hidden, screen)


class FramebufferTests(unittest.TestCase):
    def test_round_trip(self):
        lines = o.screen_text(o.phone_handoff(), o.page_with(o.sample_tags()), o.FB_BASE, 0xABC)
        fb = o.render(lines)
        self.assertEqual(len(fb), o.FB_BYTES)
        self.assertEqual(o.decode(fb), lines)
        self.assertEqual(o.tick_of(fb), 0xABC)

    def test_only_black_and_white_and_whole_pixels(self):
        fb = o.expected_fb(o.phone_handoff(), None, o.FB_BASE, 1)
        self.assertEqual(set(fb), {0x00, 0xFF})
        for i in range(0, 3 * 2000, 3):
            self.assertEqual(len(set(fb[i:i + 3])), 1)

    def test_glyph_placement(self):
        # 'R' of "REVIVAL OS": its top-left glyph pixel is lit, 3x3 screen
        # pixels at the panel's top left; the spacing column and row are dark.
        fb = o.expected_fb(o.phone_handoff())

        def px(x, y):
            return fb[y * o.STRIDE + x * o.BPP]

        self.assertEqual([px(x, y) for y in range(3) for x in range(3)], [0xFF] * 9)
        self.assertEqual({px(x, y) for y in range(24) for x in range(15, 18)}, {0x00})
        self.assertEqual({px(x, y) for y in range(21, 24) for x in range(18)}, {0x00})

    def test_tick_of_rejects_a_half_drawn_line(self):
        lines = o.screen_text(o.phone_handoff(), None, o.FB_BASE, 5)
        lines[o.TICK_LINE] = "TICK 0000".ljust(o.COLUMNS)
        self.assertIsNone(o.tick_of(o.render(lines)))
        fb = bytearray(o.render(o.screen_text(o.phone_handoff(), None, o.FB_BASE, 5)))
        fb[(o.TICK_LINE * o.CELL_H) * o.STRIDE + 6 * o.CELL_W * o.BPP] ^= 0xFF
        self.assertIsNone(o.tick_of(bytes(fb)))

    def test_moved_stripes(self):
        fb = o.moved_fb()
        self.assertEqual(len(fb), o.FB_BYTES)
        height = o.HEIGHT // o.MOVED_STRIPES
        for stripe in range(o.MOVED_STRIPES):
            rows = fb[stripe * height * o.STRIDE:(stripe + 1) * height * o.STRIDE]
            self.assertEqual(set(rows), {0xFF if stripe % 2 == 0 else 0x00})

    def test_png(self):
        fb = o.expected_fb(o.phone_handoff())
        png = o.png_bytes(fb)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">2I", png[16:24]), (o.WIDTH, o.HEIGHT))
        size = struct.unpack(">I", png[33:37])[0]
        self.assertEqual(png[37:41], b"IDAT")
        raw = zlib.decompress(png[41:41 + size])
        self.assertEqual(len(raw), (o.STRIDE + 1) * o.HEIGHT)
        self.assertEqual(raw[1:1 + o.STRIDE], fb[:o.STRIDE])


if __name__ == "__main__":
    unittest.main()
