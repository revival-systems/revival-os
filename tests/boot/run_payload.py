"""run_payload.py - boot the Phase 2 payload in QEMU and verify what it paints.

Runs the EXACT kernel-slot bytes of the Samsung image (the flat payload binary)
on `qemu-system-arm -M virt -cpu cortex-a15 -m 2048`, loaded at 0x80208000 via
`-device loader` with the PC set there and no `-kernel` (task test (a)). RAM at
0x40000000..0xC0000000 spans the load address and both framebuffers.

It drives QEMU over QMP: start paused, `cont`, then poll the program counter
(R15, read with `info registers`) until it rests in the payload's `halt_loop`
(address passed in from the ELF symbol) - so completion is detected without any
device-side marker and without racing a fixed delay. It then reads the CPU mode
(PSR) and stack pointer and `pmemsave`s the regions the case needs, into files
that are removed before the run so a stale dump can never be read. Every run is
bounded by its own timeout. The QMP socket lives in a short temporary directory removed on
exit (a long checkout path otherwise exceeds the AF_UNIX limit).

Cases (one QEMU run each, one PASS/FAIL line each):

  qemu-payload               No flash image: the MDP4 register reads 0. Both
                             candidate framebuffers must match the host oracle
                             byte for byte; no third buffer.

The others INJECT the MDP4 register value. In QEMU virt the register address
0x05190008 lies in the second flash bank (0x04000000, 64 MiB), so the value is
supplied as a read-only emulated flash image: a 64 MiB sparse file holding the
little-endian word at offset 0x01190008. This runs the Rust third-buffer code
itself, not a Python mirror of it:

  qemu-payload-third-buffer  0x89000000, plausible: the third buffer is grey
                             with all 9 rows, byte-exact; both candidates show
                             the value as row 9.
  qemu-payload-mdp-candidate 0x88100000, a candidate address: nothing extra is
                             painted; both candidates byte-exact.
  qemu-payload-mdp-reserved  0x8F000000, a reserved region: the target stays
                             all zero.
  qemu-payload-mdp-unaligned 0x89000002, not word-aligned: the target stays all
                             zero.
  qemu-payload-fault-halts   0xBFF00000, plausible for the device, but the
                             buffer crosses the emulator's RAM end (0xC0000000),
                             so the grey fill takes a data abort. The halt-only
                             vector must catch it: PC rests in halt_loop, the
                             CPU is in ABT mode, and both candidates are still
                             byte-exact with 9 rows.
  qemu-payload-third-in-reservation
                             0x8847C000, inside the bootloader's framebuffer
                             reservation but past the end of the GREEN fill:
                             the third buffer is grey with all 9 rows,
                             byte-exact, and both candidates are byte-exact.

The plain `-device loader` entry leaves r0 = r1 = r2 = 0, so it never takes the
path the phone takes (r2 pointing at the tags). Two cases enter through a
five-instruction TEST-ONLY shim, loaded outside the image at 0x80100000, that
sets r0-r3 and jumps to the payload; words are planted in RAM with
`-device loader,addr=A,data=V,data-len=4`. Nothing is added to the image:

  qemu-payload-device-handoff
                             r0 = 0, r1 = 0x00000E8F (machine 3727),
                             r2 = 0x80200100 with 0x00000005 stored there: the
                             rows show those values and row 7 (*r2) is
                             0x00000005, byte-exact, with a clean SVC halt.
  qemu-payload-r2-guard-edges
                             The edges of the *r2 guard, one run each:
                             r2 = 0x80200000 and 0x80207FFC are read;
                             0x80208000, 0x801FFFFC and 0x80200102 give the
                             sentinel 0xFFFFFFFF.

Two cases load the same bytes somewhere else, at 0x80A08000, and start there,
to prove what kstart.S says about a relocated image:

  qemu-payload-relocated     Both candidates byte-exact with the entry row =
                             0x80A08000; clean halt in the relocated halt_loop.
  qemu-payload-relocated-fault-halts
                             With 0xBFF00000 injected the fault still ends in
                             the relocated halt_loop in ABT mode (VBAR follows
                             the run-time address).

In every case that is not a fault the CPU must still be in SVC mode at the halt
(with the vectors installed, a faulted run also ends in halt_loop; the mode
tells the two apart), and its stack pointer - unchanged since kstart.S called
payload_main - must be 8-byte aligned (AAPCS). Before any run, the image's first 0x30 bytes are checked
against the vector/zImage layout kstart.S promises. Prints PASS/FAIL lines;
exits nonzero on the first failure. No device is contacted.

Usage: run_payload.py --payload BIN --workdir DIR --halt-addr ADDR [--qemu BIN] [--timeout S]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

from tests.boot import serrano_v1 as oracle

NAME = "qemu-payload"
R13_RE = re.compile(r"R13=([0-9a-fA-F]{8})")
R15_RE = re.compile(r"R15=([0-9a-fA-F]{8})")
PSR_RE = re.compile(r"PSR=([0-9a-fA-F]{8})")

LOAD_ADDR = oracle.ENTRY_ADDR
MODE_SVC = 0x13
MODE_ABT = 0x17

# QEMU virt: RAM starts at 0x40000000; `-m 2048` ends it at 0xC0000000. The
# second flash bank (pflash unit 1) is 64 MiB at 0x04000000.
QEMU_RAM_END = 0x4000_0000 + (2048 << 20)
FLASH1_BASE = 0x0400_0000
FLASH1_BYTES = 64 << 20
MDP_FLASH_OFFSET = oracle.MDP_DMA_P_BUF_ADDR - FLASH1_BASE  # 0x01190008

# Injected MDP4 values.
MDP_THIRD = 0x8900_0000      # plausible, wholly inside the emulator's RAM
MDP_CANDIDATE = oracle.FB_RED
MDP_RESERVED = 0x8F00_0000   # WCNSS
MDP_UNALIGNED = 0x8900_0002
MDP_FAULT = 0xBFF0_0000      # plausible on the device; crosses QEMU's RAM end
MDP_IN_RESERVATION = 0x8847_C000  # in [0x88300000, 0x88600000), past the GREEN fill

# Test-only entry shim: sets r0-r3 from the words after it and jumps to the
# payload. Loaded outside the image, in RAM the payload never touches.
SHIM_ADDR = 0x8010_0000
SHIM_CODE = (
    0xE59F_0010,  # ldr r0, [pc, #16]
    0xE59F_1010,  # ldr r1, [pc, #16]
    0xE59F_2010,  # ldr r2, [pc, #16]
    0xE59F_3010,  # ldr r3, [pc, #16]
    0xE59F_F010,  # ldr pc, [pc, #16]
    0x0000_0000,  # padding, so the five loads reach the five words below
)

# The same image bytes loaded 8 MiB higher (still clear of both candidates and
# of the stack, which stays at its link address).
RELOC_ADDR = 0x80A0_8000

# Words planted for the *r2 guard edges (arbitrary, distinct, not the sentinel).
EDGE_WORD = 0xA5A5_0000


class CaseFailure(Exception):
    """A case did not behave as required; the message says how."""


class Qmp:
    """Minimal QMP client over a UNIX socket (line-delimited JSON)."""

    def __init__(self, path: str):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.buf = b""
        self._recv_obj()  # greeting
        self.execute("qmp_capabilities")

    def _recv_obj(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("QMP connection closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def execute(self, command: str, **args):
        msg = {"execute": command}
        if args:
            msg["arguments"] = args
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        while True:
            obj = self._recv_obj()
            if "return" in obj:
                return obj["return"]
            if "error" in obj:
                raise RuntimeError(f"QMP error for {command}: {obj['error']}")
            # else an asynchronous event; keep reading.

    def hmc(self, command_line: str) -> str:
        return self.execute("human-monitor-command", **{"command-line": command_line})

    def registers(self) -> tuple:
        """(PC, PSR, SP) from one `info registers` snapshot; None where not
        found. SP is R13 of the CPU's current mode."""
        text = self.hmc("info registers")
        found = [rx.search(text) for rx in (R15_RE, PSR_RE, R13_RE)]
        return tuple(int(m.group(1), 16) if m else None for m in found)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def write_flash_image(path: str, mdp: int) -> None:
    """A 64 MiB sparse flash image holding `mdp` (little-endian) where the MDP4
    register address falls in QEMU virt's second flash bank."""
    with open(path, "wb") as fh:
        fh.truncate(FLASH1_BYTES)
        fh.seek(MDP_FLASH_OFFSET)
        fh.write(struct.pack("<I", mdp))


