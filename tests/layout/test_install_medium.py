"""The install medium asks instead of answering (ADR-0021), checked not remembered."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KICKSTART = ROOT / "install" / "aios-netinst.ks"
MEDIUM = ROOT / "ci" / "build-netboot-iso.sh"

# Kickstart commands that would answer a question the person installing should be
# asked: storage, the root password, the account.
ANSWERS = {
    "autopart",
    "btrfs",
    "clearpart",
    "group",
    "logvol",
    "part",
    "raid",
    "rootpw",
    "user",
    "volgroup",
    "zerombr",
}


def commands(path: Path) -> list[str]:
    return [
        line.split()[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class KickstartTests(unittest.TestCase):
    def test_it_asks_for_the_graphical_installer(self):
        self.assertIn("graphical", commands(KICKSTART))

    def test_it_leaves_the_questions_to_the_person_installing(self):
        found = sorted(ANSWERS.intersection(commands(KICKSTART)))
        self.assertEqual(
            found,
            [],
            f"{KICKSTART.name} answers {found}; ADR-0021 leaves those to the installer UI",
        )

    def test_it_boots_the_installed_system_into_graphical_target(self):
        self.assertIn("xconfig", commands(KICKSTART))
        self.assertIn("--startxonboot", KICKSTART.read_text(encoding="utf-8"))

    def test_it_names_the_payload_by_digest(self):
        bootc = [line for line in commands(KICKSTART) if line == "bootc"]
        self.assertEqual(len(bootc), 1, "exactly one bootc command places the payload")
        self.assertIn("@sha256:", KICKSTART.read_text(encoding="utf-8"))


class MediumTests(unittest.TestCase):
    def test_the_builder_forces_the_graphical_installer(self):
        self.assertIn(
            "inst.graphical",
            MEDIUM.read_text(encoding="utf-8"),
            "the boot entries must force the graphical installer, which is where Wi-Fi is configured",
        )
