#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Validate source relationships and repository-owned artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

from source_manifest import (
    LinkedEvidence,
    Manifest,
    ManifestError,
    PrivateReviewEvidence,
    RepositoryNoteEvidence,
    SnapshotEvidence,
    SourceId,
    SourceRecord,
    load_manifest,
)
from twitter_corpus import (
    DeletedTwitterCorpusRow,
    TwitterCorpus,
    TwitterCorpusOwner,
    TwitterCorpusRow,
    x_status_identity,
)

GUIDE_PATHS = frozenset(
    {
        PurePosixPath("sources/raw/acp/README.md"),
        PurePosixPath("sources/raw/hyperbola/README.md"),
        PurePosixPath("sources/raw/images/README.md"),
        PurePosixPath("sources/twitter/README.md"),
    }
)
SNAPSHOT_ROOTS = frozenset(
    {
        ("sources", "raw"),
        ("sources", "twitter"),
    }
)


def repository_file(root: Path, path: PurePosixPath, description: str) -> Path:
    candidate = root / path
    if candidate.is_symlink():
        raise ManifestError(f"{description} must not be a symlink: {path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as error:
        raise ManifestError(f"{description} does not exist: {path}") from error
    except ValueError as error:
        raise ManifestError(
            f"{description} resolves outside the repository: {path}"
        ) from error
    if not resolved.is_file():
        raise ManifestError(f"{description} is not a regular file: {path}")
    return resolved


def twitter_corpus(
    source: SourceRecord,
    root: Path,
    cache: dict[SourceId, TwitterCorpus],
) -> TwitterCorpus:
    if source.id in cache:
        return cache[source.id]
    evidence = source.evidence
    if not isinstance(evidence, SnapshotEvidence):
        raise ManifestError(f"{source.id}: collection target is not snapshot evidence")
    artifacts = tuple(
        artifact for artifact in evidence.artifacts if artifact.role == "social_corpus"
    )
    if len(artifacts) != 1:
        raise ManifestError(
            f"{source.id}: social collection requires one corpus artifact"
        )
    path = repository_file(root, artifacts[0].path, f"{source.id} social corpus")
    try:
        corpus = TwitterCorpus.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ManifestError(
            f"{source.id}: social corpus is invalid: {error}"
        ) from error
    if corpus.effective_at.date() != evidence.retrieved_at:
        raise ManifestError(
            f"{source.id}: corpus provenance date differs from retrieval date"
        )
    if corpus.owner.name not in source.authors:
        raise ManifestError(
            f"{source.id}: corpus owner is absent from snapshot authors"
        )
    cache[source.id] = corpus
    return corpus


def reconcile_twitter_source(
    source: SourceRecord,
    row: TwitterCorpusRow,
    owner: TwitterCorpusOwner,
) -> None:
    evidence = source.evidence
    if not isinstance(evidence, LinkedEvidence):
        raise ManifestError(f"{source.id}: Twitter source must use linked evidence")
    canonical = next(link for link in evidence.links if link.role == "canonical")
    reference = evidence.collection_reference
    if reference is None or reference.status_id != row.status_id:
        raise ManifestError(f"{source.id}: collection selector disagrees with row")
    if canonical.url != row.canonical_url:
        raise ManifestError(f"{source.id}: canonical URL disagrees with collection")
    if source.authors != (owner.name,):
        raise ManifestError(
            f"{source.id}: source authors disagree with collection owner"
        )
    if source.date != row.created_at.date():
        raise ManifestError(f"{source.id}: source date disagrees with collection")
    if row.created_at.date() > source.reviewed_at:
        raise ManifestError(f"{source.id}: Twitter creation follows review")
    if not isinstance(row, DeletedTwitterCorpusRow):
        return
    if canonical.archived_url != row.archive_url:
        raise ManifestError(f"{source.id}: archive URL disagrees with collection")
    if (
        row.screenshot_capture_date is not None
        and row.screenshot_capture_date > source.reviewed_at
    ):
        raise ManifestError(f"{source.id}: screenshot capture follows review")
    if (
        row.archive_captured_at is not None
        and row.archive_captured_at.date() > source.reviewed_at
    ):
        raise ManifestError(f"{source.id}: archive capture follows review")


def validate_duplicates(sources: dict[SourceId, SourceRecord]) -> None:
    for source in sources.values():
        target = source.duplicate_of
        if target == source.id:
            raise ManifestError(f"{source.id}: source cannot duplicate itself")
        if target is not None and target not in sources:
            raise ManifestError(
                f"{source.id}: duplicate target does not exist: {target}"
            )

    for source in sources.values():
        seen: set[SourceId] = set()
        current = source
        while current.duplicate_of is not None:
            if current.id in seen:
                raise ManifestError(f"duplicate_of cycle includes source: {current.id}")
            seen.add(current.id)
            current = sources[current.duplicate_of]


def validate_manifest(manifest: Manifest, repository_root: Path) -> int:
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ManifestError(f"repository root is not a directory: {root}")

    sources: dict[SourceId, SourceRecord] = {}
    for source in manifest.sources:
        if source.id in sources:
            raise ManifestError(f"duplicate source id: {source.id}")
        if source.reviewed_at > manifest.as_of:
            raise ManifestError(f"{source.id}: review is later than manifest as_of")
        sources[source.id] = source
    validate_duplicates(sources)

    owners: dict[PurePosixPath, SourceId] = {}
    for source in manifest.sources:
        evidence = source.evidence
        if isinstance(evidence, PrivateReviewEvidence):
            continue
        if isinstance(evidence, LinkedEvidence):
            if evidence.retrieval_helper is not None:
                repository_file(root, evidence.retrieval_helper, f"{source.id} helper")
            continue
        if isinstance(evidence, RepositoryNoteEvidence):
            if evidence.path.parts[:1] != ("sources",):
                raise ManifestError(
                    f"{source.id}: repository note must live under sources/"
                )
            if evidence.path.parts[:2] in SNAPSHOT_ROOTS:
                raise ManifestError(
                    f"{source.id}: repository note cannot live in a snapshot corpus"
                )
            repository_file(root, evidence.path, f"{source.id} repository note")
            continue
        if evidence.retrieved_at > source.reviewed_at:
            raise ManifestError(f"{source.id}: retrieval is later than review")
        for artifact in evidence.artifacts:
            if artifact.path.parts[:2] not in SNAPSHOT_ROOTS:
                raise ManifestError(
                    f"{source.id}: snapshot must live under sources/raw/ or "
                    f"sources/twitter/: {artifact.path}"
                )
            if owner := owners.get(artifact.path):
                raise ManifestError(
                    f"{artifact.path} is owned by {owner} and {source.id}"
                )
            owners[artifact.path] = source.id
            path = repository_file(root, artifact.path, f"{source.id} artifact")
            with path.open("rb") as artifact_file:
                actual = hashlib.file_digest(artifact_file, "sha256").hexdigest()
            if actual != artifact.sha256:
                raise ManifestError(
                    f"{source.id}: SHA-256 mismatch for {artifact.path}; "
                    f"expected {artifact.sha256}, got {actual}"
                )

    corpus_cache: dict[SourceId, TwitterCorpus] = {}
    for source in manifest.sources:
        evidence = source.evidence
        if not isinstance(evidence, LinkedEvidence):
            continue
        canonical = next(link for link in evidence.links if link.role == "canonical")
        identity = x_status_identity(canonical.url)
        reference = evidence.collection_reference
        if identity is not None and reference is None:
            raise ManifestError(f"{source.id}: X post has no collection reference")
        if reference is None:
            continue
        if identity is None or reference.status_id != identity[0]:
            raise ManifestError(
                f"{source.id}: collection selector differs from its URL"
            )
        target = sources.get(reference.source_id)
        if target is None:
            raise ManifestError(f"{source.id}: collection target does not exist")
        corpus = twitter_corpus(target, root, corpus_cache)
        row = corpus.row(reference.status_id)
        if row is None:
            raise ManifestError(f"{source.id}: status id is absent from its collection")
        reconcile_twitter_source(source, row, corpus.owner)

    for inventory_root in (root / "sources/raw", root / "sources/twitter"):
        if not inventory_root.is_dir():
            raise ManifestError(
                f"source inventory is not a directory: {inventory_root}"
            )
        for path in inventory_root.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                continue
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if relative in GUIDE_PATHS:
                continue
            if relative not in owners:
                raise ManifestError(f"source artifact is not owned: {relative}")
    return len(owners)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--manifest", type=Path, default=root / "sources/sources.json")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        artifact_count = validate_manifest(manifest, args.root)
    except (ManifestError, OSError) as error:
        print(f"source manifest validation failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Validated {len(manifest.sources)} sources and "
        f"{artifact_count} immutable artifacts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
