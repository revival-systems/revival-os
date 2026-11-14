#!/usr/bin/env python3
"""Count executed instructions per function from QEMU instruction traces.

Run QEMU with one instruction per translation block and the exec log:

  qemu-system-arm ... -accel tcg,one-insn-per-tb=on -d exec,nochain -D trace.log

Each "Trace" line then records one executed guest instruction; its guest PC is
the second field in the brackets. This maps every PC to the function that
contains it, using `arm-none-eabi-nm -S -C --defined-only` output of the same
ELF, and prints the count per function, largest first.

Given a second image and trace that ran STEPS more steps of the same work, it
prints the difference per step instead: the instructions one more step costs
in each function, with everything that happens once (start-up, reporting)
cancelled out. Measurement tool for ADR 0003. Emulator instruction counts are
not phone timings.

Usage: insn_profile.py NM TRACE [NM2 TRACE2 STEPS]
"""

from __future__ import annotations

import bisect
import re
import sys
from collections import Counter

TRACE_RE = re.compile(r"^Trace \d+: 0x[0-9a-f]+ \[[0-9a-f]+/([0-9a-f]+)/")
NM_RE = re.compile(r"^([0-9a-f]+) ([0-9a-f]+) ([tTwW]) (.+)$")


def load_symbols(path: str) -> tuple[list[int], list[tuple[int, str]]]:
    """Function symbols of an ELF from `nm -S`: sorted starts, (end, name)."""
    spans = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = NM_RE.match(line.rstrip("\n"))
            if m and int(m.group(2), 16):
                start = int(m.group(1), 16)
                spans.append((start, start + int(m.group(2), 16), m.group(4)))
    spans.sort()
    return [s[0] for s in spans], [(s[1], s[2]) for s in spans]


def profile(nm_path: str, trace_path: str) -> tuple[int, Counter[str]]:
    """Executed instructions in total and per function."""
    starts, ends = load_symbols(nm_path)
    counts: Counter[str] = Counter()
    total = 0
    with open(trace_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TRACE_RE.match(line)
            if not m:
                continue
            pc = int(m.group(1), 16)
            total += 1
            i = bisect.bisect_right(starts, pc) - 1
            if i >= 0 and pc < ends[i][0]:
                counts[ends[i][1]] += 1
            else:
                counts["<outside any function>"] += 1
    return total, counts


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 6):
        print("usage: " + __doc__.strip().splitlines()[-1].split(": ", 1)[1], file=sys.stderr)
        return 2
    total, counts = profile(argv[1], argv[2])
    if len(argv) == 3:
        print(f"{total} instructions executed")
        for name, n in counts.most_common():
            print(f"{n:10d}  {name}")
        return 0
    steps = int(argv[5])
    if steps <= 0:
        print("STEPS must be positive", file=sys.stderr)
        return 2
    total2, counts2 = profile(argv[3], argv[4])
    print(f"{(total2 - total) / steps:.2f} instructions per step in total")
    names = sorted(set(counts) | set(counts2), key=lambda n: counts[n] - counts2[n])
    for name in names:
        diff = counts2[name] - counts[name]
        if diff:
            print(f"{diff / steps:10.2f}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
