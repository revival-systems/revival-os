"""run_screen.py - boot the Phase 2 boot screen image in QEMU and verify its screen.

Runs the EXACT kernel-slot bytes of the boot screen image (the flat screen.bin)
on `qemu-system-arm -M virt -cpu cortex-a15`, loaded at 0x80208000 as the stock
bootloader loads it, and compares what it leaves in the framebuffer at
0x88100000 with the host oracle (tests/boot/screen_v3.py) byte for byte: every
pixel of the 540 x 960 panel, in every case.

It is the console image's harness (tests/boot/run_console.py) with another
oracle: the same QEMU machine, the same test-only entry shim, the same way of
pausing the CPU inside the image's wait between two counter steps (here
`screen_tick_wait`), the same noise in the framebuffer before the CPU starts
(the byte 0x55, so that a dump equal to the oracle shows the image wrote every
byte of the panel), and the same checks that the tag page and the memory on
both sides of the framebuffer were not written.

Cases (PASS/FAIL line each):

  screen-vector-header      The image's first 0x30 bytes are kstart.S's layout.
  qemu-screen               No handoff (r0-r3 = 0), the display register reads
                            0: the screen is byte-exact; the counter and its
                            bar are then watched, byte-exact at every look,
                            until the counter has passed 0x10 (so a carry into
                            the next digit and a wrap of the bar have been
                            drawn); and the whole screen is byte-exact again
                            at the end.
  qemu-screen-device-handoff
                            Entered the way the phone enters it (r1 = 3727,
                            r2 = 0x80200100) with a sample tag list there and
                            the display register reading 0x88100000: byte-exact;
                            and byte-identical to the oracle's screen for a tag
                            list in which every hidden value was replaced, so
                            nothing of those values is on the screen.
  qemu-screen-phone-list    The registers and the tag list the phone gave on
                            2026-11-19, as far as they were recorded (the
                            values of the command-line words are made up, only
                            their names and lengths are real): byte-exact.
  qemu-screen-alignment-control
                            Shows that this QEMU faults an unaligned word load
                            in the state the phone hands over (SCTLR.A set, MMU
                            off), and that the same load from an aligned
                            address does not. Without this the next cases would
                            prove nothing about alignment.
  qemu-screen-alignment-checked
                            The device handoff again with SCTLR.A set, as on
                            the phone: byte-exact, no fault.
  qemu-screen-tag-lists     Malformed and edge-case tag lists, one run each,
                            alignment checking on: byte-exact, no fault.
  qemu-screen-noise         Tag pages of pseudo-random bytes: byte-exact, no
                            fault.
  qemu-screen-moved         The image loaded and started at another address:
                            stripes, then a halt in SVC mode.
  qemu-screen-fault-halts   Memory that ends inside the framebuffer: the write
                            past its end faults, the CPU rests in halt_loop in
                            ABT mode, and everything drawn before is byte-exact.

Nothing is added to the image. No device is contacted.

Usage: run_screen.py --image BIN --workdir DIR --halt-addr A --wait-addr A
                     --wait-size N [--qemu BIN] [--timeout S]
"""

from __future__ import annotations

import argparse
import os
import random
import struct
import sys

from tests.boot import console_v2 as con
from tests.boot import run_console as rc
from tests.boot import screen_v3 as oracle
from tests.boot import serrano_v1 as v1
from tests.boot.run_payload import MODE_ABT, MODE_SVC, RELOC_ADDR, CaseFailure

NAME = "qemu-screen"
LINK_ADDR = oracle.LINK_ENTRY
FB_BASE = oracle.FB_BASE
# The plain case watches the counter until it has passed this value.
COUNT_PAST = 0x10
COUNT_LOOK_EVERY = 0.2
# The pixel rows that hold the counter's digits and its bar: what a look reads.
BAND_TOP = min(oracle.TICK_TOP, oracle.L["BAR_Y"])
BAND_END = max(oracle.TICK_TOP + oracle.TICK_ROWS, oracle.L["BAR_Y"] + oracle.L["BAR_H"])
BAND_ADDR = FB_BASE + BAND_TOP * oracle.STRIDE
BAND_BYTES = (BAND_END - BAND_TOP) * oracle.STRIDE


