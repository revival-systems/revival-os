"""Unit tests for the Phase 2 host oracle (tests/boot/serrano_v1.py).

Pure host tests, discovered by `make test-unit` (unit-python). They check the
encoding round-trips, the word-row geometry (separate cells with gaps, inside
the panel), the checksum matches the Phase 1 constant, the handoff invariants
accept the expected words and reject tampering, the image-header check accepts
the vector/zImage layout and rejects each deviation, and the two framebuffer
regions do not overlap the image, its stack, ATAGS or each other.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import struct
import unittest

from tests.boot import serrano_v1 as o


class EncodingTests(unittest.TestCase):
    def test_fb_size(self):
        self.assertEqual(o.FB_BYTES, 1_555_200)
        self.assertEqual(o.STRIDE, o.WIDTH * o.BPP)

    def test_checksum_matches_phase1_constant(self):
        # The Phase 1 fixture records this value; payload.rs reuses the table.
        self.assertEqual(o.checksum(), 0x22BECBA4)

    def test_roundtrip_expected_words(self):
        for fill in (o.FILL_RED, o.FILL_GREEN):
            buf = o.generate_fb(fill, o.EXPECTED_WORDS)
            self.assertEqual(len(buf), o.FB_BYTES)
            self.assertEqual(o.decode_words(buf), o.EXPECTED_WORDS)

    def test_roundtrip_arbitrary_words(self):
        words = [0x0000_0000, 0xFFFF_FFFF, 0x8000_0001, 0x1234_5678,
                 0xDEAD_BEEF, 0x0000_00FF, 0xA5A5_A5A5, 0x0F0F_0F0F, 0x7FFF_FFFE]
        self.assertEqual(len(words), o.WORDS)
        buf = o.generate_fb(o.FILL_RED, words)
        self.assertEqual(o.decode_words(buf), words)

    def test_fill_colour_distinguishes_byte_order(self):
        # RED fills FF 00 00 (red or blue on screen); GREEN fills 00 FF 00.
        red = o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS)
        green = o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS)
        # A pixel well below the word rows (the last row ends at y=296).
        self.assertEqual(o.fill_pixel_at(red, 300, 500), o.FILL_RED)
        self.assertEqual(o.fill_pixel_at(green, 300, 500), o.FILL_GREEN)

    def test_word_rows_are_black_and_white_only(self):
        buf = o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS)
        # Top-left block of row 0 decodes without raising (pure b/w).
        self.assertEqual(len(o.decode_words(buf)), o.WORDS)


class GeometryTests(unittest.TestCase):
    """The word rows are separate cells with gaps, inside the 540x960 panel."""

    ONES = [0xFFFF_FFFF] * o.WORDS

    def test_rows_fit_the_panel_with_a_margin(self):
        x_last, y_last = o.cell_origin(31, o.WORDS - 1)
        self.assertEqual((x_last + o.CELL_W, y_last + o.CELL_H), (535, 296))
        self.assertLessEqual(x_last + o.CELL_W, o.WIDTH)
        self.assertLessEqual(y_last + o.CELL_H, o.HEIGHT)
        self.assertGreater(o.MARGIN_X, 0)
        self.assertGreater(o.MARGIN_Y, 0)
        self.assertGreater(o.WIDTH - (x_last + o.CELL_W), 0)  # right margin

    def test_cells_never_touch(self):
        for row in range(o.WORDS):
            for bit in range(31):
                x_a, _ = o.cell_origin(bit, row)
                x_b, _ = o.cell_origin(bit + 1, row)
                gap = x_b - (x_a + o.CELL_W)
                # A wider gap separates nibbles than separates bits.
                want = 7 if bit % 4 == 3 else 4
                self.assertEqual(gap, want, f"gap after bit {bit}")
        _, y_a = o.cell_origin(0, 0)
        _, y_b = o.cell_origin(0, 1)
        self.assertEqual(y_b - (y_a + o.CELL_H), 8)  # rows do not touch either

    def test_gaps_and_margins_keep_the_fill_colour(self):
        buf = o.generate_fb(o.FILL_RED, self.ONES)
        x0, y0 = o.cell_origin(0, 0)
        y_mid = y0 + o.CELL_H // 2
        self.assertEqual(o.fill_pixel_at(buf, x0, y_mid), o.WHITE)             # in a cell
        self.assertEqual(o.fill_pixel_at(buf, x0 + o.CELL_W, y_mid), o.FILL_RED)  # bit gap
        x4, _ = o.cell_origin(4, 0)
        self.assertEqual(o.fill_pixel_at(buf, x4 - 1, y_mid), o.FILL_RED)      # nibble gap
        self.assertEqual(o.fill_pixel_at(buf, 0, y_mid), o.FILL_RED)           # left margin
        self.assertEqual(o.fill_pixel_at(buf, o.WIDTH - 1, y_mid), o.FILL_RED)  # right margin
        self.assertEqual(o.fill_pixel_at(buf, x0, 0), o.FILL_RED)              # top margin
        self.assertEqual(o.fill_pixel_at(buf, x0, y0 + o.CELL_H), o.FILL_RED)  # between rows

    def test_a_run_of_equal_bits_stays_32_separate_cells(self):
        # The v1.1 blocks touched, so 0xFFFFFFFF was one white bar. Count the
        # white runs along a scan line through row 0: one per bit.
        buf = o.generate_fb(o.FILL_GREEN, self.ONES)
        _, y0 = o.cell_origin(0, 0)
        line = [o.fill_pixel_at(buf, x, y0 + 1) for x in range(o.WIDTH)]
        runs = sum(1 for x in range(o.WIDTH)
                   if line[x] == o.WHITE and (x == 0 or line[x - 1] != o.WHITE))
        self.assertEqual(runs, 32)

    def test_decode_rejects_a_buffer_with_no_rows(self):
        # A plain fill has no black/white cells; the decoder must not guess.
        plain = bytes(o.FILL_GREY) * (o.WIDTH * o.HEIGHT)
        with self.assertRaises(ValueError):
            o.decode_words(plain)

    def test_decode_rejects_a_short_dump(self):
        buf = o.generate_fb(o.FILL_RED, self.ONES)
        with self.assertRaises(ValueError):
            o.decode_words(buf[:-1])

    def test_decode_rejects_the_old_touching_block_layout(self):
        # v1.1 drew 16x16 blocks from (0, 0). A dump in that layout must not
        # decode as v1.2: the new cell centres land on it at the wrong bits.
        words = [0x8000_0001] * o.WORDS
        old = bytearray(bytes(o.FILL_RED) * (o.WIDTH * o.HEIGHT))
        for row, w in enumerate(words):
            for bit in range(32):
                px = bytes(o.WHITE if (w >> (31 - bit)) & 1 else o.BLACK) * 16
                for y in range(row * 16, row * 16 + 16):
                    off = y * o.STRIDE + bit * 16 * o.BPP
                    old[off:off + len(px)] = px
        try:
            decoded = o.decode_words(bytes(old))
        except ValueError:
            return  # rejected outright: also fine
        self.assertNotEqual(decoded, words)


class ImageHeaderTests(unittest.TestCase):
    """check_image_header pins the reset branch, the seven halt-only vectors,
    the zImage words and the halt loop."""

    HALT = 0x34

    @staticmethod
    def _b(src: int, dst: int) -> bytes:
        return struct.pack("<I", 0xEA00_0000 | (((dst - src - 8) // 4) & 0x00FF_FFFF))

    def _image(self) -> bytearray:
        img = bytearray()
        img += self._b(0x00, 0x20)
        for off in o.VECTOR_OFFSETS:
            img += self._b(off, self.HALT)
        img += self._b(0x20, 0x30)
        img += struct.pack("<3I", o.ZIMAGE_MAGIC, 0, 0x3C)
        img += struct.pack("<I", 0xE1A0_0000)        # 0x30: real_start (a nop)
        img += struct.pack("<I", o.INSN_WFI)         # 0x34: halt_loop: wfi
        img += self._b(0x38, self.HALT)              # 0x38: b halt_loop
        self.assertEqual(len(img), 0x3C)
        return img

    def test_valid_header_passes(self):
        o.check_image_header(bytes(self._image()), self.HALT)  # must not raise

    def test_each_vector_must_branch_to_halt_loop(self):
        for off in o.VECTOR_OFFSETS:
            img = self._image()
            img[off:off + 4] = self._b(off, 0x30)  # into real_start instead
            with self.assertRaises(AssertionError, msg=f"vector {off:#x}"):
                o.check_image_header(bytes(img), self.HALT)

    def test_vector_that_is_not_a_branch_rejected(self):
        img = self._image()
        img[0x10:0x14] = struct.pack("<I", 0)  # v1.1 had zero padding here
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(img), self.HALT)

    def test_reset_and_header_branches_pinned(self):
        img = self._image()
        img[0x00:0x04] = self._b(0x00, 0x30)  # v1.1: straight to real_start
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(img), self.HALT)
        img = self._image()
        img[0x20:0x24] = self._b(0x20, self.HALT)
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(img), self.HALT)

    def test_zimage_words_pinned(self):
        for off, value in ((0x24, 0x016F_2819), (0x28, 4), (0x2C, 0x40)):
            img = self._image()
            img[off:off + 4] = struct.pack("<I", value)
            with self.assertRaises(AssertionError, msg=f"word {off:#x}"):
                o.check_image_header(bytes(img), self.HALT)

    def test_halt_loop_must_be_wfi_and_branch_to_self(self):
        img = self._image()
        img[0x34:0x38] = struct.pack("<I", 0xE1A0_0000)  # nop instead of wfi
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(img), self.HALT)
        img = self._image()
        img[0x38:0x3C] = self._b(0x38, 0x30)  # falls back into the payload
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(img), self.HALT)

    def test_halt_offset_outside_the_image_rejected(self):
        with self.assertRaises(AssertionError):
            o.check_image_header(bytes(self._image()), 0x3C)


class InvariantTests(unittest.TestCase):
    def test_expected_words_pass(self):
        o.assert_handoff_invariants(o.EXPECTED_WORDS)  # must not raise

    def test_entry_mismatch_rejected(self):
        words = list(o.EXPECTED_WORDS)
        words[5] = 0x40208000  # wrong load address
        with self.assertRaises(AssertionError):
            o.assert_handoff_invariants(words)

    def test_mmu_on_rejected(self):
        words = list(o.EXPECTED_WORDS)
        words[4] |= 1  # SCTLR M bit set
        with self.assertRaises(AssertionError):
            o.assert_handoff_invariants(words)

    def test_irq_unmasked_rejected(self):
        words = list(o.EXPECTED_WORDS)
        words[3] &= ~(1 << 7)  # clear CPSR I bit
        with self.assertRaises(AssertionError):
            o.assert_handoff_invariants(words)

    def test_plausible_mdp4_rejected_as_qemu_value(self):
        # The QEMU invariant requires the MDP4 word to be NON-plausible. A value
        # that names a real framebuffer must trip the invariant.
        words = list(o.EXPECTED_WORDS)
        words[8] = 0x8800_0000  # aligned, in RAM, not a candidate, not reserved
        self.assertTrue(o.is_plausible_fb(words[8]))
        with self.assertRaises(AssertionError):
            o.assert_handoff_invariants(words)

    def test_injected_mdp4_changes_only_the_ninth_word(self):
        words = o.expected_words(0x8900_0000)
        self.assertEqual(words[:8], o.EXPECTED_WORDS[:8])
        self.assertEqual(words[8], 0x8900_0000)
        self.assertEqual(o.expected_words(o.MDP4_QEMU), o.EXPECTED_WORDS)

    def test_cpu_invariants_ignore_the_mdp4_word_but_nothing_else(self):
        # The injected-value QEMU cases use the CPU-only invariants: a
        # plausible MDP4 word is fine there, a wrong handoff word is not.
        words = o.expected_words(0x8900_0000)
        o.assert_cpu_handoff_invariants(words)  # must not raise
        words[5] = 0x40208000  # wrong load address
        with self.assertRaises(AssertionError):
            o.assert_cpu_handoff_invariants(words)


class HandoffWordsTests(unittest.TestCase):
    """handoff_words and r2_is_read mirror what the payload paints for a given
    entry state; the device-like QEMU cases compare against them."""

    def test_defaults_are_the_plain_run(self):
        self.assertEqual(o.handoff_words(), o.EXPECTED_WORDS)

    def test_r2_guard_edges(self):
        self.assertTrue(o.r2_is_read(0x8020_0000))   # first word of the tags page
        self.assertTrue(o.r2_is_read(0x8020_0100))   # the expected tags address
        self.assertTrue(o.r2_is_read(0x8020_7FFC))   # last word of the tags page
        self.assertFalse(o.r2_is_read(0x8020_8000))  # the image itself
        self.assertFalse(o.r2_is_read(0x801F_FFFC))  # just below the page
        self.assertFalse(o.r2_is_read(0x8020_0102))  # not word-aligned
        self.assertFalse(o.r2_is_read(0))            # the plain QEMU entry

    def test_device_like_handoff(self):
        words = o.handoff_words(r0=0, r1=o.MACH_SERRANO, r2=o.TAGS_ADDR, word_at_r2=5)
        self.assertEqual(words[:3], [0, 0x0000_0E8F, 0x8020_0100])
        self.assertEqual(words[6], 5)
        self.assertEqual(words[3:6] + words[7:], o.EXPECTED_WORDS[3:6] + o.EXPECTED_WORDS[7:])

    def test_word_at_r2_is_ignored_when_the_guard_refuses(self):
        words = o.handoff_words(r2=0x8020_8000, word_at_r2=0x1234_5678)
        self.assertEqual(words[6], o.R2_OUT_OF_RANGE)

    def test_a_read_needs_the_stored_word(self):
        with self.assertRaises(AssertionError):
            o.handoff_words(r2=o.TAGS_ADDR)  # read, but nothing said to be there

    def test_relocated_entry_only_changes_the_entry_word(self):
        words = o.handoff_words(entry=0x80A0_8000)
        self.assertEqual(words[5], 0x80A0_8000)
        self.assertEqual(words[:5] + words[6:], o.EXPECTED_WORDS[:5] + o.EXPECTED_WORDS[6:])
        # A relocated entry is exactly what the plain-run invariant rejects.
        with self.assertRaises(AssertionError):
            o.assert_cpu_handoff_invariants(words)


class PlausibilityTests(unittest.TestCase):
    """is_plausible_fb mirrors the payload's third-buffer gate."""

    def test_qemu_flash_value_rejected(self):
        self.assertFalse(o.is_plausible_fb(o.MDP4_QEMU))  # 0: not in RAM

    def test_accepts_a_clean_ram_address(self):
        # Aligned, whole buffer in RAM, not a candidate, clear of every reserved
        # region: a plausible discovered framebuffer.
        self.assertTrue(o.is_plausible_fb(0x8800_0000))
        self.assertTrue(o.is_plausible_fb(0xA000_0000))

    def test_accepts_the_bootloader_framebuffer_reservation(self):
        # [0x88300000, 0x88600000) is where a framebuffer is expected. v1.1 and
        # v1.2 rejected the whole region; a buffer starting past the end of the
        # GREEN fill (0x8847BB00) would then never have been painted.
        self.assertTrue(o.is_plausible_fb(0x8847_C000))  # past the GREEN fill
        self.assertTrue(o.is_plausible_fb(0x8840_0000))  # overlapping the GREEN fill
        self.assertNotIn((0x8830_0000, 0x8860_0000), o.RESERVED)

    def test_candidate_addresses_stay_excluded(self):
        # The exact candidates are already painted; they are still refused.
        self.assertFalse(o.is_plausible_fb(0x8830_0000))
        self.assertFalse(o.is_plausible_fb(0x8810_0000))

    def test_every_other_reserved_region_is_still_rejected(self):
        for lo, hi in ((0x8020_0000, 0x8020_8000), (0x8020_8000, 0x8120_8000),
                       (0x8000_0000, 0x8020_0000), (0x8F00_0000, 0x8F70_0000),
                       (0x8FB0_0000, 0x8FE0_0000)):
            self.assertIn((lo, hi), o.RESERVED)
            self.assertFalse(o.is_plausible_fb(lo), f"{lo:#x}")
            self.assertFalse(o.is_plausible_fb(hi - 4), f"{hi - 4:#x}")

    def test_rejects_unaligned(self):
        self.assertFalse(o.is_plausible_fb(0x8800_0002))

    def test_rejects_both_candidates(self):
        self.assertFalse(o.is_plausible_fb(o.FB_RED))
        self.assertFalse(o.is_plausible_fb(o.FB_GREEN))

    def test_rejects_outside_ram(self):
        self.assertFalse(o.is_plausible_fb(0x0000_0000))        # below RAM
        self.assertFalse(o.is_plausible_fb(0xDFFF_0000))        # buffer runs past RAM end

    def test_rejects_overlap_with_image_and_reserved(self):
        self.assertFalse(o.is_plausible_fb(0x8020_8000))  # the image/stack span
        self.assertFalse(o.is_plausible_fb(0x8000_0000))  # SMEM
        self.assertFalse(o.is_plausible_fb(0x8F00_0000))  # WCNSS
        # An address just below WCNSS whose buffer would run into it.
        self.assertFalse(o.is_plausible_fb(0x8EF0_0000))

    def test_rejection_gives_the_first_reason_the_payload_hits(self):
        # fb_rejection is the rule itself; is_plausible_fb is its yes/no form.
        self.assertIsNone(o.fb_rejection(0x8800_0000))
        self.assertIsNone(o.fb_rejection(0x8847_C000))
        self.assertEqual(o.fb_rejection(0x8900_0002), "not word-aligned")
        self.assertEqual(o.fb_rejection(0x8810_0002), "not word-aligned")  # before "candidate"
        self.assertIn("not wholly inside device RAM", o.fb_rejection(0))
        self.assertIn("not wholly inside device RAM", o.fb_rejection(0xDFFF_0000))
        self.assertEqual(o.fb_rejection(o.FB_RED), "a candidate address, already painted")
        self.assertEqual(o.fb_rejection(o.FB_GREEN), "a candidate address, already painted")
        for fb, name in ((0x8020_0000, "the tags page"),
                         (0x8020_8000, "the image and its stack"),
                         (0x8000_0000, "SMEM"), (0x8F00_0000, "WCNSS"),
                         (0x8EF0_0000, "WCNSS"), (0x8FB0_0000, "modem rmtfs")):
            self.assertIn(f"overlap {name} [", o.fb_rejection(fb), f"{fb:#x}")

    def test_every_reserved_region_has_a_name(self):
        self.assertEqual(len(o.RESERVED_NAMES), len(o.RESERVED))
        self.assertEqual(len(set(o.RESERVED_NAMES)), len(o.RESERVED))


