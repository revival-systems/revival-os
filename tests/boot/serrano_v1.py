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

# Encoded-word block geometry (matches payload.rs). 9 rows * 16 = 144 <= 960.
BLOCK_W = 16
BLOCK_H = 16
WORDS = 9
WHITE = (0xFF, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00)
FILL_GREY = (0x80, 0x80, 0x80)  # a plausible third (discovered) framebuffer

# MDP4 DMA_P source-buffer address register (docs/phase-2 section 3), read last
# by the payload. In QEMU virt it is flash and reads back 0x00000000, which is
# not a plausible framebuffer, so no third buffer is painted in the emulator.
MDP_DMA_P_BUF_ADDR = 0x0519_0008
MDP4_QEMU = 0x0000_0000

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
R2_OUT_OF_RANGE = 0xFFFF_FFFF
ENTRY_ADDR = 0x80208000
QEMU_CPSR = 0x4000_01D3   # SVC(0x13) + A(0x100) + I(0x80) + F(0x40) + Z(0x40000000)
QEMU_SCTLR = 0x00C5_0078  # cortex-a15 reset; MMU bit (0) clear

# Device DRAM and the reserved regions a discovered framebuffer must avoid
# (gt-i9195.md memory map); must match payload.rs. All half-open [lo, hi).
DEV_RAM_LO = 0x8000_0000
DEV_RAM_HI = 0x8000_0000 + 0x6000_0000  # 1.5 GiB -> 0xE000_0000
RESERVED = [
    (0x8020_0000, 0x8020_8000),  # ATAGS / tags page
    (0x8020_8000, 0x8120_8000),  # the image + its 64 KiB stack (link.ld, 16 MiB)
    (0x8000_0000, 0x8020_0000),  # SMEM (2 MiB)
    (0x8830_0000, 0x8860_0000),  # bootloader framebuffer reserved (3 MiB)
    (0x8F00_0000, 0x8F70_0000),  # WCNSS (7 MiB)
    (0x8FB0_0000, 0x8FE0_0000),  # modem rmtfs (3 MiB)
]


def is_plausible_fb(fb: int) -> bool:
    """Mirror of payload.rs is_plausible_fb: would the payload also paint a
    third (grey) framebuffer at this discovered address?"""
    if fb & 3:
        return False
    lo, hi = fb, fb + FB_BYTES
    if lo < DEV_RAM_LO or hi > DEV_RAM_HI:
        return False
    if fb in (FB_RED, FB_GREEN):
        return False
    return not any(lo < rhi and rlo < hi for rlo, rhi in RESERVED)


# Order matches payload.rs: r0, r1, r2, cpsr, sctlr, entry, *r2, checksum, MDP4.
EXPECTED_WORDS = [
    0x0000_0000,      # r0  (ARM boot convention wants 0; QEMU zeroes GPRs)
    0x0000_0000,      # r1
    0x0000_0000,      # r2
    QEMU_CPSR,        # cpsr at entry
    QEMU_SCTLR,       # sctlr
    ENTRY_ADDR,       # run-time entry address
    R2_OUT_OF_RANGE,  # *r2 sentinel (r2 == 0 is outside the tags-page window)
    checksum(),       # Rust checksum, recomputed here
    MDP4_QEMU,        # MDP4 DMA_P buffer address (flash -> 0 in QEMU, read last)
]


def assert_handoff_invariants(words: list[int]) -> None:
    """Check the decoded words mean the right thing (not just equal constants).

    Raises AssertionError with a specific message on any violation.
    """
    r0, r1, r2, cpsr, sctlr, entry, at_r2, csum, mdp = words
    assert r0 == 0, f"r0 should be 0 (ARM boot convention), got {r0:#x}"
    assert entry == ENTRY_ADDR, f"entry {entry:#x} != load address {ENTRY_ADDR:#x}"
    assert (cpsr & 0x1F) == 0x13, f"CPSR mode {cpsr & 0x1F:#x} is not SVC (0x13)"
    assert (cpsr >> 7) & 1, "CPSR I bit clear: IRQ was not masked at entry"
    assert (cpsr >> 6) & 1, "CPSR F bit clear: FIQ was not masked at entry"
    assert (sctlr & 1) == 0, f"SCTLR M bit set: MMU on at entry ({sctlr:#x})"
    assert at_r2 == R2_OUT_OF_RANGE, (
        f"*r2 slot {at_r2:#x} != sentinel {R2_OUT_OF_RANGE:#x} (r2 was {r2:#x})")
    assert csum == checksum(), f"checksum {csum:#x} != {checksum():#x}"
    # In QEMU the MDP4 register is flash and reads 0, not a plausible
    # framebuffer, so the payload paints no third buffer. On the phone this may
    # differ, and reading it is the point.
    assert not is_plausible_fb(mdp), (
        f"MDP4 value {mdp:#x} was treated as a plausible framebuffer in QEMU")


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