def write_shim(path: str, regs: tuple, entry: int) -> None:
    """The test-only entry shim: five loads, then r0, r1, r2, r3 and the
    address to jump to."""
    r0, r1, r2, r3 = regs
    with open(path, "wb") as fh:
        fh.write(struct.pack("<11I", *SHIM_CODE, r0, r1, r2, r3, entry))


def boot(qemu: str, payload: str, halt_addr: int, timeout: float,
         flash: str | None, dumps: list, load_addr: int = LOAD_ADDR,
         shim: str | None = None, plant: tuple = ()) -> tuple:
    """Run the payload until the PC rests in halt_loop, save each (address,
    size, path) in `dumps` with pmemsave, and return (PSR, SP) at the halt.

    The payload is loaded at `load_addr`. Without `shim` the CPU starts there
    (r0-r3 are 0). With `shim` (a file from write_shim) the CPU starts at the
    shim instead, which sets r0-r3 and jumps to the payload. Each (address,
    word) in `plant` is stored in RAM before the CPU starts.

    Raises CaseFailure if QEMU exits early or the PC does not reach halt_loop
    within `timeout` seconds (QEMU is then killed).
    """
    # Keep the QMP socket path short (AF_UNIX sun_path is ~108 bytes); the
    # repo checkout path may be long. Removed in the finally block.
    sockdir = tempfile.mkdtemp(prefix="rvos-qmp-")
    sockpath = os.path.join(sockdir, "q.sock")

    cmd = [
        qemu, "-M", "virt", "-cpu", "cortex-a15", "-m", "2048",
        "-nic", "none", "-display", "none", "-serial", "none",
        "-qmp", f"unix:{sockpath},server=on,wait=off", "-S",
    ]
    if shim is None:
        cmd += ["-device", f"loader,file={payload},addr={load_addr:#x},cpu-num=0"]
    else:
        cmd += ["-device", f"loader,file={payload},addr={load_addr:#x}",
                "-device", f"loader,file={shim},addr={SHIM_ADDR:#x},cpu-num=0"]
    for addr, word in plant:
        cmd += ["-device", f"loader,addr={addr:#x},data={word:#x},data-len=4"]
    if flash is not None:
        cmd += ["-drive", f"if=pflash,unit=1,format=raw,readonly=on,file={flash}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + timeout
    qmp = None
    try:
        while True:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise CaseFailure(f"QEMU exited early ({proc.returncode}): {out.strip()}")
            if os.path.exists(sockpath):
                try:
                    qmp = Qmp(sockpath)
                    break
                except (OSError, EOFError):
                    pass
            if time.monotonic() > deadline:
                raise CaseFailure("QEMU QMP socket never became ready")
            time.sleep(0.05)

        qmp.execute("cont")

        # Poll the PC until it rests in the halt loop (halt_addr .. +8).
        while True:
            pc, psr, sp = qmp.registers()
            if pc is not None and halt_addr <= pc < halt_addr + 8:
                break
            if time.monotonic() > deadline:
                last = f" (last PC {pc:#x})" if pc is not None else ""
                raise CaseFailure(
                    f"payload PC did not reach halt_loop ({halt_addr:#x}) in time{last}")
            time.sleep(0.05)
        if psr is None or sp is None:
            raise CaseFailure("could not read the PSR and SP at the halt")

        for addr, size, path in dumps:
            qmp.hmc(f'pmemsave {addr:#x} {size} "{path}"')
        qmp.execute("quit")
        return psr, sp
    finally:
        if qmp:
            qmp.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        shutil.rmtree(sockdir, ignore_errors=True)


def _read(path: str, size: int, label: str) -> bytes:
    with open(path, "rb") as fh:
        got = fh.read()
    if len(got) != size:
        raise CaseFailure(f"{label} dump is {len(got)} bytes, want {size}")
    return got


def _require_mode(psr: int, mode: int, what: str) -> None:
    if psr & 0x1F != mode:
        raise CaseFailure(f"CPU mode at the halt is {psr & 0x1F:#x} (PSR {psr:#010x}), "
                          f"want {mode:#x}: {what}")


def _require_clean_halt(psr: int, sp: int, what: str) -> None:
    """A run with no fault: still in SVC mode, and the stack pointer - the same
    value it had at `bl payload_main`, since Rust restores it and kstart.S does
    not pop - is 8-byte aligned, as the AAPCS requires at a call."""
    _require_mode(psr, MODE_SVC, what)
    if sp % 8 != 0:
        raise CaseFailure(f"SP at the halt is {sp:#x}, not 8-byte aligned: "
                          f"kstart.S called payload_main with a misaligned stack")


def _check_fb(path: str, label: str, fill: tuple, words: list) -> bytes:
    """A framebuffer dump must equal the oracle byte for byte and decode back
    to `words`. Returns the dump."""
    got = _read(path, oracle.FB_BYTES, label)
    want = oracle.generate_fb(fill, words)
    if got != want:
        first = next(i for i in range(oracle.FB_BYTES) if got[i] != want[i])
        raise CaseFailure(f"{label} framebuffer differs from the oracle at byte {first}")
    decoded = oracle.decode_words(got)
    if decoded != words:
        raise CaseFailure(f"{label} decoded words {[hex(w) for w in decoded]} "
                          f"!= expected {[hex(w) for w in words]}")
    return got


def _check_candidates(red_dump: str, green_dump: str, words: list) -> bytes:
    """Both candidate framebuffers byte-exact with all 9 rows. Returns RED."""
    red = _check_fb(red_dump, "red", oracle.FILL_RED, words)
    _check_fb(green_dump, "green", oracle.FILL_GREEN, words)
    return red


class Runner:
    """Shared arguments of every case, and the per-case QEMU run."""

    def __init__(self, payload: str, workdir: str, halt_addr: int, qemu: str, timeout: float):
        self.payload = payload
        self.workdir = workdir
        self.halt_addr = halt_addr
        self.qemu = qemu
        self.timeout = timeout

    def run(self, tag: str, mdp: int | None, extra: tuple | None = None, *,
            load_addr: int = LOAD_ADDR, regs: tuple | None = None,
            plant: tuple = ()) -> tuple:
        """Boot once with the MDP4 register reading `mdp` (None: no flash
        image, the register reads 0). Dumps both candidates, plus the region
        `extra` = (address, size) if given. Returns (psr, sp, red, green,
        extra) where the last three are dump paths (extra None if not asked).

        `load_addr` loads the image somewhere other than its link address (the
        halt_loop address polled moves with it). `regs` = (r0, r1, r2, r3)
        enters through the test-only shim with those register values; `plant`
        is a tuple of (address, word) stored in RAM first."""
        red = os.path.join(self.workdir, f"{tag}-red.dump")
        green = os.path.join(self.workdir, f"{tag}-green.dump")
        dumps = [(oracle.FB_RED, oracle.FB_BYTES, red),
                 (oracle.FB_GREEN, oracle.FB_BYTES, green)]
        extra_path = None
        if extra is not None:
            extra_path = os.path.join(self.workdir, f"{tag}-extra.dump")
            dumps.append((extra[0], extra[1], extra_path))
        # A dump left by an earlier run must never stand in for this one.
        for _, _, path in dumps:
            if os.path.exists(path):
                os.remove(path)
        flash = None
        if mdp is not None:
            flash = os.path.join(self.workdir, f"{tag}-flash.img")
            write_flash_image(flash, mdp)
        shim = None
        if regs is not None:
            shim = os.path.join(self.workdir, f"{tag}-shim.bin")
            write_shim(shim, regs, load_addr)
        try:
            psr, sp = boot(self.qemu, self.payload,
                           self.halt_addr - LOAD_ADDR + load_addr, self.timeout,
                           flash, dumps, load_addr, shim, plant)
        finally:
            if flash is not None and os.path.exists(flash):
                os.remove(flash)
        return psr, sp, red, green, extra_path


def case_zero(r: Runner) -> str:
    """The plain run: no flash image, the MDP4 register reads 0."""
    psr, sp, red_dump, green_dump, _ = r.run("zero", None)
    _require_clean_halt(psr, sp, "the payload should return and halt without a fault")
    words = oracle.EXPECTED_WORDS
    red = _check_candidates(red_dump, green_dump, words)
    try:
        oracle.assert_handoff_invariants(oracle.decode_words(red))
    except AssertionError as exc:
        raise CaseFailure(f"handoff invariant: {exc}") from exc
    px = oracle.fill_pixel_at(red, oracle.WIDTH // 2, oracle.HEIGHT // 2)
    return (f"both framebuffers byte-identical to the oracle; "
            f"RED fill bytes {tuple(px)}; "
            f"entry={words[5]:#x} cpsr={words[3]:#x} sctlr={words[4]:#x} "
            f"checksum={words[7]:#x} mdp4={words[8]:#x} -> no third buffer; "
            f"halted in SVC mode, sp={sp:#x} 8-byte aligned")


def case_third_buffer(r: Runner) -> str:
    """A plausible MDP4 value: the third buffer is painted grey with 9 rows."""
    mdp = MDP_THIRD
    if not oracle.is_plausible_fb(mdp) or mdp + oracle.FB_BYTES > QEMU_RAM_END:
        raise CaseFailure(f"test value {mdp:#x} is not a plausible in-RAM framebuffer")
    psr, sp, red_dump, green_dump, third_dump = r.run("third", mdp, (mdp, oracle.FB_BYTES))
    _require_clean_halt(psr, sp, "painting an in-RAM third buffer should not fault")
    words = oracle.expected_words(mdp)
    red = _check_candidates(red_dump, green_dump, words)
    try:
        oracle.assert_cpu_handoff_invariants(oracle.decode_words(red))
    except AssertionError as exc:
        raise CaseFailure(f"handoff invariant: {exc}") from exc
    _check_fb(third_dump, "third", oracle.FILL_GREY, words)
    return (f"mdp4={mdp:#x} injected through flash: third buffer grey with all 9 rows, "
            f"byte-identical to the oracle; both candidates byte-identical, row 9 = {mdp:#x}")


def case_candidate(r: Runner) -> str:
    """The MDP4 value is a candidate address: nothing extra is painted."""
    mdp = MDP_CANDIDATE
    psr, sp, red_dump, green_dump, _ = r.run("candidate", mdp)
    _require_clean_halt(psr, sp, "a rejected MDP4 value should not fault")
    # Byte-exact RED (red fill, not grey) is what shows no third paint happened.
    _check_candidates(red_dump, green_dump, oracle.expected_words(mdp))
    return (f"mdp4={mdp:#x} (a candidate) injected through flash: no extra paint; "
            f"both candidates byte-identical, row 9 = {mdp:#x}")


def _case_rejected(r: Runner, tag: str, mdp: int, why: str) -> str:
    """An implausible MDP4 value: the region it names must stay all zero."""
    if oracle.is_plausible_fb(mdp):
        raise CaseFailure(f"test value {mdp:#x} is plausible; it cannot test a rejection")
    # Cover the whole buffer the value names, from the word it falls in.
    lo = mdp & ~3
    size = mdp + oracle.FB_BYTES - lo
    psr, sp, red_dump, green_dump, target = r.run(tag, mdp, (lo, size))
    _require_clean_halt(psr, sp, "a rejected MDP4 value should not fault")
    _check_candidates(red_dump, green_dump, oracle.expected_words(mdp))
    got = _read(target, size, "target")
    if got.count(0) != size:
        first = next(i for i in range(size) if got[i])
        raise CaseFailure(f"target region {lo:#x} was written: byte {first} is {got[first]:#x}")
    return (f"mdp4={mdp:#x} ({why}) injected through flash: target region "
            f"[{lo:#x}, {lo + size:#x}) stays all zero; both candidates byte-identical")


def case_reserved(r: Runner) -> str:
    return _case_rejected(r, "reserved", MDP_RESERVED, "reserved, WCNSS")


def case_unaligned(r: Runner) -> str:
    return _case_rejected(r, "unaligned", MDP_UNALIGNED, "not word-aligned")


def case_fault(r: Runner) -> str:
    """Fault injection: the payload accepts a value whose buffer runs past the
    emulator's RAM, so the grey fill takes a data abort; the halt-only vector
    must stop the CPU in halt_loop in ABT mode."""
    mdp = MDP_FAULT
    if not oracle.is_plausible_fb(mdp):
        raise CaseFailure(f"test value {mdp:#x} is not plausible; the payload would not write")
    if not mdp < QEMU_RAM_END < mdp + oracle.FB_BYTES:
        raise CaseFailure(f"test value {mdp:#x} does not cross the RAM end {QEMU_RAM_END:#x}")
    in_ram = QEMU_RAM_END - mdp
    psr, _sp, red_dump, green_dump, part = r.run("fault", mdp, (mdp, in_ram))
    _require_mode(psr, MODE_ABT, "a write past the end of RAM should take a data abort "
                                 "into the halt-only vector")
    _check_candidates(red_dump, green_dump, oracle.expected_words(mdp))
    # The fill got exactly as far as RAM goes: grey up to the RAM end. This
    # ties the abort to the write past RAM, not to something earlier.
    got = _read(part, in_ram, "third (in-RAM part)")
    if got.count(oracle.FILL_GREY[0]) != in_ram:
        first = next(i for i in range(in_ram) if got[i] != oracle.FILL_GREY[0])
        raise CaseFailure(f"third buffer is not grey up to the RAM end: byte {first} "
                          f"is {got[first]:#x}")
    return (f"mdp4={mdp:#x} injected through flash: the grey fill faults at the RAM end "
            f"{QEMU_RAM_END:#x}; PC rests in halt_loop, CPU mode ABT (PSR {psr:#010x}); "
            f"both candidates byte-identical with 9 rows")


def case_third_in_reservation(r: Runner) -> str:
    """An MDP4 value inside the bootloader's framebuffer reservation, past the
    end of the GREEN fill: the one place a real framebuffer is expected that
    neither candidate reaches. It must be painted (v1.2 refused it)."""
    mdp = MDP_IN_RESERVATION
    if not (0x8830_0000 <= mdp and mdp + oracle.FB_BYTES <= 0x8860_0000):
        raise CaseFailure(f"test value {mdp:#x} is not inside the framebuffer reservation")
    if mdp < oracle.FB_GREEN + oracle.FB_BYTES:
        raise CaseFailure(f"test value {mdp:#x} overlaps the GREEN candidate fill")
    psr, sp, red_dump, green_dump, third_dump = r.run("inres", mdp, (mdp, oracle.FB_BYTES))
    _require_clean_halt(psr, sp, "painting a third buffer in the reservation should not fault")
    words = oracle.expected_words(mdp)
    _check_candidates(red_dump, green_dump, words)
    _check_fb(third_dump, "third", oracle.FILL_GREY, words)
    return (f"mdp4={mdp:#x} (inside the bootloader framebuffer reservation, past the GREEN "
            f"fill) injected through flash: third buffer grey with all 9 rows, byte-identical "
            f"to the oracle; both candidates byte-identical, row 9 = {mdp:#x}")


def case_device_handoff(r: Runner) -> str:
    """Enter the way section 2 expects the phone to: r0 = 0, r1 = the machine
    number, r2 = the tags address, with a known word stored there. This is the
    only run in which the in-range *r2 read happens with device-like values."""
    r1, r2, stored = oracle.MACH_SERRANO, oracle.TAGS_ADDR, 0x0000_0005
    psr, sp, red_dump, green_dump, _ = r.run(
        "handoff", None, regs=(0, r1, r2, 0), plant=((r2, stored),))
    _require_clean_halt(psr, sp, "a device-like handoff should not fault")
    words = oracle.handoff_words(r0=0, r1=r1, r2=r2, word_at_r2=stored)
    if words[6] != stored:
        raise CaseFailure(f"the oracle does not expect *r2 to be read at {r2:#x}")
    _check_candidates(red_dump, green_dump, words)
    return (f"entered through the test shim with r0=0x0 r1={r1:#x} r2={r2:#x} and "
            f"{stored:#010x} stored there: both candidates byte-identical; rows show "
            f"r1={words[1]:#x} r2={words[2]:#x} *r2={words[6]:#010x}; halted in SVC mode")


def case_r2_guard_edges(r: Runner) -> str:
    """The edges of the *r2 guard [0x80200000, 0x80208000), word-aligned. Each
    run plants distinct known words so a read that should not happen would
    show up as that word instead of the sentinel."""
    lo, hi = oracle.R2_READ_LO, oracle.R2_READ_HI
    # (tag, r2, planted words, must the payload read *r2?)
    edges = (
        ("first", lo, ((lo, EDGE_WORD + 1),), True),
        ("last", hi - 4, ((hi - 4, EDGE_WORD + 2),), True),
        # hi is the image's own first word (a branch, not the sentinel).
        ("above", hi, (), False),
        ("below", lo - 4, ((lo - 4, EDGE_WORD + 3),), False),
        ("unaligned", lo + 0x102, ((lo + 0x100, EDGE_WORD + 4), (lo + 0x104, EDGE_WORD + 5)),
         False),
    )
    seen = []
    for tag, r2, plant, read in edges:
        if oracle.r2_is_read(r2) != read:
            raise CaseFailure(f"the oracle's guard disagrees about r2={r2:#x}")
        stored = dict(plant).get(r2)
        psr, sp, red_dump, green_dump, _ = r.run(
            f"edge-{tag}", None, regs=(0, oracle.MACH_SERRANO, r2, 0), plant=plant)
        _require_clean_halt(psr, sp, f"r2={r2:#x} should not fault")
        words = oracle.handoff_words(r0=0, r1=oracle.MACH_SERRANO, r2=r2, word_at_r2=stored)
        try:
            _check_candidates(red_dump, green_dump, words)
        except CaseFailure as exc:
            raise CaseFailure(f"r2={r2:#x}: {exc}") from exc
        seen.append(f"{r2:#x} -> {words[6]:#010x}")
    return ("*r2 row for each r2, byte-identical in both candidates: " + "; ".join(seen)
            + " (the first two are read, the others give the sentinel)")


def case_relocated(r: Runner) -> str:
    """The same bytes loaded and started at another address: the entry capture
    is position-independent and the entry row must show where it really ran."""
    psr, sp, red_dump, green_dump, _ = r.run("reloc", None, load_addr=RELOC_ADDR)
    _require_clean_halt(psr, sp, "a relocated image should paint and halt without a fault")
    words = oracle.handoff_words(entry=RELOC_ADDR)
    _check_candidates(red_dump, green_dump, words)
    return (f"image loaded and started at {RELOC_ADDR:#x}: both candidates byte-identical, "
            f"entry row = {words[5]:#x}; halted in the relocated halt_loop in SVC mode")


def case_relocated_fault(r: Runner) -> str:
    """A fault in the relocated image must reach the relocated vectors: VBAR is
    set from the run-time address, not the link address."""
    mdp = MDP_FAULT
    in_ram = QEMU_RAM_END - mdp
    psr, _sp, red_dump, green_dump, part = r.run(
        "reloc-fault", mdp, (mdp, in_ram), load_addr=RELOC_ADDR)
    _require_mode(psr, MODE_ABT, "the fault should be caught by the relocated vectors")
    _check_candidates(red_dump, green_dump, oracle.handoff_words(entry=RELOC_ADDR, mdp=mdp))
    got = _read(part, in_ram, "third (in-RAM part)")
    if got.count(oracle.FILL_GREY[0]) != in_ram:
        raise CaseFailure("third buffer is not grey up to the RAM end")
    return (f"image at {RELOC_ADDR:#x}, mdp4={mdp:#x} injected: the grey fill faults at the "
            f"RAM end; PC rests in the relocated halt_loop, CPU mode ABT (PSR {psr:#010x}); "
            f"both candidates byte-identical, entry row = {RELOC_ADDR:#x}")


CASES = (
    (NAME, case_zero),
    (f"{NAME}-third-buffer", case_third_buffer),
    (f"{NAME}-mdp-candidate", case_candidate),
    (f"{NAME}-mdp-reserved", case_reserved),
    (f"{NAME}-mdp-unaligned", case_unaligned),
    (f"{NAME}-fault-halts", case_fault),
    (f"{NAME}-third-in-reservation", case_third_in_reservation),
    (f"{NAME}-device-handoff", case_device_handoff),
    (f"{NAME}-r2-guard-edges", case_r2_guard_edges),
    (f"{NAME}-relocated", case_relocated),
    (f"{NAME}-relocated-fault-halts", case_relocated_fault),
)


def run(payload: str, workdir: str, halt_addr: int, qemu: str, timeout: float) -> int:
    os.makedirs(workdir, exist_ok=True)

    # Static check first: the vectors and zImage words the runs below rely on.
    with open(payload, "rb") as fh:
        image = fh.read()
    try:
        oracle.check_image_header(image, halt_addr - LOAD_ADDR)
    except AssertionError as exc:
        print(f"FAIL payload-vector-header: {exc}")
        return 1
    print("PASS payload-vector-header (0x00 b 0x20; 7 exception vectors b halt_loop; "
          "0x20 b 0x30; zImage words at 0x24/0x28/0x2c; halt_loop is wfi + b)")

    runner = Runner(payload, workdir, halt_addr, qemu, timeout)
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
    parser.add_argument("--payload", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--halt-addr", required=True, type=lambda s: int(s, 0),
                        help="address of the halt_loop symbol in the payload ELF")
    parser.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-arm"))
    parser.add_argument("--timeout", type=float,
                        default=float(os.environ.get("QEMU_TIMEOUT", "20")),
                        help="seconds allowed for each QEMU run")
    args = parser.parse_args(argv)
    try:
        return run(args.payload, args.workdir, args.halt_addr, args.qemu, args.timeout)
    except (OSError, EOFError, RuntimeError, ValueError) as exc:
        print(f"FAIL {NAME}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
