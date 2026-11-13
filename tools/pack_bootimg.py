#!/usr/bin/env python3
"""pack_bootimg.py - pack a flat kernel-slot binary into an Android boot image.

Host tool (ARCHITECTURE.md: tools/ = host image packaging, Phase 2). Produces
the GT-I9195 Phase 2 proof-of-execution image: a version-0 Android boot image
(`ANDROID!`) whose kernel slot is the flat payload binary, with a 1-byte zero
ramdisk and a `SEANDROIDENFORCE` trailer, per docs/phase-2/boot-payload-research.md
("Candidate payload specification", step 5 of the v1 task).

It downloads nothing and depends only on the Python standard library. The field
layout matches AOSP mkbootimg header version 0 (as used by lk2nd); the image id
is the SHA-1 that mkbootimg computes over the kernel, ramdisk and second images
with their sizes. tests/boot/read_bootimg.py re-parses the output independently.

`--invalid-magic` (off by default) builds the Phase 2 NEGATIVE-TEST image: the
same bytes with the 8-byte magic `INVALID!` in place of `ANDROID!`, and nothing
else changed (ROADMAP Phase 2, "a deliberately invalid image (bad header)").

This produces an image; it does NOT flash anything. No device is contacted.

Usage: pack_bootimg.py --kernel PAYLOAD.bin --output PAYLOAD.img [--invalid-magic]
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys

MAGIC = b"ANDROID!"
# The negative-test magic: same length, so every other byte keeps its offset.
INVALID_MAGIC = b"INVALID!"
assert len(INVALID_MAGIC) == len(MAGIC)
BOOT_NAME_SIZE = 16
BOOT_ARGS_SIZE = 512
BOOT_EXTRA_ARGS_SIZE = 1024
SEANDROID = b"SEANDROIDENFORCE"

# GT-I9195 boot-image parameters (docs/hardware/gt-i9195.md, PR #9). lk2nd
# keeps the ramdisk/second load addresses at non-zero "dummy" values that some
# MSM-era bootloaders validate, so this packer does too.
BASE = 0x80200000
KERNEL_OFFSET = 0x00008000   # -> kernel_addr 0x80208000
RAMDISK_OFFSET = 0x01000000  # -> 0x81200000
SECOND_OFFSET = 0x00F00000   # -> 0x81100000
TAGS_OFFSET = 0x00000100     # -> tags_addr 0x80200100
PAGE_SIZE = 2048
HEADER_VERSION = 0
OS_VERSION = 0               # (os_version << 11) | os_patch_level, both 0

# The ramdisk the bootloader expects is irrelevant to our payload, but lk2nd
# ships a 1-byte, single-zero ramdisk; a zero-length ramdisk is untested on the
# device, so we match lk2nd exactly (research section 1).
DEFAULT_RAMDISK = b"\x00"


def _pad_to(buf: bytearray, page_size: int) -> None:
    rem = len(buf) % page_size
    if rem:
        buf.extend(b"\x00" * (page_size - rem))


def _image_id(kernel: bytes, ramdisk: bytes, second: bytes) -> bytes:
    """SHA-1 over (data || u32 size) for kernel, ramdisk, second; mkbootimg v0.

    A `None`/empty section contributes only its u32 zero size. The 20-byte
    digest is stored in a 32-byte field, zero-padded.
    """
    sha = hashlib.sha1()
    for data in (kernel, ramdisk, second):
        if data:
            sha.update(data)
            sha.update(struct.pack("<I", len(data)))
        else:
            sha.update(struct.pack("<I", 0))
    return sha.digest().ljust(32, b"\x00")


def build_bootimg(kernel: bytes, ramdisk: bytes = DEFAULT_RAMDISK,
                  page_size: int = PAGE_SIZE, invalid_magic: bool = False) -> bytes:
    """Return the complete boot image (header + kernel + ramdisk + trailer).

    `invalid_magic` selects the negative-test image: bytes 0-7 are `INVALID!`
    instead of `ANDROID!`. Every other byte, the image id included, is the same
    as in the valid image, so the kernel slot still holds the real payload.
    """
    second = b""
    magic = INVALID_MAGIC if invalid_magic else MAGIC
    header = bytearray()
    header += struct.pack(f"<{len(magic)}s", magic)
    header += struct.pack("<I", len(kernel))
    header += struct.pack("<I", BASE + KERNEL_OFFSET)
    header += struct.pack("<I", len(ramdisk))
    header += struct.pack("<I", BASE + RAMDISK_OFFSET)
    header += struct.pack("<I", len(second))
    header += struct.pack("<I", BASE + SECOND_OFFSET)
    header += struct.pack("<I", BASE + TAGS_OFFSET)
    header += struct.pack("<I", page_size)
    header += struct.pack("<I", HEADER_VERSION)
    header += struct.pack("<I", OS_VERSION)
    header += struct.pack(f"<{BOOT_NAME_SIZE}s", b"")          # product name
    header += struct.pack(f"<{BOOT_ARGS_SIZE}s", b"")          # cmdline
    header += _image_id(kernel, ramdisk, second)              # id[32]
    header += struct.pack(f"<{BOOT_EXTRA_ARGS_SIZE}s", b"")    # extra cmdline

    img = bytearray(header)
    _pad_to(img, page_size)   # header occupies whole pages
    img += kernel
    _pad_to(img, page_size)   # kernel padded to a page boundary
    img += ramdisk
    _pad_to(img, page_size)   # ramdisk padded to a page boundary
    # (no second stage)
    img += SEANDROID          # raw trailer, after the last page
    return bytes(img)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kernel", required=True, help="flat payload binary")
    parser.add_argument("--output", required=True, help="boot image to write")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--invalid-magic", action="store_true",
                        help="NEGATIVE-TEST image: write the magic 'INVALID!' "
                             "in place of 'ANDROID!' and change nothing else")
    args = parser.parse_args(argv)

    with open(args.kernel, "rb") as fh:
        kernel = fh.read()
    if not kernel:
        print("pack_bootimg: kernel is empty", file=sys.stderr)
        return 1

    image = build_bootimg(kernel, page_size=args.page_size,
                          invalid_magic=args.invalid_magic)
    with open(args.output, "wb") as fh:
        fh.write(image)
    print(f"pack_bootimg: wrote {args.output} ({len(image)} bytes, "
          f"kernel {len(kernel)} bytes, page {args.page_size})")
    if args.invalid_magic:
        print(f"pack_bootimg: NEGATIVE-TEST IMAGE: magic {INVALID_MAGIC.decode()!r}, "
              "built to be rejected. It is not the payload image.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
