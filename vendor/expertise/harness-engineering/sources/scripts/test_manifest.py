#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path
from typing import cast

from source_manifest import (
    HttpsUrl,
    LinkedEvidence,
    ManifestError,
    PrivateReviewEvidence,
    RepositoryNoteEvidence,
    SnapshotEvidence,
    parse_manifest_data,
)
from twitter_corpus import (
    DeletedTwitterCorpusRow,
    PublicTwitterCorpusRow,
    TwitterCorpus,
    UtcDateTime,
    parse_deleted_twitter_row,
    parse_public_twitter_row,
    x_status_identity,
)
from validate_manifest import validate_duplicates, validate_manifest

ROOT = Path(__file__).resolve().parents[2]
ZERO_HASH = "0" * 64


def json_object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def json_array(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)


def linked_evidence(url: str = "https://example.com/source") -> dict[str, object]:
    return {
        "type": "linked",
        "links": [{"role": "canonical", "url": url}],
    }


def source_json(
    *,
    source_id: str,
    evidence: dict[str, object] | None = None,
    source_date: str | None = "2024-01-01",
    reviewed_at: str = "2026-07-17",
    canonical: bool = True,
    duplicate_of: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": source_id,
        "title": f"Source {source_id}",
        "date": source_date,
        "reviewed_at": reviewed_at,
        "authors": ["Author"],
        "kind": "article",
        "classification": "primary",
        "canonical": canonical,
        "review_basis": "full_text",
        "duplicate_of": duplicate_of,
        "notes": "Test source.",
        "evidence": evidence if evidence is not None else linked_evidence(),
    }
    return record


def manifest_data(*sources: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "as_of": "2026-07-18",
        "maintainer": "Maintainer",
        "repository_purpose": "Test source manifest.",
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "scope": "Original test material.",
        },
        "sources": list(sources),
    }


def snapshot_evidence(
    *,
    path: str = "sources/raw/artifact.txt",
    sha256: str = ZERO_HASH,
    retrieved_at: str = "2026-07-17",
) -> dict[str, object]:
    return {
        "type": "snapshot",
        "retrieved_at": retrieved_at,
        "artifacts": [{"role": "article_source", "path": path, "sha256": sha256}],
        "rights": {
            "license": "CC-BY-4.0",
            "scope": "Author-owned text only.",
        },
    }


def indexed_source(data: dict[str, object], source_id: str) -> dict[str, object]:
    for source_value in json_array(data["sources"]):
        source = json_object(source_value)
        if source.get("id") == source_id:
            return source
    raise AssertionError(f"missing test source: {source_id}")


