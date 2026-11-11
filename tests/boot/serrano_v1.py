"""serrano_v1.py - host oracle for the GT-I9195 Phase 2 proof-of-execution v1.

Reproduces, on the host and independently of the payload, the exact bytes the
payload paints into each framebuffer, and decodes a framebuffer dump back into
the nine recorded words. The QEMU test (tests/boot/run_payload.py) compares the
real framebuffer dumps against generate_fb(...) byte for byte and checks that
the decoded words satisfy the structural invariants below. It also checks the
first 0x30 bytes of the image (reset branch, halt-only exception vectors,
zImage words) against the layout kstart.S promises.

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

# Encoded-word geometry (matches payload.rs), readable from a phone photo: each
# bit is its own CELL_W x CELL_H cell with the fill colour left visible around
# it, a wider gap before every fourth bit, and a margin from the screen edge.
#   x = MARGIN_X + bit * BIT_PITCH + (bit // 4) * NIBBLE_GAP
#   y = MARGIN_Y + row * ROW_PITCH
# The last cell ends at x = 535 <= 540 and y = 296 <= 960.
WORDS = 9
MARGIN_X = 6
MARGIN_Y = 16
BIT_PITCH = 16
NIBBLE_GAP = 3
CELL_W = 12
ROW_PITCH = 32
CELL_H = 24
WHITE = (0xFF, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00)
FILL_GREY = (0x80, 0x80, 0x80)  # a plausible third (discovered) framebuffer

# MDP4 DMA_P source-buffer address register (docs/phase-2 section 3), read last
# by the payload. In QEMU virt it is flash and reads back 0x00000000 by default,
# which is not a plausible framebuffer, so no third buffer is painted. The QEMU
# test injects other values through an emulated flash image (run_payload.py).
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

# The payload reads *r2 only inside the tags page and only word-aligned
# (payload.rs R2_READ_LO/HI); anything else records R2_OUT_OF_RANGE.
R2_READ_LO = 0x8020_0000
R2_READ_HI = 0x8020_8000
# What section 2 of the research expects the stock bootloader to hand over.
MACH_SERRANO = 3727          # r1 = 0x00000E8F
TAGS_ADDR = 0x8020_0100      # r2
QEMU_CPSR = 0x4000_01D3   # SVC(0x13) + A(0x100) + I(0x80) + F(0x40) + Z(0x40000000)
QEMU_SCTLR = 0x00C5_0078  # cortex-a15 reset; MMU bit (0) clear

# Device DRAM and the reserved regions a discovered framebuffer must avoid
# (gt-i9195.md memory map); must match payload.rs. All half-open [lo, hi).
# DEV_RAM_HI is unverified on this unit (nominal 1.5 GiB above the DRAM base).
#
# The bootloader's framebuffer reservation [0x88300000, 0x88600000) is NOT in
# RESERVED: it is the one region where a framebuffer is expected, and a buffer
# starting at 0x8847BB00 or above inside it is reached by neither candidate
# fill. Only the exact candidate addresses are excluded.
DEV_RAM_LO = 0x8000_0000
DEV_RAM_HI = 0x8000_0000 + 0x6000_0000  # 1.5 GiB -> 0xE000_0000
RESERVED = [
    (0x8020_0000, 0x8020_8000),  # ATAGS / tags page
    (0x8020_8000, 0x8120_8000),  # the image + its 64 KiB stack (link.ld, 16 MiB)
    (0x8000_0000, 0x8020_0000),  # SMEM (2 MiB)
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


def expected_words(mdp: int) -> list[int]:
    """The nine words expected under QEMU when the MDP4 register reads `mdp`."""
    return EXPECTED_WORDS[:8] + [mdp]


def r2_is_read(r2: int) -> bool:
    """Mirror of payload.rs's guard: does the payload dereference this r2?"""
    return R2_READ_LO <= r2 < R2_READ_HI and r2 & 3 == 0


def handoff_words(r0: int = 0, r1: int = 0, r2: int = 0, word_at_r2: int | None = None,
                  entry: int = ENTRY_ADDR, mdp: int = MDP4_QEMU) -> list[int]:
    """The nine words expected under QEMU for a given entry state: registers
    r0-r2, the word stored at r2 (used only if the guard lets the payload read
    it; otherwise the sentinel), the run-time entry address and the MDP4 value.
    The defaults are the plain run, so handoff_words() == EXPECTED_WORDS."""
    if r2_is_read(r2):
        assert word_at_r2 is not None, f"r2 {r2:#x} is read; say what is stored there"
        at_r2 = word_at_r2
    else:
        at_r2 = R2_OUT_OF_RANGE
    return [r0, r1, r2, QEMU_CPSR, QEMU_SCTLR, entry, at_r2, checksum(), mdp]


def assert_cpu_handoff_invariants(words: list[int]) -> None:
    """Check the eight handoff words mean the right thing (not just equal
    constants). These hold whatever the MDP4 register (the ninth word) reads.

    Raises AssertionError with a specific message on any violation.
    """
    r0, r1, r2, cpsr, sctlr, entry, at_r2, csum, _mdp = words
    assert r0 == 0, f"r0 should be 0 (ARM boot convention), got {r0:#x}"
    assert entry == ENTRY_ADDR, f"entry {entry:#x} != load address {ENTRY_ADDR:#x}"
    assert (cpsr & 0x1F) == 0x13, f"CPSR mode {cpsr & 0x1F:#x} is not SVC (0x13)"
    assert (cpsr >> 7) & 1, "CPSR I bit clear: IRQ was not masked at entry"
    assert (cpsr >> 6) & 1, "CPSR F bit clear: FIQ was not masked at entry"
    assert (sctlr & 1) == 0, f"SCTLR M bit set: MMU on at entry ({sctlr:#x})"
    assert at_r2 == R2_OUT_OF_RANGE, (
        f"*r2 slot {at_r2:#x} != sentinel {R2_OUT_OF_RANGE:#x} (r2 was {r2:#x})")
    assert csum == checksum(), f"checksum {csum:#x} != {checksum():#x}"