class PartialRowsTests(unittest.TestCase):
    """generate_fb_rows and decode_words(rows=...) describe a picture with
    fewer than nine rows; the nine-row functions are unchanged."""

    def test_nine_rows_is_generate_fb(self):
        self.assertEqual(o.generate_fb_rows(o.FILL_RED, o.EXPECTED_WORDS),
                         o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS))

    def test_generate_fb_still_needs_nine_words(self):
        with self.assertRaises(AssertionError):
            o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS[:8])
        with self.assertRaises(AssertionError):
            o.generate_fb_rows(o.FILL_RED, o.EXPECTED_WORDS + [0])

    def test_eight_rows_leave_the_ninth_as_fill(self):
        eight = o.EXPECTED_WORDS[:8]
        buf = o.generate_fb_rows(o.FILL_GREEN, eight)
        self.assertEqual(o.decode_words(buf, rows=8), eight)
        with self.assertRaises(ValueError):
            o.decode_words(buf)  # row 9 is not cells
        nine = o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS)
        _, y9 = o.cell_origin(0, 8)
        self.assertEqual(buf[:y9 * o.STRIDE], nine[:y9 * o.STRIDE])  # rows 1-8 identical
        self.assertEqual(buf[y9 * o.STRIDE:],
                         bytes(o.FILL_GREEN) * (o.WIDTH * (o.HEIGHT - y9)))

    def test_decode_default_is_still_nine_rows(self):
        buf = o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS)
        self.assertEqual(o.decode_words(buf), o.decode_words(buf, rows=9))
        self.assertEqual(o.decode_words(buf, rows=3), o.EXPECTED_WORDS[:3])


