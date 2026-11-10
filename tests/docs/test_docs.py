"""The documentation is part of the product, so its structure is tested."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
INDEX = DOCS / "README.md"

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
STATUS = re.compile(r"- \*\*Status:\*\* (\w+)")
REQUIRED_SECTIONS = (
    "## Context",
    "## Decision",
    "## Consequences",
    "## Alternatives considered",
    "## Follow-ups",
)
STATUSES = {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded"}
EXTERNAL = ("http://", "https://", "mailto:")


def markdown_files() -> list[Path]:
    return [path for path in sorted(ROOT.rglob("*.md")) if ".git" not in path.parts]


def adrs() -> list[Path]:
    return [path for path in sorted((DOCS / "adr").glob("*.md")) if ADR_FILE.match(path.name)]


class LinkTests(unittest.TestCase):
    def test_every_relative_link_resolves(self):
        broken = []
        for path in markdown_files():
            for target in LINK.findall(path.read_text(encoding="utf-8")):
                target = target.split("#")[0]
                if not target or target.startswith(EXTERNAL):
                    continue
                if not (path.parent / target).resolve().exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")

        self.assertEqual(broken, [], "Broken links:\n  " + "\n  ".join(broken))

    def test_every_document_is_reachable_from_the_index(self):
        index = INDEX.read_text(encoding="utf-8")
        unreferenced = [
            path.relative_to(DOCS).as_posix()
            for path in sorted(DOCS.rglob("*.md"))
            if path != INDEX and path.relative_to(DOCS).as_posix() not in index
        ]

        self.assertEqual(
            unreferenced,
            [],
            "Not linked from docs/README.md:\n  " + "\n  ".join(unreferenced),
        )


class AdrTests(unittest.TestCase):
    def test_adr_numbers_are_sequential(self):
        numbers = [int(ADR_FILE.match(path.name).group(1)) for path in adrs()]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_every_adr_has_the_template_sections(self):
        incomplete = {
            path.name: [section for section in REQUIRED_SECTIONS if section not in path.read_text(encoding="utf-8")]
            for path in adrs()
        }
        incomplete = {name: missing for name, missing in incomplete.items() if missing}
        self.assertEqual(incomplete, {}, f"ADRs missing template sections: {incomplete}")

    def test_every_adr_declares_a_known_status(self):
        for path in adrs():
            match = STATUS.search(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(match, f"{path.name} has no status line")
            self.assertIn(match.group(1), STATUSES, f"{path.name} has status {match.group(1)!r}")

    def test_every_adr_is_listed_in_the_decision_log(self):
        index = INDEX.read_text(encoding="utf-8")
        unlisted = [path.name for path in adrs() if f"adr/{path.name}" not in index]
        self.assertEqual(unlisted, [], f"Add these to the decision log: {unlisted}")
