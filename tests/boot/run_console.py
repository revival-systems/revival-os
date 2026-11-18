"""run_console.py - boot the Phase 2 console image in QEMU and verify its screen.

Runs the EXACT kernel-slot bytes of the console image (the flat console.bin)
on `qemu-system-arm -M virt -cpu cortex-a15`, loaded at 0x80208000 as the stock
bootloader loads it, and compares what it leaves in the framebuffer at
0x88100000 with the host oracle (tests/boot/console_v2.py) byte for byte.

The image never halts when it works: it ends in a counter that keeps counting.
So the harness cannot wait for a halt as tests/boot/run_payload.py does. It
drives QEMU over QMP: it pauses the CPU, reads the program counter, and lets it
run again until the CPU is paused inside `console_tick_wait` (the image's wait
between two counter steps; address and size are passed in from the ELF). While
the CPU is in there the screen is complete, never half-drawn, so a dump taken
then can be compared exactly. A CPU found in kstart.S's `halt_loop` instead
means a fault, or the wrong-address case; the CPU mode tells which.

Before the CPU starts, the whole framebuffer is filled with the byte 0x55, a
value the image never writes. A dump that equals the oracle therefore shows
that the image wrote every byte of the panel. After every run the harness also
checks that the bootloader's tag page still holds exactly what was put there
and that 64 KiB on each side of the framebuffer were not written.

Cases (PASS/FAIL line each):

  console-vector-header     The image's first 0x30 bytes are kstart.S's layout.
  qemu-console              No handoff (r0-r3 = 0), the display register reads
                            0: the screen is byte-exact; the counter's line is
                            then watched, byte-exact at every look, until the
                            counter has passed 0x10 (so a carry into the next
                            digit has been drawn); and the whole screen is
                            byte-exact again at the end.
  qemu-console-device-handoff
                            Entered the way the phone enters it (r1 = 3727,
                            r2 = 0x80200100) with a sample tag list there and
                            the display register reading 0x88100000: byte-exact,
                            and none of the sample's hidden values can be read
                            back from the screen.
  qemu-console-alignment-control
                            Shows that this QEMU faults an unaligned word load
                            in the state the phone hands over (SCTLR.A set, MMU
                            off), and that the same load from an aligned
                            address does not. Without this the next case would
                            prove nothing.
  qemu-console-alignment-checked
                            The device handoff again with SCTLR.A set, as on
                            the phone: byte-exact, no fault.
  qemu-console-tag-lists    Malformed and edge-case tag lists, one run each:
                            byte-exact, no fault.
  qemu-console-noise        Tag pages of pseudo-random bytes: byte-exact, no
                            fault.
  qemu-console-moved        The image loaded and started at another address:
                            stripes, then a halt in SVC mode.
  qemu-console-fault-halts  Memory that ends inside the framebuffer: the write
                            past its end faults, the CPU rests in halt_loop in
                            ABT mode, and everything drawn before is byte-exact.

The handoff registers are set by a TEST-ONLY shim loaded outside the image (as
in run_payload.py); here it can also set SCTLR.A. Nothing is added to the
image. No device is contacted.

Usage: run_console.py --image BIN --workdir DIR --halt-addr A --wait-addr A
                      --wait-size N [--qemu BIN] [--timeout S]
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from tests.boot import console_v2 as oracle
from tests.boot import serrano_v1 as v1
from tests.boot.run_payload import (MODE_ABT, MODE_SVC, RELOC_ADDR, SHIM_ADDR, CaseFailure, Qmp,
                                    write_flash_image)

NAME = "qemu-console"
LINK_ADDR = oracle.LINK_ENTRY
FB_BASE = oracle.FB_BASE
FB_END = FB_BASE + oracle.FB_BYTES
QEMU_RAM_BASE = 0x4000_0000
RAM_MIB = 2048
# With this much memory, QEMU's RAM ends 1 MiB into the framebuffer.
FAULT_RAM_MIB = 1154
NOISE = 0x55
GUARD = 0x1_0000
# The plain case watches the counter until it has passed this value, letting
# the CPU run for COUNT_LOOK_EVERY seconds between looks. A look reads only
# the counter's line: the CPU stands still during a look, so looks must be
# cheap and far apart, or the counter gets nowhere in the time allowed.
COUNT_PAST = 0x10
COUNT_LOOK_EVERY = 0.2
TICK_BAND_ADDR = FB_BASE + oracle.TICK_LINE * oracle.LINE_BYTES

# Test-only code. Words are ARM instructions.
INSN_MRC_SCTLR_R4 = 0xEE11_4F10  # mrc p15, 0, r4, c1, c0, 0
INSN_ORR_R4_A = 0xE384_4002      # orr r4, r4, #2      (SCTLR.A)
INSN_MCR_SCTLR_R4 = 0xEE01_4F10  # mcr p15, 0, r4, c1, c0, 0
INSN_ISB = 0xF57F_F06F
SET_ALIGN = (INSN_MRC_SCTLR_R4, INSN_ORR_R4_A, INSN_MCR_SCTLR_R4, INSN_ISB)
LOAD_REGS_AND_JUMP = (
    0xE59F_0010,  # ldr r0, [pc, #16]
    0xE59F_1010,  # ldr r1, [pc, #16]
    0xE59F_2010,  # ldr r2, [pc, #16]
    0xE59F_3010,  # ldr r3, [pc, #16]
    0xE59F_F010,  # ldr pc, [pc, #16]
    0x0000_0000,  # padding, so the five loads reach the five words below
)
SCTLR_A = 1 << 1

# The alignment control: set SCTLR.A, load a word from MARKER_ADDR + `offset`,
# then store a marker. The marker is stored only if the load did not fault.
MARKER_ADDR = 0x8011_0000
MARKER = 0x600D_F00D
INSN_ADD_R7_R5_IMM = 0xE285_7000  # add r7, r5, #imm8


def control_bytes(offset: int) -> bytes:
    words = SET_ALIGN + (
        0xE59F_5010,                  # ldr r5, [pc, #16]   -> MARKER_ADDR
        0xE59F_6010,                  # ldr r6, [pc, #16]   -> MARKER
        INSN_ADD_R7_R5_IMM | offset,  # add r7, r5, #offset
        0xE597_8000,                  # ldr r8, [r7]        (the word load)
        0xE585_6000,                  # str r6, [r5]
        0xEAFF_FFFE,                  # b .
        MARKER_ADDR,
        MARKER,
    )
    return struct.pack(f"<{len(words)}I", *words)


def shim_bytes(regs: tuple, entry: int, align: bool) -> bytes:
    """The entry shim: optionally set SCTLR.A, then load r0-r3 and jump."""
    words = (SET_ALIGN if align else ()) + LOAD_REGS_AND_JUMP + tuple(regs) + (entry,)
    return struct.pack(f"<{len(words)}I", *words)


class Vm:
    """One QEMU process, started paused, driven over QMP."""

    def __init__(self, qemu: str, timeout: float, workdir: str, tag: str, *,
                 ram_mib: int, blobs: list, flash: str | None):
        """`blobs` is a list of (bytes or path, address, starts_cpu)."""
        self.workdir = workdir
        self.tag = tag
        self.deadline = time.monotonic() + timeout
        self.sockdir = tempfile.mkdtemp(prefix="rvos-qmp-")  # short path for AF_UNIX
        sockpath = os.path.join(self.sockdir, "q.sock")
        self.files = []
        cmd = [qemu, "-M", "virt", "-cpu", "cortex-a15", "-m", str(ram_mib),
               "-nic", "none", "-display", "none", "-serial", "none",
               "-qmp", f"unix:{sockpath},server=on,wait=off", "-S"]
        for index, (data, addr, starts_cpu) in enumerate(blobs):
            if isinstance(data, bytes):
                path = os.path.join(workdir, f"{tag}-blob{index}.bin")
                with open(path, "wb") as fh:
                    fh.write(data)
                self.files.append(path)
            else:
                path = data
            cmd += ["-device", f"loader,file={path},addr={addr:#x},force-raw=on"
                               + (",cpu-num=0" if starts_cpu else "")]
        if flash is not None:
            cmd += ["-drive", f"if=pflash,unit=1,format=raw,readonly=on,file={flash}"]
            self.files.append(flash)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.qmp = None
        try:
            while self.qmp is None:
                if self.proc.poll() is not None:
                    out = self.proc.stdout.read().decode(errors="replace")
                    raise CaseFailure(f"QEMU exited early ({self.proc.returncode}): "
                                      f"{out.strip()}")
                if os.path.exists(sockpath):
                    try:
                        self.qmp = Qmp(sockpath)
                    except (OSError, EOFError):
                        pass
                if self.qmp is None:
                    self.check_time("QEMU's QMP socket never became ready")
                    time.sleep(0.05)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self) -> None:
        if self.qmp is not None:
            try:
                self.qmp.execute("quit")
            except (OSError, EOFError, RuntimeError):
                pass
            self.qmp.close()
            self.qmp = None
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        shutil.rmtree(self.sockdir, ignore_errors=True)
        for path in self.files:
            if os.path.exists(path):
                os.remove(path)

    def check_time(self, what: str) -> None:
        if time.monotonic() > self.deadline:
            raise CaseFailure(what)

    def resume(self) -> None:
        self.qmp.execute("cont")

    def pause(self) -> tuple:
        """Pause the CPU; returns (PC, PSR, SP) at the pause."""
        self.qmp.execute("stop")
        pc, psr, sp = self.qmp.registers()
        if pc is None or psr is None or sp is None:
            raise CaseFailure("could not read the PC, PSR and SP")
        return pc, psr, sp

    def read(self, addr: int, size: int) -> bytes:
        """`size` bytes of guest memory at `addr`. The CPU must be paused."""
        path = os.path.join(self.workdir, f"{self.tag}-mem.dump")
        if os.path.exists(path):
            os.remove(path)  # a stale dump must never stand in for this one
        self.qmp.hmc(f'pmemsave {addr:#x} {size} "{path}"')
        with open(path, "rb") as fh:
            got = fh.read()
        os.remove(path)
        if len(got) != size:
            raise CaseFailure(f"dump of {size} bytes at {addr:#x} is {len(got)} bytes")
        return got

    def settle(self, spans: dict, run_for: float = 0.02) -> tuple:
        """Let the CPU run for `run_for` seconds, and then on in short turns
        until it is paused with its PC inside one of `spans`
        ({name: (lo, hi)}). Returns (name, PSR, SP)."""
        last = None
        while True:
            self.resume()
            time.sleep(run_for)
            run_for = 0.02
            pc, psr, sp = self.pause()
            for name, (lo, hi) in spans.items():
                if lo <= pc < hi:
                    return name, psr, sp
            last = pc
            self.check_time(f"the CPU reached none of {sorted(spans)} in time "
                             f"(last PC {last:#x})")


class Runner:
    """Shared arguments of every case, and the per-case QEMU run."""

    def __init__(self, image: str, workdir: str, halt_addr: int, wait_addr: int,
                 wait_size: int, qemu: str, timeout: float):
        self.image = image
        self.workdir = workdir
        self.halt_addr = halt_addr
        self.wait = (wait_addr, wait_addr + wait_size)
        self.qemu = qemu
        self.timeout = timeout

    def spans(self, load_addr: int) -> dict:
        moved = load_addr - LINK_ADDR
        return {"halt": (self.halt_addr + moved, self.halt_addr + moved + 8),
                "wait": (self.wait[0] + moved, self.wait[1] + moved)}

    def vm(self, tag: str, *, load_addr: int = LINK_ADDR, ram_mib: int = RAM_MIB,
           regs: tuple | None = None, align: bool = False, page: bytes | None = None,
           mdp: int | None = None) -> Vm:
        """A paused QEMU with the image loaded at `load_addr`, the framebuffer
        filled with NOISE, `page` (if given) stored as the whole tag page, and
        the display register reading `mdp` (None: no flash image, reads 0).
        With `regs` = (r0, r1, r2, r3) the CPU enters through the shim, which
        also sets SCTLR.A if `align`."""
        ram_end = QEMU_RAM_BASE + (ram_mib << 20)
        blobs = [(self.image, load_addr, regs is None),
                 (bytes([NOISE]) * (min(FB_END, ram_end) - FB_BASE), FB_BASE, False)]
        if regs is not None:
            blobs.append((shim_bytes(regs, load_addr, align), SHIM_ADDR, True))
        elif align:
            raise ValueError("SCTLR.A can only be set through the shim")
        if page is not None:
            blobs.append((page, oracle.TAGS_PAGE_LO, False))
        flash = None
        if mdp is not None:
            flash = os.path.join(self.workdir, f"{tag}-flash.img")
            write_flash_image(flash, mdp)
        return Vm(self.qemu, self.timeout, self.workdir, tag,
                  ram_mib=ram_mib, blobs=blobs, flash=flash)

    def screen(self, tag: str, handoff: oracle.Handoff, *, page: bytes | None = None,
               mdp: int | None = None, align: bool = False, shim: bool = True) -> bytes:
        """Run once with this handoff and require a complete, byte-exact screen
        with the counter showing. Returns the framebuffer dump."""
        regs = (handoff.r0, handoff.r1, handoff.r2, handoff.r3) if shim else None
        with self.vm(tag, regs=regs, align=align, page=page, mdp=mdp) as vm:
            state, psr, sp = vm.settle(self.spans(LINK_ADDR))
            require_running(state, psr, sp)
            fb = vm.read(FB_BASE, oracle.FB_BYTES)
            require_screen(fb, handoff, page, mdp or 0)
            require_untouched(vm, page)
        return fb


def qemu_handoff(r0: int = 0, r1: int = 0, r2: int = 0, r3: int = 0, *,
                 align: bool = False) -> oracle.Handoff:
    """What kstart.S captures under QEMU for these register values."""
    sctlr = v1.QEMU_SCTLR | (SCTLR_A if align else 0)
    return oracle.Handoff(r0, r1, r2, r3, v1.QEMU_CPSR, sctlr, LINK_ADDR)


def require_running(state: str, psr: int, sp: int) -> None:
    """The image must be counting, not halted: in console_tick_wait, in SVC
    mode, with a word-aligned stack pointer. (The 8-byte rule of the AAPCS
    holds at calls; console_tick_wait calls nothing and may hold one word.)"""
    if state != "wait":
        mode = psr & 0x1F
        why = "a data or prefetch abort" if mode == MODE_ABT else f"CPU mode {mode:#x}"
        raise CaseFailure(f"the image halted in kstart.S's halt_loop ({why}, "
                          f"PSR {psr:#010x}) instead of counting")
    if psr & 0x1F != MODE_SVC:
        raise CaseFailure(f"CPU mode while counting is {psr & 0x1F:#x}, want SVC")
    if sp % 4:
        raise CaseFailure(f"SP in console_tick_wait is {sp:#x}, not word-aligned")


def first_difference(got: bytes, want: bytes) -> str:
    index = next(i for i in range(len(want)) if got[i] != want[i])
    y, rest = divmod(index, oracle.STRIDE)
    x = rest // oracle.BPP
    return (f"byte {index} (pixel x={x} y={y}, text line {y // oracle.CELL_H} column "
            f"{x // oracle.CELL_W}) is {got[index]:#04x}, want {want[index]:#04x}")


def require_screen(fb: bytes, handoff: oracle.Handoff, page: bytes | None, mdp: int) -> int:
    """The framebuffer must equal the oracle's screen for the counter value it
    shows. Returns that counter value."""
    tick = oracle.tick_of(fb)
    if tick is None:
        shown = oracle.decode(fb)[oracle.TICK_LINE].rstrip()
        raise CaseFailure(f"the last line is not a counter: {shown!r}")
    want = oracle.expected_fb(handoff, page, mdp, tick)
    if fb != want:
        raise CaseFailure("the framebuffer differs from the oracle: "
                          + first_difference(fb, want))
    return tick


def require_untouched(vm: Vm, page: bytes | None, after: bool = True) -> None:
    """The image writes only to the framebuffer: the tag page still holds what
    was stored, and the memory next to the framebuffer is still zero."""
    want = page if page is not None else bytes(oracle.TAGS_PAGE_BYTES)
    if vm.read(oracle.TAGS_PAGE_LO, oracle.TAGS_PAGE_BYTES) != want:
        raise CaseFailure("the tag page was written")
    guards = [(FB_BASE - GUARD, "before")] + ([(FB_END, "after")] if after else [])
    for addr, where in guards:
        got = vm.read(addr, GUARD)
        if got.count(0) != GUARD:
            first = next(i for i in range(GUARD) if got[i])
            raise CaseFailure(f"memory {where} the framebuffer was written at "
                              f"{addr + first:#x}")


def case_plain(r: Runner) -> str:
    """No handoff, no display-register value; and the counter must step."""
    handoff = qemu_handoff()
    with r.vm("plain") as vm:
        spans = r.spans(LINK_ADDR)
        state, psr, sp = vm.settle(spans)
        require_running(state, psr, sp)
        seen = [require_screen(vm.read(FB_BASE, oracle.FB_BYTES), handoff, None, 0)]
        # The image redraws only the digits that change. Watch the counter's
        # line until the counter has passed COUNT_PAST, so that a carry into
        # the next digit has been drawn. tick_of_line gives a value only for
        # a line that is byte for byte a counter line, so every look is exact.
        while seen[-1] <= COUNT_PAST:
            state, psr, sp = vm.settle(spans, run_for=COUNT_LOOK_EVERY)
            require_running(state, psr, sp)
            band = vm.read(TICK_BAND_ADDR, oracle.LINE_BYTES)
            now = oracle.tick_of_line(band)
            if now is None:
                raise CaseFailure("while the image waits, its last line is not a counter: "
                                  f"{oracle.decode_line(band).rstrip()!r}")
            if now < seen[-1]:
                raise CaseFailure(f"the counter went from {seen[-1]:#x} back to {now:#x}")
            if now != seen[-1]:
                seen.append(now)
            vm.check_time(f"the counter did not pass {COUNT_PAST:#x} in time "
                          f"(it shows {now:#x})")
        # The CPU is still paused: the whole screen, at the value just seen.
        last = require_screen(vm.read(FB_BASE, oracle.FB_BYTES), handoff, None, 0)
        if last != seen[-1]:
            raise CaseFailure(f"the counter shows {last:#x} on the whole screen and "
                              f"{seen[-1]:#x} on its line, with the CPU paused")
        require_untouched(vm, None)
    return (f"framebuffer byte-identical to the oracle with the counter at {seen[0]:#x} and "
            f"again at {seen[-1]:#x}; the counter's line byte-exact at {len(seen)} values "
            f"on the way, past the carry at {COUNT_PAST:#x}; every byte of the panel "
            f"written; cpsr={handoff.cpsr:#x} sctlr={handoff.sctlr:#x}; counting in SVC "
            f"mode, sp={sp:#x}")


def sample_page() -> bytes:
    return oracle.page_with(oracle.sample_tags())


def require_no_secret(fb: bytes) -> None:
    screen = "\n".join(oracle.decode(fb))
    for secret in oracle.SAMPLE_SECRETS:
        if secret.decode() in screen:
            raise CaseFailure(f"a hidden value ({secret.decode()}) is readable on screen")


def case_device_handoff(r: Runner) -> str:
    handoff = qemu_handoff(0, oracle.PHONE_R1, oracle.PHONE_R2, 0)
    fb = r.screen("handoff", handoff, page=sample_page(), mdp=FB_BASE)
    require_no_secret(fb)
    lines = oracle.decode(fb)
    return (f"entered through the test shim with r1={handoff.r1:#x} r2={handoff.r2:#x}, a "
            f"sample tag list there and the display register reading {FB_BASE:#x}: "
            f"framebuffer byte-identical to the oracle; {lines[oracle.MDP_LINE].rstrip()!r}; "
            f"no hidden value readable; tag page unchanged")


def case_align_control(r: Runner) -> str:
    """Does this QEMU fault an unaligned word load in the state the phone
    hands over, SCTLR.A set and the MMU off? The same program with an aligned
    address is the control of the control: it must store its marker."""
    seen = {}
    for offset in (0, 1):
        tag = f"align-control-{offset}"
        with Vm(r.qemu, r.timeout, r.workdir, tag, ram_mib=RAM_MIB,
                blobs=[(control_bytes(offset), SHIM_ADDR, True)], flash=None) as vm:
            while True:
                vm.resume()
                time.sleep(0.05)
                _pc, psr, _sp = vm.pause()
                (marker,) = struct.unpack("<I", vm.read(MARKER_ADDR, 4))
                if marker == MARKER or psr & 0x1F == MODE_ABT:
                    break
                vm.check_time("the control program neither stored its marker nor faulted")
            seen[offset] = (marker == MARKER, psr & 0x1F)
    if seen[0] != (True, MODE_SVC):
        raise CaseFailure("the aligned load should succeed and the marker be stored; got "
                          f"stored={seen[0][0]} mode={seen[0][1]:#x}: the control program "
                          "itself does not work here")
    if seen[1][0]:
        raise CaseFailure("this QEMU does not fault an unaligned word load with SCTLR.A "
                          "set, so it cannot show that the image is free of unaligned "
                          "accesses; a QEMU that enforces alignment is needed")
    if seen[1][1] != MODE_ABT:
        raise CaseFailure(f"the unaligned load did not store the marker, but the CPU mode "
                          f"is {seen[1][1]:#x}, not ABT")
    return ("with SCTLR.A set and the MMU off, a word load from an aligned address "
            "succeeds and the same load from an odd address takes a data abort: this "
            "QEMU enforces alignment")


def case_aligned(r: Runner) -> str:
    handoff = qemu_handoff(0, oracle.PHONE_R1, oracle.PHONE_R2, 0, align=True)
    fb = r.screen("aligned", handoff, page=sample_page(), mdp=FB_BASE, align=True)
    if "SCTLR 00C5007A M0 C0 I0 A1 V0" not in oracle.decode(fb)[7]:
        raise CaseFailure("the screen does not show SCTLR.A set")
    return (f"sctlr={handoff.sctlr:#x} (alignment checking on, as on the phone) with the "
            f"sample tag list: framebuffer byte-identical to the oracle, no fault")


def tag_lists() -> list:
    """(tag, r2, data stored at r2 or at `at`, at) for the edge cases."""
    o = oracle
    lo, hi = o.TAGS_PAGE_LO, o.TAGS_PAGE_HI
    marker = o.tag(o.ATAG_REVISION, 0x1234_5678) + o.end_tag()
    return [
        ("r2-page-end", hi, marker, o.PHONE_R2),
        ("r2-below-page", lo - 4, marker, o.PHONE_R2),
        ("r2-unaligned", o.PHONE_R2 + 2, marker, o.PHONE_R2),
        ("first-word", lo, o.end_tag(), lo),
        ("last-word", hi - 4, b"", hi - 4),
        ("device-tree", o.PHONE_R2, struct.pack(">I", 0xD00D_FEED) + b"SECRET" * 4, o.PHONE_R2),
        ("empty-list", o.PHONE_R2, o.end_tag(), o.PHONE_R2),
        ("core-with-body", o.PHONE_R2, o.tag(o.ATAG_CORE, 0, 0x1000, 0) + o.end_tag(),
         o.PHONE_R2),
        ("short-bodies", o.PHONE_R2,
         o.tag(o.ATAG_MEM, 0x10) + o.tag(o.ATAG_INITRD2) + o.tag(o.ATAG_REVISION) + o.end_tag(),
         o.PHONE_R2),
        ("size-one", o.PHONE_R2, o.tag(o.ATAG_CORE) + struct.pack("<2I", 1, o.ATAG_MEM),
         o.PHONE_R2),
        ("size-too-big", o.PHONE_R2,
         o.tag(o.ATAG_CORE) + struct.pack("<2I", o.MAX_TAG_WORDS + 1, o.ATAG_MEM), o.PHONE_R2),
        ("largest-tag", o.PHONE_R2,
         o.tag(0x1111_1111, *([0xA5A5_A5A5] * (o.MAX_TAG_WORDS - 2))) + o.end_tag(),
         o.PHONE_R2),
        ("past-page-end", hi - 64, struct.pack("<2I", 17, o.ATAG_MEM), hi - 64),
        ("fills-page-end", hi - 64, struct.pack("<2I", 16, 0x2222_2222), hi - 64),
        ("too-many-tags", o.PHONE_R2, o.tag(0x3333_3333) * (o.MAX_TAGS + 1) + o.end_tag(),
         o.PHONE_R2),
        ("end-with-kind", o.PHONE_R2, o.tag(o.ATAG_CORE) + struct.pack("<2I", 0, 0xABCD_0123),
         o.PHONE_R2),
        ("cmdline-no-body", o.PHONE_R2, o.tag(o.ATAG_CMDLINE) + o.end_tag(), o.PHONE_R2),
        ("report-overflow", o.PHONE_R2, o.tag(o.ATAG_MEM, 1, 2) * 40 + o.end_tag(),
         o.PHONE_R2),
        ("cmdline-forms", o.PHONE_R2,
         o.cmdline_tag(b'  a=1\tbb= =SECRET quiet c="SECRET one two" d==x a\x01\xffb=1 '
                       + b"n" * 40 + b'=1 z="SECRET unclosed b=1')
         + o.end_tag(), o.PHONE_R2),
        ("cmdline-no-terminator", o.PHONE_R2,
         struct.pack("<2I", 5, o.ATAG_CMDLINE) + b"key=SECRET12" + o.tag(o.ATAG_REVISION, 7)
         + o.end_tag(), o.PHONE_R2),
        ("cmdline-empty", o.PHONE_R2, o.cmdline_tag(b"") + o.cmdline_tag(b"   ") + o.end_tag(),
         o.PHONE_R2),
    ]


def case_tag_lists(r: Runner) -> str:
    names = []
    for tag, r2, data, at in tag_lists():
        page = oracle.page_with(data, at)
        handoff = qemu_handoff(0, oracle.PHONE_R1, r2, 0, align=True)
        try:
            fb = r.screen(f"tags-{tag}", handoff, page=page, align=True)
            require_no_secret(fb)
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
        page = bytearray(rnd.randbytes(oracle.TAGS_PAGE_BYTES))
        # Seeds 3 and 4 start with a few well-formed tags so that the walk gets
        # past the first header and into the noise.
        if seed >= 3:
            head = (oracle.tag(oracle.ATAG_CORE) + oracle.tag(oracle.ATAG_MEM, 1, 2)
                    + struct.pack("<2I", 2 + 300, oracle.ATAG_CMDLINE))
            offset = oracle.PHONE_R2 - oracle.TAGS_PAGE_LO
            page[offset:offset + len(head)] = head
        handoff = qemu_handoff(0, oracle.PHONE_R1, oracle.PHONE_R2, 0, align=True)
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
            raise CaseFailure("the framebuffer is not the stripes: "
                              + first_difference(fb, want))
        require_untouched(vm, None)
    return (f"image loaded and started at {RELOC_ADDR:#x}: {oracle.MOVED_STRIPES} stripes "
            f"byte-identical to the oracle, no text; halted in the relocated halt_loop in "
            f"SVC mode")


def case_fault(r: Runner) -> str:
    """QEMU's memory ends 1 MiB into the framebuffer. Clearing the lines below
    the report runs past it: a data abort, caught by the halt-only vectors."""
    ram_end = QEMU_RAM_BASE + (FAULT_RAM_MIB << 20)
    in_ram = ram_end - FB_BASE
    if not 0 < in_ram < oracle.FB_BYTES:
        raise CaseFailure(f"RAM end {ram_end:#x} is not inside the framebuffer")
    handoff = qemu_handoff()
    # Everything that lies in memory is drawn before the write that faults:
    # the report's text lines and the cleared lines down to the memory's end.
    want = oracle.expected_fb(handoff, None, None)[:in_ram]
    fault_line = in_ram // oracle.STRIDE // oracle.CELL_H
    report_lines = sum(1 for line in oracle.report_text(handoff) if line.strip())
    if not report_lines < fault_line < oracle.REPORT_LINES:
        raise CaseFailure(f"the fault would be on text line {fault_line}, not on a "
                          f"cleared line below the {report_lines}-line report")
    with r.vm("fault", ram_mib=FAULT_RAM_MIB) as vm:
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
        require_untouched(vm, None, after=False)
    return (f"memory ends at {ram_end:#x}, inside the framebuffer: clearing text line "
            f"{fault_line} faults; PC rests in halt_loop, CPU mode ABT (PSR {psr:#010x}); "
            f"the {in_ram} bytes in memory are byte-identical to the oracle")


CASES = (
    (NAME, case_plain),
    (f"{NAME}-device-handoff", case_device_handoff),
    (f"{NAME}-alignment-control", case_align_control),
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
        v1.check_image_header(data, halt_addr - LINK_ADDR)
        assert LINK_ADDR < wait_addr and wait_addr + wait_size <= LINK_ADDR + len(data), (
            f"console_tick_wait [{wait_addr:#x}, +{wait_size}) is outside the image")
        assert wait_size >= 8, f"console_tick_wait is only {wait_size} bytes"
    except AssertionError as exc:
        print(f"FAIL console-vector-header: {exc}")
        return 1
    print("PASS console-vector-header (0x00 b 0x20; 7 exception vectors b halt_loop; "
          "0x20 b 0x30; zImage words at 0x24/0x28/0x2c; halt_loop is wfi + b; "
          f"console_tick_wait is {wait_size} bytes inside the image)")

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
    parser.add_argument("--image", required=True, help="the flat console.bin")
    parser.add_argument("--workdir", required=True)

    def number(text: str) -> int:
        return int(text, 0)

    parser.add_argument("--halt-addr", required=True, type=number,
                        help="address of the halt_loop symbol in the ELF")
    parser.add_argument("--wait-addr", required=True, type=number,
                        help="address of the console_tick_wait symbol in the ELF")
    parser.add_argument("--wait-size", required=True, type=number,
                        help="size of console_tick_wait in bytes (nm -S)")
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