def first_difference(got: bytes, want: bytes) -> str:
    index = next(i for i in range(len(want)) if got[i] != want[i])
    y, rest = divmod(index, oracle.STRIDE)
    different = sum(1 for i in range(0, len(want), oracle.BPP)
                    if got[i:i + oracle.BPP] != want[i:i + oracle.BPP])
    return (f"byte {index} (pixel x={rest // oracle.BPP} y={y}) is {got[index]:#04x}, want "
            f"{want[index]:#04x}; {different} pixels differ in all")


def require_running(state: str, psr: int, sp: int) -> None:
    """The image must be counting, not halted: in screen_tick_wait, in SVC
    mode, with a word-aligned stack pointer. (The 8-byte rule of the AAPCS
    holds at calls; screen_tick_wait calls nothing and may hold one word.)"""
    if state != "wait":
        mode = psr & 0x1F
        why = "a data or prefetch abort" if mode == MODE_ABT else f"CPU mode {mode:#x}"
        raise CaseFailure(f"the image halted in kstart.S's halt_loop ({why}, "
                          f"PSR {psr:#010x}) instead of counting")
    if psr & 0x1F != MODE_SVC:
        raise CaseFailure(f"CPU mode while counting is {psr & 0x1F:#x}, want SVC")
    if sp % 4:
        raise CaseFailure(f"SP in screen_tick_wait is {sp:#x}, not word-aligned")


def require_screen(fb: bytes, handoff: con.Handoff, page: bytes | None, mdp: int) -> int:
    """The framebuffer must equal the oracle's screen for the counter value it
    shows. Returns that counter value."""
    tick = oracle.tick_of(fb)
    if tick is None:
        raise CaseFailure("the counter's eight cells are not eight digits; against the screen "
                          "with the counter at 0: "
                          + first_difference(fb, oracle.expected_fb(handoff, page, mdp, 0)))
    want = oracle.expected_fb(handoff, page, mdp, tick)
    if fb != want:
        raise CaseFailure("the framebuffer differs from the oracle: " + first_difference(fb, want))
    return tick


def band_of(fb: bytes) -> bytes:
    return fb[BAND_TOP * oracle.STRIDE:BAND_END * oracle.STRIDE]


class Runner(rc.Runner):
    """The console harness's runner, with this image's oracle."""

    def screen(self, tag: str, handoff: con.Handoff, *, page: bytes | None = None,
               mdp: int | None = None, align: bool = False, shim: bool = True) -> bytes:
        """Run once with this handoff and require a complete, byte-exact screen
        with the counter showing. Returns the framebuffer dump."""
        regs = (handoff.r0, handoff.r1, handoff.r2, handoff.r3) if shim else None
        with self.vm(tag, regs=regs, align=align, page=page, mdp=mdp) as vm:
            state, psr, sp = vm.settle(self.spans(LINK_ADDR))
            require_running(state, psr, sp)
            fb = vm.read(FB_BASE, oracle.FB_BYTES)
            require_screen(fb, handoff, page, mdp or 0)
            rc.require_untouched(vm, page)
        return fb


