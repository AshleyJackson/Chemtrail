"""Command line for the release machinery.

Every command is a thin wrapper around a pure function. That is deliberate: the
workflow file should contain scheduling and git plumbing, and nothing that could
be wrong in a way tests cannot catch.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import __version__, demo, evidence, gates, promote, resolve
from .manifest import (
    CHANNELS,
    ChannelManifest,
    ManifestError,
    format_time,
    parse_time,
    validate,
)
from .signing import DevHmacSigner, UnsignedSigner, signer_from_spec, verify_manifest

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


def _now(args: argparse.Namespace) -> datetime:
    if getattr(args, "now", None):
        return parse_time(args.now)
    return datetime.now(timezone.utc)


def _prior(channel_dir: str | Path) -> dict[str, ChannelManifest]:
    found: dict[str, ChannelManifest] = {}
    directory = Path(channel_dir)
    for channel in CHANNELS:
        path = directory / f"{channel}.json"
        if path.exists():
            found[channel] = ChannelManifest.load(path)
    return found


def _signer(args: argparse.Namespace):
    if getattr(args, "unsigned", False):
        return UnsignedSigner()
    spec = getattr(args, "sign", None)
    if not spec:
        raise ManifestError("choose --sign hmac:<ENV_VAR> or --unsigned explicitly")
    return signer_from_spec(spec)


def _print_checks(result: gates.GateResult) -> None:
    print(result.summary())


def cmd_plan(args: argparse.Namespace) -> int:
    records = evidence.load(args.evidence_dir)
    result = gates.evaluate(
        channel=args.channel,
        candidate_digest=args.candidate,
        evidence=records,
        prior=_prior(args.channels),
        now=_now(args),
        emergency=args.emergency,
        approvals=args.approved_by,
    )
    _print_checks(result)
    return EXIT_OK if result.ok else EXIT_REFUSED


def cmd_select(args: argparse.Namespace) -> int:
    records = evidence.load(args.evidence_dir)
    candidate = promote.select_candidate(
        channel=args.channel,
        evidence=records,
        prior=_prior(args.channels),
        now=_now(args),
    )
    if candidate is None:
        print(
            f"nothing eligible for {args.channel}: no digest currently passes its gate",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    print(candidate)
    return EXIT_OK


def cmd_promote(args: argparse.Namespace) -> int:
    records = evidence.load(args.evidence_dir)
    prior = _prior(args.channels)
    signer = _signer(args)
    now = _now(args)
    manifest, result = promote.promote(
        channel=args.channel,
        candidate_digest=args.candidate,
        evidence=records,
        prior=prior,
        now=now,
        signer=signer,
        version=args.version,
        rollout_percentage=args.rollout,
        seed=args.seed,
        min_source_version=args.min_source_version,
        notes_url=args.notes_url,
        emergency=args.emergency,
        approvals=args.approved_by,
    )
    _print_checks(result)
    manifest.dump(args.out)
    if args.promotion_record_out:
        evidence.dump(promote.promotion_record(manifest, now), args.promotion_record_out)
    print(f"wrote {args.out}: {manifest.channel} -> {manifest.digest}"
          + (f" ({manifest.version})" if manifest.version else ""))
    return EXIT_OK


def cmd_widen(args: argparse.Namespace) -> int:
    path = Path(args.channels) / "stable.json"
    current = ChannelManifest.load(path)
    widened = promote.widen(
        current,
        now=_now(args),
        signer=_signer(args),
        min_days=args.min_days,
        force=args.force,
    )
    widened.dump(args.out)
    print(f"wrote {args.out}: stable rollout {current.rollout.percentage if current.rollout else 100}% -> 100%")
    return EXIT_OK


def cmd_withdraw(args: argparse.Namespace) -> int:
    current = ChannelManifest.load(Path(args.channels) / f"{args.channel}.json")
    target = ChannelManifest.load(args.target_manifest)
    withdrawn = promote.withdraw(
        current=current,
        target=target,
        now=_now(args),
        signer=_signer(args),
        bad_digest=args.bad,
    )
    withdrawn.dump(args.out)
    print(
        f"wrote {args.out}: {args.channel} -> {withdrawn.digest} as {withdrawn.version}; "
        f"withdrew {args.bad or current.digest}"
    )
    return EXIT_OK


def cmd_attach_signature(args: argparse.Namespace) -> int:
    manifest = ChannelManifest.load(args.manifest)
    signature = Path(args.signature_file).read_text(encoding="utf-8").strip()
    if not signature:
        raise ManifestError(f"{args.signature_file} is empty")
    signed = manifest.with_signature(signature)
    validate(signed, require_signature=True)
    signed.dump(args.out or args.manifest)
    print(f"attached signature to {args.out or args.manifest}")
    return EXIT_OK


def cmd_payload(args: argparse.Namespace) -> int:
    """Write the canonical bytes a signer signs.

    Deliberately separate from ``verify``: an unsigned manifest is the normal
    intermediate state in CI (promote → sign → attach), and requiring a signature
    to extract the payload would make that flow impossible.
    """
    manifest = validate(ChannelManifest.load(args.manifest))
    Path(args.out).write_bytes(manifest.payload())
    print(f"wrote canonical payload to {args.out}")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    manifest = validate(ChannelManifest.load(args.manifest), require_signature=True)
    if args.hmac_key_env:
        signer = DevHmacSigner(
            _env(args.hmac_key_env).encode("utf-8"), key_id=args.hmac_key_env
        )
        verify_manifest(manifest, signer)
        print(f"{args.manifest}: signature valid (hmac-sha256:{args.hmac_key_env})")
    else:
        print(
            f"{args.manifest}: structurally valid, signature not checked "
            "(pass --hmac-key-env, or verify the payload with cosign)"
        )
    if args.payload_out:
        Path(args.payload_out).write_bytes(manifest.payload())
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    manifest = validate(ChannelManifest.load(args.manifest), require_signature=False)
    bad = ()
    if args.bad_digests:
        bad = tuple(
            line.strip()
            for line in Path(args.bad_digests).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
    decision = resolve.resolve(
        manifest=manifest,
        running_digest=args.running_digest,
        running_version=args.running_version,
        machine_id=args.machine_id,
        bad_digests=bad,
        now=_now(args),
    )
    if args.json:
        print(json.dumps(asdict(decision), indent=2))
    else:
        print(decision)
    return EXIT_OK


def cmd_record(args: argparse.Namespace) -> int:
    """Write one evidence record. Used by the build, check and hardware jobs."""
    record = evidence.Evidence(
        kind=args.kind,
        digest=args.digest,
        build_id=args.build_id,
        source_commit=args.commit,
        channel=args.channel,
        result=args.result,
        created=format_time(_now(args)),
        checks=dict(_pair(item, "--check") for item in args.check),
        labels=dict(_pair(item, "--label") for item in args.label),
        notes=args.notes,
    )
    evidence.dump(record, args.out)
    print(f"wrote {args.out}: {record.kind} {record.digest[:19]} {record.result}")
    return EXIT_OK


def _pair(item: str, flag: str) -> tuple[str, str]:
    if "=" not in item:
        raise ManifestError(f"{flag} expects KEY=VALUE, found {item!r}")
    key, value = item.split("=", 1)
    return key, value


def cmd_demo(args: argparse.Namespace) -> int:
    demo.run(Path(args.out), now=_now(args) if args.now else None)
    return EXIT_OK


def _env(name: str) -> str:
    import os

    value = os.environ.get(name)
    if not value:
        raise ManifestError(f"environment variable {name} is empty or unset")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aios-release",
        description="Promote channel pointers and resolve them on a device.",
    )
    parser.add_argument("--version", action="version", version=f"aios-release {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--channels", default="channels", help="directory holding <channel>.json")
        sp.add_argument("--channel", choices=CHANNELS, required=True)
        sp.add_argument("--now", help="ISO-8601 timestamp; defaults to the current UTC time")

    plan = sub.add_parser("plan", help="evaluate the gate for a digest without writing anything")
    add_common(plan)
    plan.add_argument("--candidate", required=True)
    plan.add_argument("--evidence-dir", default=".evidence")
    plan.add_argument("--emergency", action="store_true")
    plan.add_argument("--approved-by", action="append", default=[])
    plan.set_defaults(func=cmd_plan)

    select = sub.add_parser("select", help="print the digest that should be promoted now")
    add_common(select)
    select.add_argument("--evidence-dir", default=".evidence")
    select.set_defaults(func=cmd_select)

    promote_cmd = sub.add_parser("promote", help="write the next channel file")
    add_common(promote_cmd)
    promote_cmd.add_argument("--candidate", required=True)
    promote_cmd.add_argument("--evidence-dir", default=".evidence")
    promote_cmd.add_argument("--out", required=True)
    promote_cmd.add_argument("--version", help="stable only; defaults to the deterministic next version")
    promote_cmd.add_argument("--rollout", type=int, default=5, help="stable only; percent, default 5")
    promote_cmd.add_argument("--seed", help="stable only; default derives from month + digest")
    promote_cmd.add_argument("--min-source-version")
    promote_cmd.add_argument("--notes-url")
    promote_cmd.add_argument(
        "--promotion-record-out",
        help="write the promotion evidence record here (CI uploads it as an artefact)",
    )
    promote_cmd.add_argument("--emergency", action="store_true")
    promote_cmd.add_argument("--approved-by", action="append", default=[])
    promote_cmd.add_argument("--sign", help="hmac:<ENV_VAR>; use --unsigned to skip deliberately")
    promote_cmd.add_argument("--unsigned", action="store_true", help="write an unsigned file for CI to sign")
    promote_cmd.set_defaults(func=cmd_promote)

    widen = sub.add_parser("widen", help="take a stable rollout to 100%%")
    widen.add_argument("--channels", default="channels")
    widen.add_argument("--out", required=True)
    widen.add_argument("--min-days", type=float, default=7.0)
    widen.add_argument("--force", action="store_true")
    widen.add_argument("--now")
    widen.add_argument("--sign")
    widen.add_argument("--unsigned", action="store_true")
    widen.set_defaults(func=cmd_widen)

    withdraw = sub.add_parser("withdraw", help="return a channel to a known-good digest")
    withdraw.add_argument("--channels", default="channels")
    withdraw.add_argument("--channel", choices=CHANNELS, default="stable")
    withdraw.add_argument("--target-manifest", required=True)
    withdraw.add_argument("--bad")
    withdraw.add_argument("--out", required=True)
    withdraw.add_argument("--now")
    withdraw.add_argument("--sign")
    withdraw.add_argument("--unsigned", action="store_true")
    withdraw.set_defaults(func=cmd_withdraw)

    attach = sub.add_parser("attach-signature", help="insert a CI-produced signature")
    attach.add_argument("--manifest", required=True)
    attach.add_argument("--signature-file", required=True)
    attach.add_argument("--out")
    attach.set_defaults(func=cmd_attach_signature)

    payload = sub.add_parser("payload", help="write the canonical bytes for a signer")
    payload.add_argument("--manifest", required=True)
    payload.add_argument("--out", required=True)
    payload.set_defaults(func=cmd_payload)

    verify = sub.add_parser("verify", help="validate a channel file, optionally its signature")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--hmac-key-env")
    verify.add_argument("--payload-out", help="write the canonical bytes for cosign to verify")
    verify.set_defaults(func=cmd_verify)

    resolve_cmd = sub.add_parser("resolve", help="ask what a device should do")
    resolve_cmd.add_argument("--manifest", required=True)
    resolve_cmd.add_argument("--running-digest", required=True)
    resolve_cmd.add_argument("--running-version")
    resolve_cmd.add_argument("--machine-id", required=True)
    resolve_cmd.add_argument("--bad-digests", help="file holding one blacklisted digest per line")
    resolve_cmd.add_argument("--now")
    resolve_cmd.add_argument("--json", action="store_true")
    resolve_cmd.set_defaults(func=cmd_resolve)

    record = sub.add_parser("record", help="write one evidence record")
    record.add_argument("--kind", required=True, choices=evidence.KINDS)
    record.add_argument("--digest", required=True)
    record.add_argument("--commit")
    record.add_argument("--build-id")
    record.add_argument("--channel", choices=CHANNELS)
    record.add_argument("--result", default="pass", choices=evidence.RESULTS)
    record.add_argument("--check", action="append", default=[], help="KEY=VALUE")
    record.add_argument("--label", action="append", default=[], help="KEY=VALUE")
    record.add_argument("--notes", default="")
    record.add_argument("--now")
    record.add_argument("--out", required=True)
    record.set_defaults(func=cmd_record)

    demo_cmd = sub.add_parser("demo", help="simulate four weeks of promotions into a directory")
    demo_cmd.add_argument("--out", default=".demo")
    demo_cmd.add_argument("--now")
    demo_cmd.set_defaults(func=cmd_demo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ManifestError, gates.GateError, promote.PromotionError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    except FileNotFoundError as error:
        print(f"missing input: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
