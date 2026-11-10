#!/usr/bin/env python3
"""Parse every workflow and fail on YAML that GitHub would reject.

Deliberately dependency-light: PyYAML only, which Fedora ships as
python3-pyyaml. This catches the class of mistake that otherwise only shows up
as a red X on a branch nobody is watching.
"""

from __future__ import annotations

import glob
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("PyYAML is required: dnf install python3-pyyaml")


def main() -> int:
    paths = sorted(glob.glob(".github/workflows/*.yml"))
    if not paths:
        print("no workflows found; run from the repository root")
        return 1

    failed = False
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                document = yaml.safe_load(handle)
        except yaml.YAMLError as error:
            print(f"{path}: {error}")
            failed = True
            continue

        if not isinstance(document, dict):
            print(f"{path}: not a mapping")
            failed = True
            continue

        jobs = document.get("jobs") or {}
        if not isinstance(jobs, dict) or not jobs:
            print(f"{path}: no jobs")
            failed = True
            continue

        print(f"{path}: {len(jobs)} job(s): {', '.join(sorted(jobs))}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
