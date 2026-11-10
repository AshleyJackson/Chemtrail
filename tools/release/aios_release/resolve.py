"""Device-side resolution: may this machine move, and if not, why not.

The client asks five questions in a fixed order. Each one has a reason code so
``aios update status`` can say which clause is holding, instead of "up to date"
when it means "you are in the 95% that did not get the rollout".

Pure by design: the caller supplies the clock, the machine identity, and the
local blacklist. No network, no filesystem, no bootc invocation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .manifest import ChannelManifest, ManifestError, parse_version

UP_TO_DATE = "up-to-date"
UPDATE = "update"
DEFERRED = "deferred"
BLOCKED = "blocked"


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    detail: str
    bucket: int | None = None

    def __str__(self) -> str:
        suffix = "" if self.bucket is None else f" (bucket {self.bucket})"
        return f"{self.action}: {self.reason}{suffix} — {self.detail}"


def bucket_for(machine_id: str, seed: str) -> int:
    """Deterministic 0-99 bucket.

    ``machine_id`` and ``seed`` are joined with a NUL so ``ab`` + ``c`` and
    ``a`` + ``bc`` cannot collide. blake2b is in the standard library, which
    matters: the update client should not need a crypto dependency to decide
    whether it is in a rollout.
    """
    material = machine_id.encode("utf-8") + b"\x00" + seed.encode("utf-8")
    digest = hashlib.blake2b(material, digest_size=4).digest()
    return int.from_bytes(digest, "big") % 100


def classify(*, action: str, reason: str, detail: str, bucket: int | None = None) -> Decision:
    return Decision(action=action, reason=reason, detail=detail, bucket=bucket)


def resolve(
    *,
    manifest: ChannelManifest,
    running_digest: str,
    machine_id: str,
    running_version: str | None = None,
    bad_digests: Iterable[str] = (),
    now: datetime | None = None,
) -> Decision:
    """Decide what the device should do with the channel it follows.

    Signature verification happens before this function is called: an unsigned
    or invalid manifest must never reach here. This function assumes the file is
    authentic, not that it is sensible — hence the defensive checks.
    """
    candidate = manifest.digest
    blacklist = set(bad_digests)

    if candidate in blacklist:
        return classify(
            action=BLOCKED,
            reason="candidate-blacklisted",
            detail=f"{candidate} failed on this device and will not be retried",
        )
    if candidate in manifest.supersedes:
        return classify(
            action=BLOCKED,
            reason="candidate-withdrawn",
            detail="the channel file points at a digest it also withdraws; refusing to install it",
        )
    if candidate == running_digest:
        return classify(
            action=UP_TO_DATE,
            reason="running-candidate",
            detail=f"running the digest {manifest.channel} names",
        )

    if manifest.rollout is not None and manifest.rollout.percentage < 100:
        bucket = bucket_for(machine_id, manifest.rollout.seed)
        if bucket >= manifest.rollout.percentage:
            return classify(
                action=DEFERRED,
                reason="rollout-ineligible",
                detail=(
                    f"{manifest.rollout.percentage}% rollout; this device is in the "
                    f"remaining {100 - manifest.rollout.percentage}%"
                ),
                bucket=bucket,
            )
    else:
        bucket = None

    withdrawn_running = running_digest in manifest.supersedes
    if manifest.min_source_version:
        floor = parse_version(manifest.min_source_version)
        try:
            have = parse_version(running_version) if running_version else (0, 0, 0)
        except ManifestError:
            # A nightly build carries a build id rather than a version. It is
            # older than any migration floor by definition.
            have = (0, 0, 0)
        if have < floor:
            return classify(
                action=BLOCKED,
                reason="state-migration-required",
                detail=(
                    f"this update expects /var state from {manifest.min_source_version} "
                    f"or later; running {running_version or 'an unversioned build'}"
                ),
                bucket=bucket,
            )

    if withdrawn_running:
        return classify(
            action=UPDATE,
            reason="running-withdrawn",
            detail=f"{running_digest} was withdrawn; moving to {candidate}",
            bucket=bucket,
        )
    return classify(
        action=UPDATE,
        reason="candidate-newer",
        detail=f"{manifest.channel} now names {candidate}",
        bucket=bucket,
    )


def rollout_snapshot(manifest: ChannelManifest, machine_ids: Iterable[str]) -> dict[str, int]:
    """How a rollout lands on a population. Used by tests and by the demo."""
    if manifest.rollout is None:
        return {"eligible": -1, "total": -1}
    eligible = 0
    total = 0
    for machine_id in machine_ids:
        total += 1
        if bucket_for(machine_id, manifest.rollout.seed) < manifest.rollout.percentage:
            eligible += 1
    return {"eligible": eligible, "total": total}
