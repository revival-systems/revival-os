"""Unit tests for the boot-image packer and its independent reader.

Cross-checks tools/pack_bootimg.py against tests/boot/read_bootimg.py: a freshly
packed image validates cleanly, and each deliberate corruption (magic, trailer,
ramdisk, a zImage word, a load address, trailing junk) is reported. Also covers
the packer's negative-test option (`--invalid-magic`) and its checker
(tests/boot/check_negative_img.py). Pure host tests, discovered by
`make test-unit`.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import contextlib
import io
import os
import struct
import tempfile
import unittest

from tests.boot import check_negative_img, read_bootimg
from tools import pack_bootimg

# A minimal, valid flat payload: a branch, then the zImage words at 0x24/0x28/0x2c,
# padded so the "end" word equals the kernel length. Mirrors the real image's
# header without needing the toolchain.
def _fake_kernel(size=0x40):
    assert size >= 0x30 and size % 4 == 0
    k = bytearray(size)
    struct.pack_into("<I", k, 0x00, 0xEA00000A)          # b (some forward branch)
    struct.pack_into("<III", k, 0x24, 0x016F2818, 0, size)  # magic, start, end
    return bytes(k)


class PackReadRoundTrip(unittest.TestCase):
    def setUp(self):
        self.kernel = _fake_kernel()
        self.img = pack_bootimg.build_bootimg(self.kernel)

    def test_valid_image_passes(self):
        self.assertEqual(read_bootimg.validate(self.img), [])

    def test_structure(self):
        self.assertTrue(self.img.startswith(b"ANDROID!"))
        self.assertTrue(self.img.endswith(b"SEANDROIDENFORCE"))
        # header + kernel page + ramdisk page, then the 16-byte trailer.
        self.assertEqual(len(self.img), 3 * 2048 + 16)

    def test_corrupt_magic_rejected(self):
        bad = b"DROID!!!" + self.img[8:]
        self.assertTrue(any("magic" in p for p in read_bootimg.validate(bad)))

    def test_missing_trailer_rejected(self):
        bad = self.img[:-16]
        self.assertTrue(read_bootimg.validate(bad))

    def test_wrong_trailer_rejected(self):
        bad = self.img[:-16] + b"NOTSEANDROID!!!!"
        self.assertTrue(any("trailer" in p for p in read_bootimg.validate(bad)))

    def test_bad_ramdisk_rejected(self):
        buf = bytearray(self.img)
        buf[2 * 2048] = 0x01  # first ramdisk byte (page 2), should be 0x00
        self.assertTrue(any("ramdisk" in p for p in read_bootimg.validate(bytes(buf))))

    def test_bad_zimage_magic_rejected(self):
        buf = bytearray(self.img)
        struct.pack_into("<I", buf, 2048 + 0x24, 0xDEADBEEF)  # kernel at page 1
        self.assertTrue(any("zImage" in p for p in read_bootimg.validate(bytes(buf))))

    def test_bad_kernel_addr_rejected(self):
        buf = bytearray(self.img)
        struct.pack_into("<I", buf, 12, 0x40208000)  # kernel_addr field
        self.assertTrue(any("kernel_addr" in p for p in read_bootimg.validate(bytes(buf))))

    def test_trailing_junk_rejected(self):
        bad = self.img + b"\x00"
        self.assertTrue(read_bootimg.validate(bad))

    def test_image_id_recomputed(self):
        # Corrupt one kernel byte (not a checked field) and confirm the id check
        # catches it (id covers the kernel bytes).
        buf = bytearray(self.img)
        buf[2048 + 0x10] ^= 0xFF
        self.assertTrue(any("image id" in p for p in read_bootimg.validate(bytes(buf))))


class NegativeTestImage(unittest.TestCase):
    """The packer's --invalid-magic option: `INVALID!` for `ANDROID!`, nothing
    else, and off by default."""

    def setUp(self):
        self.kernel = _fake_kernel()
        self.valid = pack_bootimg.build_bootimg(self.kernel)
        self.invalid = pack_bootimg.build_bootimg(self.kernel, invalid_magic=True)

    def test_option_is_off_by_default(self):
        self.assertEqual(pack_bootimg.build_bootimg(self.kernel, invalid_magic=False),
                         self.valid)
        self.assertTrue(self.valid.startswith(b"ANDROID!"))

    def test_only_the_magic_differs(self):
        self.assertEqual(self.invalid[:8], b"INVALID!")
        self.assertEqual(len(self.invalid), len(self.valid))
        self.assertEqual(self.invalid[8:], self.valid[8:])
        self.assertNotEqual(self.invalid, self.valid)

    def test_kernel_slot_is_still_the_real_kernel(self):
        self.assertEqual(self.invalid[2048:2048 + len(self.kernel)], self.kernel)

    def test_reader_rejects_it_for_the_magic_alone(self):
        self.assertEqual(read_bootimg.validate(self.invalid),
                         ["magic b'INVALID!' != b'ANDROID!'"])

    def test_checker_accepts_the_pair(self):
        self.assertEqual(check_negative_img.problems(self.valid, self.invalid), [])

    def test_checker_rejects_a_second_difference(self):
        buf = bytearray(self.invalid)
        buf[2048 + 0x10] ^= 0xFF  # one kernel byte as well as the magic
        found = check_negative_img.problems(self.valid, bytes(buf))
        self.assertTrue(any("differ outside bytes 0-7" in p and "0x810" in p
                            for p in found), found)

    def test_checker_rejects_an_unchanged_magic(self):
        found = check_negative_img.problems(self.valid, self.valid)
        self.assertTrue(any("invalid image starts with b'ANDROID!'" in p for p in found))
        self.assertTrue(any("accepts the invalid image" in p for p in found))

    def test_checker_rejects_a_different_bad_magic(self):
        other = b"DROID!!!" + self.valid[8:]
        found = check_negative_img.problems(self.valid, other)
        self.assertTrue(any("invalid image starts with b'DROID!!!'" in p for p in found))

    def test_checker_rejects_a_length_change(self):
        found = check_negative_img.problems(self.valid, self.invalid + b"\x00")
        self.assertTrue(any("lengths differ" in p for p in found))

    def test_checker_rejects_swapped_arguments(self):
        self.assertTrue(check_negative_img.problems(self.invalid, self.valid))


class PackerCommandLine(unittest.TestCase):
    """The command line the Makefile uses, with and without --invalid-magic."""

    def _pack(self, tmp, name, *flags):
        kernel = os.path.join(tmp, "kernel.bin")
        with open(kernel, "wb") as fh:
            fh.write(_fake_kernel())
        out = os.path.join(tmp, name)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = pack_bootimg.main(["--kernel", kernel, "--output", out, *flags])
        self.assertEqual(status, 0)
        with open(out, "rb") as fh:
            return fh.read(), stdout.getvalue()

    def test_default_writes_the_valid_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            img, said = self._pack(tmp, "a.img")
        self.assertEqual(img, pack_bootimg.build_bootimg(_fake_kernel()))
        self.assertNotIn("NEGATIVE", said)

    def test_flag_writes_the_invalid_image_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            img, said = self._pack(tmp, "b.img", "--invalid-magic")
        self.assertEqual(img, pack_bootimg.build_bootimg(_fake_kernel(), invalid_magic=True))
        self.assertIn("NEGATIVE-TEST IMAGE", said)
        self.assertIn("'INVALID!'", said)


if __name__ == "__main__":
    unittest.main()
