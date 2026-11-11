"""check_negative_img.py - check the Phase 2 negative-test image against the real one.

The negative-test image (`make payload-invalid`) must be the payload image with
the 8-byte magic `INVALID!` in place of `ANDROID!` and NOTHING else changed, so
that the trial answers one question: does the stock bootloader check the magic?
(docs/phase-2/boot-payload-research.md, "Trial kit".)

`problems(valid, invalid)` returns a list of problem strings (empty == OK):

  - the two images have the same length;
  - the valid image starts with `ANDROID!`, the invalid one with `INVALID!`;
  - every byte from offset 8 on is identical;
  - the repository's boot-image reader accepts the valid image, and rejects the
    invalid one for exactly one reason, the magic.

Like read_bootimg.py it does not import the packer. The CLI prints each problem
and exits 1 if any, else prints a one-line summary and exits 0. Nothing here
contacts a device.

Usage: python3 -m tests.boot.check_negative_img VALID.img INVALID.img
"""

from __future__ import annotations

import sys

from tests.boot import read_bootimg

MAGIC_LEN = len(read_bootimg.MAGIC)
INVALID_MAGIC = b"INVALID!"


def problems(valid: bytes, invalid: bytes) -> list[str]:
    found = []
    if valid[:MAGIC_LEN] != read_bootimg.MAGIC:
        found.append(f"valid image starts with {valid[:MAGIC_LEN]!r}, "
                     f"not {read_bootimg.MAGIC!r}")
    if invalid[:MAGIC_LEN] != INVALID_MAGIC:
        found.append(f"invalid image starts with {invalid[:MAGIC_LEN]!r}, "
                     f"not {INVALID_MAGIC!r}")
    if len(valid) != len(invalid):
        found.append(f"lengths differ: valid {len(valid)} bytes, "
                     f"invalid {len(invalid)} bytes")
    else:
        diff = [i for i in range(MAGIC_LEN, len(valid)) if valid[i] != invalid[i]]
        if diff:
            found.append(f"{len(diff)} byte(s) differ outside bytes 0-{MAGIC_LEN - 1}, "
                         f"the first at offset {diff[0]:#x}")

    for p in read_bootimg.validate(valid):
        found.append(f"the reader rejects the valid image: {p}")
    rejected = read_bootimg.validate(invalid)
    if not rejected:
        found.append("the reader accepts the invalid image")
    elif len(rejected) != 1 or not rejected[0].startswith("magic "):
        found.append("the reader should reject the invalid image for the magic "
                     f"alone, but reports: {'; '.join(rejected)}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_negative_img.py VALID.img INVALID.img", file=sys.stderr)
        return 2
    with open(argv[0], "rb") as fh:
        valid = fh.read()
    with open(argv[1], "rb") as fh:
        invalid = fh.read()
    found = problems(valid, invalid)
    if found:
        for p in found:
            print(f"check_negative_img: {p}")
        return 1
    print(f"check_negative_img: OK ({len(invalid)} bytes; differs from the valid "
          f"image in bytes 0-{MAGIC_LEN - 1} only: {INVALID_MAGIC!r} for "
          f"{read_bootimg.MAGIC!r}; the reader rejects it for the magic alone)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
