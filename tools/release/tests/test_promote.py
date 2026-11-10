from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from aios_release import promote
from aios_release.manifest import ManifestError, Rollout, format_time
from aios_release.signing import DevHmacSigner
from tests.factories import BASE, boots, build, digest, hardware, image, manifest, promotion

SIGNER = DevHmacSigner(b"test-key", key_id="test")


def evidence_for(sha, at, *, boots_count=5, nightly=True, weekly=None, gpu=False, char="a"):
    records = [build(sha, at, char), image(sha, at, char), *boots(sha, at, count=boots_count, char=char)]
    if nightly:
        records.append(promotion(sha, "nightly", at, char))
    if weekly is not None:
        records.append(promotion(sha, "weekly", weekly, char=char))
    if gpu:
        records.append(hardware(sha, at + timedelta(hours=1), char=char))
    return records


class VersionTests(unittest.TestCase):
    def test_first_release(self):
        self.assertEqual(promote.next_version(None, BASE), "1.0.0")

    def test_patch_bump_within_a_month(self):
        current = manifest("stable", digest("a"), BASE, version="1.4.0")
        self.assertEqual(promote.next_version(current, BASE + timedelta(days=3)), "1.4.1")

    def test_minor_bump_in_a_new_month(self):
        current = manifest("stable", digest("a"), BASE, version="1.4.2")
        self.assertEqual(promote.next_version(current, BASE + timedelta(days=40)), "1.5.0")


class NightlyTests(unittest.TestCase):
    def test_nightly_has_no_version_and_a_signed_file(self):
        sha = digest("a")
        result, gate = promote.promote(
            channel="nightly",
            candidate_digest=sha,
            evidence=evidence_for(sha, BASE),
            prior={},
            now=BASE,
            signer=SIGNER,
        )
        self.assertTrue(gate.ok)
        self.assertIsNone(result.version)
        self.assertIsNone(result.release)
        self.assertIsNone(result.rollout)
        self.assertEqual(result.build_id, build(sha, BASE).build_id)
        self.assertTrue(result.signature)

    def test_promotion_is_not_a_rebuild_and_refuses_a_no_op(self):
        sha = digest("a")
        prior = {"nightly": manifest("nightly", sha, BASE)}
        with self.assertRaises(promote.PromotionError):
            promote.promote(
                channel="nightly",
                candidate_digest=sha,
                evidence=evidence_for(sha, BASE),
                prior=prior,
                now=BASE,
                signer=SIGNER,
            )

    def test_promotion_does_not_mark_the_replaced_digest_as_withdrawn(self):
        old, new = digest("a"), digest("b")
        prior = {"nightly": manifest("nightly", old, BASE)}
        result, _ = promote.promote(
            channel="nightly",
            candidate_digest=new,
            evidence=evidence_for(new, BASE, char="b"),
            prior=prior,
            now=BASE + timedelta(days=1),
            signer=SIGNER,
        )
        self.assertEqual(result.supersedes, ())

    def test_promotion_carries_existing_withdrawals_forward(self):
        bad, new = digest("c"), digest("b")
        prior = {"nightly": manifest("nightly", digest("a"), BASE, supersedes=(bad,))}
        result, _ = promote.promote(
            channel="nightly",
            candidate_digest=new,
            evidence=evidence_for(new, BASE, char="b"),
            prior=prior,
            now=BASE + timedelta(days=1),
            signer=SIGNER,
        )
        self.assertEqual(result.supersedes, (bad,))

    def test_a_withdrawn_digest_cannot_be_promoted_again(self):
        bad = digest("a")
        prior = {"weekly": manifest("weekly", digest("b"), BASE, supersedes=(bad,))}
        records = evidence_for(bad, BASE)
        with self.assertRaises(Exception):
            promote.promote(
                channel="weekly",
                candidate_digest=bad,
                evidence=records,
                prior=prior,
                now=BASE + timedelta(days=8),
                signer=SIGNER,
            )

    def test_supersedes_chain_is_bounded_and_deduplicated(self):
        chain = tuple(f"sha256:{index:064x}" for index in range(20))
        prior = {"nightly": manifest("nightly", digest("b"), BASE, supersedes=chain)}
        new = digest("a")
        result, _ = promote.promote(
            channel="nightly",
            candidate_digest=new,
            evidence=evidence_for(new, BASE),
            prior=prior,
            now=BASE,
            signer=SIGNER,
        )
        self.assertLessEqual(len(result.supersedes), 16)
        self.assertEqual(len(set(result.supersedes)), len(result.supersedes))
        self.assertNotIn(new, result.supersedes)

    def test_gate_failure_prevents_promotion(self):
        sha = digest("a")
        with self.assertRaises(Exception):
            promote.promote(
                channel="nightly",
                candidate_digest=sha,
                evidence=[build(sha, BASE)],  # no image check
                prior={},
                now=BASE,
                signer=SIGNER,
            )