class ManifestParserTests(unittest.TestCase):
    def test_models_are_immutable_and_keyword_only(self) -> None:
        parsed = parse_manifest_data(
            manifest_data(source_json(source_id="example-source"))
        )
        with self.assertRaises(FrozenInstanceError):
            parsed.sources[0].title = "Changed"  # ty: ignore[invalid-assignment]
        constructor = cast(Callable[..., object], type(parsed.sources[0]))
        with self.assertRaises(TypeError):
            constructor("example-source")

    def test_boundary_errors_identify_the_exact_field(self) -> None:
        missing_review = source_json(source_id="example-source")
        del missing_review["reviewed_at"]
        with self.assertRaisesRegex(
            ManifestError,
            r"manifest\.sources\[0\]\.reviewed_at is required",
        ):
            parse_manifest_data(manifest_data(missing_review))

        invalid_boolean = source_json(source_id="example-source")
        invalid_boolean["canonical"] = 1
        with self.assertRaisesRegex(
            ManifestError,
            r"manifest\.sources\[0\]\.canonical must be a boolean",
        ):
            parse_manifest_data(manifest_data(invalid_boolean))

    def test_source_nullable_fields_distinguish_missing_from_null(self) -> None:
        explicit_nulls = source_json(
            source_id="example-source",
            source_date=None,
            duplicate_of=None,
        )
        parsed = parse_manifest_data(manifest_data(explicit_nulls))
        self.assertIsNone(parsed.sources[0].date)
        self.assertIsNone(parsed.sources[0].duplicate_of)

        for field_name in ("date", "duplicate_of"):
            with self.subTest(field_name=field_name):
                missing = copy.deepcopy(explicit_nulls)
                del missing[field_name]
                with self.assertRaisesRegex(
                    ManifestError,
                    rf"manifest\.sources\[0\]\.{field_name} is required",
                ):
                    parse_manifest_data(manifest_data(missing))

    def test_evidence_variants_have_distinct_models(self) -> None:
        cases: tuple[tuple[dict[str, object], type[object]], ...] = (
            (
                linked_evidence(),
                LinkedEvidence,
            ),
            (
                snapshot_evidence(),
                SnapshotEvidence,
            ),
            (
                {"type": "repository_note", "path": "sources/note.md"},
                RepositoryNoteEvidence,
            ),
            (
                {"type": "private_review", "access": "private"},
                PrivateReviewEvidence,
            ),
        )
        for evidence, expected_type in cases:
            with self.subTest(expected_type=expected_type.__name__):
                record = source_json(
                    source_id="example-source",
                    evidence=evidence,
                )
                parsed = parse_manifest_data(manifest_data(record))
                self.assertIsInstance(parsed.sources[0].evidence, expected_type)

    def test_unknown_fields_are_rejected_at_the_parse_boundary(self) -> None:
        record = source_json(source_id="example-source")
        evidence = json_object(record["evidence"])
        evidence["guessed_field"] = "value"
        with self.assertRaisesRegex(ManifestError, "guessed_field"):
            parse_manifest_data(manifest_data(record))

    def test_access_labels_fail_closed(self) -> None:
        public = source_json(
            source_id="public-source",
        )
        public["visibility"] = "public"
        with self.assertRaisesRegex(ManifestError, "visibility"):
            parse_manifest_data(manifest_data(public))

        unlabeled_private = source_json(
            source_id="private-source",
            evidence={"type": "private_review"},
        )
        with self.assertRaisesRegex(ManifestError, "access"):
            parse_manifest_data(manifest_data(unlabeled_private))

        labeled_private = source_json(
            source_id="private-source",
            evidence={"type": "private_review", "access": "private"},
        )
        parsed = parse_manifest_data(manifest_data(labeled_private))
        self.assertIsInstance(parsed.sources[0].evidence, PrivateReviewEvidence)

        misplaced_access = source_json(source_id="public-source")
        evidence = json_object(misplaced_access["evidence"])
        evidence["access"] = "private"
        with self.assertRaisesRegex(ManifestError, "access"):
            parse_manifest_data(manifest_data(misplaced_access))

    def test_repository_paths_cannot_escape(self) -> None:
        cases: tuple[dict[str, object], ...] = (
            snapshot_evidence(path="../artifact.txt"),
            {"type": "repository_note", "path": "/absolute/note.md"},
            snapshot_evidence(path=""),
            {"type": "repository_note", "path": "."},
        )
        for evidence in cases:
            with self.subTest(evidence=evidence["type"]):
                record = source_json(source_id="example-source", evidence=evidence)
                with self.assertRaisesRegex(
                    ManifestError, "safe repository-relative path"
                ):
                    parse_manifest_data(manifest_data(record))

    def test_snapshot_rights_are_local_to_snapshot_evidence(self) -> None:
        record = source_json(source_id="snapshot-source", evidence=snapshot_evidence())
        evidence = json_object(record["evidence"])
        del evidence["rights"]
        with self.assertRaisesRegex(ManifestError, "rights"):
            parse_manifest_data(manifest_data(record))

        record = source_json(source_id="linked-source")
        data = manifest_data(record)
        license_record = json_object(data["license"])
        license_record["snapshot_scopes"] = {"sources/raw/": "wrong owner"}
        with self.assertRaisesRegex(ManifestError, "snapshot_scopes"):
            parse_manifest_data(data)


