#!/usr/bin/env python3
"""Independent oracle for probe_checksum in tests/goose/probe.goose.

Computes acc = acc * 31 + i for i in 0 .. n-1 with 32-bit two's-complement
wrapping, the semantics of the Goose code in a release build. The host and
QEMU tests compare Goose's result with this value, so a wrong result cannot
pass by agreeing with itself.

Usage: checksum_oracle.py N
"""

import sys


def checksum(n: int) -> int:
    acc = 0
    for i in range(n):
        acc = (acc * 31 + i) & 0xFFFFFFFF
    return acc - (1 << 32) if acc & 0x80000000 else acc


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit():
        print("usage: checksum_oracle.py N", file=sys.stderr)
        return 2
    print(checksum(int(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
