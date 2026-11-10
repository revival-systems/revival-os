"""Unit tests for the boot-image packer and its independent reader.

Cross-checks tools/pack_bootimg.py against tests/boot/read_bootimg.py: a freshly
packed image validates cleanly, and each deliberate corruption (magic, trailer,
ramdisk, a zImage word, a load address, trailing junk) is reported. Pure host
tests, discovered by `make test-unit`.

Run: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import struct
import unittest

from tests.boot import read_bootimg
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


if __name__ == "__main__":
    unittest.main()
