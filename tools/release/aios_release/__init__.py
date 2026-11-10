"""Release machinery for AI_OS.

Two halves, deliberately separate:

* :mod:`aios_release.promote` — decide and write the next channel file (CI).
* :mod:`aios_release.resolve` — decide whether a device should move to the
  digest its channel file names (``aios-updated``, device side).

Both are pure functions over plain data: no implicit clock, no network, no
subprocesses. That is what makes the decisions testable and reproducible, and
the whole point of ADR-0015 is that the decision can be reproduced.
"""

__version__ = "0.1.0"