def case_plain(r: Runner) -> str:
    """No handoff, no display-register value; and the counter must step."""
    handoff = rc.qemu_handoff()
    with r.vm("plain") as vm:
        spans = r.spans(LINK_ADDR)
        state, psr, sp = vm.settle(spans)
        require_running(state, psr, sp)
        seen = [require_screen(vm.read(FB_BASE, oracle.FB_BYTES), handoff, None, 0)]
        # The image redraws only the digits that change, and the bar. Watch
        # both until the counter has passed COUNT_PAST: by then a carry into
        # the next digit and a wrap of the bar have been drawn. Each look reads
        # only the rows they are in, and those rows must be byte for byte the
        # oracle's rows for the value the counter shows.
        first_tick_row = (oracle.TICK_TOP - BAND_TOP) * oracle.STRIDE
        while seen[-1] <= COUNT_PAST:
            state, psr, sp = vm.settle(spans, run_for=COUNT_LOOK_EVERY)
            require_running(state, psr, sp)
            band = vm.read(BAND_ADDR, BAND_BYTES)
            now = oracle.tick_of_band(
                band[first_tick_row:first_tick_row + oracle.TICK_ROWS * oracle.STRIDE])
            if now is None:
                raise CaseFailure("while the image waits, the counter's cells are not eight "
                                  "digits")
            if now < seen[-1]:
                raise CaseFailure(f"the counter went from {seen[-1]:#x} back to {now:#x}")
            want = band_of(oracle.expected_fb(handoff, None, 0, now))
            if band != want:
                raise CaseFailure(f"with the counter at {now:#x}, its rows differ from the "
                                  f"oracle: byte {next(i for i in range(len(want)) if band[i] != want[i])} "
                                  f"of the rows from y={BAND_TOP}")
            if now != seen[-1]:
                seen.append(now)
            vm.check_time(f"the counter did not pass {COUNT_PAST:#x} in time "
                          f"(it shows {now:#x})")
        # The CPU is still paused: the whole screen, at the value just seen.
        last = require_screen(vm.read(FB_BASE, oracle.FB_BYTES), handoff, None, 0)
        if last != seen[-1]:
            raise CaseFailure(f"the counter shows {last:#x} on the whole screen and "
                              f"{seen[-1]:#x} in its rows, with the CPU paused")
        rc.require_untouched(vm, None)
    return (f"framebuffer byte-identical to the oracle with the counter at {seen[0]:#x} and "
            f"again at {seen[-1]:#x}; the counter's digits and its bar byte-exact at "
            f"{len(seen)} values on the way, past the carry at {COUNT_PAST:#x}; every byte "
            f"of the panel written; cpsr={handoff.cpsr:#x} sctlr={handoff.sctlr:#x}; "
            f"counting in SVC mode, sp={sp:#x}")


def sample_page() -> bytes:
    return con.page_with(con.sample_tags())


def other_values(data: bytes) -> bytes:
    """`data`, a sample tag list, with every value the image must hide
    replaced by another of the same length: the command-line values, the
    serial tag's words and the words of the tag of an unknown kind."""
    other = (data.replace(b"SECRET", b"public").replace(b"5EC2E7", b"A1B2C3")
             .replace(b"\xe7\xc2\x5e", b"\x11\x22\x33").replace(b"null", b"ttyS")
             .replace(b"qcom", b"abcd").replace(b"0x3F", b"0x00").replace(b"=31", b"=77")
             .replace(b"=3 ", b"=9 ").replace(b"=4 ", b"=7 "))
    if len(other) != len(data) or other == data:
        raise CaseFailure("the sample tag list's values could not be replaced")
    for secret in con.SAMPLE_SECRETS:
        if secret not in data or secret in other:
            raise CaseFailure(f"the sample's hidden value {secret!r} was not replaced")
    return other


def case_device_handoff(r: Runner) -> str:
    handoff = rc.qemu_handoff(0, con.PHONE_R1, con.PHONE_R2, 0)
    data = con.sample_tags()
    fb = r.screen("handoff", handoff, page=con.page_with(data), mdp=FB_BASE)
    tick = oracle.tick_of(fb)
    if fb != oracle.expected_fb(handoff, con.page_with(other_values(data)), FB_BASE, tick):
        raise CaseFailure("the screen changes when a hidden value changes")
    return (f"entered through the test shim with r1={handoff.r1:#x} r2={handoff.r2:#x}, a "
            f"sample tag list there and the display register reading {FB_BASE:#x}: "
            f"framebuffer byte-identical to the oracle, and to the oracle's screen for the "
            f"same list with every hidden value replaced; tag page unchanged")


