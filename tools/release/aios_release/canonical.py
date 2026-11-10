"""Canonical bytes for signing.

The signature covers the *parsed document minus its signature field*, serialised
with sorted keys, no insignificant whitespace, and UTF-8 encoding. It does not
cover the file as written.

Consequences, both intended:

* Reformatting the committed JSON (indentation, key order) cannot invalidate a
  signature, so the file can stay diff-friendly.
* A client re-derives the payload from the document it parsed, so it never has
  to trust the bytes on the wire to be byte-identical to the bytes that were
  signed.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

SIGNATURE_FIELD = "signature"


def canonical_bytes(document: Mapping[str, Any], *, omit: tuple[str, ...] = (SIGNATURE_FIELD,)) -> bytes:
    payload = {key: value for key, value in document.items() if key not in omit}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
