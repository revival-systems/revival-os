#!/usr/bin/env python3
"""Documentation consistency check for Revival OS.

Checks every Markdown file under the given root (default: the repository):

1. Every relative link points at an existing file or directory.
2. Every #anchor, in the same file or another Markdown file, matches a
   heading there (GitHub's heading-slug rules).
3. ROADMAP.md has a section for each of Phases 0-9, and each section has
   every required field (the milestone template in the roadmap).
4. No document contains an absolute path into a home directory.

Prints each problem as "file:line: message" and exits 1 if there is any,
0 otherwise. Links inside code blocks and code spans are ignored.

Usage: check_docs.py [ROOT]
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

SKIP_DIRS = {".git", "build", "node_modules", "__pycache__"}

PHASES = range(10)
PHASE_FIELDS = (
    "**Entry gate:**",
    "**Capability:**",
    "**Observable test:**",
    "**Pass criteria:**",
    "**Fail criteria",
    "**Negative and failure tests:**",
    "**Physical verification:**",
    "**Boot, reboot and recovery evidence:**",
    "**Next safe milestone:**",
)

LINK_RE = re.compile(r"(?<!!)\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CODE_SPAN_RE = re.compile(r"`+[^`]*`+")
HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/")


def slugify(heading: str) -> str:
    """GitHub's anchor for a heading's text."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # links -> their text
    text = text.replace("`", "").replace("*", "")
    text = text.strip().lower()
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in " -_" or cat[0] in ("L", "N") or cat == "Mn":
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


def markdown_lines(text: str):
    """Yield (line number, line) outside fenced code blocks."""
    fence = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if fence is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence = stripped[:3]
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        yield number, line


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        seen: dict[str, int] = {}
        found: set[str] = set()
        for _, line in markdown_lines(path.read_text(encoding="utf-8")):
            match = HEADING_RE.match(line)
            if not match:
                continue
            slug = slugify(match.group(2))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            found.add(slug if count == 0 else f"{slug}-{count}")
        cache[path] = found
    return cache[path]


def markdown_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*.md")):
        if not any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            files.append(path)
    return files


def check_links(root: Path, path: Path, cache: dict[Path, set[str]]) -> list[str]:
    problems = []
    rel = path.relative_to(root)
    for number, line in markdown_lines(path.read_text(encoding="utf-8")):
        line = CODE_SPAN_RE.sub("", line)
        targets = LINK_RE.findall(line) + IMAGE_RE.findall(line)
        for target in targets:
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, https:, mailto: ...
                continue
            file_part, _, anchor = target.partition("#")
            dest = path if file_part == "" else (path.parent / file_part).resolve()
            if not dest.exists():
                problems.append(f"{rel}:{number}: broken link '{target}'")
                continue
            if anchor and dest.is_file() and dest.suffix == ".md":
                if anchor not in anchors_of(dest, cache):
                    problems.append(f"{rel}:{number}: no heading for anchor '#{anchor}' in {file_part or rel}")
    return problems


def check_home_paths(root: Path, path: Path) -> list[str]:
    rel = path.relative_to(root)
    return [
        f"{rel}:{number}: absolute home-directory path; use a relative or $HOME path"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if HOME_PATH_RE.search(line)
    ]


def check_roadmap(root: Path) -> list[str]:
    roadmap = root / "ROADMAP.md"
    if not roadmap.exists():
        return ["ROADMAP.md: missing"]
    sections: dict[int, list[str]] = {}
    current = None
    for _, line in markdown_lines(roadmap.read_text(encoding="utf-8")):
        match = re.match(r"^###\s+Phase\s+(\d+)\b", line)
        if match:
            current = int(match.group(1))
            sections[current] = []
        elif re.match(r"^#{1,3}\s", line):
            current = None
        elif current is not None:
            sections[current].append(line)
    problems = []
    for phase in PHASES:
        if phase not in sections:
            problems.append(f"ROADMAP.md: no '### Phase {phase}' section")
            continue
        body = "\n".join(sections[phase])
        for field in PHASE_FIELDS:
            if field not in body:
                problems.append(f"ROADMAP.md: Phase {phase} lacks {field.strip('*').rstrip(':')}")
    return problems


def check(root: Path) -> list[str]:
    cache: dict[Path, set[str]] = {}
    problems = []
    for path in markdown_files(root):
        problems += check_links(root, path, cache)
        problems += check_home_paths(root, path)
    problems += check_roadmap(root)
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else Path(__file__).resolve().parents[2]).resolve()
    problems = check(root)
    for problem in problems:
        print(problem)
    files = len(markdown_files(root))
    if problems:
        print(f"check_docs: {len(problems)} problem(s) in {files} Markdown file(s)")
        return 1
    print(f"check_docs: {files} Markdown file(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