def case_phone_list(r: Runner) -> str:
    handoff = rc.qemu_handoff(0, con.PHONE_R1, con.PHONE_R2, 0x1141, align=True)
    r.screen("phone", handoff, page=con.page_with(oracle.phone_tags()), mdp=FB_BASE, align=True)
    rows, shown = oracle.word_places(len(oracle.PHONE_WORDS))
    return (f"r1={handoff.r1:#x} r2={handoff.r2:#x} r3={handoff.r3:#x} and the tag list recorded "
            f"on 2026-11-19 (six memory regions, {len(oracle.PHONE_WORDS)} command-line words "
            f"with made-up values): framebuffer byte-identical to the oracle; the words take "
            f"{rows} rows and all {shown} are shown")


def case_aligned(r: Runner) -> str:
    handoff = rc.qemu_handoff(0, con.PHONE_R1, con.PHONE_R2, 0, align=True)
    page = sample_page()
    fb = r.screen("aligned", handoff, page=page, mdp=FB_BASE, align=True)
    clear = rc.qemu_handoff(0, con.PHONE_R1, con.PHONE_R2, 0)
    if fb == oracle.expected_fb(clear, page, FB_BASE, oracle.tick_of(fb)):
        raise CaseFailure("the screen does not show SCTLR.A set")
    return (f"sctlr={handoff.sctlr:#x} (alignment checking on, as on the phone) with the "
            f"sample tag list: framebuffer byte-identical to the oracle, which differs from "
            f"the screen for SCTLR.A clear; no fault")


def words_list(count: int, name: str = "w") -> bytes:
    text = " ".join(f"{name}{i}={'v' * (i % 13)}" for i in range(count)).encode()
    return con.cmdline_tag(text) + con.end_tag()


def tag_lists() -> list:
    """The console harness's edge cases, and those that only this screen has:
    more words, tags and letters than it has places for."""
    r2 = con.PHONE_R2
    extra = [
        ("words-21", words_list(21)),
        ("words-22", words_list(22)),
        ("words-25", words_list(25)),
        ("words-26", words_list(26)),
        ("words-200", words_list(200, "a_longer_name_")),
        ("head-line-full", con.cmdline_tag(b"f" * 60 + b"=1 second=2 third=3") + con.end_tag()),
        ("head-line-exact", con.cmdline_tag(b"g" * 46 + b"=1 h=22 third=3") + con.end_tag()),
        ("column-exact", con.cmdline_tag(b"a=1 b=2 " + b"c" * 28 + b"=1 " + b"d" * 26 + b"=1 "
                                         + b"e" * 29 + b"=1 " + b"f" * 27 + b"=1") + con.end_tag()),
        ("seven-memory-tags", con.tag(con.ATAG_MEM, 0x100, 0x200) * 7 + con.end_tag()),
        ("every-kind-twice",
         (con.tag(con.ATAG_CORE, 0, 0x1000, 0) + con.tag(con.ATAG_INITRD2, 0x8120_0000, 0x10)
          + con.tag(con.ATAG_REVISION, 5) + con.tag(con.ATAG_SERIAL, 0x5EC2_E700, 0x5EC2_E701)) * 2
         + con.end_tag()),
        ("two-command-lines", con.cmdline_tag(b"a=1 b=22") + con.tag(con.ATAG_MEM, 1, 2)
         + con.cmdline_tag(b"c=333 bare") + con.end_tag()),
        ("words-and-no-terminator", words_list(30)[:-8]
         + struct.pack("<2I", 4, con.ATAG_CMDLINE) + b"tail=123" + con.end_tag()),
    ]
    return rc.tag_lists() + [(tag, r2, data, r2) for tag, data in extra]


