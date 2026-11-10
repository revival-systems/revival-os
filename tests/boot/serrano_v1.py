"""serrano_v1.py - host oracle for the GT-I9195 Phase 2 proof-of-execution v1.

Reproduces, on the host and independently of the payload, the exact bytes the
payload paints into each framebuffer, and decodes a framebuffer dump back into
the eight recorded handoff words. The QEMU test (tests/boot/run_payload.py)
compares the real framebuffer dumps against generate_fb(...) byte for byte and
checks that the decoded words satisfy the structural invariants below.

This is the single source of truth for the geometry and encoding; the payload
(boot/samsung-serranolte/payload.rs) holds the same constants, and the
byte-for-byte compare is what proves the two agree. Nothing here touches a
device or a network.
"""

from __future__ import annotations

import struct

# Framebuffer geometry (docs/hardware/gt-i9195.md; matches payload.rs).
WIDTH = 540
HEIGHT = 960
BPP = 3
STRIDE = 1620  # WIDTH * BPP, no padding
FB_BYTES = STRIDE * HEIGHT  # 1_555_200

FB_RED = 0x8810_0000   # contested address (Jan 2026 LKML report)
FB_GREEN = 0x8830_0000  # mainline-fork / reserved framebuffer
FILL_RED = (0xFF, 0x00, 0x00)
FILL_GREEN = (0x00, 0xFF, 0x00)

# Encoded-word block geometry (matches payload.rs).
BLOCK_W = 16
BLOCK_H = 16
WORDS = 8
WHITE = (0xFF, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00)

# Completion marker the payload writes last (matches payload.rs).
DONE_ADDR = 0x8829_0000
DONE_VALUE = 0xD09E_D09E

# Checksum: same table and algorithm as the Phase 1 fixture and payload.rs,
# recomputed here independently so the test does not trust the payload's value.
_TABLE = [
    0x5245_5649, 0x414C_204F, 0x5350_4841, 0x5345_3120,
    0x0000_0001, 0x0000_0002, 0x0000_0003, 0x0000_0004,
]
MASK32 = 0xFFFF_FFFF


def _rotl32(v: int, n: int) -> int:
    v &= MASK32
    return ((v << n) | (v >> (32 - n))) & MASK32


def checksum() -> int:
    acc = 0x1234_5678
    for i, entry in enumerate(_TABLE):
        acc = _rotl32(acc, 5) ^ ((entry + i) & MASK32)
    return acc & MASK32


# Expected handoff words under QEMU `-M virt -cpu cortex-a15` with the payload
# loaded at 0x80208000 via `-device loader` (PC set there, GPRs zeroed at reset).
# These are EMULATOR values; on the phone they are what Phase 2 measures. The
# byte-for-byte compare pins them, and assert_handoff_invariants() documents what
# each must mean. r3 is captured by kstart.S but is not among the painted words.
R2_NOT_IN_RAM = 0xFFFF_FFFF
ENTRY_ADDR = 0x80208000
QEMU_CPSR = 0x4000_01D3   # SVC(0x13) + A(0x100) + I(0x80) + F(0x40) + Z(0x40000000)
QEMU_SCTLR = 0x00C5_0078  # cortex-a15 reset; MMU bit (0) clear

# Order matches payload.rs: r0, r1, r2, cpsr, sctlr, entry, *r2, checksum.
EXPECTED_WORDS = [
    0x0000_0000,   # r0  (ARM boot convention wants 0; QEMU zeroes GPRs)
    0x0000_0000,   # r1
    0x0000_0000,   # r2
    QEMU_CPSR,     # cpsr at entry
    QEMU_SCTLR,    # sctlr
    ENTRY_ADDR,    # run-time entry address
    R2_NOT_IN_RAM,  # *r2 sentinel (r2 == 0 is not in the device RAM window)
    checksum(),    # Rust checksum, recomputed here
]


def assert_handoff_invariants(words: list[int]) -> None:
    """Check the decoded words mean the right thing (not just equal constants).

    Raises AssertionError with a specific message on any violation.
    """
    r0, r1, r2, cpsr, sctlr, entry, at_r2, csum = words
    assert r0 == 0, f"r0 should be 0 (ARM boot convention), got {r0:#x}"
    assert entry == ENTRY_ADDR, f"entry {entry:#x} != load address {ENTRY_ADDR:#x}"
    assert (cpsr & 0x1F) == 0x13, f"CPSR mode {cpsr & 0x1F:#x} is not SVC (0x13)"
    assert (cpsr >> 7) & 1, "CPSR I bit clear: IRQ was not masked at entry"
    assert (cpsr >> 6) & 1, "CPSR F bit clear: FIQ was not masked at entry"
    assert (sctlr & 1) == 0, f"SCTLR M bit set: MMU on at entry ({sctlr:#x})"
    assert at_r2 == R2_NOT_IN_RAM, (
        f"*r2 slot {at_r2:#x} != sentinel {R2_NOT_IN_RAM:#x} (r2 was {r2:#x})")
    assert csum == checksum(), f"checksum {csum:#x} != {checksum():#x}"


def _put_px(buf: bytearray, x: int, y: int, px: tuple) -> None:
    o = y * STRIDE + x * BPP
    buf[o], buf[o + 1], buf[o + 2] = px


def _get_px(buf, x: int, y: int) -> tuple:
    o = y * STRIDE + x * BPP
    return (buf[o], buf[o + 1], buf[o + 2])


def _draw_block(buf: bytearray, bx: int, by: int, on: bool) -> None:
    px = WHITE if on else BLACK
    for y in range(by * BLOCK_H, by * BLOCK_H + BLOCK_H):
        for x in range(bx * BLOCK_W, bx * BLOCK_W + BLOCK_W):
            _put_px(buf, x, y, px)


def generate_fb(fill_px: tuple, words: list[int]) -> bytes:
    """The exact FB_BYTES the payload paints: solid fill, then 8 word rows."""
    assert len(words) == WORDS
    buf = bytearray(FB_BYTES)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            _put_px(buf, x, y, fill_px)
    for row, w in enumerate(words):
        for bit in range(32):
            on = (w >> (31 - bit)) & 1 != 0
            _draw_block(buf, bit, row, on)
    return bytes(buf)


def decode_words(buf: bytes) -> list[int]:
    """Read the eight words back from a framebuffer dump (block centres)."""
    if len(buf) < FB_BYTES:
        raise ValueError(f"dump is {len(buf)} bytes, need {FB_BYTES}")
    out = []
    for row in range(WORDS):
        v = 0
        for bit in range(32):
            x = bit * BLOCK_W + BLOCK_W // 2
            y = row * BLOCK_H + BLOCK_H // 2
            px = _get_px(buf, x, y)
            if px == WHITE:
                v = (v << 1) | 1
            elif px == BLACK:
                v = (v << 1)
            else:
                raise ValueError(f"row {row} bit {bit} not black/white: {px}")
        out.append(v)
    return out


def fill_pixel_at(buf: bytes, x: int, y: int) -> tuple:
    """Sample one pixel of a dump (used to report the observed fill colour)."""
    return _get_px(buf, x, y)


def done_marker_word(raw4: bytes) -> int:
    """Interpret a 4-byte dump of DONE_ADDR as a little-endian u32."""
    return struct.unpack("<I", raw4)[0]
