from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aios_release.evidence import Evidence
from aios_release.manifest import ChannelManifest, Rollout, format_time

BASE = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


def digest(char: str) -> str:
    return "sha256:" + char * 64


def commit(char: str = "a") -> str:
    return char * 12


def build_id(when: datetime, char: str = "a") -> str:
    return f"{when:%Y.%m.%d}+g{commit(char)[:7]}.r1"


def build(sha: str, when: datetime, char: str = "a") -> Evidence:
    return Evidence(
        kind="build",
        digest=sha,
        build_id=build_id(when, char),
        source_commit=commit(char),
        result="pass",
        created=format_time(when),
    )


def image(sha: str, when: datetime, char: str = "a") -> Evidence:
    return Evidence(
        kind="image",
        digest=sha,
        source_commit=commit(char),
        result="pass",
        created=format_time(when),
        checks={"lint": "pass"},
    )


def boots(
    sha: str,
    when: datetime,
    count: int = 5,
    result: str = "pass",
    char: str = "a",
) -> list[Evidence]:
    return [
        Evidence(
            kind="boot",
            digest=sha,
            source_commit=commit(char),
            result=result,
            created=format_time(when + timedelta(hours=index + 1)),
        )
        for index in range(count)
    ]


def hardware(sha: str, when: datetime, gpu_context: str = "pass", char: str = "a") -> Evidence:
    return Evidence(
        kind="hw",
        digest=sha,
        source_commit=commit(char),
        result="pass",
        created=format_time(when),
        checks={"gpu_context": gpu_context, "nvidia_module": "pass"},
    )


def promotion(sha: str, channel: str, when: datetime, char: str = "a") -> Evidence:
    return Evidence(
        kind="promotion",
        digest=sha,
        channel=channel,
        source_commit=commit(char),
        result="pass",
        created=format_time(when),
    )


def manifest(
    channel: str,
    sha: str,
    created: datetime,
    *,
    version: str | None = None,
    supersedes: tuple[str, ...] = (),
    rollout: Rollout | None = None,
    min_source_version: str | None = None,
    char: str = "a",
) -> ChannelManifest:
    return ChannelManifest(
        channel=channel,
        digest=sha,
        build_id=build_id(created, char),
        source_commit=commit(char),
        created=format_time(created),
        version=version,
        release=f"v{version}" if version else None,
        supersedes=supersedes,
        rollout=rollout,
        min_source_version=min_source_version,
    )