def assert_handoff_invariants(words: list[int]) -> None:
    """The invariants of the plain QEMU run (no injected MDP4 value): the eight
    handoff words, plus an MDP4 word that is NOT a plausible framebuffer.

    Raises AssertionError with a specific message on any violation.
    """
    assert_cpu_handoff_invariants(words)
    mdp = words[8]
    # In plain QEMU the MDP4 register is flash and reads 0, not a plausible
    # framebuffer, so the payload paints no third buffer. On the phone this may
    # differ, and reading it is the point.
    assert not is_plausible_fb(mdp), (
        f"MDP4 value {mdp:#x} was treated as a plausible framebuffer in QEMU")


def _get_px(buf, x: int, y: int) -> tuple:
    o = y * STRIDE + x * BPP
    return (buf[o], buf[o + 1], buf[o + 2])


def cell_origin(bit: int, row: int) -> tuple:
    """Top-left pixel (x, y) of the cell of bit `bit` (0 = MSB) in row `row`."""
    return (MARGIN_X + bit * BIT_PITCH + (bit // 4) * NIBBLE_GAP,
            MARGIN_Y + row * ROW_PITCH)


def _draw_cell(buf: bytearray, bit: int, row: int, on: bool) -> None:
    x0, y0 = cell_origin(bit, row)
    line = bytes(WHITE if on else BLACK) * CELL_W
    for y in range(y0, y0 + CELL_H):
        o = y * STRIDE + x0 * BPP
        buf[o:o + len(line)] = line


def generate_fb(fill_px: tuple, words: list[int]) -> bytes:
    """The exact FB_BYTES the payload paints: solid fill, then 9 word rows of
    32 separate cells each (the fill colour stays visible between cells)."""
    assert len(words) == WORDS
    buf = bytearray(bytes(fill_px) * (WIDTH * HEIGHT))
    for row, w in enumerate(words):
        for bit in range(32):
            _draw_cell(buf, bit, row, (w >> (31 - bit)) & 1 != 0)
    assert len(buf) == FB_BYTES
    return bytes(buf)


def decode_words(buf: bytes) -> list[int]:
    """Read the nine words back from a framebuffer dump (cell centres)."""
    if len(buf) < FB_BYTES:
        raise ValueError(f"dump is {len(buf)} bytes, need {FB_BYTES}")
    out = []
    for row in range(WORDS):
        v = 0
        for bit in range(32):
            x0, y0 = cell_origin(bit, row)
            px = _get_px(buf, x0 + CELL_W // 2, y0 + CELL_H // 2)
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


# --- image header: reset branch, halt-only vectors, zImage words -------------
# kstart.S mirrors lk2nd's arch/arm/crt0.S header. Offsets are from the image
# base; `b` is the ARM unconditional branch (cond AL, 0xEA, signed imm24 words
# relative to the instruction address + 8).
HEADER_BYTES = 0x30
VECTOR_OFFSETS = (0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C)  # undef .. fiq
ZIMAGE_MAGIC = 0x016F_2818
INSN_WFI = 0xE320_F003


def _branch_target(image: bytes, off: int) -> int:
    """Image offset an ARM `b` at image offset `off` jumps to."""
    (insn,) = struct.unpack_from("<I", image, off)
    assert insn >> 24 == 0xEA, f"offset {off:#x}: {insn:#010x} is not an ARM `b`"
    imm = insn & 0x00FF_FFFF
    if imm & 0x0080_0000:
        imm -= 0x0100_0000
    return off + 8 + imm * 4


def check_image_header(image: bytes, halt_off: int) -> None:
    """Check the flat image starts with the layout kstart.S promises:

      0x00            b 0x20                 (reset / bootloader entry)
      0x04 .. 0x1c    b halt_loop            (the seven exception vectors)
      0x20            b 0x30                 (over the zImage words)
      0x24/0x28/0x2c  zImage magic, 0, image size

    and that halt_loop is exactly `wfi; b halt_loop` (halt only, no handler).
    `halt_off` is halt_loop's offset from the image base. Raises AssertionError
    with a specific message on any violation.
    """
    assert len(image) >= HEADER_BYTES, f"image is only {len(image)} bytes"
    assert halt_off % 4 == 0 and HEADER_BYTES <= halt_off <= len(image) - 8, (
        f"halt_loop offset {halt_off:#x} is outside the image")
    assert _branch_target(image, 0x00) == 0x20, "0x00 does not branch to 0x20"
    for off in VECTOR_OFFSETS:
        target = _branch_target(image, off)
        assert target == halt_off, (
            f"vector at {off:#x} branches to {target:#x}, not halt_loop {halt_off:#x}")
    assert _branch_target(image, 0x20) == HEADER_BYTES, "0x20 does not branch to 0x30"
    magic, start, end = struct.unpack_from("<3I", image, 0x24)
    assert magic == ZIMAGE_MAGIC, f"zImage magic at 0x24 is {magic:#010x}"
    assert start == 0, f"zImage start at 0x28 is {start:#x}, want 0"
    assert end == len(image), f"zImage end at 0x2c is {end:#x}, image is {len(image):#x}"
    (wfi,) = struct.unpack_from("<I", image, halt_off)
    assert wfi == INSN_WFI, f"halt_loop starts with {wfi:#010x}, not wfi"
    assert _branch_target(image, halt_off + 4) == halt_off, (
        "halt_loop does not branch back to itself")
