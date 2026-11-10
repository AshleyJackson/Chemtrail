from __future__ import annotations

import unittest

from aios_release import resolve
from aios_release.manifest import Rollout
from tests.factories import BASE, digest, manifest


class ResolveTests(unittest.TestCase):
    def stable(self, **kwargs):
        return manifest("stable", digest("b"), BASE, version="1.0.0", **kwargs)

    def test_running_the_named_digest_is_up_to_date(self):
        decision = resolve.resolve(
            manifest=self.stable(),
            running_digest=digest("b"),
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.UP_TO_DATE)
        self.assertEqual(decision.reason, "running-candidate")

    def test_a_different_digest_is_an_update(self):
        decision = resolve.resolve(
            manifest=self.stable(),
            running_digest=digest("a"),
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.UPDATE)
        self.assertEqual(decision.reason, "candidate-newer")

    def test_rollout_excludes_devices_outside_the_percentage(self):
        rollout = Rollout(percentage=5, seed="2026-11-abcd", started="2026-11-01T00:00:00Z")
        excluded = [
            f"machine-{index}" for index in range(200)
            if resolve.bucket_for(f"machine-{index}", rollout.seed) >= 5
        ][0]
        decision = resolve.resolve(
            manifest=self.stable(rollout=rollout),
            running_digest=digest("a"),
            machine_id=excluded,
        )
        self.assertEqual(decision.action, resolve.DEFERRED)
        self.assertEqual(decision.reason, "rollout-ineligible")

    def test_rollout_includes_devices_inside_the_percentage(self):
        rollout = Rollout(percentage=5, seed="2026-11-abcd", started="2026-11-01T00:00:00Z")
        included = [
            f"machine-{index}" for index in range(200)
            if resolve.bucket_for(f"machine-{index}", rollout.seed) < 5
        ][0]
        decision = resolve.resolve(
            manifest=self.stable(rollout=rollout),
            running_digest=digest("a"),
            machine_id=included,
        )
        self.assertEqual(decision.action, resolve.UPDATE)
        self.assertIsNotNone(decision.bucket)

    def test_a_full_rollout_has_no_bucket(self):
        decision = resolve.resolve(
            manifest=self.stable(rollout=Rollout(100, "seed", "2026-11-01T00:00:00Z")),
            running_digest=digest("a"),
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.UPDATE)
        self.assertIsNone(decision.bucket)

    def test_buckets_are_deterministic(self):
        first = resolve.bucket_for("machine-42", "2026-11-abcd")
        second = resolve.bucket_for("machine-42", "2026-11-abcd")
        self.assertEqual(first, second)
        self.assertNotEqual(resolve.bucket_for("machine-42", "other-seed"), first)

    def test_bucket_distribution_is_roughly_the_percentage(self):
        machines = [f"machine-{index}" for index in range(20_000)]
        snapshot = resolve.rollout_snapshot(
            self.stable(rollout=Rollout(5, "2026-11-abcd", "2026-11-01T00:00:00Z")),
            machines,
        )
        share = snapshot["eligible"] / snapshot["total"]
        self.assertGreater(share, 0.035, snapshot)
        self.assertLess(share, 0.065, snapshot)

    def test_a_locally_blacklisted_candidate_is_not_retried(self):
        decision = resolve.resolve(
            manifest=self.stable(),
            running_digest=digest("a"),
            machine_id="machine-1",
            bad_digests=[digest("b")],
        )
        self.assertEqual(decision.action, resolve.BLOCKED)
        self.assertEqual(decision.reason, "candidate-blacklisted")

    def test_a_channel_may_not_point_at_a_digest_it_withdraws(self):
        decision = resolve.resolve(
            manifest=self.stable(supersedes=(digest("b"),)),
            running_digest=digest("a"),
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.BLOCKED)
        self.assertEqual(decision.reason, "candidate-withdrawn")

    def test_a_withdrawn_running_digest_is_replaced_even_with_a_lower_version(self):
        decision = resolve.resolve(
            manifest=self.stable(supersedes=(digest("a"),)),
            running_digest=digest("a"),
            machine_id="machine-1",
            running_version="2.0.0",
        )
        self.assertEqual(decision.action, resolve.UPDATE)
        self.assertEqual(decision.reason, "running-withdrawn")

    def floored(self):
        return manifest(
            "stable", digest("b"), BASE, version="2.0.0", min_source_version="1.4.0"
        )

    def test_a_migration_floor_blocks_old_state(self):
        decision = resolve.resolve(
            manifest=self.floored(),
            running_digest=digest("a"),
            running_version="1.3.9",
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.BLOCKED)
        self.assertEqual(decision.reason, "state-migration-required")

    def test_meeting_the_migration_floor_allows_the_update(self):
        decision = resolve.resolve(
            manifest=self.floored(),
            running_digest=digest("a"),
            running_version="1.4.0",
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.UPDATE)

    def test_an_unversioned_build_is_below_every_floor(self):
        decision = resolve.resolve(
            manifest=self.floored(),
            running_digest=digest("a"),
            running_version=None,
            machine_id="machine-1",
        )
        self.assertEqual(decision.action, resolve.BLOCKED)
