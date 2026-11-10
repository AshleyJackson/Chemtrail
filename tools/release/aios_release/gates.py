"""Promotion gates, as checks over recorded evidence.

A gate is a fact about a **digest**, so every check here reads evidence records
for that exact digest. There is no inference from a branch, a tag, or "the build
that ran before". If the evidence is missing, the gate fails, loudly.

Soak is measured from a ``promotion`` evidence record, not from the channel
pointer. The pointer is mutable and moving it is the thing being decided; using
it as the clock would make nightly promotion stop weekly promotion forever,
because nightly always points at a build from minutes ago.

Thresholds live in :data:`GATES` and nowhere else. They are product decisions
(ADR-0015 §4), so changing one should be a visible edit, not a side effect of
somebody's refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from .evidence import Evidence
from .manifest import ChannelManifest, parse_time

SECONDS_PER_DAY = 86_400.0


class GateError(RuntimeError):
    """A promotion was attempted that the evidence does not support."""


@dataclass(frozen=True)
class Gate:
    channel: str
    min_boot_passes: int
    min_hw_passes: int
    min_image_checks: int = 0
    from_channel: str | None = None
    min_soak_days: float = 0.0


GATES: Mapping[str, Gate] = {
    # Per commit. Cheap gate: it built and passed the static image checks.
    # Deliberately not a boot: hosted runners have no KVM. Once boot-test.yml has
    # a runner, raise this to a real boot — nightly should mean "it starts" to
    # anyone reading the channel description.
    "nightly": Gate("nightly", min_boot_passes=0, min_hw_passes=0, min_image_checks=1),
    # Seven days as a nightly, and five boots that reached a session.
    "weekly": Gate(
        "weekly",
        min_boot_passes=5,
        min_hw_passes=0,
        from_channel="nightly",
        min_soak_days=7.0,
    ),
    # A week as a weekly, five boots, and a real GPU pass. The only gate that
    # cannot be fully automated on hosted runners.
    "stable": Gate(
        "stable",
        min_boot_passes=5,
        min_hw_passes=1,
        from_channel="weekly",
        min_soak_days=7.0,
    ),
}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class GateResult:
    channel: str
    checks: tuple[Check, ...]
    emergency: bool = False
    approvals: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.ok)

    def summary(self) -> str:
        lines = [f"{self.channel}: {'PASS' if self.ok else 'FAIL'}"
                 + (" (emergency lane)" if self.emergency else "")]
        for check in self.checks:
            mark = "x" if check.ok else " "
            detail = f" — {check.detail}" if check.detail else ""
            lines.append(f"  [{mark}] {check.name}{detail}")
        return "\n".join(lines)


def _pass_count(records: Sequence[Evidence]) -> int:
    return sum(1 for record in records if record.result == "pass")


def _latest(records: Sequence[Evidence], kind: str) -> Evidence | None:
    matching = [record for record in records if record.kind == kind]
    return max(matching, key=lambda r: r.time) if matching else None


def evaluate(
    *,
    channel: str,
    candidate_digest: str,
    evidence: Sequence[Evidence],
    prior: Mapping[str, ChannelManifest],
    now: datetime,
    emergency: bool = False,
    approvals: Sequence[str] = (),
) -> GateResult:
    """Evaluate the gate for ``channel`` against evidence for one digest."""
    gate = GATES.get(channel)
    if gate is None:
        raise GateError(f"unknown channel {channel!r}")

    records = [record for record in evidence if record.digest == candidate_digest]
    boots = sorted((record for record in records if record.kind == "boot"), key=lambda r: r.time)
    hardware = sorted((record for record in records if record.kind == "hw"), key=lambda r: r.time)

    checks: list[Check] = []
    builds = [record for record in records if record.kind == "build"]
    build = _latest(records, "build")
    built = build is not None and build.result == "pass"
    checks.append(Check(
        "image-built",
        built,
        "no build record for this digest" if build is None
        else f"{build.build_id or 'unknown build'} {build.result}",
    ))
    if not built:
        # Without a build there is no digest to reason about. Stop rather than
        # emitting a page of derived failures that hide the real one.
        return GateResult(channel, tuple(checks), emergency, tuple(approvals))

    assert build is not None
    competing = sorted({b.build_id for b in builds if b.build_id and b.build_id != build.build_id})
    checks.append(Check(
        "one-build-per-digest",
        not competing,
        "" if not competing else f"also claimed by {', '.join(competing)}",
    ))

    if gate.min_image_checks:
        image_passes = [
            record for record in records if record.kind == "image" and record.result == "pass"
        ]
        checks.append(Check(
            "image-check",
            len(image_passes) >= gate.min_image_checks,
            f"{len(image_passes)} pass(es), need {gate.min_image_checks}",
        ))

    if build.source_commit:
        divergent = sorted({r.source_commit for r in records if r.source_commit and r.source_commit != build.source_commit})
        checks.append(Check(
            "provenance",
            not divergent,
            "" if not divergent else f"records cite other commits: {', '.join(divergent)}",
        ))

    if gate.from_channel:
        entries = [
            record
            for record in records
            if record.kind == "promotion" and record.channel == gate.from_channel and record.result == "pass"
        ]
        entry = max(entries, key=lambda r: r.time) if entries else None
        if emergency:
            checks.append(Check(
                f"entered-{gate.from_channel}",
                True,
                "bypassed by emergency lane",
            ))
        else:
            checks.append(Check(
                f"entered-{gate.from_channel}",
                entry is not None,
                "no promotion record; this digest never went through the channel below",
            ))
        if entry is not None:
            age_days = (now - entry.time).total_seconds() / SECONDS_PER_DAY
            if emergency:
                checks.append(Check("soak-in-channel", True, f"bypassed by emergency lane ({age_days:.1f}d)"))
            else:
                checks.append(Check(
                    "soak-in-channel",
                    age_days >= gate.min_soak_days,
                    f"{age_days:.1f}d in {gate.from_channel}, need {gate.min_soak_days:.0f}d",
                ))
        elif not emergency:
            checks.append(Check("soak-in-channel", False, f"never entered {gate.from_channel}"))

    boot_passes = _pass_count(boots)
    checks.append(Check(
        "boot-passes",
        boot_passes >= gate.min_boot_passes,
        f"{boot_passes} passed of {len(boots)} run(s), need {gate.min_boot_passes}",
    ))

    latest_boot = boots[-1] if boots else None
    if latest_boot is not None:
        checks.append(Check("latest-boot-pass", latest_boot.result == "pass",
                            f"last boot was {latest_boot.result}"))
    elif gate.min_boot_passes:
        checks.append(Check("latest-boot-pass", False, "no boot evidence"))

    hw_passes = [record for record in hardware if record.result == "pass"]
    if gate.min_hw_passes:
        checks.append(Check(
            "hardware-pass",
            len(hw_passes) >= gate.min_hw_passes,
            f"{len(hw_passes)} pass(es), need {gate.min_hw_passes}",
        ))
        gpu_context = any(record.checks.get("gpu_context") == "pass" for record in hw_passes)
        checks.append(Check(
            "gpu-context",
            gpu_context,
            "the driver loaded but no GPU context was created" if hw_passes and not gpu_context
            else ("" if gpu_context else "no hardware evidence"),
        ))
    else:
        checks.append(Check(
            "hardware-evidence",
            True,
            f"{len(hw_passes)} hardware pass(es); not required for {channel}",
        ))

    p1 = [record for record in records if record.known_p1]
    checks.append(Check(
        "no-known-p1",
        not p1,
        "" if not p1 else f"{len(p1)} record(s) marked P1",
    ))

    withdrawn = sorted({digest for manifest in prior.values() for digest in manifest.supersedes})
    checks.append(Check(
        "not-withdrawn",
        candidate_digest not in withdrawn,
        "this digest was withdrawn from a channel" if candidate_digest in withdrawn else "",
    ))

    if emergency:
        distinct = tuple(sorted({approval.strip() for approval in approvals if approval and approval.strip()}))
        checks.append(Check(
            "two-approvals",
            len(distinct) >= 2,
            f"approved by {', '.join(distinct) or 'nobody'}; the emergency lane needs two",
        ))

    return GateResult(channel, tuple(checks), emergency, tuple(approvals))


def require(result: GateResult) -> GateResult:
    if result.ok:
        return result
    failures = "; ".join(f"{check.name} ({check.detail})" for check in result.failures)
    raise GateError(f"{result.channel} gate failed: {failures}")
