"""Unit tests for the Phase 2 row-reading tool (tools/read_rows.py).

Pure host tests, discovered by `make test-unit` (unit-python). They check each
decoded field (CPSR, SCTLR, entry address, *r2, the MDP4 word, the fill colour),
the record for the QEMU words and for the handoff section 2 of the research
expects from the phone, a misread checksum row, an eight-row input, inputs that
contradict each other, the command line, and that the PNG of the screen decodes
back to the same words with the host oracle.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import contextlib
import io
import os
import struct
import tempfile
import unittest
import zlib

from tests.boot import serrano_v1 as o
from tools import read_rows as rr

# What section 2 of docs/phase-2/boot-payload-research.md expects the stock
# bootloader to hand over: r0 = 0, r1 = 3727, r2 = the tags address with an
# ATAGS list there, SVC mode with IRQ masked and FIQ not, MMU and caches off,
# the image at its link address. The ninth word is the display register.
SVC_IRQ_MASKED = 0x0000_0093


def device_words(mdp: int) -> list:
    return [0, o.MACH_SERRANO, o.TAGS_ADDR, SVC_IRQ_MASKED, o.QEMU_SCTLR,
            o.ENTRY_ADDR, 5, o.checksum(), mdp]


def read_png(data: bytes) -> tuple:
    """(width, height, RGB bytes) of an 8-bit RGB PNG whose scan lines all use
    filter type 0. Checks the signature, every chunk CRC and the chunk order."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, chunks = 8, []
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack_from(">I", data, pos + 8 + length)
        assert crc == zlib.crc32(kind + body), f"bad CRC in {kind!r}"
        chunks.append((kind, body))
        pos += 12 + length
    assert [k for k, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"], chunks
    width, height, depth, colour, comp, filt, lace = struct.unpack(">IIBBBBB", chunks[0][1])
    assert (depth, colour, comp, filt, lace) == (8, 2, 0, 0, 0)
    raw = zlib.decompress(chunks[1][1])
    stride = width * 3
    assert len(raw) == height * (stride + 1)
    rgb = bytearray()
    for y in range(height):
        row = raw[y * (stride + 1):(y + 1) * (stride + 1)]
        assert row[0] == 0, f"scan line {y} uses filter {row[0]}"
        rgb += row[1:]
    return width, height, bytes(rgb)


def run_main(*argv) -> tuple:
    """(exit status, stdout) of the tool's command line."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = rr.main(list(argv))
    return status, out.getvalue()


def hexwords(words) -> list:
    return [f"{w:08X}" for w in words]


class CpsrTests(unittest.TestCase):
    def test_qemu_value(self):
        c = rr.decode_cpsr(o.QEMU_CPSR)  # 0x400001D3
        self.assertEqual((c.mode, c.mode_name), (0x13, "SVC"))
        self.assertTrue(c.irq_masked and c.fiq_masked and c.abort_masked)
        self.assertFalse(c.thumb or c.big_endian)

    def test_expected_device_value(self):
        c = rr.decode_cpsr(SVC_IRQ_MASKED)
        self.assertEqual(c.mode_name, "SVC")
        self.assertTrue(c.irq_masked)
        self.assertFalse(c.fiq_masked or c.abort_masked or c.thumb or c.big_endian)

    def test_each_mask_bit_alone(self):
        base = 0x13
        self.assertEqual(rr.decode_cpsr(base | 1 << 7)[2:], (True, False, False, False, False))
        self.assertEqual(rr.decode_cpsr(base | 1 << 6)[2:], (False, True, False, False, False))
        self.assertEqual(rr.decode_cpsr(base | 1 << 8)[2:], (False, False, True, False, False))
        self.assertEqual(rr.decode_cpsr(base | 1 << 5)[2:], (False, False, False, True, False))
        self.assertEqual(rr.decode_cpsr(base | 1 << 9)[2:], (False, False, False, False, True))

    def test_modes(self):
        for bits, name in ((0x10, "USR"), (0x11, "FIQ"), (0x12, "IRQ"), (0x13, "SVC"),
                           (0x16, "MON"), (0x17, "ABT"), (0x1A, "HYP"), (0x1B, "UND"),
                           (0x1F, "SYS")):
            self.assertEqual(rr.decode_cpsr(0xFFFF_FFE0 | bits).mode_name, name)
        self.assertIsNone(rr.decode_cpsr(0x0000_0000).mode_name)  # not a mode


class SctlrTests(unittest.TestCase):
    def test_qemu_value_has_everything_off(self):
        self.assertEqual(rr.decode_sctlr(o.QEMU_SCTLR), (False,) * 5)

    def test_each_bit_alone(self):
        for bit, field in ((0, "mmu"), (1, "align"), (2, "dcache"), (12, "icache"),
                           (13, "high_vectors")):
            s = rr.decode_sctlr(o.QEMU_SCTLR | 1 << bit)
            self.assertEqual([f for f in s._fields if getattr(s, f)], [field])

    def test_neighbouring_bits_are_not_read(self):
        # Bits 3-6, 11 and 14 are not fields this tool reports.
        self.assertEqual(rr.decode_sctlr(0x0000_4878), (False,) * 5)


class EntryTests(unittest.TestCase):
    def test_link_address(self):
        self.assertEqual(rr.classify_entry(o.ENTRY_ADDR), ("link", 0))

    def test_relocated_up_and_down(self):
        self.assertEqual(rr.classify_entry(0x80A0_8000), ("relocated", 0x0080_0000))
        self.assertEqual(rr.classify_entry(0x8000_8000), ("relocated", -0x0020_0000))


class AtR2Tests(unittest.TestCase):
    def test_sentinel_when_r2_is_not_read(self):
        self.assertEqual(rr.classify_at_r2(0, o.R2_OUT_OF_RANGE)[0], "sentinel")
        self.assertEqual(rr.classify_at_r2(0x8020_0102, o.R2_OUT_OF_RANGE)[0], "sentinel")

    def test_atag_core_header(self):
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 5)[0], "atag_core")
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 2)[0], "atag_core")

    def test_dtb_magic_as_a_little_endian_word(self):
        (word,) = struct.unpack("<I", bytes.fromhex("d00dfeed"))
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, word)[0], "dtb")
        # The magic written as a number is not what a little-endian read gives.
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 0xD00D_FEED)[0], "other")

    def test_other_words(self):
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 0x1234_5678)[0], "other")
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 0x5441_0001)[0], "other")
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, 3)[0], "other")
        # 0xFFFFFFFF at an r2 the payload does read is memory, not the sentinel.
        self.assertEqual(rr.classify_at_r2(o.TAGS_ADDR, o.R2_OUT_OF_RANGE)[0], "other")

    def test_a_word_at_an_unread_r2_is_impossible(self):
        kind, text = rr.classify_at_r2(0, 5)
        self.assertEqual(kind, "impossible")
        self.assertIn("misread", text)


class Mdp4Tests(unittest.TestCase):
    def test_candidates(self):
        self.assertEqual(rr.classify_mdp4(o.FB_RED)[0], "candidate")
        self.assertEqual(rr.classify_mdp4(o.FB_GREEN)[0], "candidate")
        self.assertIn("red or blue", rr.classify_mdp4(o.FB_RED)[1])
        self.assertIn("green", rr.classify_mdp4(o.FB_GREEN)[1])

    def test_painted_third_buffer(self):
        for mdp in (0x8900_0000, 0x8847_C000, 0x8800_0000):
            self.assertEqual(rr.classify_mdp4(mdp)[0], "third", hex(mdp))

    def test_rejected_with_the_reason(self):
        for mdp, why in ((0x0000_0000, "not wholly inside device RAM"),
                         (0x8900_0002, "not word-aligned"),
                         (0x8F00_0000, "WCNSS"),
                         (0x8000_0000, "SMEM"),
                         (0x8020_8000, "the image and its stack"),
                         (0x8020_0000, "the tags page"),
                         (0x8FB0_0000, "modem rmtfs"),
                         (0xDFFF_0000, "not wholly inside device RAM")):
            kind, text = rr.classify_mdp4(mdp)
            self.assertEqual(kind, "rejected", hex(mdp))
            self.assertIn(why, text, hex(mdp))

    def test_it_is_the_oracles_rule(self):
        # "third" exactly when the oracle says the payload paints a third buffer.
        for mdp in (0, 4, 0x8000_0000, 0x8020_0100, 0x8810_0000, 0x8810_0004,
                    0x8830_0000, 0x8840_0000, 0x8847_C000, 0x8900_0000, 0x8900_0001,
                    0x8EF0_0000, 0x8F00_0000, 0xA000_0000, 0xDFE8_4500, 0xDFE8_4504,
                    0xE000_0000, 0xFFFF_FFFC):
            self.assertEqual(rr.classify_mdp4(mdp)[0] == "third", o.is_plausible_fb(mdp),
                             hex(mdp))


class FillTests(unittest.TestCase):
    def test_which_buffer_each_colour_means(self):
        self.assertEqual(rr.FILLS["red"].buffer, 0x8810_0000)
        self.assertEqual(rr.FILLS["blue"].buffer, 0x8810_0000)
        self.assertEqual(rr.FILLS["green"].buffer, 0x8830_0000)
        self.assertIsNone(rr.FILLS["grey"].buffer)  # the MDP4 address

    def test_colours_as_seen(self):
        self.assertEqual(rr.FILLS["red"].seen_px, (255, 0, 0))
        self.assertEqual(rr.FILLS["blue"].seen_px, (0, 0, 255))
        self.assertEqual(rr.FILLS["green"].seen_px, (0, 255, 0))
        self.assertEqual(rr.FILLS["grey"].seen_px, (128, 128, 128))

    def test_byte_order_lines(self):
        red = rr.build_record("red", device_words(o.FB_RED)).text
        self.assertIn("Fill colour red: the buffer at 0x88100000 is on screen; byte 0 "
                      "is red, so the order in memory is red, green, blue", red)
        blue = rr.build_record("blue", device_words(o.FB_RED)).text
        self.assertIn("Fill colour blue: the buffer at 0x88100000 is on screen; byte 0 "
                      "is blue, so the order in memory is blue, green, red", blue)
        green = rr.build_record("green", device_words(o.FB_GREEN)).text
        self.assertIn("Fill colour green: the buffer at 0x88300000 is on screen", green)
        self.assertIn("the byte order is not shown", green)

    def test_grey_means_the_mdp4_address(self):
        rec = rr.build_record("grey", device_words(0x8900_0000))
        self.assertEqual(rec.status, 0)
        self.assertIn("Fill colour grey: the buffer at the MDP4 address 0x89000000 is "
                      "on screen", rec.text)
        self.assertIn("MDP4 word 0x89000000: a plausible framebuffer", rec.text)

    def test_grey_with_an_unpaintable_mdp4_word_is_impossible(self):
        for mdp in (o.FB_RED, 0x8F00_0000, 0):
            rec = rr.build_record("grey", device_words(mdp))
            self.assertEqual(rec.status, 1, hex(mdp))
            self.assertFalse(rec.misread)
            self.assertIn("not a picture the payload paints", rec.text)
            self.assertIn("Cannot be right as typed:", rec.text)

    def test_grey_with_eight_rows_is_impossible(self):
        rec = rr.build_record("grey", device_words(0)[:8])
        self.assertEqual(rec.status, 1)
        self.assertIn("grey is painted only after row 9's value is known", rec.text)

    def test_screen_and_register_disagreeing_is_reported_not_refused(self):
        rec = rr.build_record("red", device_words(o.FB_GREEN))
        self.assertEqual(rec.status, 0)
        self.assertIn("The MDP4 word names 0x88300000, not the buffer on screen", rec.text)
        self.assertEqual(len(rec.attention), 1)


class EchoTests(unittest.TestCase):
    def test_cells(self):
        self.assertEqual(rr.cells(0x4000_01D3), ".#.. .... .... .... .... ...# ##.# ..##")
        self.assertEqual(rr.cells(0x8000_0001), "#... .... .... .... .... .... .... ...#")
        self.assertEqual(rr.cells(0xFFFF_FFFF), " ".join(["####"] * 8))

    def test_every_row_is_echoed_as_32_cells_in_nibble_groups(self):
        words = device_words(o.FB_RED)
        lines = rr.build_record("blue", words).text.splitlines()
        for i, word in enumerate(words):
            (row,) = [ln for ln in lines if ln.startswith(f"  row {i + 1} ")]
            self.assertIn(f"0x{word:08X}", row)
            groups = row.split()[-8:]
            self.assertTrue(all(len(g) == 4 and set(g) <= set("#.") for g in groups), row)
            bits = "".join(groups).replace("#", "1").replace(".", "0")
            self.assertEqual(int(bits, 2), word)


class RecordTests(unittest.TestCase):
    def test_qemu_words(self):
        # The plain QEMU run: r0 = r1 = r2 = 0, the sentinel, MDP4 reads 0.
        rec = rr.build_record("green", o.EXPECTED_WORDS)
        self.assertFalse(rec.misread)
        self.assertEqual(rec.impossible, [])
        self.assertEqual(rec.status, 0)
        text = rec.text
        self.assertTrue(text.startswith("Checksum row OK: row 8 is 0x22BECBA4"))
        self.assertRegex(text, r"r0 +0x00000000 +as expected")
        self.assertRegex(text, r"r1 +0x00000000 +NOT as expected: 0, not machine number 3727")
        self.assertRegex(text, r"r2 +0x00000000 +NOT as expected: outside the tags page")
        self.assertRegex(text, r"mode +SVC \(0x13\) +as expected")
        self.assertRegex(text, r"IRQ \(I\) +masked +as expected")
        self.assertRegex(text, r"FIQ \(F\) +masked ")
        self.assertRegex(text, r"abort \(A\) +masked ")
        self.assertRegex(text, r"MMU \(M, bit 0\) +off +as expected")
        self.assertRegex(text, r"high vectors \(V, bit 13\) +off +VBAR was in effect")
        self.assertIn("Entry address 0x80208000: as expected, the link address", text)
        self.assertIn("*r2 0xFFFFFFFF: the sentinel", text)
        self.assertIn("MDP4 word 0x00000000: rejected, no third buffer is painted: the "
                      "buffer [0x00000000, 0x0017bb00) is not wholly inside device RAM",
                      text)
        self.assertIn("Rows: 9 of 9. The display-register read returned.", text)
        self.assertEqual(rec.attention, [
            "r1 is 0x00000000, not 3727",
            "r2 is 0x00000000, outside the tags page [0x80200000, 0x80208000)",
            "the screen shows the buffer at 0x88300000, but the MDP4 word is 0x00000000",
        ])

    def test_section_2_expected_device_words(self):
        for fill, mdp in (("red", o.FB_RED), ("blue", o.FB_RED), ("green", o.FB_GREEN)):
            rec = rr.build_record(fill, device_words(mdp))
            self.assertEqual((rec.status, rec.misread, rec.impossible, rec.attention),
                             (0, False, [], []), fill)
            text = rec.text
            self.assertNotIn("NOT as expected", text)
            self.assertRegex(text, r"r0 +0x00000000 +as expected: 0")
            self.assertRegex(text, r"r1 +0x00000E8F +as expected: machine number 3727")
            self.assertRegex(text, r"r2 +0x80200100 +as expected: inside the tags page "
                                   r"\[0x80200000, 0x80208000\), word-aligned; it is the "
                                   r"header's tags address 0x80200100")
            self.assertRegex(text, r"FIQ \(F\) +not masked ")
            self.assertRegex(text, r"abort \(A\) +not masked ")
            self.assertRegex(text, r"Thumb \(T\) +0, ARM +as expected")
            self.assertRegex(text, r"endianness \(E\) +0, little +as expected")
            self.assertRegex(text, r"data cache \(C, bit 2\) +off +as expected")
            self.assertRegex(text, r"instr\. cache \(I, bit 12\) +off +as expected")
            self.assertRegex(text, r"alignment \(A, bit 1\) +off ")
            self.assertIn("*r2 0x00000005: an ATAG_CORE header", text)
            self.assertIn("a candidate address", text)
            self.assertIn("The MDP4 word names the same buffer.", text)
            self.assertTrue(text.rstrip().endswith(
                "Result: everything decoded matches the expected handoff."))

    def test_each_unexpected_field_is_reported(self):
        cases = (
            (0, 0x0000_0001, "r0 is 0x00000001, not 0"),
            (1, 0x0000_0E8E, "r1 is 0x00000E8E, not 3727"),
            (3, 0x0000_0097, "CPU mode is ABT (0x17), not SVC"),
            (3, 0x0000_0013, "IRQ was not masked at entry"),
            (3, 0x0000_00B3, "CPSR shows Thumb state"),
            (3, 0x0000_0293, "CPSR shows big-endian data"),
            (4, o.QEMU_SCTLR | 1 << 0, "the MMU was on at entry"),
            (4, o.QEMU_SCTLR | 1 << 2, "the data cache was on at entry"),
            (4, o.QEMU_SCTLR | 1 << 12, "the instruction cache was on at entry"),
            (4, o.QEMU_SCTLR | 1 << 13, "SCTLR.V was set: the halt-only vectors were inert"),
            (5, 0x80A0_8000, "the image ran at 0x80A08000, not 0x80208000"),
        )
        for row, value, want in cases:
            words = device_words(o.FB_RED)
            words[row] = value
            rec = rr.build_record("blue", words)
            self.assertEqual(rec.attention, [want], f"row {row + 1} = {value:#x}")
            self.assertEqual(rec.status, 0)

    def test_r2_inside_the_page_but_unaligned(self):
        words = device_words(o.FB_RED)
        words[2], words[6] = 0x8020_0102, o.R2_OUT_OF_RANGE
        rec = rr.build_record("blue", words)
        self.assertEqual(rec.attention,
                         ["r2 is 0x80200102, inside the tags page but not word-aligned"])

    def test_r2_elsewhere_in_the_page_is_still_expected(self):
        words = device_words(o.FB_RED)
        words[2] = 0x8020_0000
        rec = rr.build_record("blue", words)
        self.assertEqual(rec.attention, [])
        self.assertIn("it is not the header's tags address 0x80200100", rec.text)

    def test_high_vectors_consequence(self):
        words = device_words(o.FB_RED)
        words[4] |= 1 << 13
        text = rr.build_record("blue", words).text
        self.assertRegex(text, r"high vectors \(V, bit 13\) +ON +VBAR is ignored, so the "
                               r"halt-only vectors were inert")

    def test_relocated_entry_line(self):
        words = device_words(o.FB_RED)
        words[5] = 0x80A0_8000
        self.assertIn("Entry address 0x80A08000: NOT as expected, relocated: loaded "
                      "0x00800000 above the link address 0x80208000.",
                      rr.build_record("blue", words).text)

    def test_misread_checksum_row_is_said_first(self):
        words = device_words(o.FB_RED)
        words[7] ^= 1  # one cell of row 8 read wrongly
        rec = rr.build_record("blue", words)
        self.assertTrue(rec.misread)
        self.assertEqual(rec.status, 1)
        first = rec.text.splitlines()[0]
        self.assertEqual(first, "ROWS MISREAD: row 8 (checksum) is 0x22BECBA5, and the "
                                "payload can only paint 0x22BECBA4 there.")
        self.assertNotIn("everything decoded matches", rec.text)
        self.assertIn("Result: ROWS MISREAD (row 8)", rec.text)

    def test_a_misread_in_another_row_is_not_caught_by_the_checksum(self):
        # The checksum row vouches for row 8 only, and the record says so.
        words = device_words(o.FB_RED)
        words[1] ^= 1
        rec = rr.build_record("blue", words)
        self.assertFalse(rec.misread)
        self.assertIn("This checks row 8 only.", rec.text.splitlines()[0])

    def test_eight_rows(self):
        rec = rr.build_record("blue", device_words(o.FB_RED)[:8])
        self.assertEqual((rec.status, rec.misread, rec.impossible), (0, False, []))
        self.assertIn("Input: fill colour blue; 8 rows.", rec.text)
        self.assertIn("  row 9  MDP4      not painted", rec.text)
        self.assertIn("MDP4 word: row 9 is missing.", rec.text)
        self.assertIn("Rows: 8 of 9. The display-register read hung or faulted", rec.text)
        self.assertEqual(rec.attention,
                         ["row 9 is missing: the display-register read hung or faulted"])
        self.assertNotIn("everything decoded matches", rec.text)

    def test_impossible_r2_row(self):
        words = list(o.EXPECTED_WORDS)
        words[6] = 5  # r2 = 0 is never read, so *r2 cannot be 5
        rec = rr.build_record("green", words)
        self.assertEqual(rec.status, 1)
        self.assertEqual(rec.impossible,
                         ["*r2 is 0x00000005 although r2 = 0x00000000 is never read"])


class PngTests(unittest.TestCase):
    ARBITRARY = [0x0000_0000, 0xFFFF_FFFF, 0x8000_0001, 0x1234_5678, 0xDEAD_BEEF,
                 0x0000_00FF, 0xA5A5_A5A5, 0x0F0F_0F0F, 0x7FFF_FFFE]

    def _roundtrip(self, fill, words):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "screen.png")
            rr.write_png(path, fill, words)
            with open(path, "rb") as fh:
                width, height, rgb = read_png(fh.read())
        self.assertEqual((width, height), (o.WIDTH, o.HEIGHT))
        self.assertEqual(len(rgb), o.FB_BYTES)
        return rgb

    def test_png_decodes_back_to_the_same_words(self):
        for fill in rr.FILLS:
            for words in (o.EXPECTED_WORDS, device_words(o.FB_RED), self.ARBITRARY):
                rgb = self._roundtrip(fill, words)
                self.assertEqual(o.decode_words(rgb), words, fill)

    def test_png_fill_is_the_colour_as_seen(self):
        for fill, px in (("red", (255, 0, 0)), ("blue", (0, 0, 255)),
                         ("green", (0, 255, 0)), ("grey", (128, 128, 128))):
            rgb = self._roundtrip(fill, o.EXPECTED_WORDS)
            self.assertEqual(o.fill_pixel_at(rgb, 300, 500), px)   # below the rows
            self.assertEqual(o.fill_pixel_at(rgb, 0, 0), px)       # the margin

    def test_red_and_green_pngs_are_the_framebuffer_bytes(self):
        # For red and green the colour as seen equals the bytes the payload
        # writes, so the PNG pixels are the oracle's framebuffer exactly.
        self.assertEqual(self._roundtrip("red", o.EXPECTED_WORDS),
                         o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS))
        self.assertEqual(self._roundtrip("green", o.EXPECTED_WORDS),
                         o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS))

    def test_eight_row_png_leaves_row_nine_unpainted(self):
        words = device_words(0)[:8]
        rgb = self._roundtrip("blue", words)
        self.assertEqual(o.decode_words(rgb, rows=8), words)
        with self.assertRaises(ValueError):
            o.decode_words(rgb)  # row 9 is fill colour, not cells
        x0, y0 = o.cell_origin(0, 8)
        self.assertEqual(o.fill_pixel_at(rgb, x0 + 1, y0 + 1), (0, 0, 255))

    def test_a_changed_word_changes_the_png(self):
        other = list(o.EXPECTED_WORDS)
        other[0] ^= 1
        self.assertNotEqual(self._roundtrip("red", o.EXPECTED_WORDS),
                            self._roundtrip("red", other))

    def test_png_reader_rejects_a_corrupt_file(self):
        good = rr.encode_png(rr.screen_rgb("red", o.EXPECTED_WORDS), o.WIDTH, o.HEIGHT)
        bad = bytearray(good)
        bad[60] ^= 0xFF  # inside the IDAT data
        with self.assertRaises(AssertionError):
            read_png(bytes(bad))

    def test_default_path_is_under_build(self):
        path = rr.default_png_path("blue", 9)
        self.assertEqual(os.path.relpath(path, rr.REPO),
                         os.path.join("build", "boot-serrano",
                                      "expected-screen-blue-9rows.png"))
        self.assertIsNone(rr.png_path_problem(path))

    def test_a_path_in_the_tracked_tree_is_refused(self):
        for inside in ("screen.png", os.path.join("docs", "screen.png"),
                       os.path.join("build-other", "screen.png")):
            self.assertIn("never committed",
                          rr.png_path_problem(os.path.join(rr.REPO, inside)))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(rr.png_path_problem(os.path.join(tmp, "screen.png")))


class CommandLineTests(unittest.TestCase):
    def test_nine_rows_prints_the_record_and_writes_the_png(self):
        words = device_words(o.FB_RED)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out", "screen.png")
            status, said = run_main("--fill", "blue", "--png", path, *hexwords(words))
            with open(path, "rb") as fh:
                _, _, rgb = read_png(fh.read())
        self.assertEqual(status, 0)
        self.assertTrue(said.startswith(rr.build_record("blue", words).text))
        self.assertIn(path, said.splitlines()[-1])
        self.assertEqual(o.decode_words(rgb), words)

    def test_words_may_carry_0x_and_lower_case(self):
        words = device_words(o.FB_RED)
        typed = [f"0x{w:08x}" for w in words]
        status, said = run_main("--fill", "blue", "--no-png", *typed)
        self.assertEqual((status, said), (0, rr.build_record("blue", words).text))

    def test_no_png_writes_nothing(self):
        status, said = run_main("--fill", "green", "--no-png", *hexwords(o.EXPECTED_WORDS))
        self.assertEqual(status, 0)
        self.assertNotIn(".png", said)

    def test_misread_checksum_exits_1(self):
        words = list(o.EXPECTED_WORDS)
        words[7] = 0x22BE_CBA5
        status, said = run_main("--fill", "green", "--no-png", *hexwords(words))
        self.assertEqual(status, 1)
        self.assertTrue(said.startswith("ROWS MISREAD"))

    def test_eight_rows_exit_0(self):
        status, said = run_main("--fill", "green", "--no-png",
                                *hexwords(o.EXPECTED_WORDS[:8]))
        self.assertEqual(status, 0)
        self.assertIn("The display-register read hung or faulted", said)

    def _usage_error(self, *argv) -> str:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            run_main(*argv)
        self.assertEqual(caught.exception.code, 2)
        return err.getvalue()

    def test_wrong_number_of_rows(self):
        nine = hexwords(o.EXPECTED_WORDS)
        self.assertIn("need 8 or 9 rows, got 7",
                      self._usage_error("--fill", "red", "--no-png", *nine[:7]))
        self.assertIn("need 8 or 9 rows, got 10",
                      self._usage_error("--fill", "red", "--no-png", *nine, "00000000"))

    def test_a_row_must_be_eight_hex_digits(self):
        nine = hexwords(o.EXPECTED_WORDS)
        for bad in ("E8F", "0x0E8F", "00000E8G", "000000E8F", "", "0x"):
            said = self._usage_error("--fill", "red", "--no-png", bad, *nine[1:])
            self.assertIn("not eight hex digits", said, bad)

    def test_unknown_colour(self):
        self._usage_error("--fill", "yellow", "--no-png", *hexwords(o.EXPECTED_WORDS))

    def test_png_path_in_the_tracked_tree_is_refused_before_anything_is_written(self):
        target = os.path.join(rr.REPO, "docs", "refused-by-test.png")
        said = self._usage_error("--fill", "red", "--png", target,
                                 *hexwords(o.EXPECTED_WORDS))
        self.assertIn("never committed", said)
        self.assertFalse(os.path.exists(target))


if __name__ == "__main__":
    unittest.main()
