#!/usr/bin/env python3
"""Link check for the freestanding test images (build-link-map).

Reads the GNU ld map that a link wrote (-Wl,-Map) and the symbol tables of
the link's inputs, and fails when the link:

1. loaded an object file that is not one of the expected ones, or missed one;
2. searched an archive other than the toolchain's libgcc (the C library, for
   example);
3. took a member from any other archive, or a libgcc member that is not
   approved;
4. left a reference undefined: an undefined symbol, strong or weak, of any
   input, that no input and no linker-script assignment defines.

The linker itself fails on an undefined strong reference in code it keeps.
It accepts an undefined weak reference silently, as address 0, and an option
such as --unresolved-symbols=ignore-all makes it accept strong ones too.
The image's own symbol table may then not show the reference at all, so
references are checked at the inputs.

Prints each problem as "link check: IMAGE: message" and exits 1 if there is
any, 0 otherwise.

Usage: check_link.py --nm NM --map MAP --elf ELF --libgcc LIBGCC
                     [--approve MEMBER]... OBJECT...
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ARCHIVE_HEADER = "Archive member included to satisfy reference by file (symbol)"
# "/path/lib.a(member.o)", alone or followed by its reference on the same line.
MEMBER_LINE = re.compile(r"^(?P<archive>\S+\.a)\((?P<member>[^()]+)\)(?:\s+(?P<ref>\S.*))?$")
# What pulled the member in: "/path/file.o (symbol)" or "/path/lib.a(m.o) (symbol)".
REFERENCE = re.compile(r"^(?P<by>\S.*) \((?P<symbol>[^()\s]+)\)$")
# nm -A -P: "file: name type [value [size]]" or "archive[member]: name type ...".
NM_LINE = re.compile(r"^(?P<file>.+?)(?:\[(?P<member>[^\]]+)\])?: (?P<name>\S+) (?P<type>\S)(?: |$)")
UNDEFINED = frozenset("Uwv")

Member = tuple[str, str, str, str]  # archive, member, referenced by, symbol
Symbol = tuple[str, str | None, str, str]  # file, archive member, name, nm type


def parse_map(text: str) -> tuple[list[str], list[Member]]:
    """Return the files the link loaded and the archive members it included.

    Raises ValueError for a line of the member section that does not parse,
    so that a format change fails the check instead of passing it."""
    lines = text.splitlines()
    loads = [line[len("LOAD "):] for line in lines if line.startswith("LOAD ")]
    loads = [path for path in loads if path != "linker stubs"]
    members: list[Member] = []
    if ARCHIVE_HEADER not in lines:
        return loads, members
    pending: tuple[str, str] | None = None
    for line in lines[lines.index(ARCHIVE_HEADER) + 1:]:
        if not line.strip():
            if members or pending:
                break
            continue
        if line[0].isspace():
            ref = line.strip()
        else:
            m = MEMBER_LINE.match(line)
            if not m or pending:
                raise ValueError(f"unexpected line in the map's archive section: {line!r}")
            pending = (m["archive"], m["member"])
            ref = m["ref"]
            if ref is None:
                continue
        r = REFERENCE.match(ref)
        if not r or not pending:
            raise ValueError(f"unexpected line in the map's archive section: {line!r}")
        members.append((*pending, r["by"], r["symbol"]))
        pending = None
    if pending:
        raise ValueError(f"no reference recorded for archive member {pending[0]}({pending[1]})")
    return loads, members


def parse_nm(text: str) -> list[Symbol]:
    """Parse the output of nm -A -P."""
    symbols = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = NM_LINE.match(line)
        if not m:
            raise ValueError(f"unexpected nm output: {line!r}")
        symbols.append((m["file"], m["member"], m["name"], m["type"]))
    return symbols


def is_global_definition(nm_type: str) -> bool:
    return (nm_type.isupper() and nm_type != "U") or nm_type == "u"


def check(loads: list[str], members: list[Member], symbols: list[Symbol],
          image: list[Symbol], expected: list[str], libgcc: str,
          approved: set[str]) -> list[str]:
    """Return every problem with the link, as messages."""
    real = os.path.realpath
    base = os.path.basename
    objects = {real(p): p for p in loads if not p.endswith(".a")}
    archives = {real(p): p for p in loads if p.endswith(".a")}
    want = {real(p): p for p in expected}
    problems = []

    for path in sorted(objects.keys() - want.keys()):
        problems.append(f"unexpected input object: {base(path)} ({objects[path]})")
    for path in sorted(want.keys() - objects.keys()):
        problems.append(f"expected input object not linked: {base(path)} ({want[path]})")
    for path in sorted(archives.keys() - {real(libgcc)}):
        problems.append(f"archive not approved: {base(path)} ({archives[path]})")
    for archive, member, by, symbol in members:
        reason = f"pulled in by {base(by)} for {symbol}"
        if real(archive) != real(libgcc):
            problems.append(f"archive member not approved: {base(archive)}({member}), {reason}")
        elif member not in approved:
            problems.append(f"libgcc member not approved: {member}, {reason}")

    defined = {name for _, _, name, t in symbols + image if is_global_definition(t)}
    for path, member, name, t in symbols:
        if t not in UNDEFINED or name in defined:
            continue
        source = f"{base(path)}({member})" if member else base(path)
        if t == "U":
            problems.append(f"unresolved reference to {name}, from {source}")
        else:
            problems.append(f"unresolved weak reference to {name}, from {source}:"
                            " the linker accepts it silently, as address 0")
    for _, _, name, t in image:
        if t in UNDEFINED:
            problems.append(f"undefined symbol in the image: {name}")
    return problems


def nm(tool: str, paths: list[str]) -> list[Symbol]:
    result = subprocess.run([tool, "-A", "-P", *paths], check=True,
                            capture_output=True, text=True)
    return parse_nm(result.stdout)


def input_symbols(tool: str, loads: list[str], members: list[Member]) -> list[Symbol]:
    """The symbols of every loaded object and of every included archive member."""
    objects = [p for p in loads if not p.endswith(".a")]
    symbols = nm(tool, objects) if objects else []
    included: dict[str, set[str]] = {}
    for archive, member, _, _ in members:
        included.setdefault(archive, set()).add(member)
    for archive, names in included.items():
        symbols += [s for s in nm(tool, [archive]) if s[1] in names]
    return symbols


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="check_link.py", description=__doc__.splitlines()[0])
    parser.add_argument("--nm", required=True, help="the toolchain's nm")
    parser.add_argument("--map", required=True, help="the map the link wrote (-Wl,-Map)")
    parser.add_argument("--elf", required=True, help="the image the link wrote")
    parser.add_argument("--libgcc", required=True, help="the only archive the link may use")
    parser.add_argument("--approve", action="append", default=[], metavar="MEMBER",
                        help="a libgcc member the image may contain (repeatable)")
    parser.add_argument("objects", nargs="+", help="every object file the link must load")
    args = parser.parse_args(argv[1:])

    image_name = os.path.basename(args.elf)
    try:
        with open(args.map, encoding="utf-8") as f:
            loads, members = parse_map(f.read())
        symbols = input_symbols(args.nm, loads, members)
        image = nm(args.nm, [args.elf])
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"link check: {image_name}: cannot check: {e}")
        return 1
    problems = check(loads, members, symbols, image, args.objects, args.libgcc,
                     set(args.approve))
    for problem in problems:
        print(f"link check: {image_name}: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
