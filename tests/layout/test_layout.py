"""The rules in ADR-0017, checked instead of remembered."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
TOOLS = ROOT / "tools"
WIRING = {"__init__", "__main__"}


def production_packages() -> list[Path]:
    """Every importable package inside tools/, wherever a tool puts it."""
    return sorted({marker.parent for marker in TOOLS.glob("*/*/__init__.py")})


class LayoutTests(unittest.TestCase):
    def test_every_module_has_a_test_file(self):
        missing = []
        for package in production_packages():
            area = package.parent.name
            for module in sorted(package.glob("*.py")):
                if module.stem in WIRING:
                    continue
                expected = TESTS / area / f"test_{module.stem}.py"
                if not expected.exists():
                    missing.append(str(expected.relative_to(ROOT)))

        self.assertEqual(
            missing,
            [],
            "ADR-0017 requires a test module per module. Missing:\n  " + "\n  ".join(missing),
        )

    def test_no_test_module_lives_outside_tests(self):
        stray = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("test_*.py")
            if TESTS not in path.parents
        ]

        self.assertEqual(
            stray,
            [],
            "ADR-0017 keeps every test under tests/. Move these:\n  " + "\n  ".join(stray),
        )

    def test_every_test_directory_is_a_package(self):
        # Discovery uses `-t .`, so a missing marker means the module is silently
        # not collected rather than failing loudly.
        for path in sorted(TESTS.rglob("test_*.py")):
            self.assertTrue(
                (path.parent / "__init__.py").exists(),
                f"{path.relative_to(ROOT)} is in a directory with no __init__.py",
            )

    def test_the_discovery_rule_actually_matches_something(self):
        found = list(TESTS.rglob("test_*.py"))
        self.assertGreater(len(found), 5)
        self.assertTrue(production_packages(), "tools/ contains no packages to check")


class NamingTests(unittest.TestCase):
    def test_test_modules_are_named_after_a_module(self):
        known = {module.stem for package in production_packages() for module in package.glob("*.py")}
        for path in sorted(TESTS.rglob("test_*.py")):
            stem = path.stem.removeprefix("test_")
            if path.parent.name in {"layout", "docs"}:
                # Convention suites check the tree, not a module.
                continue
            self.assertIn(stem, known, f"{path.relative_to(ROOT)} matches no module in tools/")
