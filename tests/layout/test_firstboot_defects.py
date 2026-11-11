"""The two first-boot defects the install exposed, fixed in the image (checked, not remembered).

The install is interactive (ADR-0021), so the installer writes its own
/etc/fstab and the account; the image must still come up clean on the first
boot. Two defects were measured on the installed system:

* systemd-remount-fs.service fails, because Anaconda's conventional / fstab line
  is applied to a composefs overlay (root is mounted by the kernel command line,
  not fstab); the fix is to drop the / line before that unit runs.
* the locale falls back to C.UTF-8, because the image ships no English locale
  data; the fix is to ship glibc-langpack-en.

Neither is a kickstart problem: both show up on the installed system regardless
of the medium, so both fixes live in the image.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINERFILE = ROOT / "Containerfile"
RECONCILE_SERVICE = ROOT / "image" / "systemd" / "aios-firstboot-fstab.service"
RECONCILE_SCRIPT = ROOT / "image" / "scripts" / "aios-firstboot-fstab.sh"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class LocaleDefectTests(unittest.TestCase):
    def test_the_image_ships_the_english_locale(self):
        # Without glibc-langpack-en the deployment carries only C.utf8, so the
        # installer's en_US.UTF-8 request falls back to C.UTF-8 and the greeter
        # rejects the language. The package must be installed into the image.
        body = text(CONTAINERFILE)
        self.assertIn(
            "glibc-langpack-en",
            body,
            "the image must install glibc-langpack-en so en_US.UTF-8 exists",
        )
        # It has to be a real dnf install, not a comment.
        installs = re.findall(r"dnf install[^\n]*(?:\\[^\n]*)*", body)
        self.assertTrue(
            any("glibc-langpack-en" in block for block in installs),
            "glibc-langpack-en must appear in a `dnf install`, not only in a comment",
        )


class RootFstabDefectTests(unittest.TestCase):
    def test_the_reconciler_unit_and_script_exist(self):
        self.assertTrue(
            RECONCILE_SERVICE.exists(),
            f"{RECONCILE_SERVICE.relative_to(ROOT)} is missing",
        )
        self.assertTrue(
            RECONCILE_SCRIPT.exists(),
            f"{RECONCILE_SCRIPT.relative_to(ROOT)} is missing",
        )

    def test_the_image_ships_and_enables_the_reconciler(self):
        body = text(CONTAINERFILE)
        self.assertIn(
            "image/systemd/aios-firstboot-fstab.service",
            body,
            "the Containerfile must copy the reconcile unit into the image",
        )
        self.assertIn(
            "image/scripts/aios-firstboot-fstab.sh",
            body,
            "the Containerfile must copy the reconcile script into the image",
        )
        self.assertIn(
            "systemctl enable aios-firstboot-fstab.service",
            body,
            "the reconcile unit must be enabled so it runs on first boot",
        )

    def test_the_reconciler_runs_before_remount_fs(self):
        # It has to run before systemd-remount-fs applies the / line, otherwise
        # the first boot still shows the failure.
        service = text(RECONCILE_SERVICE)
        self.assertIn("Before=systemd-remount-fs.service", service)
        self.assertIn("ExecStart=/usr/local/libexec/aios/aios-firstboot-fstab.sh", service)

    def test_the_reconciler_drops_the_root_line(self):
        # The fix is to remove the line whose mountpoint is the root, keeping
        # /boot, /var, etc. Verify the script does exactly that.
        script = text(RECONCILE_SCRIPT)
        self.assertIn('$2 == "/"', script, "the script must target the line mounting /")
        self.assertIn("if ($2 == \"/\") next", script, "the script must drop the / line")


if __name__ == "__main__":
    unittest.main()
