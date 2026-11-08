"""Unit tests for tests/docs/check_docs.py and tests/goose/checksum_oracle.py.

Run with: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.docs import check_docs
from tests.goose import checksum_oracle

PHASE_BODY = "\n".join(f"{field} x" for field in check_docs.PHASE_FIELDS)


def roadmap(phases=range(10), drop_field=None):
    parts = ["# Roadmap\n"]
    for n in phases:
        body = PHASE_BODY if drop_field is None or n != 0 else PHASE_BODY.replace(drop_field, "")
        parts.append(f"### Phase {n} — Name\n\n{body}\n")
    return "\n".join(parts)


class SlugTests(unittest.TestCase):
    def test_github_rules(self):
        cases = {
            "Phase 0 — Samsung identification, boot, reboot and recovery":
                "phase-0--samsung-identification-boot-reboot-and-recovery",
            "Boot image format and handoff": "boot-image-format-and-handoff",
            "`make check` and friends": "make-check-and-friends",
            "A [linked](x.md) heading": "a-linked-heading",
            "Bootloader lock and Knox": "bootloader-lock-and-knox",
        }
        for heading, slug in cases.items():
            with self.subTest(heading=heading):
                self.assertEqual(check_docs.slugify(heading), slug)


class CheckTests(unittest.TestCase):
    def tree(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        files.setdefault("ROADMAP.md", roadmap())
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text), encoding="utf-8")
        return root

    def test_clean_tree_passes(self):
        root = self.tree({
            "README.md": "# Title\n\nSee [docs](docs/a.md#part-one) and [roadmap](ROADMAP.md).\n",
            "docs/a.md": "# A\n\n## Part one\n\nBack to [top](#a) and [readme](../README.md).\n",
        })
        self.assertEqual(check_docs.check(root), [])

    def test_broken_link_is_reported(self):
        root = self.tree({"README.md": "# T\n\n[missing](docs/nope.md)\n"})
        problems = check_docs.check(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("broken link 'docs/nope.md'", problems[0])

    def test_missing_anchor_is_reported(self):
        root = self.tree({
            "README.md": "# T\n\n[x](docs/a.md#no-such-heading)\n",
            "docs/a.md": "# A\n",
        })
        problems = check_docs.check(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("no heading for anchor '#no-such-heading'", problems[0])

    def test_links_in_code_are_ignored(self):
        root = self.tree({
            "README.md": "# T\n\n`[x](nope.md)`\n\n```\n[y](nope.md)\n```\n",
        })
        self.assertEqual(check_docs.check(root), [])

    def test_external_links_are_not_fetched(self):
        root = self.tree({"README.md": "# T\n\n[web](https://example.com/x#y)\n"})
        self.assertEqual(check_docs.check(root), [])

    def test_home_path_is_reported(self):
        root = self.tree({"README.md": "# T\n\nRun /home/someone/x.sh\n"})
        problems = check_docs.check(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("absolute home-directory path", problems[0])

    def test_missing_phase_is_reported(self):
        root = self.tree({"ROADMAP.md": roadmap(phases=range(9))})
        self.assertEqual(check_docs.check(root), ["ROADMAP.md: no '### Phase 9' section"])

    def test_missing_phase_field_is_reported(self):
        root = self.tree({"ROADMAP.md": roadmap(drop_field="**Physical verification:**")})
        self.assertEqual(check_docs.check(root), ["ROADMAP.md: Phase 0 lacks Physical verification"])

    def test_duplicate_headings_get_suffixes(self):
        root = self.tree({"README.md": "# T\n\n## Same\n\n## Same\n\n[second](#same-1)\n"})
        self.assertEqual(check_docs.check(root), [])


class OracleTests(unittest.TestCase):
    def test_small_values(self):
        # acc = acc * 31 + i: 0, 1, 33, 1026
        self.assertEqual([checksum_oracle.checksum(n) for n in range(5)], [0, 0, 1, 33, 1026])

    def test_wraps_to_signed_32_bits(self):
        value = checksum_oracle.checksum(100000)
        self.assertGreaterEqual(value, -(2**31))
        self.assertLess(value, 2**31)

    def test_value_used_by_the_probe_tests(self):
        self.assertEqual(checksum_oracle.checksum(1000), 562641396)


if __name__ == "__main__":
    unittest.main()
