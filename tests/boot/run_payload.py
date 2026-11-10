"""run_payload.py - boot the Phase 2 payload in QEMU and verify what it paints.

Runs the EXACT kernel-slot bytes of the Samsung image (the flat payload binary)
on `qemu-system-arm -M virt -cpu cortex-a15 -m 2048`, loaded at 0x80208000 via
`-device loader` with the PC set there and no `-kernel` (task test (a)). RAM at
0x40000000..0xC0000000 spans the load address and both framebuffers.

It drives QEMU over QMP: start paused, `cont`, then poll the program counter
(R15, read with `info registers`) until it rests in the payload's `halt_loop`
(address passed in from the ELF symbol) - so completion is detected without any
device-side marker and without racing a fixed delay. It then `pmemsave`s both
framebuffer regions. Each dump is compared BYTE FOR BYTE against the host oracle
(serrano_v1.generate_fb with the expected handoff words), the nine encoded word
rows are decoded and checked for structural invariants, and the observed fill
colour is reported. The QMP socket lives in a short temporary directory removed
on exit (a long checkout path otherwise exceeds the AF_UNIX limit). Prints
PASS/FAIL lines; exits nonzero on any failure. No device is contacted.

Usage: run_payload.py --payload BIN --workdir DIR --halt-addr ADDR [--qemu BIN] [--timeout S]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from tests.boot import serrano_v1 as oracle

NAME = "qemu-payload"
R15_RE = re.compile(r"R15=([0-9a-fA-F]{8})")


def _fail(msg: str) -> int:
    print(f"FAIL {NAME}: {msg}")
    return 1


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

    def pc(self) -> int | None:
        m = R15_RE.search(self.hmc("info registers"))
        return int(m.group(1), 16) if m else None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def run(payload: str, workdir: str, halt_addr: int, qemu: str, timeout: float) -> int:
    os.makedirs(workdir, exist_ok=True)
    red_dump = os.path.join(workdir, "red.dump")
    green_dump = os.path.join(workdir, "green.dump")
    # Keep the QMP socket path short (AF_UNIX sun_path is ~108 bytes); the
    # repo checkout path may be long. Removed in the finally block.
    sockdir = tempfile.mkdtemp(prefix="rvos-qmp-")
    sockpath = os.path.join(sockdir, "q.sock")

    cmd = [
        qemu, "-M", "virt", "-cpu", "cortex-a15", "-m", "2048",
        "-nic", "none", "-display", "none", "-serial", "none",
        "-qmp", f"unix:{sockpath},server=on,wait=off", "-S",
        "-device", f"loader,file={payload},addr=0x80208000,cpu-num=0",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + timeout
    qmp = None
    try:
        while True:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                return _fail(f"QEMU exited early ({proc.returncode}): {out.strip()}")
            if os.path.exists(sockpath):
                try:
                    qmp = Qmp(sockpath)
                    break
                except (OSError, EOFError):
                    pass
            if time.monotonic() > deadline:
                return _fail("QEMU QMP socket never became ready")
            time.sleep(0.05)

        qmp.execute("cont")

        # Poll the PC until it rests in the halt loop (halt_addr .. +8).
        while True:
            pc = qmp.pc()
            if pc is not None and halt_addr <= pc < halt_addr + 8:
                break
            if time.monotonic() > deadline:
                return _fail(f"payload PC did not reach halt_loop ({halt_addr:#x}) in time "
                             f"(last PC {pc:#x})" if pc is not None else
                             f"payload PC did not reach halt_loop ({halt_addr:#x}) in time")
            time.sleep(0.05)

        qmp.hmc(f'pmemsave {oracle.FB_RED:#x} {oracle.FB_BYTES} "{red_dump}"')
        qmp.hmc(f'pmemsave {oracle.FB_GREEN:#x} {oracle.FB_BYTES} "{green_dump}"')
        qmp.execute("quit")
    finally:
        if qmp:
            qmp.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(sockdir, ignore_errors=True)

    # --- verification (pure host, deterministic) ------------------------------
    expected = {
        "red": (red_dump, oracle.FILL_RED),
        "green": (green_dump, oracle.FILL_GREEN),
    }
    for label, (path, fill) in expected.items():
        with open(path, "rb") as fh:
            got = fh.read()
        if len(got) != oracle.FB_BYTES:
            return _fail(f"{label} dump is {len(got)} bytes, want {oracle.FB_BYTES}")
        want = oracle.generate_fb(fill, oracle.EXPECTED_WORDS)
        if got != want:
            first = next((i for i in range(oracle.FB_BYTES) if got[i] != want[i]), -1)
            return _fail(f"{label} framebuffer differs from the oracle at byte {first}")
        words = oracle.decode_words(got)
        try:
            oracle.assert_handoff_invariants(words)
        except AssertionError as exc:
            return _fail(f"{label} handoff invariant: {exc}")
        if words != oracle.EXPECTED_WORDS:
            return _fail(f"{label} decoded words {[hex(w) for w in words]} "
                         f"!= expected {[hex(w) for w in oracle.EXPECTED_WORDS]}")

    with open(red_dump, "rb") as fh:
        red = fh.read()
    px = oracle.fill_pixel_at(red, oracle.WIDTH // 2, oracle.HEIGHT // 2)
    words = oracle.decode_words(red)
    print(f"PASS {NAME} (both framebuffers byte-identical to the oracle; "
          f"RED fill bytes {tuple(px)}; "
          f"entry={words[5]:#x} cpsr={words[3]:#x} sctlr={words[4]:#x} "
          f"checksum={words[7]:#x} mdp4={words[8]:#x} -> no third buffer)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--payload", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--halt-addr", required=True, type=lambda s: int(s, 0),
                        help="address of the halt_loop symbol in the payload ELF")
    parser.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-arm"))
    parser.add_argument("--timeout", type=float,
                        default=float(os.environ.get("QEMU_TIMEOUT", "20")))
    args = parser.parse_args(argv)
    try:
        return run(args.payload, args.workdir, args.halt_addr, args.qemu, args.timeout)
    except (OSError, EOFError, RuntimeError, ValueError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
