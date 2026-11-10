from __future__ import annotations

import unittest
from datetime import timedelta
from dataclasses import replace

from aios_release import gates
from tests.factories import BASE, boots, build, digest, hardware, image, manifest, promotion


class GateTests(unittest.TestCase):
    def setUp(self):
        self.sha = digest("a")
        self.prior = {}
        self.now = BASE + timedelta(days=9)

    def evaluate(self, channel, records, now=None, **kwargs):
        return gates.evaluate(
            channel=channel,
            candidate_digest=self.sha,
            evidence=tuple(records),
            prior=self.prior,
            now=now or self.now,
            **kwargs,
        )

    # -- nightly --------------------------------------------------------

    def test_nightly_passes_with_a_build_and_an_image_check(self):
        result = self.evaluate("nightly", [build(self.sha, BASE), image(self.sha, BASE)])
        self.assertTrue(result.ok, result.summary())

    def test_nightly_fails_without_a_build(self):
        result = self.evaluate("nightly", [image(self.sha, BASE)])
        self.assertFalse(result.ok)
        self.assertEqual([check.name for check in result.failures], ["image-built"])

    def test_nightly_fails_without_an_image_check(self):
        result = self.evaluate("nightly", [build(self.sha, BASE)])
        self.assertFalse(result.ok)
        self.assertIn("image-check", {check.name for check in result.failures})

    # -- weekly ---------------------------------------------------------

    def weekly_records(self, promoted_at=BASE, boot_count=5):
        return [
            build(self.sha, promoted_at),
            image(self.sha, promoted_at),
            promotion(self.sha, "nightly", promoted_at),
            *boots(self.sha, promoted_at, count=boot_count),
        ]

    def test_weekly_requires_an_entry_into_nightly(self):
        result = self.evaluate("weekly", [build(self.sha, BASE), *boots(self.sha, BASE)])
        self.assertFalse(result.ok)
        self.assertIn("entered-nightly", {check.name for check in result.failures})

    def test_weekly_passes_after_seven_days_and_five_boots(self):
        result = self.evaluate("weekly", self.weekly_records(), now=BASE + timedelta(days=7, hours=1))
        self.assertTrue(result.ok, result.summary())

    def test_weekly_fails_after_six_days(self):
        result = self.evaluate("weekly", self.weekly_records(), now=BASE + timedelta(days=6, hours=23))
        self.assertFalse(result.ok)
        self.assertIn("soak-in-channel", {check.name for check in result.failures})

    def test_weekly_fails_with_four_boots(self):
        result = self.evaluate(
            "weekly", self.weekly_records(boot_count=4),
            now=BASE + timedelta(days=8),
        )
        self.assertFalse(result.ok)
        self.assertIn("boot-passes", {check.name for check in result.failures})

    def test_weekly_fails_when_the_latest_boot_failed(self):
        records = self.weekly_records()
        failing = replace(records[-1], result="fail", created=records[-1].created)
        result = self.evaluate("weekly", [*records, failing], now=BASE + timedelta(days=8))
        self.assertFalse(result.ok)
        self.assertIn("latest-boot-pass", {check.name for check in result.failures})

    def test_weekly_fails_on_a_known_p1(self):
        records = self.weekly_records()
        records.append(replace(records[1], known_p1=True))
        result = self.evaluate("weekly", records, now=BASE + timedelta(days=8))
        self.assertFalse(result.ok)
        self.assertIn("no-known-p1", {check.name for check in result.failures})

    # -- stable ---------------------------------------------------------

    def stable_records(self, weekly_at=BASE + timedelta(days=1)):
        return [
            *self.weekly_records(),
            promotion(self.sha, "weekly", weekly_at),
            hardware(self.sha, BASE + timedelta(hours=2)),
        ]

    def test_stable_passes_with_weekly_soak_and_a_gpu_context(self):
        result = self.evaluate("stable", self.stable_records(), now=BASE + timedelta(days=9))
        self.assertTrue(result.ok, result.summary())

    def test_stable_requires_a_weekly_entry(self):
        records = [record for record in self.stable_records() if record.channel != "weekly"]
        result = self.evaluate("stable", records, now=BASE + timedelta(days=9))
        self.assertFalse(result.ok)
        self.assertIn("entered-weekly", {check.name for check in result.failures})

    def test_stable_requires_hardware_evidence(self):
        records = [record for record in self.stable_records() if record.kind != "hw"]
        result = self.evaluate("stable", records, now=BASE + timedelta(days=9))
        self.assertFalse(result.ok)
        self.assertIn("hardware-pass", {check.name for check in result.failures})

    def test_stable_rejects_a_loaded_driver_without_a_context(self):
        records = [
            record if record.kind != "hw" else hardware(self.sha, BASE + timedelta(hours=2), gpu_context="fail")
            for record in self.stable_records()
        ]
        result = self.evaluate("stable", records, now=BASE + timedelta(days=9))
        self.assertFalse(result.ok)
        self.assertIn("gpu-context", {check.name for check in result.failures})

    def test_stable_rejects_a_withdrawn_digest(self):
        self.prior = {"stable": manifest("stable", digest("b"), BASE, version="1.0.0",
                                         supersedes=(self.sha,))}
        result = self.evaluate("stable", self.stable_records(), now=BASE + timedelta(days=9))
        self.assertFalse(result.ok)
        self.assertIn("not-withdrawn", {check.name for check in result.failures})

    # -- emergency lane -------------------------------------------------

    def test_emergency_bypasses_soak_but_not_hardware(self):
        records = [
            build(self.sha, BASE),
            *boots(self.sha, BASE),
        ]
        result = self.evaluate(
            "stable", records, now=BASE + timedelta(hours=1),
            emergency=True, approvals=("alice", "bob"),
        )
        self.assertFalse(result.ok)
        self.assertIn("hardware-pass", {check.name for check in result.failures})

    def test_emergency_passes_with_two_approvals_and_hardware(self):
        records = [
            build(self.sha, BASE),
            *boots(self.sha, BASE),
            hardware(self.sha, BASE + timedelta(minutes=30)),
        ]
        result = self.evaluate(
            "stable", records, now=BASE + timedelta(hours=1),
            emergency=True, approvals=("alice", "bob"),
        )
        self.assertTrue(result.ok, result.summary())

    def test_emergency_needs_two_distinct_approvals(self):
        records = [
            build(self.sha, BASE),
            *boots(self.sha, BASE),
            hardware(self.sha, BASE + timedelta(minutes=30)),
        ]
        result = self.evaluate(
            "stable", records, now=BASE + timedelta(hours=1),
            emergency=True, approvals=("alice", "alice"),
        )
        self.assertFalse(result.ok)
        self.assertIn("two-approvals", {check.name for check in result.failures})

    def test_unknown_channel_is_an_error(self):
        with self.assertRaises(gates.GateError):
            self.evaluate("weeklyish", [build(self.sha, BASE)])
