"""Four weeks of the release pipeline, simulated, with no image and no network.

This exists so the machinery can be exercised before a single byte of the OS is
built: four dummy digests are built, promoted to nightly, soaked, promoted to
weekly, promoted to stable at 5%, and finally widened to 100%. The output is a
set of real, signed, schema-valid channel files you can diff.

    python -m aios_release demo --out .demo
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import evidence, promote, resolve
from .manifest import ChannelManifest, format_time
from .signing import DevHmacSigner

DEMO_KEY = b"demo-only-not-a-secret"


def digest_for(label: str) -> str:
    return "sha256:" + hashlib.sha256(f"aios-demo-{label}".encode("utf-8")).hexdigest()


def commit_for(label: str) -> str:
    return hashlib.sha1(f"aios-demo-commit-{label}".encode("utf-8")).hexdigest()[:12]


def _boots(digest: str, commit: str, when: datetime, count: int = 5) -> list[evidence.Evidence]:
    return [
        evidence.Evidence(
            kind="boot",
            digest=digest,
            source_commit=commit,
            result="pass",
            created=format_time(when + timedelta(hours=index + 1)),
            checks={"compositor": "pass", "agentd": "pass", "gpu_context": "skip"},
        )
        for index in range(count)
    ]


def run(out: Path, now: datetime | None = None) -> None:
    base = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    out = Path(out)
    (out / "channels").mkdir(parents=True, exist_ok=True)

    signer = DevHmacSigner(DEMO_KEY, key_id="demo")
    records: list[evidence.Evidence] = []
    channels: dict[str, ChannelManifest] = {}

    t0 = base - timedelta(days=21)
    t1 = base - timedelta(days=14)
    t2 = base - timedelta(days=7)
    t3 = base

    labels = {"A": t0, "B": t1, "C": t2, "D": t3}
    digests = {label: digest_for(label) for label in labels}
    commits = {label: commit_for(label) for label in labels}

    print(f"simulating four weeks, ending {format_time(base)}\n")
    print(f"{'when':<17} {'action':<9} {'channel':<8} {'version':<8} digest")
    print("-" * 78)

    def log(when: datetime, action: str, channel: str, manifest: ChannelManifest | None) -> None:
        version = (manifest.version if manifest else None) or "-"
        digest = (manifest.digest if manifest else "")[:19]
        rollout = (
            ""
            if manifest is None or manifest.rollout is None
            else f", {manifest.rollout.percentage}% rollout"
        )
        print(f"{format_time(when):<17} {action:<9} {channel:<8} {version:<8} {digest}{rollout}")

    def record_build(label: str, when: datetime) -> None:
        records.append(
            evidence.build_record(
                digest=digests[label],
                build_id=f"{when:%Y.%m.%d}+g{commits[label][:7]}.r{len(labels)}",
                source_commit=commits[label],
                now=when,
                labels={"base_digest": "sha256:" + "0" * 64, "nvidia_branch": "620"},
            )
        )
        records.append(
            evidence.Evidence(
                kind="image",
                digest=digests[label],
                source_commit=commits[label],
                result="pass",
                created=format_time(when + timedelta(minutes=10)),
                checks={"lint": "pass"},
            )
        )
        records.extend(_boots(digests[label], commits[label], when))
        log(when, "build", "-", None)
        print(f"{'':<17} {'':<9} {'':<8} {'':<8} {digests[label]}")

    def record_hardware(label: str, when: datetime) -> None:
        records.append(
            evidence.Evidence(
                kind="hw",
                digest=digests[label],
                source_commit=commits[label],
                result="pass",
                created=format_time(when),
                checks={"gpu_context": "pass", "nvidia_module": "pass", "tokens_per_second": "62"},
            )
        )

    def promote_to(channel: str, label: str, when: datetime, **kwargs) -> None:
        manifest, _ = promote.promote(
            channel=channel,
            candidate_digest=digests[label],
            evidence=tuple(records),
            prior=dict(channels),
            now=when,
            signer=signer,
            **kwargs,
        )
        manifest.dump(out / "channels" / f"{channel}.json")
        records.append(promote.promotion_record(manifest, when))
        channels[channel] = manifest
        log(when, "promote", channel, manifest)

    # Week 1: A is built and enters nightly.
    record_build("A", t0)
    promote_to("nightly", "A", t0)

    # Week 2: A has soaked for seven days and boots five times; B is built.
    record_hardware("A", t0 + timedelta(days=1))
    record_build("B", t1)
    promote_to("weekly", "A", t1)
    promote_to("nightly", "B", t1)

    # Week 3: A has a week as weekly plus a GPU pass; C is built.
    record_build("C", t2)
    promote_to("stable", "A", t2)
    staged_stable = channels["stable"]
    promote_to("weekly", "B", t2)
    promote_to("nightly", "C", t2)

    # Week 4: stable's 5% rollout has run a week; D is built.
    record_build("D", t3)
    widened = promote.widen(channels["stable"], now=t3, signer=signer)
    widened.dump(out / "channels" / "stable.json")
    channels["stable"] = widened
    log(t3, "widen", "stable", widened)
    promote_to("weekly", "C", t3)
    promote_to("nightly", "D", t3)

    print("-" * 78)
    print("\nfinal pointers")
    for channel, manifest in channels.items():
        target = manifest.version or "(no version; build " + manifest.build_id + ")"
        rollout = "" if manifest.rollout is None else f", {manifest.rollout.percentage}% rollout"
        print(f"  {channel:<8} {manifest.digest[:19]}  {target}{rollout}")

    machines = [f"machine-{index:04d}" for index in range(1000)]
    snapshot = resolve.rollout_snapshot(staged_stable, machines)
    print(
        f"\nwhile stable was at {staged_stable.rollout.percentage}%, "
        f"{snapshot['eligible']}/{snapshot['total']} simulated devices were eligible — "
        "deterministically, with no telemetry and no device registry"
    )

    stable_file = out / "channels" / "stable.json"
    print("\ntry the device side against the file just written:")
    print(
        f"  python -m aios_release resolve --manifest {stable_file} "
        f"--running-digest {digests['D']} --machine-id machine-0007"
    )
    print(f"\nchannel files: {out / 'channels'}")
