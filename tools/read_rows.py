#!/usr/bin/env python3
"""read_rows.py - turn the word rows photographed on the phone into the Phase 2 record.

Host tool (ARCHITECTURE.md: tools/ = host tools, evidence collection). The
Phase 2 payload paints nine 32-bit words as rows of black and white cells
(docs/phase-2/boot-payload-research.md, "v1 payload decision"). On trial day the
owner photographs the screen and types each row as a hex word. This tool decodes
those words into a short plain-text record and draws the screen they describe.

Input: the fill colour seen (red, blue, green or grey) and the rows as hex
words, top row first: nine, or eight if the ninth row is missing.

Output, on stdout:
  - the checksum row first: it must be the value the Rust code computes, and a
    mismatch means the rows were misread;
  - each row echoed as 32 cells in groups of four, to compare with the photo;
  - r0, r1, r2 against the expected handoff; the CPSR and SCTLR fields; the
    entry address; what *r2 is; what the MDP4 word is; what the fill colour and
    the number of rows mean.
It also writes the screen for that colour and those words as a PNG under
build/ (never committed), so the owner can see what to look for.

The geometry, the checksum, the handoff constants and the third-buffer rule all
come from the host oracle (tests/boot/serrano_v1.py); this file holds no copy.
It depends only on the Python standard library. It decodes what was typed: it
contacts no device, and its output is not hardware evidence by itself.

Exit status: 0 = decoded; 1 = the rows cannot be right as typed (the checksum
row is wrong, or two inputs contradict each other); 2 = usage error.

Usage: python3 tools/read_rows.py --fill COLOUR [--png PATH | --no-png] WORD...
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from typing import NamedTuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if __package__ in (None, ""):  # run as a script: make the repository importable
    sys.path.insert(0, REPO)

from tests.boot import serrano_v1 as oracle  # noqa: E402

ROW_NAMES = ("r0", "r1", "r2", "CPSR", "SCTLR", "entry", "*r2", "checksum", "MDP4")
assert len(ROW_NAMES) == oracle.WORDS

AS_EXPECTED = "as expected"
NOT_EXPECTED = "NOT as expected"


def hx(word: int) -> str:
    return f"0x{word:08X}"


class Fill(NamedTuple):
    seen_px: tuple        # the colour as seen (R, G, B), for the PNG
    buffer: int | None    # the framebuffer it means; None = the MDP4 address
    order: str            # what the colour says about the byte order


# The payload fills 0x88100000 with bytes FF 00 00 (red if byte 0 is red, blue
# if byte 0 is blue), 0x88300000 with 00 FF 00, and a plausible MDP4 address
# with 80 80 80 (payload.rs). Only red and blue reveal the byte order.
FILLS = {
    "red": Fill(oracle.FILL_RED, oracle.FB_RED,
                "byte 0 is red, so the order in memory is red, green, blue "
                "(section 3 expected blue, green, red)"),
    "blue": Fill(tuple(reversed(oracle.FILL_RED)), oracle.FB_RED,
                 "byte 0 is blue, so the order in memory is blue, green, red, "
                 "as section 3 expects"),
    "green": Fill(oracle.FILL_GREEN, oracle.FB_GREEN,
                  "green is the middle byte in either order, so the byte order "
                  "is not shown"),
    "grey": Fill(oracle.FILL_GREY, None,
                 "grey is the same in either order, so the byte order is not shown"),
}

# --- CPSR and SCTLR fields (ARMv7-A) ------------------------------------------
CPSR_MODES = {0x10: "USR", 0x11: "FIQ", 0x12: "IRQ", 0x13: "SVC", 0x16: "MON",
              0x17: "ABT", 0x1A: "HYP", 0x1B: "UND", 0x1F: "SYS"}
MODE_SVC = 0x13


class Cpsr(NamedTuple):
    mode: int
    mode_name: str | None   # None = not a defined mode
    irq_masked: bool        # I, bit 7
    fiq_masked: bool        # F, bit 6
    abort_masked: bool      # A, bit 8
    thumb: bool             # T, bit 5
    big_endian: bool        # E, bit 9


def decode_cpsr(word: int) -> Cpsr:
    mode = word & 0x1F
    return Cpsr(mode, CPSR_MODES.get(mode), bool(word >> 7 & 1), bool(word >> 6 & 1),
                bool(word >> 8 & 1), bool(word >> 5 & 1), bool(word >> 9 & 1))


class Sctlr(NamedTuple):
    mmu: bool            # M, bit 0
    align: bool          # A, bit 1
    dcache: bool         # C, bit 2
    icache: bool         # I, bit 12
    high_vectors: bool   # V, bit 13


def decode_sctlr(word: int) -> Sctlr:
    return Sctlr(bool(word & 1), bool(word >> 1 & 1), bool(word >> 2 & 1),
                 bool(word >> 12 & 1), bool(word >> 13 & 1))


# --- entry address, *r2, MDP4 --------------------------------------------------

def classify_entry(entry: int) -> tuple:
    """("link", 0) or ("relocated", signed distance from the link address)."""
    delta = entry - oracle.ENTRY_ADDR
    return ("link", 0) if delta == 0 else ("relocated", delta)


# An ATAGS list begins with ATAG_CORE, whose header is {size in words, tag
# 0x54410001}. The payload records the FIRST word at r2, which is the size: 5
# with the core tag's three fields, 2 without them. A device tree begins with
# the bytes d0 0d fe ed, which read as a little-endian word are 0xEDFE0DD0.
ATAG_CORE_SIZES = (5, 2)
ATAG_CORE_TAG = 0x5441_0001
DTB_MAGIC_AS_LE_WORD = 0xEDFE_0DD0


def classify_at_r2(r2: int, at_r2: int) -> tuple:
    """(kind, text) for the *r2 row. kind is "sentinel", "atag_core", "dtb",
    "other", or "impossible" when the row contradicts the r2 row."""
    sentinel = oracle.R2_OUT_OF_RANGE
    if not oracle.r2_is_read(r2):
        if at_r2 == sentinel:
            return ("sentinel", "the sentinel: the payload does not read memory at "
                                "this r2 (outside the tags page, or not word-aligned)")
        return ("impossible", f"the payload does not read memory at r2 = {hx(r2)}, so "
                              f"this row can only be the sentinel {hx(sentinel)}: "
                              "row 3 or row 7 was misread")
    if at_r2 in ATAG_CORE_SIZES:
        return ("atag_core", f"an ATAG_CORE header: the size word ({at_r2}) that "
                             "begins an ATAGS list, so r2 points at ATAGS")
    if at_r2 == DTB_MAGIC_AS_LE_WORD:
        return ("dtb", "the device-tree magic (bytes d0 0d fe ed), so r2 points at "
                       "a DTB")
    if at_r2 == sentinel:
        return ("other", "the word read from memory at r2 (the payload does read "
                         "this r2, so it is not the sentinel); neither ATAGS nor a DTB")
    if at_r2 == ATAG_CORE_TAG:
        return ("other", "the ATAG_CORE tag number, which is normally the second "
                         "word of the list, not the first: not a recognised start")
    return ("other", "neither an ATAG_CORE header (size word 5 or 2) nor the "
                     "device-tree magic")


def classify_mdp4(mdp: int) -> tuple:
    """(kind, text) for the MDP4 row, by the oracle's third-buffer rule. kind is
    "candidate", "third" (the payload painted a grey buffer there) or
    "rejected" (with the rule's reason)."""
    if mdp == oracle.FB_RED:
        return ("candidate", "a candidate address, the buffer filled FF 00 00 (red "
                             "or blue on screen); no third buffer is painted")
    if mdp == oracle.FB_GREEN:
        return ("candidate", "a candidate address, the buffer filled green; no third "
                             "buffer is painted")
    reason = oracle.fb_rejection(mdp)
    if reason is None:
        return ("third", "a plausible framebuffer: the payload also painted a third, "
                         "grey buffer there, with all nine rows")
    return ("rejected", f"rejected, no third buffer is painted: {reason}")


# --- the record ----------------------------------------------------------------

def cells(word: int) -> str:
    """A row as it looks on screen: 32 cells, most significant bit first, in
    groups of four. '#' is a white cell (1), '.' a black one (0)."""
    bits = "".join("#" if word >> (31 - b) & 1 else "." for b in range(32))
    return " ".join(bits[i:i + 4] for i in range(0, 32, 4))


class Record(NamedTuple):
    text: str
    misread: bool      # the checksum row is not the value the payload paints
    impossible: list   # inputs that contradict each other
    attention: list    # decoded fields that differ from the expected handoff

    @property
    def status(self) -> int:
        return 1 if self.misread or self.impossible else 0


def build_record(fill: str, words: list) -> Record:
    """Decode eight or nine typed rows and the fill colour into the record."""
    assert fill in FILLS, fill
    assert len(words) in (oracle.WORDS - 1, oracle.WORDS), len(words)
    r0, r1, r2, cpsr_w, sctlr_w, entry, at_r2, csum = words[:8]
    mdp = words[8] if len(words) == oracle.WORDS else None
    out, attention, impossible = [], [], []

    def line(label: str, value: str, verdict: str, note: str = "") -> None:
        text = f"  {label:<26}{value:<12}"
        text += verdict + (": " if verdict and note else "") + note
        out.append(text.rstrip())

    # The checksum row comes first: if it is wrong, nothing below can be trusted.
    want = oracle.checksum()
    misread = csum != want
    if misread:
        out.append(f"ROWS MISREAD: row 8 (checksum) is {hx(csum)}, and the payload can "
                   f"only paint {hx(want)} there.")
        out.append("At least that row was typed wrongly. Read the photograph again; do "
                   "not use the decode below until row 8 matches.")
    else:
        out.append(f"Checksum row OK: row 8 is {hx(want)}, the value the Rust code "
                   "computes. This checks row 8 only.")
    out.append("")
    out.append("Phase 2 row record, decoded on the host from rows typed by hand.")
    out.append(f"Input: fill colour {fill}; {len(words)} rows.")

    out.append("")
    out.append("Rows as typed (# = white = 1, . = black = 0, most significant bit "
               "on the left):")
    for i, name in enumerate(ROW_NAMES):
        shown = f"{hx(words[i])}  {cells(words[i])}" if i < len(words) else "not painted"
        out.append(f"  row {i + 1}  {name:<9} {shown}")

    out.append("")
    out.append("Handoff registers:")
    if r0 == 0:
        line("r0", hx(r0), AS_EXPECTED, "0")
    else:
        line("r0", hx(r0), NOT_EXPECTED, "the ARM boot convention wants 0")
        attention.append(f"r0 is {hx(r0)}, not 0")
    if r1 == oracle.MACH_SERRANO:
        line("r1", hx(r1), AS_EXPECTED, f"machine number {oracle.MACH_SERRANO}")
    else:
        line("r1", hx(r1), NOT_EXPECTED,
             f"{r1}, not machine number {oracle.MACH_SERRANO} ({hx(oracle.MACH_SERRANO)})")
        attention.append(f"r1 is {hx(r1)}, not {oracle.MACH_SERRANO}")
    page = f"[{hx(oracle.R2_READ_LO)}, {hx(oracle.R2_READ_HI)})"
    if oracle.r2_is_read(r2):
        same = "it is" if r2 == oracle.TAGS_ADDR else "it is not"
        line("r2", hx(r2), AS_EXPECTED, f"inside the tags page {page}, word-aligned; "
             f"{same} the header's tags address {hx(oracle.TAGS_ADDR)}")
    else:
        inside = oracle.R2_READ_LO <= r2 < oracle.R2_READ_HI
        why = "inside the tags page but not word-aligned" if inside else \
            f"outside the tags page {page}"
        line("r2", hx(r2), NOT_EXPECTED, why)
        attention.append(f"r2 is {hx(r2)}, {why}")

    cpsr = decode_cpsr(cpsr_w)
    out.append("")
    out.append(f"CPSR {hx(cpsr_w)} (as the bootloader left it, before the payload "
               "masks interrupts):")
    mode_text = f"{cpsr.mode_name or 'undefined'} (0x{cpsr.mode:02X})"
    if cpsr.mode == MODE_SVC:
        line("mode", mode_text, AS_EXPECTED)
    else:
        line("mode", mode_text, NOT_EXPECTED, "section 2 expects SVC (0x13)")
        attention.append(f"CPU mode is {mode_text}, not SVC")
    if cpsr.irq_masked:
        line("IRQ (I)", "masked", AS_EXPECTED)
    else:
        line("IRQ (I)", "not masked", NOT_EXPECTED, "section 2 expects IRQ masked")
        attention.append("IRQ was not masked at entry")
    line("FIQ (F)", "masked" if cpsr.fiq_masked else "not masked", "",
         "section 2 expects it probably not masked; the payload masks it itself")
    line("abort (A)", "masked" if cpsr.abort_masked else "not masked", "",
         "no expectation recorded")
    if cpsr.thumb:
        line("Thumb (T)", "1", NOT_EXPECTED, "the entry code is ARM, so a set T bit "
             "cannot have been captured: check row 4")
        attention.append("CPSR shows Thumb state")
    else:
        line("Thumb (T)", "0, ARM", AS_EXPECTED)
    if cpsr.big_endian:
        line("endianness (E)", "1, big", NOT_EXPECTED, "little-endian data is expected")
        attention.append("CPSR shows big-endian data")
    else:
        line("endianness (E)", "0, little", AS_EXPECTED)

    sctlr = decode_sctlr(sctlr_w)
    out.append("")
    out.append(f"SCTLR {hx(sctlr_w)}:")
    for label, on, what in (("MMU (M, bit 0)", sctlr.mmu, "the MMU"),
                            ("data cache (C, bit 2)", sctlr.dcache, "the data cache"),
                            ("instr. cache (I, bit 12)", sctlr.icache,
                             "the instruction cache")):
        if on:
            line(label, "ON", NOT_EXPECTED, f"section 2 expects {what} off")
            attention.append(f"{what} was on at entry")
        else:
            line(label, "off", AS_EXPECTED)
    line("alignment (A, bit 1)", "ON" if sctlr.align else "off", "",
         "no expectation recorded")
    if sctlr.high_vectors:
        line("high vectors (V, bit 13)", "ON", "", "VBAR is ignored, so the halt-only "
             "vectors were inert: a fault would have run whatever the bootloader "
             "left at 0xFFFF0000")
        attention.append("SCTLR.V was set: the halt-only vectors were inert")
    else:
        line("high vectors (V, bit 13)", "off", "", "VBAR was in effect, so the "
             "halt-only vectors were active once the payload had set it")

    out.append("")
    kind, delta = classify_entry(entry)
    if kind == "link":
        out.append(f"Entry address {hx(entry)}: {AS_EXPECTED}, the link address; the "
                   "image was not relocated.")
    else:
        where = "above" if delta > 0 else "below"
        out.append(f"Entry address {hx(entry)}: {NOT_EXPECTED}, relocated: loaded "
                   f"{hx(abs(delta))} {where} the link address {hx(oracle.ENTRY_ADDR)}.")
        attention.append(f"the image ran at {hx(entry)}, not {hx(oracle.ENTRY_ADDR)}")

    kind, text = classify_at_r2(r2, at_r2)
    out.append(f"*r2 {hx(at_r2)}: {text}.")
    if kind == "impossible":
        impossible.append(f"*r2 is {hx(at_r2)} although r2 = {hx(r2)} is never read")

    mdp_kind = None
    if mdp is None:
        out.append("MDP4 word: row 9 is missing.")
    else:
        mdp_kind, text = classify_mdp4(mdp)
        out.append(f"MDP4 word {hx(mdp)}: {text}.")

    look = FILLS[fill]
    if look.buffer is not None:
        out.append(f"Fill colour {fill}: the buffer at {hx(look.buffer)} is on screen; "
                   f"{look.order}.")
        if mdp is None:
            out.append("  Row 9 is missing, so the display register does not say "
                       "which buffer it names.")
        elif mdp == look.buffer:
            out.append("  The MDP4 word names the same buffer.")
        else:
            out.append(f"  The MDP4 word names {hx(mdp)}, not the buffer on screen: "
                       "record the disagreement.")
            attention.append(f"the screen shows the buffer at {hx(look.buffer)}, but "
                             f"the MDP4 word is {hx(mdp)}")
    elif mdp_kind == "third":
        out.append(f"Fill colour grey: the buffer at the MDP4 address {hx(mdp)} is on "
                   f"screen; {look.order}.")
    else:
        why = ("row 9 is missing, and grey is painted only after row 9's value is "
               "known" if mdp is None else
               f"the MDP4 word {hx(mdp)} is not an address the payload paints grey")
        out.append(f"Fill colour grey: not a picture the payload paints: {why}. Check "
                   "the colour and row 9.")
        impossible.append(f"a grey screen, but {why}")

    if mdp is None:
        out.append("Rows: 8 of 9. The display-register read hung or faulted: rows 1-8 "
                   "are drawn before that read, and row 9 only after it returns.")
        attention.append("row 9 is missing: the display-register read hung or faulted")
    else:
        out.append("Rows: 9 of 9. The display-register read returned.")

    out.append("")
    if misread:
        out.append("Result: ROWS MISREAD (row 8). Read the photograph again.")
    if impossible:
        out.append("Cannot be right as typed:")
        out.extend(f"  - {item}" for item in impossible)
    if attention:
        out.append(f"Differs from the expected handoff ({len(attention)}):")
        out.extend(f"  - {item}" for item in attention)
    elif not misread and not impossible:
        out.append("Result: everything decoded matches the expected handoff.")
    return Record("\n".join(out) + "\n", misread, impossible, attention)


# --- the expected screen, as a PNG ---------------------------------------------

def screen_rgb(fill: str, words: list) -> bytes:
    """The 540x960 screen as seen (R, G, B per pixel) for this colour and these
    rows, painted by the oracle. The cells are black and white, which look the
    same in either byte order; only the fill is given as it is seen."""
    return oracle.generate_fb_rows(FILLS[fill].seen_px, words)


def encode_png(rgb: bytes, width: int, height: int) -> bytes:
    """An 8-bit RGB PNG, no interlace, every scan line with filter type 0."""
    assert len(rgb) == width * height * 3

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    stride = width * 3
    lines = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(lines, 9))
            + chunk(b"IEND", b""))


