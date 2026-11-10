from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from aios_release import evidence
from aios_release.evidence import Evidence
from aios_release.manifest import ManifestError, format_time
from tests.release.factories import BASE, boots, build, digest, hardware, image, promotion


def build_record(**kwargs) -> Evidence:
    return build(digest("a"), BASE, **kwargs)


class ProblemsTests(unittest.TestCase):
    def test_every_kind_is_accepted(self):
        records = [
            build_record(),
            image(digest("a"), BASE),
            *boots(digest("a"), BASE, count=1),
            hardware(digest("a"), BASE),
            promotion(digest("a"), "stable", BASE),
        ]
        for record in records:
            self.assertEqual(record.problems(), [], record.kind)

    def test_unknown_kind_is_reported(self):
        found = replace(build_record(), kind="vibes").problems()
        self.assertTrue(any("kind must be one of" in item for item in found), found)

    def test_wrong_schema_is_reported(self):
        found = replace(build_record(), schema=99).problems()
        self.assertTrue(any("schema must be 1" in item for item in found), found)

    def test_bad_digest_is_reported(self):
        found = replace(build_record(), digest="sha256:nothex").problems()
        self.assertTrue(any("digest must be" in item for item in found), found)

    def test_bad_result_is_reported(self):
        found = replace(build_record(), result="pass-ish").problems()
        self.assertTrue(any("result must be one of" in item for item in found), found)

    def test_bad_timestamp_is_reported(self):
        found = replace(build_record(), created="yesterday").problems()
        self.assertTrue(any("ISO-8601" in item for item in found), found)

    def test_bad_source_commit_is_reported(self):
        found = replace(build_record(), source_commit="zz").problems()
        self.assertTrue(any("source_commit is not a hex commit" in item for item in found), found)

    def test_promotion_records_need_a_channel(self):
        found = replace(promotion(digest("a"), "stable", BASE), channel=None).problems()
        self.assertTrue(any("promotion records need a known channel" in item for item in found), found)

    def test_promotion_records_reject_an_unknown_channel(self):
        found = replace(promotion(digest("a"), "stable", BASE), channel="beta").problems()
        self.assertTrue(any("known channel" in item for item in found), found)

    def test_other_records_must_not_carry_a_channel(self):
        found = replace(build_record(), channel="stable").problems()
        self.assertTrue(any("must not carry a channel" in item for item in found), found)


class FileTests(unittest.TestCase):
    def test_dump_then_load_round_trips(self):
        record = build_record()
        with tempfile.TemporaryDirectory() as directory:
            path = evidence.dump(record, Path(directory) / "one.json")
            self.assertEqual(evidence.load(directory), (record,))
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_dump_refuses_an_invalid_record(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ManifestError):
                evidence.dump(replace(build_record(), result="maybe"), Path(directory) / "bad.json")

    def test_load_is_oldest_first_even_when_filenames_sort_the_other_way(self):
        older = build_record()
        newer = replace(older, created=format_time(BASE + timedelta(days=1)))
        with tempfile.TemporaryDirectory() as directory:
            # "a" holds the newer record, so name order and time order disagree.
            evidence.dump(newer, Path(directory) / "a.json")
            evidence.dump(older, Path(directory) / "b.json")
            self.assertEqual([record.created for record in evidence.load(directory)],
                             [older.created, newer.created])

    def test_load_is_strict_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence.dump(build_record(), Path(directory) / "good.json")
            (Path(directory) / "bad.json").write_text(json.dumps({"kind": "vibes"}), encoding="utf-8")
            with self.assertRaises(ManifestError) as caught:
                evidence.load(directory)
            self.assertIn("bad.json", str(caught.exception))

    def test_load_can_skip_broken_records(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence.dump(build_record(), Path(directory) / "good.json")
            (Path(directory) / "bad.json").write_text(json.dumps({"kind": "vibes"}), encoding="utf-8")
            self.assertEqual(len(evidence.load(directory, strict=False)), 1)

    def test_write_names_files_that_sort_by_time(self):
        with tempfile.TemporaryDirectory() as directory:
            first = evidence.write(build(digest("a"), BASE), directory)
            second = evidence.write(build(digest("a"), BASE + timedelta(hours=1)), directory)
            self.assertRegex(first.name, r"^\d{8}T\d{6}Z-build-[0-9a-f]{12}\.json$")
            self.assertLess(first.name, second.name)

    def test_write_puts_the_channel_in_promotion_filenames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = evidence.write(promotion(digest("a"), "stable", BASE), directory)
            self.assertIn("-promotion-stable-", path.name)


class QueryTests(unittest.TestCase):
    def test_for_digest_filters(self):
        records = [
            build(digest("a"), BASE),
            build(digest("b"), BASE),
            image(digest("a"), BASE),
        ]
        self.assertEqual(len(evidence.for_digest(records, digest("a"))), 2)
        self.assertEqual(len(evidence.for_digest(records, digest("c"))), 0)

    def test_to_dict_and_from_dict_round_trip(self):
        record = hardware(digest("a"), BASE)
        self.assertEqual(Evidence.from_dict(record.to_dict()), record)

    def test_missing_fields_default_rather_than_raise(self):
        # Old or partly written artefacts must be diagnosable, not a traceback.
        parsed = Evidence.from_dict({"kind": "build"})
        self.assertEqual(parsed.result, "")
        self.assertTrue(parsed.problems())


class BuildRecordTests(unittest.TestCase):
    def test_build_record_is_valid_and_keeps_labels(self):
        record = evidence.build_record(
            digest=digest("a"),
            build_id="2026.11.01+gabcdef0.r1",
            source_commit="abcdef012345",
            now=BASE,
            labels={"base_digest": "sha256:" + "0" * 64},
        )
        self.assertEqual(record.problems(), [])
        self.assertEqual(record.kind, "build")
        self.assertEqual(record.labels["base_digest"], "sha256:" + "0" * 64)

    def test_build_record_labels_default_to_empty(self):
        record = evidence.build_record(
            digest=digest("a"),
            build_id="2026.11.01+gabcdef0.r1",
            source_commit="abcdef012345",
            now=BASE,
        )
        self.assertEqual(record.labels, {})
