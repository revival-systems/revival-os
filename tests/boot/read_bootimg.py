"""read_bootimg.py - independent validator for the Phase 2 boot image.

Parses a version-0 Android boot image WITHOUT importing the packer and checks
every field against the expected GT-I9195 values: magic, load addresses, page
size, header version, sizes, the image id (recomputed SHA-1), page alignment of
each section, the zImage words at offset 0x24/0x28/0x2c of the kernel, the
1-byte zero ramdisk, and the `SEANDROIDENFORCE` trailer (task test (c)).

`validate()` returns a list of problem strings (empty == OK). The CLI prints
each problem and exits 1 if any, else prints a one-line summary and exits 0.
Nothing here contacts a device.
"""

from __future__ import annotations

import hashlib
import struct
import sys

MAGIC = b"ANDROID!"
SEANDROID = b"SEANDROIDENFORCE"
ZIMAGE_MAGIC = 0x016F2818

# Expected GT-I9195 values (duplicated from the packer on purpose: this reader
# is an independent check, so it must not import pack_bootimg).
EXP_KERNEL_ADDR = 0x80208000
EXP_RAMDISK_ADDR = 0x81200000
EXP_SECOND_ADDR = 0x81100000
EXP_TAGS_ADDR = 0x80200100
EXP_PAGE = 2048
EXP_HEADER_VERSION = 0
EXP_RAMDISK = b"\x00"

_HDR = struct.Struct("<8s10I16s512s32s1024s")  # through extra_cmdline


def _pages(size: int, page: int) -> int:
    return (size + page - 1) // page


def _recompute_id(kernel: bytes, ramdisk: bytes, second: bytes) -> bytes:
    sha = hashlib.sha1()
    for data in (kernel, ramdisk, second):
        if data:
            sha.update(data)
            sha.update(struct.pack("<I", len(data)))
        else:
            sha.update(struct.pack("<I", 0))
    return sha.digest().ljust(32, b"\x00")


def validate(img: bytes) -> list[str]:
    problems = []

    def bad(msg):
        problems.append(msg)

    if len(img) < _HDR.size:
        return [f"image too small: {len(img)} bytes"]

    (magic, ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, hver,
     osver, name, cmdline, img_id, extra) = _HDR.unpack_from(img, 0)

    if magic != MAGIC:
        bad(f"magic {magic!r} != {MAGIC!r}")
    if page != EXP_PAGE:
        bad(f"page_size {page} != {EXP_PAGE}")
    if kaddr != EXP_KERNEL_ADDR:
        bad(f"kernel_addr {kaddr:#x} != {EXP_KERNEL_ADDR:#x}")
    if raddr != EXP_RAMDISK_ADDR:
        bad(f"ramdisk_addr {raddr:#x} != {EXP_RAMDISK_ADDR:#x}")
    if saddr != EXP_SECOND_ADDR:
        bad(f"second_addr {saddr:#x} != {EXP_SECOND_ADDR:#x}")
    if tags != EXP_TAGS_ADDR:
        bad(f"tags_addr {tags:#x} != {EXP_TAGS_ADDR:#x}")
    if hver != EXP_HEADER_VERSION:
        bad(f"header_version {hver} != {EXP_HEADER_VERSION}")
    if osver != 0:
        bad(f"os_version field {osver} != 0")
    if ssize != 0:
        bad(f"second_size {ssize} != 0")
    if name.strip(b"\x00"):
        bad(f"product name not empty: {name!r}")
    if cmdline.strip(b"\x00"):
        bad(f"cmdline not empty: {cmdline!r}")
    if extra.strip(b"\x00"):
        bad(f"extra cmdline not empty")
    if page <= 0:
        return problems  # cannot locate sections without a sane page size

    # Section offsets, each a whole number of pages (task: page alignment).
    hdr_pages = _pages(_HDR.size, page)
    koff = hdr_pages * page
    roff = koff + _pages(ksize, page) * page
    soff = roff + _pages(rsize, page) * page
    trailer_off = soff + _pages(ssize, page) * page

    if koff % page or roff % page or soff % page:
        bad("a section does not start on a page boundary")

    if len(img) < roff:
        bad(f"image truncated: {len(img)} < kernel end {roff}")
        return problems

    kernel = img[koff:koff + ksize]
    ramdisk = img[roff:roff + rsize]
    second = img[soff:soff + ssize]

    if len(kernel) != ksize:
        bad(f"kernel section short: {len(kernel)} != {ksize}")
    if ramdisk != EXP_RAMDISK:
        bad(f"ramdisk {ramdisk!r} != {EXP_RAMDISK!r}")

    # zImage words at kernel offset 0x24/0x28/0x2c.
    if ksize >= 0x30:
        magic_w, start_w, end_w = struct.unpack_from("<III", kernel, 0x24)
        if magic_w != ZIMAGE_MAGIC:
            bad(f"zImage magic {magic_w:#x} != {ZIMAGE_MAGIC:#x}")
        if start_w != 0:
            bad(f"zImage start word {start_w:#x} != 0")
        if end_w != ksize:
            bad(f"zImage end word {end_w:#x} != kernel size {ksize:#x}")
    else:
        bad(f"kernel too small for zImage words: {ksize} bytes")

    # Recomputed image id.
    want_id = _recompute_id(kernel, ramdisk, second)
    if img_id != want_id:
        bad(f"image id {img_id.hex()} != recomputed {want_id.hex()}")

    # Trailer: exactly the 16-byte marker at the end, on the page boundary.
    trailer = img[trailer_off:trailer_off + len(SEANDROID)]
    if trailer != SEANDROID:
        bad(f"trailer {trailer!r} != {SEANDROID!r}")
    if len(img) != trailer_off + len(SEANDROID):
        bad(f"trailing bytes after the marker: image is {len(img)} bytes, "
            f"expected {trailer_off + len(SEANDROID)}")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: read_bootimg.py IMAGE", file=sys.stderr)
        return 2
    with open(argv[0], "rb") as fh:
        img = fh.read()
    problems = validate(img)
    if problems:
        for p in problems:
            print(f"read_bootimg: {p}")
        return 1
    ksize = struct.unpack_from("<I", img, 8)[0]
    print(f"read_bootimg: OK ({len(img)} bytes, kernel {ksize} bytes, "
          f"v0, page {EXP_PAGE}, SEANDROIDENFORCE trailer)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