def case_tag_lists(r: Runner) -> str:
    names = []
    for tag, r2, data, at in tag_lists():
        page = con.page_with(data, at)
        handoff = rc.qemu_handoff(0, con.PHONE_R1, r2, 0, align=True)
        try:
            r.screen(f"tags-{tag}", handoff, page=page, align=True)
        except CaseFailure as exc:
            raise CaseFailure(f"{tag} (r2={r2:#x}): {exc}") from exc
        names.append(tag)
    return (f"{len(names)} tag lists, one run each with alignment checking on, each "
            f"byte-identical to the oracle with no fault: " + ", ".join(names))


def case_noise(r: Runner) -> str:
    """Tag pages nobody designed: the walk must stay inside the page and the
    screen must still be exactly what the oracle says."""
    seeds = (1, 2, 3, 4)
    for seed in seeds:
        rnd = random.Random(seed)
        page = bytearray(rnd.randbytes(con.TAGS_PAGE_BYTES))
        # Seeds 3 and 4 start with a few well-formed tags so that the walk gets
        # past the first header and into the noise.
        if seed >= 3:
            head = (con.tag(con.ATAG_CORE) + con.tag(con.ATAG_MEM, 1, 2)
                    + struct.pack("<2I", 2 + 300, con.ATAG_CMDLINE))
            offset = con.PHONE_R2 - con.TAGS_PAGE_LO
            page[offset:offset + len(head)] = head
        handoff = rc.qemu_handoff(0, con.PHONE_R1, con.PHONE_R2, 0, align=True)
        try:
            r.screen(f"noise-{seed}", handoff, page=bytes(page), align=True)
        except CaseFailure as exc:
            raise CaseFailure(f"seed {seed}: {exc}") from exc
    return (f"{len(seeds)} tag pages of pseudo-random bytes (seeds {seeds}), alignment "
            f"checking on: each byte-identical to the oracle, no fault, tag page unchanged")


def case_moved(r: Runner) -> str:
    """Loaded and started somewhere else: stripes, and a halt."""
    with r.vm("moved", load_addr=RELOC_ADDR) as vm:
        state, psr, sp = vm.settle(r.spans(RELOC_ADDR))
        if state != "halt":
            raise CaseFailure("a moved image should halt, but it is counting")
        if psr & 0x1F != MODE_SVC:
            raise CaseFailure(f"CPU mode at the halt is {psr & 0x1F:#x}, want SVC (a return "
                              f"from payload_main, not a fault)")
        if sp % 8:
            raise CaseFailure(f"SP at the halt is {sp:#x}, not 8-byte aligned")
        fb = vm.read(FB_BASE, oracle.FB_BYTES)
        want = oracle.moved_fb()
        if fb != want:
            raise CaseFailure("the framebuffer is not the stripes: " + first_difference(fb, want))
        rc.require_untouched(vm, None)
    return (f"image loaded and started at {RELOC_ADDR:#x}: {oracle.MOVED_STRIPES} stripes "
            f"byte-identical to the oracle, nothing of the stored pictures; halted in the "
            f"relocated halt_loop in SVC mode")


def case_fault(r: Runner) -> str:
    """QEMU's memory ends 1 MiB into the framebuffer. The first thing the
    image draws is the background, from the top; the write that passes the end
    of memory takes a data abort, caught by the halt-only vectors."""
    ram_end = rc.QEMU_RAM_BASE + (rc.FAULT_RAM_MIB << 20)
    in_ram = ram_end - FB_BASE
    if not 0 < in_ram < oracle.FB_BYTES:
        raise CaseFailure(f"RAM end {ram_end:#x} is not inside the framebuffer")
    want = oracle.background_fb()[:in_ram]
    with r.vm("fault", ram_mib=rc.FAULT_RAM_MIB) as vm:
        state, psr, _sp = vm.settle(r.spans(LINK_ADDR))
        if state != "halt":
            raise CaseFailure("the write past the end of memory did not stop the image")
        if psr & 0x1F != MODE_ABT:
            raise CaseFailure(f"CPU mode at the halt is {psr & 0x1F:#x} (PSR {psr:#010x}), "
                              f"want ABT: a data abort into the halt-only vector")
        got = vm.read(FB_BASE, in_ram)
        if got != want:
            raise CaseFailure("the part of the framebuffer in memory differs from the "
                              "oracle: " + first_difference(got, want))
        rc.require_untouched(vm, None, after=False)
    return (f"memory ends at {ram_end:#x}, inside the framebuffer: the background's pixel row "
            f"{in_ram // oracle.STRIDE} faults; PC rests in halt_loop, CPU mode ABT (PSR "
            f"{psr:#010x}); the {in_ram} bytes in memory are byte-identical to the stored "
            f"background")


