"""The channel file: the only mutable thing in the release system.

One file per channel, a few hundred bytes, committed to ``channels/`` on
``master`` and served over HTTPS. It names a digest, never a build. See ADR-0015.

Validation is strict and centralised: a channel file that is wrong in a way we
have thought about must fail in CI rather than on ten thousand devices.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_bytes

CHANNELS: tuple[str, ...] = ("nightly", "weekly", "stable")
SCHEMA_VERSION = 1
MAX_SUPERSEDES = 16

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
BUILD_ID_PATTERN = re.compile(r"^\d{4}\.\d{2}\.\d{2}\+g[0-9a-f]{7,40}(?:\.r\d+)?$")
VERSION_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


class ManifestError(ValueError):
    """A channel file that must not be written, signed, or obeyed."""


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, treating a missing offset as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_time(moment: datetime) -> str:
    """Second-precision UTC, so two promotions of the same second are equal."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_digest(value: object) -> bool:
    return isinstance(value, str) and DIGEST_PATTERN.match(value) is not None


def parse_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or VERSION_PATTERN.match(value) is None:
        raise ManifestError(f"not a MAJOR.MINOR.PATCH version: {value!r}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


@dataclass(frozen=True)
class Rollout:
    """A staged rollout.

    ``started`` is the anchor for widening. Without it the widening decision
    would depend on git history, which the device does not have and CI should
    not have to reconstruct.
    """

    percentage: int
    seed: str
    started: str

    def to_dict(self) -> dict[str, Any]:
        return {"percentage": self.percentage, "seed": self.seed, "started": self.started}

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "Rollout":
        return cls(
            percentage=document.get("percentage"),  # type: ignore[arg-type]
            seed=document.get("seed", ""),
            started=document.get("started", ""),
        )


@dataclass(frozen=True)
class ChannelManifest:
    """A pointer: this channel means this digest, right now."""

    channel: str
    digest: str
    build_id: str
    source_commit: str
    created: str
    supersedes: tuple[str, ...] = ()
    version: str | None = None
    release: str | None = None
    rollout: Rollout | None = None
    min_source_version: str | None = None
    notes_url: str | None = None
    signature: str = ""
    schema: int = SCHEMA_VERSION

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Fixed field order. Promotion diffs should read as one changed line."""
        return {
            "schema": self.schema,
            "channel": self.channel,
            "digest": self.digest,
            "version": self.version,
            "build_id": self.build_id,
            "source_commit": self.source_commit,
            "release": self.release,
            "created": self.created,
            "rollout": None if self.rollout is None else self.rollout.to_dict(),
            "min_source_version": self.min_source_version,
            "notes_url": self.notes_url,
            "supersedes": list(self.supersedes),
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ChannelManifest":
        if not isinstance(document, Mapping):
            raise ManifestError("channel file must be a JSON object")
        rollout = document.get("rollout")
        if rollout is not None and not isinstance(rollout, Mapping):
            raise ManifestError("rollout must be an object or null")
        supersedes = document.get("supersedes") or []
        if not isinstance(supersedes, (list, tuple)):
            raise ManifestError("supersedes must be a list")
        return cls(
            schema=document.get("schema", 0),  # type: ignore[arg-type]
            channel=document.get("channel", ""),
            digest=document.get("digest", ""),
            version=document.get("version"),
            build_id=document.get("build_id", ""),
            source_commit=document.get("source_commit", ""),
            release=document.get("release"),
            created=document.get("created", ""),
            rollout=None if rollout is None else Rollout.from_dict(rollout),
            min_source_version=document.get("min_source_version"),
            notes_url=document.get("notes_url"),
            supersedes=tuple(supersedes),
            signature=document.get("signature") or "",
        )

    def payload(self) -> bytes:
        """The exact bytes a signer signs and a client verifies."""
        return canonical_bytes(self.to_dict())

    def with_signature(self, signature: str) -> "ChannelManifest":
        return replace(self, signature=signature)

    # -- files -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "ChannelManifest":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def dump(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def problems(manifest: ChannelManifest, *, require_signature: bool = False) -> list[str]:
    """Every reason this manifest must not be published."""
    found: list[str] = []

    if manifest.schema != SCHEMA_VERSION:
        found.append(f"schema must be {SCHEMA_VERSION}, found {manifest.schema!r}")
    if manifest.channel not in CHANNELS:
        found.append(f"unknown channel {manifest.channel!r}; expected one of {', '.join(CHANNELS)}")
    if not is_digest(manifest.digest):
        found.append(f"digest must be sha256:<64 hex>, found {manifest.digest!r}")
    if not isinstance(manifest.build_id, str) or BUILD_ID_PATTERN.match(manifest.build_id) is None:
        found.append(f"build_id must look like 2026.11.10+g1a2b3c4d, found {manifest.build_id!r}")
    if not isinstance(manifest.source_commit, str) or COMMIT_PATTERN.match(manifest.source_commit) is None:
        found.append(f"source_commit must be a 7-40 character hex commit, found {manifest.source_commit!r}")
    try:
        parse_time(manifest.created)
    except (TypeError, ValueError):
        found.append(f"created is not an ISO-8601 timestamp: {manifest.created!r}")

    if len(manifest.supersedes) > MAX_SUPERSEDES:
        found.append(f"supersedes holds {len(manifest.supersedes)} digests; the cap is {MAX_SUPERSEDES}")
    if len(set(manifest.supersedes)) != len(manifest.supersedes):
        found.append("supersedes contains duplicates")
    for withdrawn in manifest.supersedes:
        if not is_digest(withdrawn):
            found.append(f"supersedes entry is not a digest: {withdrawn!r}")
        if withdrawn == manifest.digest:
            found.append("supersedes contains the digest the channel points at")

    if manifest.rollout is not None:
        rollout = manifest.rollout
        if type(rollout.percentage) is not int or not 0 <= rollout.percentage <= 100:
            found.append(f"rollout.percentage must be an integer 0-100, found {rollout.percentage!r}")
        if not rollout.seed:
            found.append("rollout.seed is empty; a rollout needs a seed for deterministic bucketing")
        try:
            parse_time(rollout.started)
        except (TypeError, ValueError):
            found.append(f"rollout.started is not an ISO-8601 timestamp: {rollout.started!r}")

    if manifest.channel == "stable":
        if manifest.version is None:
            found.append("stable requires a version assigned at promotion")
        elif VERSION_PATTERN.match(manifest.version) is None:
            found.append(f"version must be MAJOR.MINOR.PATCH, found {manifest.version!r}")
        if manifest.release != (f"v{manifest.version}" if manifest.version else None):
            found.append(f"release must be 'v' + version, found {manifest.release!r}")
    elif manifest.version is not None or manifest.release is not None:
        found.append(f"{manifest.channel} has no version or release; both are assigned only on promotion to stable")

    if manifest.min_source_version is not None and VERSION_PATTERN.match(manifest.min_source_version) is None:
        found.append(f"min_source_version must be MAJOR.MINOR.PATCH, found {manifest.min_source_version!r}")

    if manifest.notes_url is not None and not str(manifest.notes_url).startswith(("https://", "http://")):
        found.append(f"notes_url must be http(s), found {manifest.notes_url!r}")

    if require_signature and not manifest.signature:
        found.append("signature is empty")

    return found


def validate(manifest: ChannelManifest, *, require_signature: bool = False) -> ChannelManifest:
    found = problems(manifest, require_signature=require_signature)
    if found:
        raise ManifestError("invalid channel file:\n  - " + "\n  - ".join(found))
    return manifest
