"""Test evidence.

Gates are facts about a digest, not judgements about a branch or a pointer, so
they are recorded as records and evaluated mechanically. A record is produced by
the workflow that observed the fact:

* ``build``     — the image built and was pushed. Anchors provenance.
* ``image``     — static checks on the image (``bootc container lint``). Runnable
  on a hosted runner; weaker than a boot, so only nightly accepts it.
* ``boot``      — the image booted and reached a healthy session.
* ``hw``        — the driver loaded and a GPU context was created (real GPU).
* ``promotion`` — a channel pointer moved to this digest. **This, not the current
  pointer, is what a soak is measured from**: the nightly pointer moves every
  commit, so "the digest nightly points at is seven days old" is never true.

Evidence is a CI artefact, not repository content: it accumulates faster than the
repository should, and the channel files are the only thing that must be
versioned. In CI it is downloaded into ``.evidence/`` before promotion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .manifest import (
    CHANNELS,
    COMMIT_PATTERN,
    DIGEST_PATTERN,
    ManifestError,
    format_time,
    parse_time,
)

KINDS: tuple[str, ...] = ("build", "image", "boot", "hw", "promotion")
RESULTS: tuple[str, ...] = ("pass", "fail", "skip")
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Evidence:
    kind: str
    digest: str
    created: str
    result: str
    build_id: str | None = None
    source_commit: str | None = None
    channel: str | None = None
    known_p1: bool = False
    checks: Mapping[str, str] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)
    notes: str = ""
    schema: int = SCHEMA_VERSION

    @property
    def time(self):
        return parse_time(self.created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "kind": self.kind,
            "digest": self.digest,
            "build_id": self.build_id,
            "source_commit": self.source_commit,
            "channel": self.channel,
            "result": self.result,
            "created": self.created,
            "known_p1": self.known_p1,
            "checks": dict(self.checks),
            "labels": dict(self.labels),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "Evidence":
        return cls(
            schema=document.get("schema", 0),  # type: ignore[arg-type]
            kind=document.get("kind", ""),
            digest=document.get("digest", ""),
            build_id=document.get("build_id"),
            source_commit=document.get("source_commit"),
            channel=document.get("channel"),
            result=document.get("result", ""),
            created=document.get("created", ""),
            known_p1=bool(document.get("known_p1", False)),
            checks=dict(document.get("checks") or {}),
            labels=dict(document.get("labels") or {}),
            notes=document.get("notes", ""),
        )

    def problems(self) -> list[str]:
        found: list[str] = []
        if self.schema != SCHEMA_VERSION:
            found.append(f"schema must be {SCHEMA_VERSION}, found {self.schema!r}")
        if self.kind not in KINDS:
            found.append(f"kind must be one of {', '.join(KINDS)}, found {self.kind!r}")
        if not isinstance(self.digest, str) or DIGEST_PATTERN.match(self.digest) is None:
            found.append(f"digest must be sha256:<64 hex>, found {self.digest!r}")
        if self.result not in RESULTS:
            found.append(f"result must be one of {', '.join(RESULTS)}, found {self.result!r}")
        try:
            parse_time(self.created)
        except (TypeError, ValueError):
            found.append(f"created is not an ISO-8601 timestamp: {self.created!r}")
        if self.source_commit is not None and COMMIT_PATTERN.match(self.source_commit) is None:
            found.append(f"source_commit is not a hex commit: {self.source_commit!r}")
        if self.kind == "promotion":
            if self.channel not in CHANNELS:
                found.append(f"promotion records need a known channel, found {self.channel!r}")
        elif self.channel is not None:
            found.append(f"{self.kind} records must not carry a channel")
        return found


def load(directory: str | Path, *, strict: bool = True) -> tuple[Evidence, ...]:
    """Load every ``*.json`` record in a directory, oldest first."""
    records: list[Evidence] = []
    for path in sorted(Path(directory).glob("*.json")):
        with open(path, "r", encoding="utf-8") as handle:
            record = Evidence.from_dict(json.load(handle))
        found = record.problems()
        if found:
            message = f"{path.name}: " + "; ".join(found)
            if strict:
                raise ManifestError(message)
            continue
        records.append(record)
    records.sort(key=lambda record: record.time)
    return tuple(records)


def for_digest(records: Iterable[Evidence], digest: str) -> tuple[Evidence, ...]:
    return tuple(record for record in records if record.digest == digest)


def dump(record: Evidence, path: str | Path) -> Path:
    found = record.problems()
    if found:
        raise ManifestError("invalid evidence: " + "; ".join(found))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record.to_dict(), handle, indent=2)
        handle.write("\n")
    return target


def write(record: Evidence, directory: str | Path) -> Path:
    """Write one record. Filenames sort by time, so a directory reads in order."""
    stamp = format_time(record.time).replace(":", "").replace("-", "")
    suffix = f"-{record.channel}" if record.channel else ""
    return dump(record, Path(directory) / f"{stamp}-{record.kind}{suffix}-{record.digest[7:19]}.json")


def build_record(
    *,
    digest: str,
    build_id: str,
    source_commit: str,
    now,
    labels: Mapping[str, str] | None = None,
) -> Evidence:
    return Evidence(
        kind="build",
        digest=digest,
        build_id=build_id,
        source_commit=source_commit,
        result="pass",
        created=format_time(now),
        labels=dict(labels or {}),
    )