class SelectionTests(unittest.TestCase):
    def test_nightly_picks_the_newest_digest_that_passes_its_gate(self):
        older, newer = digest("a"), digest("b")
        records = [
            *evidence_for(older, BASE),
            # Newer, but the image check has not finished: it must not be chosen.
            build(newer, BASE + timedelta(hours=1), "b"),
        ]
        selected = promote.select_candidate(
            channel="nightly", evidence=records, prior={}, now=BASE + timedelta(hours=2)
        )
        self.assertEqual(selected, older)

    def test_nightly_picks_the_newest_when_both_pass(self):
        older, newer = digest("a"), digest("b")
        records = [
            *evidence_for(older, BASE),
            *evidence_for(newer, BASE + timedelta(hours=1), char="b"),
        ]
        selected = promote.select_candidate(
            channel="nightly", evidence=records, prior={}, now=BASE + timedelta(hours=2)
        )
        self.assertEqual(selected, newer)

    def test_weekly_uses_promotion_evidence_not_the_moved_pointer(self):
        # The regression this pipeline was designed around: nightly points at B,
        # but A is the digest that has actually been in nightly for a week.
        a, b = digest("a"), digest("b")
        records = [
            *evidence_for(a, BASE),
            *evidence_for(b, BASE + timedelta(days=6), char="b"),
        ]
        prior = {"nightly": manifest("nightly", b, BASE + timedelta(days=6), char="b")}
        selected = promote.select_candidate(
            channel="weekly", evidence=records, prior=prior, now=BASE + timedelta(days=7, hours=1)
        )
        self.assertEqual(selected, a)

    def test_weekly_selects_nothing_before_the_soak(self):
        a = digest("a")
        selected = promote.select_candidate(
            channel="weekly", evidence=evidence_for(a, BASE), prior={}, now=BASE + timedelta(days=2)
        )
        self.assertIsNone(selected)

    def test_stable_only_considers_digests_that_were_weekly(self):
        a = digest("a")
        records = evidence_for(a, BASE, weekly=None, gpu=True)
        selected = promote.select_candidate(
            channel="stable", evidence=records, prior={}, now=BASE + timedelta(days=10)
        )
        self.assertIsNone(selected)

    def test_stable_selects_a_soaked_weekly(self):
        a = digest("a")
        records = evidence_for(a, BASE, weekly=BASE + timedelta(days=2), gpu=True)
        selected = promote.select_candidate(
            channel="stable", evidence=records, prior={}, now=BASE + timedelta(days=9)
        )
        self.assertEqual(selected, a)


class StableTests(unittest.TestCase):
    def stable_records(self, sha, at=BASE):
        return evidence_for(sha, at, weekly=at + timedelta(days=1), gpu=True, char=sha[-1])

    def test_stable_assigns_version_release_and_a_staged_rollout(self):
        sha = digest("a")
        result, gate = promote.promote(
            channel="stable",
            candidate_digest=sha,
            evidence=self.stable_records(sha),
            prior={},
            now=BASE + timedelta(days=9),
            signer=SIGNER,
            rollout_percentage=5,
        )
        self.assertTrue(gate.ok)
        self.assertEqual(result.version, "1.0.0")
        self.assertEqual(result.release, "v1.0.0")
        self.assertIsNotNone(result.rollout)
        self.assertEqual(result.rollout.percentage, 5)
        self.assertTrue(result.rollout.seed)
        self.assertTrue(result.rollout.started)

    def test_version_cannot_be_reused_or_lowered(self):
        sha = digest("a")
        prior = {"stable": manifest("stable", digest("b"), BASE, version="1.4.0")}
        with self.assertRaises(promote.PromotionError):
            promote.promote(
                channel="stable",
                candidate_digest=sha,
                evidence=self.stable_records(sha),
                prior=prior,
                now=BASE + timedelta(days=9),
                signer=SIGNER,
                version="1.4.0",
            )

    def test_a_full_rollout_is_absent_not_zero(self):
        sha = digest("a")
        result, _ = promote.promote(
            channel="stable",
            candidate_digest=sha,
            evidence=self.stable_records(sha),
            prior={},
            now=BASE + timedelta(days=9),
            signer=SIGNER,
            rollout_percentage=100,
        )
        self.assertIsNone(result.rollout)

    def test_nightly_rejects_a_version_argument(self):
        sha = digest("a")
        with self.assertRaises(promote.PromotionError):
            promote.promote(
                channel="nightly",
                candidate_digest=sha,
                evidence=evidence_for(sha, BASE),
                prior={},
                now=BASE,
                signer=SIGNER,
                version="2.0.0",
            )