def default_png_path(fill: str, rows: int) -> str:
    return os.path.join(REPO, "build", "boot-serrano",
                        f"expected-screen-{fill}-{rows}rows.png")


def png_path_problem(path: str) -> str | None:
    """The PNG must never be committed: inside the repository it may only go
    under build/, which git ignores."""
    real = os.path.realpath(path)
    repo = os.path.realpath(REPO)
    build = os.path.join(repo, "build")
    if os.path.commonpath([real, repo]) == repo and \
            os.path.commonpath([real, build]) != build:
        return (f"{path} is inside the repository but not under build/; the PNG is "
                "never committed")
    return None


def write_png(path: str, fill: str, words: list) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(encode_png(screen_rgb(fill, words), oracle.WIDTH, oracle.HEIGHT))


# --- command line --------------------------------------------------------------

def parse_word(text: str) -> int:
    """One row as typed: exactly eight hex digits, with or without 0x. A row is
    32 cells, so a shorter word is a dropped digit, not a small number."""
    digits = text[2:] if text[:2] in ("0x", "0X") else text
    if len(digits) != 8 or any(c not in "0123456789abcdefABCDEF" for c in digits):
        raise ValueError(f"'{text}' is not eight hex digits (a row is 32 cells)")
    return int(digits, 16)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="read_rows.py", description=__doc__.splitlines()[0])
    parser.add_argument("--fill", required=True, choices=sorted(FILLS),
                        help="the fill colour seen on the screen")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--png", metavar="PATH",
                       help="where to write the screen for this colour and these "
                            "rows (default: build/boot-serrano/ in the repository)")
    group.add_argument("--no-png", action="store_true", help="write no PNG")
    parser.add_argument("words", nargs="+", metavar="WORD",
                        help="the rows, top first, as eight hex digits each: nine, "
                             "or eight if the ninth row is missing")
    args = parser.parse_args(argv)

    if len(args.words) not in (oracle.WORDS - 1, oracle.WORDS):
        parser.error(f"need 8 or 9 rows, got {len(args.words)}. A screen with fewer "
                     "than eight rows is not decoded here: record it as seen.")
    try:
        words = [parse_word(w) for w in args.words]
    except ValueError as exc:
        parser.error(str(exc))
    png = None if args.no_png else args.png or default_png_path(args.fill, len(words))
    if png is not None and png_path_problem(png):
        parser.error(png_path_problem(png))

    record = build_record(args.fill, words)
    sys.stdout.write(record.text)
    if png is not None:
        write_png(png, args.fill, words)
        print(f"\nThe screen for this colour and these rows: {png}")
    return record.status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
