#!/usr/bin/env python3
"""Expected order checksum of the task experiment's "many" case (ADR 0003).

tests/qemu/virt-armv7/tasks.rs runs N worker tasks round robin; each runs
Y iterations and yields after each one. Every iteration folds the running
task's id and the iteration number into a 32-bit checksum (xor, then
multiply by an odd constant, as in FNV-1a), so the result depends on exactly
which task ran each step, in order. A plain rotate-and-xor was rejected: its
rotation repeats every 32 steps, and for N a multiple of 32 and Y = 4 every
task's contributions cancel, so a skipped task went unseen. This computes the
same value independently, for the Makefile to pass to the build.

Usage: tasks_oracle.py N Y   (prints the checksum as 0x and 8 hex digits)
"""

from __future__ import annotations

import sys

MASK = 0xFFFFFFFF


def order_checksum(tasks: int, yields: int) -> int:
    acc = 0x12345678
    for i in range(yields):
        for task in range(tasks):
            acc ^= (task * 0x9E3779B9 + i) & MASK
            acc = (acc * 0x01000193) & MASK
    return acc


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    tasks, yields = int(argv[1]), int(argv[2])
    if tasks < 1 or yields < 0:
        print("N must be at least 1 and Y at least 0", file=sys.stderr)
        return 2
    print(f"0x{order_checksum(tasks, yields):08x}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