class WidenTests(unittest.TestCase):
    def manifest(self, started_days_ago=7):
        started = BASE + timedelta(days=1)
        return manifest(
            "stable", digest("a"), BASE, version="1.0.0",
            rollout=Rollout(percentage=5, seed="seed", started=format_time(started)),
        )

    def test_widening_requires_the_soak(self):
        manifest = self.manifest()
        with self.assertRaises(promote.PromotionError):
            promote.widen(manifest, now=BASE + timedelta(days=3), signer=SIGNER)

    def test_widening_preserves_identity(self):
        manifest = self.manifest()
        widened = promote.widen(manifest, now=BASE + timedelta(days=9), signer=SIGNER)
        self.assertEqual(widened.digest, manifest.digest)
        self.assertEqual(widened.version, manifest.version)
        self.assertEqual(widened.created, manifest.created)
        self.assertEqual(widened.rollout.percentage, 100)
        self.assertEqual(widened.rollout.seed, manifest.rollout.seed)
        self.assertNotEqual(widened.signature, manifest.signature)

    def test_force_overrides_the_soak(self):
        widened = promote.widen(
            self.manifest(), now=BASE + timedelta(days=2), signer=SIGNER, force=True
        )
        self.assertEqual(widened.rollout.percentage, 100)


class WithdrawTests(unittest.TestCase):
    def test_withdrawal_moves_back_and_issues_a_new_version(self):
        bad = manifest("stable", digest("a"), BASE, version="1.4.0")
        good = manifest("stable", digest("b"), BASE - timedelta(days=30), version="1.3.0")
        withdrawn = promote.withdraw(
            current=bad, target=good, now=BASE + timedelta(days=1), signer=SIGNER
        )
        self.assertEqual(withdrawn.digest, good.digest)
        self.assertEqual(withdrawn.version, "1.4.1")
        self.assertEqual(withdrawn.release, "v1.4.1")
        self.assertIn(bad.digest, withdrawn.supersedes)
        self.assertIsNone(withdrawn.rollout)

    def test_cannot_withdraw_the_digest_being_restored(self):
        same = manifest("stable", digest("a"), BASE, version="1.4.0")
        with self.assertRaises(promote.PromotionError):
            promote.withdraw(current=same, target=same, now=BASE, signer=SIGNER)

    def test_cannot_withdraw_an_unrelated_digest(self):
        bad = manifest("stable", digest("a"), BASE, version="1.4.0")
        good = manifest("stable", digest("b"), BASE, version="1.3.0")
        with self.assertRaises(promote.PromotionError):
            promote.withdraw(
                current=bad, target=good, now=BASE, signer=SIGNER, bad_digest=digest("c")
            )

    def test_withdrawal_of_nightly_is_refused(self):
        bad = manifest("nightly", digest("a"), BASE)
        good = manifest("nightly", digest("b"), BASE)
        with self.assertRaises(promote.PromotionError):
            promote.withdraw(current=bad, target=good, now=BASE, signer=SIGNER)


class PromotionRecordTests(unittest.TestCase):
    def test_record_names_the_channel_and_the_digest(self):
        sha = digest("a")
        channel_manifest = manifest("weekly", sha, BASE)
        record = promote.promotion_record(channel_manifest, BASE)
        self.assertEqual(record.kind, "promotion")
        self.assertEqual(record.channel, "weekly")
        self.assertEqual(record.digest, sha)
        self.assertEqual(record.created, channel_manifest.created)
        self.assertEqual(record.problems(), [])


class SigningTests(unittest.TestCase):
    def test_signature_covers_the_content(self):
        sha = digest("a")
        result, _ = promote.promote(
            channel="nightly",
            candidate_digest=sha,
            evidence=evidence_for(sha, BASE),
            prior={},
            now=BASE,
            signer=SIGNER,
        )
        self.assertTrue(SIGNER.verify(result.payload(), result.signature))
        tampered = replace(result, digest=digest("b"))
        self.assertFalse(SIGNER.verify(tampered.payload(), result.signature))

    def test_unsigned_output_is_possible_for_ci_to_sign_but_fails_validation(self):
        from aios_release.manifest import validate
        from aios_release.signing import UnsignedSigner

        sha = digest("a")
        result, _ = promote.promote(
            channel="nightly",
            candidate_digest=sha,
            evidence=evidence_for(sha, BASE),
            prior={},
            now=BASE,
            signer=UnsignedSigner(),
        )
        self.assertEqual(result.signature, "")
        with self.assertRaises(ManifestError):
            validate(result, require_signature=True)
