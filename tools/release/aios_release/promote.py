"""Promotion: the only operation that changes what users receive.

Nothing in this module builds or pulls an image. It reads evidence, checks a
gate, and writes a new pointer. If a function here ever needs a registry, the
design has drifted (ADR-0015).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from . import gates
from .evidence import Evidence
from .gates import GateResult
from .manifest import (
    MAX_SUPERSEDES,
    VERSION_PATTERN,
    ChannelManifest,
    Rollout,
    format_time,
    parse_time,
    parse_version,
    validate,
)
from .signing import Signer, UnsignedSigner, sign_manifest

SECONDS_PER_DAY = 86_400.0


class PromotionError(RuntimeError):
    """The requested promotion is not a legal state transition."""


def next_version(current: ChannelManifest | None, now: datetime) -> str:
    """Assign the next stable version.

    Deterministic from the current pointer alone, so it can be tested and
    replayed:

    * no current stable → ``1.0.0``;
    * a new calendar month → minor bump, patch reset;
    * otherwise → patch bump.

    Majors are manual. Nothing in an automated pipeline should decide that the
    next release is 2.0.
    """
    if current is None or current.version is None:
        return "1.0.0"
    major, minor, patch = parse_version(current.version)
    released = parse_time(current.created)
    if (now.year, now.month) > (released.year, released.month):
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def default_seed(now: datetime, digest: str) -> str:
    """A seed per promotion: the population is re-rolled for each new digest."""
    return f"{now:%Y-%m}-{digest[-4:]}"


def _supersedes(current: ChannelManifest | None, candidate_digest: str) -> tuple[str, ...]:
    """Withdrawals, carried forward across promotions.

    ``supersedes`` means **withdrawn**, not "the digest this one replaces". Git
    history already records the chain, and conflating the two would make every
    digest that nightly ever replaced look unsafe to promote, which would stop
    the pipeline at the first weekly promotion.
    """
    if current is None:
        return ()
    ordered = dict.fromkeys(digest for digest in current.supersedes if digest != candidate_digest)
    return tuple(ordered)[:MAX_SUPERSEDES]


def _built_digests(evidence: Sequence[Evidence]) -> list[str]:
    """Digests with a successful build, newest first."""
    newest: dict[str, datetime] = {}
    for record in evidence:
        if record.kind == "build" and record.result == "pass":
            newest[record.digest] = max(newest.get(record.digest, record.time), record.time)
    return sorted(newest, key=lambda digest: newest[digest], reverse=True)


def _entered_channel(evidence: Sequence[Evidence], channel: str) -> list[str]:
    """Digests promoted to ``channel``, most recently first.

    This is the candidate list for the channel above it. Using the promotion
    record rather than the channel pointer is what makes the pipeline work: the
    nightly pointer always names a build from minutes ago, so it can never
    satisfy "has been in nightly for a week".
    """
    entered: dict[str, datetime] = {}
    for record in evidence:
        if record.kind == "promotion" and record.channel == channel and record.result == "pass":
            entered[record.digest] = max(entered.get(record.digest, record.time), record.time)
    return sorted(entered, key=lambda digest: entered[digest], reverse=True)


def select_candidate(
    *,
    channel: str,
    evidence: Sequence[Evidence],
    prior: Mapping[str, ChannelManifest],
    now: datetime,
) -> str | None:
    """Which digest (if any) should be promoted to ``channel`` right now.

    Candidates are ordered newest first and the first one whose gate passes wins.
    A newer digest that has not finished soaking does not block an older one that
    has, and a digest that never reached the channel below cannot skip it.
    """
    if channel == "nightly":
        candidates = _built_digests(evidence)
    elif channel == "weekly":
        candidates = _entered_channel(evidence, "nightly")
    elif channel == "stable":
        candidates = _entered_channel(evidence, "weekly")
    else:
        raise PromotionError(f"unknown channel {channel!r}")

    current = prior.get(channel)
    if current is not None:
        candidates = [digest for digest in candidates if digest != current.digest]

    for candidate in candidates:
        result = gates.evaluate(
            channel=channel,
            candidate_digest=candidate,
            evidence=evidence,
            prior=prior,
            now=now,
        )
        if result.ok:
            return candidate
    return None


def promote(
    *,
    channel: str,
    candidate_digest: str,
    evidence: Sequence[Evidence],
    prior: Mapping[str, ChannelManifest],
    now: datetime,
    signer: Signer,
    version: str | None = None,
    rollout_percentage: int = 5,
    seed: str | None = None,
    min_source_version: str | None = None,
    notes_url: str | None = None,
    emergency: bool = False,
    approvals: Sequence[str] = (),
) -> tuple[ChannelManifest, GateResult]:
    """Produce the next channel file for ``channel``. It never rebuilds."""
    if channel not in ("nightly", "weekly", "stable"):
        raise PromotionError(f"unknown channel {channel!r}")

    current = prior.get(channel)
    if current is not None and current.digest == candidate_digest:
        raise PromotionError(
            f"{channel} already points at {candidate_digest}; promotion is a no-op"
        )

    result = gates.evaluate(
        channel=channel,
        candidate_digest=candidate_digest,
        evidence=evidence,
        prior=prior,
        now=now,
        emergency=emergency,
        approvals=approvals,
    )
    gates.require(result)

    builds = sorted(
        (
            record
            for record in evidence
            if record.digest == candidate_digest and record.kind == "build" and record.result == "pass"
        ),
        key=lambda record: record.time,
    )
    if not builds:
        # gates.require already covers this, but the type checker cannot know.
        raise PromotionError(f"no successful build record for {candidate_digest}")
    build = builds[-1]
    if not build.build_id or not build.source_commit:
        raise PromotionError("the build record is missing build_id or source_commit")

    supersedes = _supersedes(current, candidate_digest)

    assigned_version: str | None = None
    release: str | None = None
    rollout: Rollout | None = None

    if channel == "stable":
        assigned_version = version or next_version(current, now)
        if VERSION_PATTERN.match(assigned_version) is None:
            raise PromotionError(f"version must be MAJOR.MINOR.PATCH, found {assigned_version!r}")
        if current is not None and current.version is not None:
            if parse_version(assigned_version) <= parse_version(current.version):
                raise PromotionError(
                    f"version {assigned_version} must be greater than the current {current.version}; "
                    "a published version cannot be reused"
                )
        release = f"v{assigned_version}"
        if not 0 <= rollout_percentage <= 100:
            raise PromotionError("rollout percentage must be 0-100")
        if rollout_percentage < 100:
            rollout = Rollout(
                percentage=rollout_percentage,
                seed=seed or default_seed(now, candidate_digest),
                started=format_time(now),
            )
    elif version is not None or release is not None:
        raise PromotionError("only stable carries a version; it is assigned at promotion")

    manifest = ChannelManifest(
        channel=channel,
        digest=candidate_digest,
        build_id=build.build_id,
        source_commit=build.source_commit,
        created=format_time(now),
        supersedes=supersedes,
        version=assigned_version,
        release=release,
        rollout=rollout,
        min_source_version=min_source_version,
        notes_url=notes_url,
    )
    validate(manifest)
    signed = sign_manifest(manifest, signer)
    validate(signed, require_signature=not isinstance(signer, UnsignedSigner))
    return signed, result


def widen(
    manifest: ChannelManifest,
    *,
    now: datetime,
    signer: Signer,
    min_days: float = 7.0,
    force: bool = False,
) -> ChannelManifest:
    """Take a staged rollout to 100% without touching the digest or the version.

    ``created`` is deliberately left alone: it records when this digest became
    the pointer, which is the anchor the soak checks and version arithmetic use.
    The widening is visible in git history and in the rollout field itself.
    """
    if manifest.channel != "stable":
        raise PromotionError("only stable has a staged rollout")
    if manifest.rollout is None or manifest.rollout.percentage >= 100:
        raise PromotionError(f"{manifest.channel} is not in a staged rollout")
    age_days = (now - parse_time(manifest.rollout.started)).total_seconds() / SECONDS_PER_DAY
    if age_days < min_days and not force:
        raise PromotionError(
            f"rollout is {age_days:.1f}d old; widening needs {min_days:.0f}d (or --force)"
        )
    widened = replace(
        manifest,
        rollout=Rollout(100, manifest.rollout.seed, manifest.rollout.started),
        signature="",
    )
    validate(widened)
    signed = sign_manifest(widened, signer)
    validate(signed, require_signature=not isinstance(signer, UnsignedSigner))
    return signed


def withdraw(
    *,
    current: ChannelManifest,
    target: ChannelManifest,
    now: datetime,
    signer: Signer,
    bad_digest: str | None = None,
) -> ChannelManifest:
    """Move a channel back to a known-good digest and record why.

    The replacement is published under a **new** version, because the version
    that shipped the regression is taken: a GitHub release's tag is immutable, so
    reusing ``v1.4.0`` is impossible and reusing ``1.4.0`` for different notes
    would be a lie. ``1.4.1`` that reverts ``1.4.0``'s change is the standard
    and honest form.

    ``target`` carries the digest to return to; it is normally the previous
    channel file from git history (see tools/release/README.md).
    """
    if current.channel != target.channel:
        raise PromotionError("both manifests must belong to the same channel")
    bad = bad_digest or current.digest
    if bad == target.digest:
        raise PromotionError("cannot withdraw the digest being restored")
    if bad != current.digest and bad not in current.supersedes:
        raise PromotionError(f"{bad} is not the current or a recently withdrawn digest")
    if current.channel != "stable":
        raise PromotionError("nightly and weekly move by promotion alone; nothing to withdraw")

    supersedes = tuple(
        dict.fromkeys(digest for digest in [bad, *target.supersedes] if digest != target.digest)
    )[:MAX_SUPERSEDES]

    version = next_version(current, now)
    withdrawn = replace(
        target,
        created=format_time(now),
        supersedes=supersedes,
        version=version,
        release=f"v{version}",
        rollout=None,
        signature="",
    )
    validate(withdrawn)
    signed = sign_manifest(withdrawn, signer)
    validate(signed, require_signature=not isinstance(signer, UnsignedSigner))
    return signed


def promotion_record(manifest: ChannelManifest, now: datetime) -> Evidence:
    """The evidence a promotion leaves behind.

    CI uploads this as an artefact. It is what lets the *next* gate ask "how long
    has this digest been in the channel below?" without reading git history or
    trusting a pointer that has since moved.
    """
    return Evidence(
        kind="promotion",
        digest=manifest.digest,
        channel=manifest.channel,
        build_id=manifest.build_id,
        source_commit=manifest.source_commit,
        result="pass",
        created=format_time(now),
    )


def withdrawal_versions(manifests: Iterable[ChannelManifest]) -> set[str]:
    """Versions already consumed by a channel, for diagnostics."""
    return {manifest.version for manifest in manifests if manifest.version}