class LayoutTests(unittest.TestCase):
    # Addresses the payload writes (docs/phase-2/boot-payload-research.md).
    IMAGE_BASE = 0x80208000
    IMAGE_SPAN = 0x0100_0000      # link.ld reserves 16 MiB for the image
    ATAGS = 0x80200100
    SMEM_START, SMEM_END = 0x80000000, 0x80200000  # 2 MiB reserved (gt-i9195)

    def _region(self, base):
        return (base, base + o.FB_BYTES)

    def test_framebuffers_do_not_overlap_each_other(self):
        r0, r1 = self._region(o.FB_RED)
        g0, g1 = self._region(o.FB_GREEN)
        self.assertLessEqual(r1, g0, "RED framebuffer runs into GREEN")

    def test_framebuffers_clear_the_image_and_stack(self):
        img_end = self.IMAGE_BASE + self.IMAGE_SPAN
        for base in (o.FB_RED, o.FB_GREEN):
            self.assertGreaterEqual(base, img_end,
                                    f"{base:#x} overlaps the image span")

    def test_framebuffers_clear_atags_and_smem(self):
        for base in (o.FB_RED, o.FB_GREEN):
            lo, hi = self._region(base)
            self.assertFalse(lo <= self.ATAGS < hi, "framebuffer covers ATAGS")
            self.assertTrue(lo >= self.SMEM_END, "framebuffer overlaps SMEM")


if __name__ == "__main__":
    unittest.main()
