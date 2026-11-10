"""Unit tests for the Phase 2 host oracle (tests/boot/serrano_v1.py).

Pure host tests, discovered by `make test-unit` (unit-python). They check the
encoding round-trips, the checksum matches the Phase 1 constant, the handoff
invariants accept the expected words and reject tampering, and the two
framebuffer regions do not overlap the image, its stack, ATAGS or each other.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

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
                 0xDEAD_BEEF, 0x0000_00FF, 0xA5A5_A5A5, 0x0F0F_0F0F]
        buf = o.generate_fb(o.FILL_RED, words)
        self.assertEqual(o.decode_words(buf), words)

    def test_fill_colour_distinguishes_byte_order(self):
        # RED fills FF 00 00 (red or blue on screen); GREEN fills 00 FF 00.
        red = o.generate_fb(o.FILL_RED, o.EXPECTED_WORDS)
        green = o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS)
        # A pixel well outside the 512x128 word-row band (word rows end at y=128).
        self.assertEqual(o.fill_pixel_at(red, 300, 500), o.FILL_RED)
        self.assertEqual(o.fill_pixel_at(green, 300, 500), o.FILL_GREEN)

    def test_word_rows_are_black_and_white_only(self):
        buf = o.generate_fb(o.FILL_GREEN, o.EXPECTED_WORDS)
        # Top-left block of row 0 decodes without raising (pure b/w).
        self.assertEqual(len(o.decode_words(buf)), o.WORDS)


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

    def test_completion_marker_sits_in_the_gap(self):
        red_end = o.FB_RED + o.FB_BYTES
        self.assertGreaterEqual(o.DONE_ADDR, red_end)
        self.assertLess(o.DONE_ADDR + 4, o.FB_GREEN)


if __name__ == "__main__":
    unittest.main()