CASES = (
    (NAME, case_plain),
    (f"{NAME}-device-handoff", case_device_handoff),
    (f"{NAME}-phone-list", case_phone_list),
    (f"{NAME}-alignment-control", rc.case_align_control),
    (f"{NAME}-alignment-checked", case_aligned),
    (f"{NAME}-tag-lists", case_tag_lists),
    (f"{NAME}-noise", case_noise),
    (f"{NAME}-moved", case_moved),
    (f"{NAME}-fault-halts", case_fault),
)


def run(image: str, workdir: str, halt_addr: int, wait_addr: int, wait_size: int,
        qemu: str, timeout: float) -> int:
    os.makedirs(workdir, exist_ok=True)
    with open(image, "rb") as fh:
        data = fh.read()
    try:
        oracle.check_assets()
        v1.check_image_header(data, halt_addr - LINK_ADDR)
        assert LINK_ADDR < wait_addr and wait_addr + wait_size <= LINK_ADDR + len(data), (
            f"screen_tick_wait [{wait_addr:#x}, +{wait_size}) is outside the image")
        assert wait_size >= 8, f"screen_tick_wait is only {wait_size} bytes"
        assert oracle.BLOB in data, "the image does not hold assets.bin as it is in the tree"
    except (AssertionError, ValueError) as exc:
        print(f"FAIL screen-vector-header: {exc}")
        return 1
    print("PASS screen-vector-header (0x00 b 0x20; 7 exception vectors b halt_loop; "
          "0x20 b 0x30; zImage words at 0x24/0x28/0x2c; halt_loop is wfi + b; "
          f"screen_tick_wait is {wait_size} bytes inside the image; the image holds the "
          f"{len(oracle.BLOB)} bytes of assets.bin)")

    runner = Runner(image, workdir, halt_addr, wait_addr, wait_size, qemu, timeout)
    for name, case in CASES:
        try:
            detail = case(runner)
        except (CaseFailure, OSError, EOFError, RuntimeError, ValueError) as exc:
            print(f"FAIL {name}: {exc}")
            return 1
        print(f"PASS {name} ({detail})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True, help="the flat screen.bin")
    parser.add_argument("--workdir", required=True)

    def number(text: str) -> int:
        return int(text, 0)

    parser.add_argument("--halt-addr", required=True, type=number,
                        help="address of the halt_loop symbol in the ELF")
    parser.add_argument("--wait-addr", required=True, type=number,
                        help="address of the screen_tick_wait symbol in the ELF")
    parser.add_argument("--wait-size", required=True, type=number,
                        help="size of screen_tick_wait in bytes (nm -S)")
    parser.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-arm"))
    parser.add_argument("--timeout", type=float,
                        default=float(os.environ.get("QEMU_TIMEOUT", "20")),
                        help="seconds allowed for each QEMU run")
    args = parser.parse_args(argv)
    try:
        return run(args.image, args.workdir, args.halt_addr, args.wait_addr, args.wait_size,
                   args.qemu, args.timeout)
    except (OSError, EOFError, RuntimeError, ValueError) as exc:
        print(f"FAIL {NAME}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
