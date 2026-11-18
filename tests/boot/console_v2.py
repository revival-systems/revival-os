"""console_v2.py - host oracle for the GT-I9195 Phase 2 console image.

Works out, on the host and without the image, the exact bytes the console
image (boot/samsung-serranolte/console/) must leave in the framebuffer for a
given handoff, tag page, display-register value and counter value. The QEMU
test (tests/boot/run_console.py) compares real framebuffer dumps against
expected_fb(...) byte for byte.

It is written from the description in docs/phase-2/console-payload.md, not
from the Rust: the tag list is parsed whole and then formatted, the command
line is split in one pass, and the glyphs are read from font.txt, not from
the generated font.rs. Where the two disagree, one of them is wrong.

It also reads a framebuffer back into text (decode), which is how the tests
find the counter value and how they check that no hidden value is on screen,
and it can write the expected screen as a PNG picture:

  python3 -m tests.boot.console_v2 --png build/console-sample.png

Nothing here touches a device or a network.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from typing import NamedTuple

# --- panel and grid (docs/phase-2/console-payload.md; board.rs, console.rs) --
WIDTH = 540
HEIGHT = 960
BPP = 3
STRIDE = 1620
FB_BYTES = STRIDE * HEIGHT  # 1_555_200
FB_BASE = 0x8810_0000

GLYPH_COLS = 5
GLYPH_ROWS = 7
SCALE = 3
CELL_W = (GLYPH_COLS + 1) * SCALE  # 18
CELL_H = (GLYPH_ROWS + 1) * SCALE  # 24
COLUMNS = WIDTH // CELL_W  # 30
LINES = HEIGHT // CELL_H   # 40

REPORT_LINES = LINES - 2
MDP_LINE = LINES - 2
TICK_LINE = LINES - 1

INK = 0xFF
PAPER = 0x00

# --- what the image reads ----------------------------------------------------
TAGS_PAGE_LO = 0x8020_0000
TAGS_PAGE_HI = 0x8020_8000
TAGS_PAGE_BYTES = TAGS_PAGE_HI - TAGS_PAGE_LO
MDP_DMA_P_BUF_ADDR = 0x0519_0008
LINK_ENTRY = 0x8020_8000

ATAG_CORE = 0x5441_0001
ATAG_MEM = 0x5441_0002
ATAG_INITRD2 = 0x5442_0005
ATAG_SERIAL = 0x5441_0006
ATAG_REVISION = 0x5441_0007
ATAG_CMDLINE = 0x5441_0009
DEVICE_TREE_MAGIC = 0xEDFE_0DD0  # 0xD00DFEED stored most significant byte first
MAX_TAGS = 64
MAX_TAG_WORDS = 2048

SELFTEST_SUM = 0x22BE_CBA4
MOVED_STRIPES = 20

# What the stock bootloader handed the first image on 2026-11-18 (Measured;
# docs/evidence/phase-2/2026-11-18-v5-session.md). r3 was not measured.
PHONE_R1 = 0x0000_0E8F
PHONE_R2 = 0x8020_0100
PHONE_CPSR = 0x6000_0193
PHONE_SCTLR = 0x00C5_487A

FONT_ART = Path(__file__).resolve().parents[2] / "boot/samsung-serranolte/console/font.txt"

MODE_NAMES = {
    0x10: "USR", 0x11: "FIQ", 0x12: "IRQ", 0x13: "SVC", 0x16: "MON",
    0x17: "ABT", 0x1A: "HYP", 0x1B: "UND", 0x1F: "SYS",
}


class Handoff(NamedTuple):
    """The seven words kstart.S captures at entry."""
    r0: int = 0
    r1: int = 0
    r2: int = 0
    r3: int = 0
    cpsr: int = 0
    sctlr: int = 0
    entry: int = LINK_ENTRY


# --- the font ----------------------------------------------------------------

def load_font(path: Path = FONT_ART) -> dict[int, tuple[str, ...]]:
    """The glyph art, as {character code: seven rows of '#' and '.'}. A reader
    of its own, separate from tools/gen_console_font.py."""
    glyphs: dict[int, list[str]] = {}
    current: list[str] | None = None
    for raw in path.read_text(encoding="ascii").splitlines():
        line = raw.strip()
        if not line or line[0] == ";":
            continue
        if line[0] == "@":
            current = glyphs.setdefault(int(line[1:], 16), [])
        elif current is not None:
            current.append(line)
    for code, rows in glyphs.items():
        if len(rows) != GLYPH_ROWS or any(len(r) != GLYPH_COLS for r in rows):
            raise ValueError(f"glyph {code:#04x} is not {GLYPH_COLS}x{GLYPH_ROWS}")
    if sorted(glyphs) != list(range(0x20, 0x7F)):
        raise ValueError("font.txt does not define exactly 0x20 to 0x7E")
    return {code: tuple(rows) for code, rows in glyphs.items()}


def _cell_rows(art: tuple[str, ...]) -> tuple[bytes, ...]:
    """One character cell as CELL_H rows of CELL_W * BPP framebuffer bytes."""
    out = []
    for row in art:
        pixels = b"".join((bytes([INK]) if cell == "#" else bytes([PAPER])) * (SCALE * BPP)
                          for cell in row)
        pixels += bytes([PAPER]) * (SCALE * BPP)  # the spacing column
        out.extend([pixels] * SCALE)
    out.extend([bytes([PAPER]) * (CELL_W * BPP)] * SCALE)  # the spacing row
    assert len(out) == CELL_H and all(len(r) == CELL_W * BPP for r in out)
    return tuple(out)


_CELLS: dict[str, tuple[bytes, ...]] = {}


def cells() -> dict[str, tuple[bytes, ...]]:
    """{character: its cell's rows of framebuffer bytes}, built once."""
    if not _CELLS:
        for code, art in load_font().items():
            _CELLS[chr(code)] = _cell_rows(art)
    return _CELLS


# --- the console, as text ----------------------------------------------------

class Window:
    """A console window as rows of text: what console.rs draws, without the
    pixels. Rows that the text never reaches are empty (the image clears
    them); a character dropped from a full window sets `overflow`."""

    def __init__(self, lines: int):
        self.lines = lines
        self.rows = [""] * lines
        self.line = 0
        self.col = 0
        self.overflow = False

    def put(self, code: int) -> None:
        if code == 0x0A:
            self.newline()
            return
        if self.col >= COLUMNS:
            self.newline()
        if self.line >= self.lines:
            self.overflow = True
            return
        self.rows[self.line] += chr(code) if 0x20 <= code <= 0x7E else "?"
        self.col += 1

    def puts(self, text: str | bytes) -> None:
        for code in (text.encode("latin-1") if isinstance(text, str) else text):
            self.put(code)

    def newline(self) -> None:
        if self.line < self.lines:
            self.line += 1
            self.col = 0

    def text(self) -> list[str]:
        """The window's rows, each exactly COLUMNS characters, with the `+`
        in the last cell if anything was dropped."""
        rows = [row.ljust(COLUMNS) for row in self.rows]
        if self.overflow and rows:
            rows[-1] = rows[-1][:COLUMNS - 1] + "+"
        return rows


# --- the tag list ------------------------------------------------------------

def _words(page: bytes, address: int) -> list[int]:
    """The words of the tag page from `address` to its end."""
    offset = address - TAGS_PAGE_LO
    count = (TAGS_PAGE_BYTES - offset) // 4
    return list(struct.unpack_from(f"<{count}I", page, offset))


def parse_tags(words: list[int]) -> tuple[list[tuple[int, list[int]]], tuple]:
    """Read a tag list from `words`. Returns (tags, how_it_ended): tags is a
    list of (kind, body words); how_it_ended is ("end", kind word),
    ("bad-size", size), ("past-end",) or ("too-many",)."""
    tags: list[tuple[int, list[int]]] = []
    at = 0
    while True:
        if at + 2 > len(words):
            return tags, ("past-end",)
        size, kind = words[at], words[at + 1]
        if size == 0:
            return tags, ("end", kind)
        if size == 1 or size > MAX_TAG_WORDS:
            return tags, ("bad-size", size)
        if len(tags) == MAX_TAGS:
            return tags, ("too-many",)
        if at + size > len(words):
            return tags, ("past-end",)
        tags.append((kind, words[at + 2:at + size]))
        at += size


def split_cmdline(body: list[int]) -> list[tuple[bytes, int | None, int]]:
    """Split a command-line tag's text into words, as the Linux kernel's
    next_arg does: white space separates words except inside double quotes,
    and a word's name ends at its first '='. Returns, for each word,
    (name bytes, value length, word length); for a word with no '=' the name
    is empty and the value length is None. Values, and words with no '=', are
    dropped here and go no further: only their lengths leave this function."""
    text = struct.pack(f"<{len(body)}I", *body)
    text = text.split(b"\0", 1)[0]
    words: list[bytes] = []
    current = bytearray()
    quoted = False
    for byte in text:
        if byte in b" \t\n\v\f\r" and not quoted:
            if current:
                words.append(bytes(current))
                current.clear()
            continue
        if byte == ord('"'):
            quoted = not quoted
        current.append(byte)
    if current:
        words.append(bytes(current))
    out = []
    for word in words:
        name, equals, value = word.partition(b"=")
        out.append((name, len(value), len(word)) if equals else (b"", None, len(word)))
    return out


def _report_cmdline(win: Window, body: list[int]) -> None:
    win.puts(" CMDLINE")
    for name, value_length, word_length in split_cmdline(body):
        if value_length is None:
            shown = f"<{word_length}>".encode()
        else:
            shown = name + f"=<{value_length}>".encode()
        win.puts("\n  " if win.col + 1 + len(shown) > COLUMNS else " ")
        win.puts(shown)
    win.newline()
    if b"\0" not in struct.pack(f"<{len(body)}I", *body):
        # Malformed: the text has no terminating zero; it was cut at the tag's end.
        win.puts(" CMDLINE UNTERMINATED\n")


def _report_tag(win: Window, kind: int, body: list[int]) -> None:
    if kind == ATAG_CORE:
        win.puts(" CORE")
        if len(body) >= 2:
            win.puts(f" PAGE {body[1]:08X}")
        win.newline()
    elif kind == ATAG_MEM:
        win.puts(f" MEM {body[0]:08X} AT {body[1]:08X}\n" if len(body) >= 2 else " MEM SHORT\n")
    elif kind == ATAG_INITRD2:
        win.puts(f" INITRD2 {body[0]:08X} SZ {body[1]:08X}\n" if len(body) >= 2
                 else " INITRD2 SHORT\n")
    elif kind == ATAG_REVISION:
        win.puts(f" REVISION {body[0]:08X}\n" if body else " REVISION\n")
    elif kind == ATAG_SERIAL:
        win.puts(" SERIAL HIDDEN\n")
    elif kind == ATAG_CMDLINE:
        _report_cmdline(win, body)
    else:
        win.puts(f" TAG {kind:08X} W{len(body)}\n")


def _report_tags(win: Window, r2: int, page: bytes) -> None:
    win.puts(f"ATAGS {r2:08X}")
    if not TAGS_PAGE_LO <= r2 < TAGS_PAGE_HI:
        win.puts(" OUT OF PAGE\n")
        return
    if r2 % 4:
        win.puts(" UNALIGNED\n")
        return
    words = _words(page, r2)
    if words[0] == DEVICE_TREE_MAGIC:
        win.puts(" DEVICE TREE\n")
        return
    win.newline()
    tags, ended = parse_tags(words)
    for kind, body in tags:
        _report_tag(win, kind, body)
    if ended[0] == "end":
        # A size of 0 ends the list whatever the kind word is, but a kind
        # other than 0 is a malformed end, shown as a STOP like the others.
        win.puts(f" END {len(tags)} TAGS\n" if ended[1] == 0
                 else f" STOP END KIND {ended[1]:08X}\n")
    elif ended[0] == "bad-size":
        win.puts(f" STOP SIZE {ended[1]:08X}\n")
    elif ended[0] == "past-end":
        win.puts(" STOP PAST PAGE END\n")
    else:
        win.puts(f" STOP AT {MAX_TAGS} TAGS\n")


# --- the whole screen --------------------------------------------------------

def _bit(word: int, bit: int) -> int:
    return (word >> bit) & 1


def report_text(handoff: Handoff, page: bytes | None = None) -> list[str]:
    """The REPORT_LINES lines of the report for this handoff and tag page
    (None: a page of zeros, which is what QEMU's memory holds)."""
    if page is None:
        page = bytes(TAGS_PAGE_BYTES)
    if len(page) != TAGS_PAGE_BYTES:
        raise ValueError("the tag page must be exactly 0x8000 bytes")
    h = handoff
    win = Window(REPORT_LINES)
    win.puts("REVIVAL OS\n")
    win.puts("PHASE 2 IMAGE 2\n")
    win.puts(f"SELFTEST {SELFTEST_SUM:08X} OK\n")
    win.puts(f"R0 {h.r0:08X} R1 {h.r1:08X}\n")
    win.puts(f"R2 {h.r2:08X} R3 {h.r3:08X}\n")
    win.puts(f"MACH {h.r1}\n")
    win.puts(f"CPSR {h.cpsr:08X} {MODE_NAMES.get(h.cpsr & 0x1F, '???')}"
             f" I{_bit(h.cpsr, 7)} F{_bit(h.cpsr, 6)} A{_bit(h.cpsr, 8)} T{_bit(h.cpsr, 5)}\n")
    win.puts(f"SCTLR {h.sctlr:08X} M{_bit(h.sctlr, 0)} C{_bit(h.sctlr, 2)}"
             f" I{_bit(h.sctlr, 12)} A{_bit(h.sctlr, 1)} V{_bit(h.sctlr, 13)}\n")
    win.puts(f"ENTRY {h.entry:08X} OK\n")
    _report_tags(win, h.r2, page)
    return win.text()


def screen_text(handoff: Handoff, page: bytes | None = None, mdp: int | None = 0,
                tick: int | None = 0) -> list[str]:
    """All LINES lines of the screen. `mdp` is the value the display register
    reads; None gives the screen as it stands while that read has not come
    back. `tick` is the counter value shown; None leaves its line empty (the
    counter starts only after the register read)."""
    if handoff.entry != LINK_ENTRY:
        raise ValueError("an image entered at another address draws stripes: moved_fb()")
    if mdp is None:
        mdp_line, tick_line = "MDP4 READ PENDING", ""
    else:
        mdp_line = f"MDP4 {mdp:08X} " + ("IS FB" if mdp == FB_BASE else "NOT FB")
        tick_line = "" if tick is None else f"TICK {tick & 0xFFFF_FFFF:08X}"
    return report_text(handoff, page) + [mdp_line.ljust(COLUMNS), tick_line.ljust(COLUMNS)]


def render(lines: list[str]) -> bytes:
    """The framebuffer for LINES lines of COLUMNS characters."""
    if len(lines) != LINES or any(len(line) != COLUMNS for line in lines):
        raise ValueError(f"render needs {LINES} lines of {COLUMNS} characters")
    cell = cells()
    out = bytearray()
    for line in lines:
        glyphs = [cell[ch] for ch in line]
        for row in range(CELL_H):
            out += b"".join(glyph[row] for glyph in glyphs)
    assert len(out) == FB_BYTES
    return bytes(out)


def expected_fb(handoff: Handoff, page: bytes | None = None, mdp: int | None = 0,
                tick: int | None = 0) -> bytes:
    """The framebuffer the image must leave: see screen_text."""
    return render(screen_text(handoff, page, mdp, tick))


def moved_fb() -> bytes:
    """The framebuffer of an image that was entered at another address than
    it is linked for: MOVED_STRIPES stripes, white first."""
    height = HEIGHT // MOVED_STRIPES
    out = bytearray()
    for stripe in range(MOVED_STRIPES):
        out += bytes([INK if stripe % 2 == 0 else PAPER]) * (STRIDE * height)
    assert len(out) == FB_BYTES
    return bytes(out)


def decode(fb: bytes) -> list[str]:
    """Read a framebuffer back into LINES lines of COLUMNS characters. A cell
    that is not exactly one glyph reads as U+FFFD."""
    if len(fb) != FB_BYTES:
        raise ValueError(f"a framebuffer is {FB_BYTES} bytes, not {len(fb)}")
    by_pixels = {b"".join(rows): ch for ch, rows in cells().items()}
    lines = []
    width = CELL_W * BPP
    for line in range(LINES):
        text = []
        for col in range(COLUMNS):
            block = b"".join(
                fb[(line * CELL_H + row) * STRIDE + col * width:][:width]
                for row in range(CELL_H))
            text.append(by_pixels.get(block, "�"))
        lines.append("".join(text))
    return lines


def tick_of(fb: bytes) -> int | None:
    """The counter value on the screen's last line, or None if that line is
    not a complete "TICK xxxxxxxx"."""
    line = decode(fb)[TICK_LINE]
    digits = line[5:13]
    if (line[:5] != "TICK " or line[13:].strip()
            or any(d not in "0123456789ABCDEF" for d in digits)):
        return None
    return int(digits, 16)


# --- building tag pages for tests and samples --------------------------------

def tag(kind: int, *body: int) -> bytes:
    """One tag: its size and kind words, then `body`."""
    return struct.pack(f"<{2 + len(body)}I", 2 + len(body), kind, *body)


def cmdline_tag(text: bytes) -> bytes:
    """A command-line tag holding `text` and its terminating zero, padded with
    zeros to whole words."""
    padded = text + b"\0"
    padded += b"\0" * (-len(padded) % 4)
    return struct.pack("<2I", 2 + len(padded) // 4, ATAG_CMDLINE) + padded


def end_tag() -> bytes:
    return struct.pack("<2I", 0, 0)


def page_with(data: bytes, address: int = PHONE_R2) -> bytes:
    """A tag page of zeros with `data` stored at `address`."""
    offset = address - TAGS_PAGE_LO
    if offset < 0 or offset + len(data) > TAGS_PAGE_BYTES:
        raise ValueError("data does not fit in the tag page")
    page = bytearray(TAGS_PAGE_BYTES)
    page[offset:offset + len(data)] = data
    return bytes(page)


# A made-up tag list in the shape a Qualcomm bootloader of this age passes. It
# is NOT what the phone passes (that is what the image is for). Every value in
# it that the image must hide is the word SECRET or built from it.
SAMPLE_SECRETS = (b"SECRET", b"5EC2E7")
SAMPLE_CMDLINE = (
    b"console=null androidboot.hardware=qcom user_debug=31 msm_rtb.filter=0x3F "
    b"ehci-hcd.park=3 androidboot.bootloader=SECRETSECRET "
    b"androidboot.serialno=SECRET5EC2E7 loglevel=4 quiet "
    b'label="SECRET with spaces" SECRET5EC2E7'
)


def sample_tags() -> bytes:
    return b"".join((
        tag(ATAG_CORE),
        tag(ATAG_MEM, 0x0800_0000, 0x8020_0000),
        tag(ATAG_MEM, 0x1000_0000, 0x9000_0000),
        tag(ATAG_INITRD2, 0x8220_0000, 0x0000_0000),
        tag(ATAG_REVISION, 0x0000_000B),
        tag(ATAG_SERIAL, 0x5EC2_E700, 0x5EC2_E701),
        tag(0x4D53_4D70, *([0x5EC2_E7AA] * 12)),
        cmdline_tag(SAMPLE_CMDLINE),
        end_tag(),
    ))


def phone_handoff(r3: int = 0) -> Handoff:
    """The handoff measured on the phone; r3 was not measured."""
    return Handoff(0, PHONE_R1, PHONE_R2, r3, PHONE_CPSR, PHONE_SCTLR, LINK_ENTRY)


# --- PNG ---------------------------------------------------------------------

def png_bytes(fb: bytes) -> bytes:
    """The framebuffer as a PNG file (8-bit RGB). The image draws only greys,
    so the phone's blue-green-red byte order makes no difference here."""
    if len(fb) != FB_BYTES:
        raise ValueError(f"a framebuffer is {FB_BYTES} bytes, not {len(fb)}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFF_FFFF))

    raw = b"".join(b"\0" + fb[y * STRIDE:(y + 1) * STRIDE] for y in range(HEIGHT))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">2I5B", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--png", metavar="FILE",
                        help="write the sample screen (the phone's measured registers "
                             "with a made-up tag list) as a PNG picture")
    parser.add_argument("--tick", type=lambda s: int(s, 0), default=0)
    args = parser.parse_args(argv)
    lines = screen_text(phone_handoff(), page_with(sample_tags()), FB_BASE, args.tick)
    for number, line in enumerate(lines):
        print(f"{number:2} |{line}|")
    if args.png:
        Path(args.png).write_bytes(png_bytes(render(lines)))
        print(f"wrote {args.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