class ManifestRelationshipTests(unittest.TestCase):
    def test_duplicate_targets_and_cycles_are_rejected(self) -> None:
        dangling = source_json(
            source_id="duplicate-source",
            canonical=False,
            duplicate_of="missing-source",
        )
        parsed = parse_manifest_data(manifest_data(dangling))
        with self.assertRaisesRegex(ManifestError, "does not exist"):
            validate_duplicates({source.id: source for source in parsed.sources})

        first = source_json(
            source_id="first-source",
            canonical=False,
            duplicate_of="second-source",
        )
        second = source_json(
            source_id="second-source",
            canonical=False,
            duplicate_of="first-source",
        )
        parsed = parse_manifest_data(manifest_data(first, second))
        with self.assertRaisesRegex(ManifestError, "cycle"):
            validate_duplicates({source.id: source for source in parsed.sources})

    def test_temporal_order_is_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sources/raw").mkdir(parents=True)
            (root / "sources/twitter").mkdir(parents=True)
            future_event = source_json(
                source_id="future-event",
                source_date="2027-01-01",
                reviewed_at="2026-07-17",
            )
            self.assertEqual(
                validate_manifest(
                    parse_manifest_data(manifest_data(future_event)), root
                ),
                0,
            )
            reviewed_after_as_of = source_json(
                source_id="late-review",
                reviewed_at="2026-07-19",
            )
            with self.assertRaisesRegex(ManifestError, "manifest as_of"):
                validate_manifest(
                    parse_manifest_data(manifest_data(reviewed_after_as_of)),
                    root,
                )

            artifact = root / "sources/raw/artifact.txt"
            artifact.write_text("artifact\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            record = source_json(
                source_id="snapshot-source",
                evidence=snapshot_evidence(sha256=digest, retrieved_at="2026-07-18"),
            )
            with self.assertRaisesRegex(ManifestError, "later than review"):
                validate_manifest(parse_manifest_data(manifest_data(record)), root)

    def test_artifact_hashes_and_ownership_are_repository_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "sources/raw"
            twitter = root / "sources/twitter"
            raw.mkdir(parents=True)
            twitter.mkdir(parents=True)
            artifact = raw / "artifact.txt"
            artifact.write_text("artifact\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            record = source_json(
                source_id="snapshot-source",
                evidence=snapshot_evidence(sha256=digest),
            )
            data = manifest_data(record)
            self.assertEqual(validate_manifest(parse_manifest_data(data), root), 1)

            wrong_hash = copy.deepcopy(data)
            wrong_source = indexed_source(wrong_hash, "snapshot-source")
            wrong_evidence = json_object(wrong_source["evidence"])
            wrong_artifacts = json_array(wrong_evidence["artifacts"])
            wrong_artifact = json_object(wrong_artifacts[0])
            wrong_artifact["sha256"] = ZERO_HASH
            with self.assertRaisesRegex(ManifestError, "SHA-256 mismatch"):
                validate_manifest(parse_manifest_data(wrong_hash), root)

            duplicate_owner = copy.deepcopy(data)
            second = copy.deepcopy(record)
            second["id"] = "second-snapshot"
            json_array(duplicate_owner["sources"]).append(second)
            with self.assertRaisesRegex(ManifestError, "is owned by"):
                validate_manifest(parse_manifest_data(duplicate_owner), root)

            (raw / "orphan.txt").write_text("orphan\n", encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "is not owned"):
                validate_manifest(parse_manifest_data(data), root)


class TwitterReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(
            (ROOT / "sources/sources.json").read_text(encoding="utf-8")
        )
        self.corpus_data = json.loads(
            (ROOT / "sources/twitter/lopopolo-public-x-2026.json").read_text(
                encoding="utf-8"
            )
        )

    def assert_current_failure(self, data: dict[str, object], message: str) -> None:
        with self.assertRaisesRegex(ManifestError, message):
            validate_manifest(parse_manifest_data(data), ROOT)

    def test_rows_reconcile_manifest_identity_and_date(self) -> None:
        cases = (
            (
                "x-code-uniformity",
                lambda source: source.update(date="2026-03-08"),
                "source date disagrees",
            ),
            (
                "x-code-uniformity",
                lambda source: source.update(reviewed_at="2026-03-06"),
                "Twitter creation follows review",
            ),
            (
                "x-code-uniformity",
                lambda source: source.update(authors=["Someone Else"]),
                "source authors disagree with collection owner",
            ),
            (
                "x-code-uniformity",
                lambda source: source["evidence"]["links"][0].update(
                    url=("https://twitter.com/_lopopolo/status/2030325081868837216")
                ),
                "canonical URL disagrees",
            ),
            (
                "x-model-native-harness",
                lambda source: source["evidence"]["links"][0].update(
                    archived_url=(
                        "https://web.archive.org/web/20260502223332id_/"
                        "https://twitter.com/_lopopolo/status/"
                        "2050705271840989347"
                    )
                ),
                "archive URL disagrees",
            ),
            (
                "twitter-public-crawl-2026",
                lambda source: source.update(authors=["Someone Else"]),
                "corpus owner is absent from snapshot authors",
            ),
        )
        for source_id, mutate, expected in cases:
            with self.subTest(source_id=source_id, expected=expected):
                data = copy.deepcopy(self.data)
                mutate(indexed_source(data, source_id))
                self.assert_current_failure(data, expected)

    def test_deleted_row_owns_capture_and_screenshot_provenance(self) -> None:
        deleted = self.corpus_data["deleted_posts"][0]
        cases = (
            (
                lambda row: row.pop("screenshot_capture_date"),
                "screenshot_capture_date",
            ),
            (
                lambda row: row.update(screenshot_artifact_sha256="bad"),
                "screenshot artifact SHA-256",
            ),
            (
                lambda row: row.update(archive_capture_time="2026-05-01T22:33:31Z"),
                "archive capture cannot precede",
            ),
            (
                lambda row: row["engagement_from_screenshot"].update(likes=-1),
                "likes must be a nonnegative count",
            ),
            (
                lambda row: row.update(screenshot_redistributed=True),
                "redistributed screenshot requires an owned artifact path",
            ),
            (
                lambda row: row.update(text=""),
                "deleted Twitter post text must be nonempty",
            ),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                row = copy.deepcopy(deleted)
                mutate(row)
                with self.assertRaisesRegex(ValueError, expected):
                    parse_deleted_twitter_row(
                        row,
                        "twitter corpus.deleted_posts[0]",
                    )

    def test_corpus_owns_count_identity_and_curated_relationships(self) -> None:
        cases = (
            (
                lambda value: value.update(post_count=value["post_count"] - 1),
                "number of public posts",
            ),
            (
                lambda value: value["posts"][0].update(
                    url=value["posts"][0]["url"].replace("_lopopolo", "someone_else")
                ),
                "declared owner",
            ),
            (
                lambda value: value["mld_thread"]["ryan_post_ids_in_order"].append(
                    "9999999999999999999"
                ),
                "public thread URLs must follow Ryan post order",
            ),
            (
                lambda value: value["posts"][0].pop("replying_to"),
                r"posts\[0\]\.replying_to is required",
            ),
            (
                lambda value: value["posts"][0].pop("text"),
                r"posts\[0\]\.text is required",
            ),
            (
                lambda value: value["posts"][0].pop("public_provenance"),
                r"posts\[0\]\.public_provenance is required",
            ),
            (
                lambda value: value["posts"][0].update(text=None),
                "requires text, quote, or media",
            ),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                value = copy.deepcopy(self.corpus_data)
                mutate(value)
                with self.assertRaisesRegex(ValueError, expected):
                    TwitterCorpus.from_json(value)

    def test_corpus_boundary_is_closed_and_models_both_row_variants(self) -> None:
        corpus = TwitterCorpus.from_json(self.corpus_data)
        self.assertTrue(
            all(isinstance(row, PublicTwitterCorpusRow) for row in corpus.posts)
        )
        self.assertTrue(
            all(
                isinstance(row, DeletedTwitterCorpusRow) for row in corpus.deleted_posts
            )
        )

        unknown_root = copy.deepcopy(self.corpus_data)
        unknown_root["unexpected"] = True
        with self.assertRaisesRegex(
            ManifestError,
            "twitter corpus has unknown field.*unexpected",
        ):
            TwitterCorpus.from_json(unknown_root)

        unknown_row = copy.deepcopy(self.corpus_data)
        unknown_row["posts"][0]["guessed"] = "value"
        with self.assertRaisesRegex(
            ManifestError,
            r"twitter corpus\.posts\[0\] has unknown field.*guessed",
        ):
            TwitterCorpus.from_json(unknown_row)

    def test_mld_evidence_and_thread_roles_are_owned_fields(self) -> None:
        missing_evidence = copy.deepcopy(self.corpus_data)
        del missing_evidence["mld_thread"]["evidence"]
        with self.assertRaisesRegex(
            ManifestError,
            r"twitter corpus\.mld_thread\.evidence is required",
        ):
            TwitterCorpus.from_json(missing_evidence)

        missing_role = copy.deepcopy(self.corpus_data)
        index = next(
            index
            for index, row in enumerate(missing_role["posts"])
            if "thread_role" in row
        )
        del missing_role["posts"][index]["thread_role"]
        with self.assertRaisesRegex(
            ManifestError,
            "thread_role is required for a retained thread relation",
        ):
            TwitterCorpus.from_json(missing_role)

        coordinated_deletion = copy.deepcopy(self.corpus_data)
        del coordinated_deletion["mld_thread"]["ryan_post_ids_in_order"][2]
        del coordinated_deletion["mld_thread"]["evidence"]["public_thread_urls"][2]
        with self.assertRaisesRegex(
            ManifestError,
            "curated thread rows must match Ryan post order",
        ):
            TwitterCorpus.from_json(coordinated_deletion)

    def test_quote_identity_and_snowflake_range_are_semantic(self) -> None:
        mismatched_quote = copy.deepcopy(self.corpus_data)
        quoted = next(
            row for row in mismatched_quote["posts"] if "quoted_status_id" in row
        )
        quoted["quoted_url"] = "https://x.com/_lopopolo/status/1991024524410958066"
        with self.assertRaisesRegex(
            ManifestError,
            "quoted status id disagrees with quoted URL",
        ):
            TwitterCorpus.from_json(mismatched_quote)

        huge_status = copy.deepcopy(self.corpus_data["posts"][0])
        huge_status["id"] = "9" * 200
        huge_status["url"] = f"https://x.com/_lopopolo/status/{huge_status['id']}"
        with self.assertRaisesRegex(
            ManifestError,
            "exceeds the supported timestamp range",
        ):
            parse_public_twitter_row(huge_status, "twitter corpus.posts[0]")

    def test_status_urls_reject_impossible_handles(self) -> None:
        public_data = copy.deepcopy(self.corpus_data["posts"][0])
        impossible_url = f"https://x.com/handle_is_too_long/status/{public_data['id']}"
        self.assertIsNone(x_status_identity(impossible_url))

        public_data["url"] = impossible_url
        with self.assertRaisesRegex(
            ManifestError,
            "public Twitter row URL must match its status id",
        ):
            parse_public_twitter_row(public_data, "twitter corpus.posts[0]")

        valid = parse_public_twitter_row(
            self.corpus_data["posts"][0],
            "public row",
        )
        with self.assertRaisesRegex(
            ValueError,
            "public Twitter row URL must match its status id",
        ):
            replace(valid, canonical_url=HttpsUrl(impossible_url))

    def test_row_invariants_apply_to_direct_construction(self) -> None:
        public_data = next(
            row for row in self.corpus_data["posts"] if "thread_role" in row
        )
        public = parse_public_twitter_row(public_data, "public row")
        with self.assertRaisesRegex(
            ValueError,
            "thread_role is required for a retained thread relation",
        ):
            replace(public, thread_role=None)

        deleted = parse_deleted_twitter_row(
            self.corpus_data["deleted_posts"][0],
            "deleted row",
        )
        with self.assertRaisesRegex(
            ValueError,
            "redistributed screenshot requires an owned artifact path",
        ):
            replace(deleted, screenshot_redistributed=True)

    def test_utc_is_owned_by_a_semantic_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "UTC datetime value must use UTC"):
            UtcDateTime(value=datetime(2026, 7, 18, 12, 0))

        non_utc = copy.deepcopy(self.corpus_data["deleted_posts"][0])
        non_utc["created_at"] = "2026-05-02T23:33:31+01:00"
        with self.assertRaisesRegex(
            ManifestError,
            r"deleted row\.created_at: UTC datetime value must use UTC",
        ):
            parse_deleted_twitter_row(non_utc, "deleted row")

        deleted = parse_deleted_twitter_row(
            self.corpus_data["deleted_posts"][0],
            "deleted row",
        )
        with self.assertRaisesRegex(
            ValueError,
            "deleted creation time must be a UtcDateTime",
        ):
            replace(
                deleted,
                created_at_utc=deleted.created_at,  # type: ignore[arg-type]
            )

        corpus = TwitterCorpus.from_json(self.corpus_data)
        with self.assertRaisesRegex(
            ValueError,
            "corpus generation time must be a UtcDateTime",
        ):
            replace(
                corpus,
                generated_at_utc=corpus.generated_at,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
