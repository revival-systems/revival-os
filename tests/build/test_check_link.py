"""Unit tests for tests/build/check_link.py.

The negative tests in `make test-build` run the check on real bad links.
These cover the parsing and the rules on their own, including map layouts
that the real links here do not produce.

Run with: python3 -I -m unittest discover -s tests -t . -p 'test_*.py'
"""

import unittest

from tests.build import check_link

MAP = """\
Archive member included to satisfy reference by file (symbol)

/tc/lib/libgcc.a(_aeabi_uldivmod.o)
                              /b/div.o (__aeabi_uldivmod)
/tc/lib/libgcc.a(_udivmoddi4.o)
                              /tc/lib/libgcc.a(_aeabi_uldivmod.o) (__udivmoddi4)
x.a(y.o)                      /b/div.o (y_func)

Discarded input sections

LOAD /b/start.o
LOAD /b/div.o
LOAD /tc/lib/libgcc.a
LOAD linker stubs
"""

LIBGCC = "/tc/lib/libgcc.a"


def sym(name, nm_type, path="/b/start.o", member=None):
    return (path, member, name, nm_type)


class ParseMapTests(unittest.TestCase):
    def test_loads_and_members(self):
        loads, members = check_link.parse_map(MAP)
        self.assertEqual(loads, ["/b/start.o", "/b/div.o", LIBGCC])
        self.assertEqual(members, [
            (LIBGCC, "_aeabi_uldivmod.o", "/b/div.o", "__aeabi_uldivmod"),
            (LIBGCC, "_udivmoddi4.o", "/tc/lib/libgcc.a(_aeabi_uldivmod.o)", "__udivmoddi4"),
            ("x.a", "y.o", "/b/div.o", "y_func"),  # short name: reference on the same line
        ])

    def test_no_archive_section(self):
        self.assertEqual(check_link.parse_map("LOAD /b/a.o\n"), (["/b/a.o"], []))

    def test_unparsable_lines_fail(self):
        header = check_link.ARCHIVE_HEADER + "\n\n"
        for body in ("something unexpected\n", "/tc/lib/libgcc.a(m.o)\n\n", "   /b/a.o (s)\n"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                check_link.parse_map(header + body)


class ParseNmTests(unittest.TestCase):
    def test_objects_and_archive_members(self):
        text = ("/b/a.o: calloc T 1c 4c\n"
                "/b/a.o: gs_panic U\n"
                "/tc/lib/libgcc.a[_dvmd_tls.o]: __aeabi_idiv0 W 0 4\n")
        self.assertEqual(check_link.parse_nm(text), [
            ("/b/a.o", None, "calloc", "T"),
            ("/b/a.o", None, "gs_panic", "U"),
            (LIBGCC, "_dvmd_tls.o", "__aeabi_idiv0", "W"),
        ])

    def test_unparsable_line_fails(self):
        with self.assertRaises(ValueError):
            check_link.parse_nm("no symbols here\n")


class CheckTests(unittest.TestCase):
    def run_check(self, loads=("/b/start.o", LIBGCC), members=(), symbols=(),
                  image=(), expected=("/b/start.o",), approved=()):
        return check_link.check(list(loads), list(members), list(symbols), list(image),
                                list(expected), LIBGCC, set(approved))

    def test_clean_link(self):
        symbols = [sym("_start", "T"), sym("__bss_start", "U")]
        image = [sym("_start", "T", "/b/x.elf"), sym("__bss_start", "B", "/b/x.elf")]
        self.assertEqual(self.run_check(symbols=symbols, image=image), [])

    def test_objects_must_match(self):
        problems = self.run_check(loads=["/b/start.o", "/b/extra.o"], expected=["/b/start.o", "/b/main.o"])
        self.assertEqual(problems, ["unexpected input object: extra.o (/b/extra.o)",
                                    "expected input object not linked: main.o (/b/main.o)"])

    def test_only_libgcc_and_approved_members(self):
        members = [("/tc/libc.a", "strlen.o", "/b/start.o", "strlen"),
                   (LIBGCC, "_udivsi3.o", "/b/start.o", "__aeabi_uidiv"),
                   (LIBGCC, "_dvmd_tls.o", "/tc/lib/libgcc.a(_udivsi3.o)", "__aeabi_idiv0")]
        problems = self.run_check(loads=["/b/start.o", "/tc/libc.a", LIBGCC], members=members,
                                  approved=["_dvmd_tls.o"])
        self.assertEqual(problems, [
            "archive not approved: libc.a (/tc/libc.a)",
            "archive member not approved: libc.a(strlen.o), pulled in by start.o for strlen",
            "libgcc member not approved: _udivsi3.o, pulled in by start.o for __aeabi_uidiv",
        ])

    def test_unresolved_references(self):
        symbols = [sym("defined_elsewhere", "U"), sym("defined_elsewhere", "T", "/b/main.o"),
                   sym("missing", "U"), sym("missing_weak", "w"),
                   sym("only_local", "U"), sym("only_local", "t", "/b/main.o")]
        problems = self.run_check(loads=["/b/start.o", "/b/main.o"], symbols=symbols,
                                  expected=["/b/start.o", "/b/main.o"])
        self.assertEqual(problems, [
            "unresolved reference to missing, from start.o",
            "unresolved weak reference to missing_weak, from start.o:"
            " the linker accepts it silently, as address 0",
            "unresolved reference to only_local, from start.o",
        ])

    def test_undefined_symbol_in_the_image(self):
        image = [sym("getpid", "U", "/b/x.elf")]
        self.assertEqual(self.run_check(image=image), ["undefined symbol in the image: getpid"])


if __name__ == "__main__":
    unittest.main()
