"""Typed source-manifest model and JSON boundary parser."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import NewType, cast
from urllib.parse import urlsplit

SCHEMA_VERSION = 2
SOURCE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
STATUS_ID = re.compile(r"[0-9]+\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

SourceId = NewType("SourceId", str)
StatusId = NewType("StatusId", str)
HttpsUrl = NewType("HttpsUrl", str)
Sha256Digest = NewType("Sha256Digest", str)


class ManifestError(ValueError):
    """The manifest failed structural or repository validation."""


def require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be nonempty without surrounding whitespace")
    return value


def require_https(value: object, name: str) -> HttpsUrl:
    text = require_text(value, name)
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTPS URL: {text!r}")
    if any(character.isspace() for character in text):
        raise ValueError(f"{name} must not contain whitespace: {text!r}")
    return HttpsUrl(text)


def require_path(value: object, name: str) -> PurePosixPath:
    if not isinstance(value, PurePosixPath):
        raise ValueError(f"{name} must be a repository path")
    rendered = value.as_posix()
    if (
        rendered in {"", "."}
        or value.is_absolute()
        or ".." in value.parts
        or "\\" in rendered
    ):
        raise ValueError(f"{name} must be a safe repository-relative path")
    return value


def require_sha256(value: object, name: str) -> Sha256Digest:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return Sha256Digest(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceLink:
    role: str
    url: HttpsUrl | None = None
    archived_url: HttpsUrl | None = None
    archive_status: str | None = None

    def __post_init__(self) -> None:
        require_text(self.role, "link role")
        if self.url is None and self.archived_url is None:
            raise ValueError("source link requires a URL or archived URL")
        if self.url is not None:
            require_https(self.url, "source URL")
        if self.archived_url is not None:
            require_https(self.archived_url, "archived URL")
        if self.archive_status is not None:
            require_text(self.archive_status, "archive status")
            if self.url is None or self.archived_url is not None:
                raise ValueError(
                    "archive status requires a source URL without an archived URL"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionReference:
    source_id: SourceId
    status_id: StatusId

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not SOURCE_ID.fullmatch(
            self.source_id
        ):
            raise ValueError("collection source id must be lowercase kebab-case")
        if not isinstance(self.status_id, str) or not STATUS_ID.fullmatch(
            self.status_id
        ):
            raise ValueError("collection selector must be a numeric status id")


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotArtifact:
    role: str
    path: PurePosixPath
    sha256: Sha256Digest
    upstream_path: str | None = None

    def __post_init__(self) -> None:
        require_text(self.role, "artifact role")
        require_path(self.path, "artifact path")
        require_sha256(self.sha256, "artifact SHA-256")
        if self.upstream_path is not None:
            require_text(self.upstream_path, "upstream path")


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotRights:
    license: str
    scope: str
    disposition: str | None = None

    def __post_init__(self) -> None:
        require_text(self.license, "snapshot license")
        require_text(self.scope, "snapshot license scope")
        if self.disposition is not None:
            require_text(self.disposition, "rights disposition")


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkedEvidence:
    links: tuple[SourceLink, ...]
    related_urls: tuple[HttpsUrl, ...] = ()
    retrieval_helper: PurePosixPath | None = None
    collection_reference: CollectionReference | None = None

    def __post_init__(self) -> None:
        if not self.links:
            raise ValueError("linked evidence requires a link")
        if sum(link.role == "canonical" for link in self.links) != 1:
            raise ValueError("linked evidence requires one canonical link")
        for url in self.related_urls:
            require_https(url, "related URL")
        if self.retrieval_helper is not None:
            require_path(self.retrieval_helper, "retrieval helper")


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotEvidence:
    retrieved_at: date
    artifacts: tuple[SnapshotArtifact, ...]
    rights: SnapshotRights
    links: tuple[SourceLink, ...] = ()
    related_urls: tuple[HttpsUrl, ...] = ()
    pinned_revision: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.retrieved_at, date):
            raise ValueError("retrieval date must be an ISO 8601 date")
        if not self.artifacts:
            raise ValueError("snapshot evidence requires artifacts")
        paths = [artifact.path for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("snapshot artifact paths must be unique")
        if sum(link.role == "canonical" for link in self.links) > 1:
            raise ValueError("snapshot evidence permits at most one canonical link")
        for url in self.related_urls:
            require_https(url, "related URL")
        if self.pinned_revision is not None:
            require_text(self.pinned_revision, "pinned revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class RepositoryNoteEvidence:
    path: PurePosixPath

    def __post_init__(self) -> None:
        require_path(self.path, "repository note path")


@dataclass(frozen=True, slots=True, kw_only=True)
class PrivateReviewEvidence:
    access: str

    def __post_init__(self) -> None:
        require_text(self.access, "private-review access label")


type Evidence = (
    LinkedEvidence | SnapshotEvidence | RepositoryNoteEvidence | PrivateReviewEvidence
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRecord:
    id: SourceId
    title: str
    date: date | None
    reviewed_at: date
    authors: tuple[str, ...]
    kind: str
    classification: str
    canonical: bool
    review_basis: str
    duplicate_of: SourceId | None
    notes: str
    evidence: Evidence
    publisher: str | None = None
    authorship_scope: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not SOURCE_ID.fullmatch(self.id):
            raise ValueError("source id must be a lowercase kebab-case slug")
        if self.date is not None and not isinstance(self.date, date):
            raise ValueError("source date must be an ISO 8601 date")
        if not isinstance(self.reviewed_at, date):
            raise ValueError("review date must be an ISO 8601 date")
        if type(self.canonical) is not bool:
            raise ValueError("canonical must be a boolean")
        for value, name in (
            (self.title, "source title"),
            (self.kind, "source kind"),
            (self.classification, "source classification"),
            (self.review_basis, "review basis"),
            (self.notes, "source notes"),
        ):
            require_text(value, name)
        if not self.authors:
            raise ValueError("source requires an author or speaker")
        for author in self.authors:
            require_text(author, "author or speaker")
        for value, name in (
            (self.publisher, "publisher"),
            (self.authorship_scope, "authorship scope"),
        ):
            if value is not None:
                require_text(value, name)
        if self.duplicate_of is not None:
            if not isinstance(self.duplicate_of, str) or not SOURCE_ID.fullmatch(
                self.duplicate_of
            ):
                raise ValueError("duplicate source id must be lowercase kebab-case")
            if self.canonical:
                raise ValueError("a duplicate source cannot be canonical")


@dataclass(frozen=True, slots=True, kw_only=True)
class LicensePolicy:
    id: str
    url: HttpsUrl
    scope: str

    def __post_init__(self) -> None:
        require_text(self.id, "license id")
        require_https(self.url, "license URL")
        require_text(self.scope, "license scope")


@dataclass(frozen=True, slots=True, kw_only=True)
class Manifest:
    schema_version: int
    as_of: date
    maintainer: str
    repository_purpose: str
    license: LicensePolicy
    sources: tuple[SourceRecord, ...]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if not isinstance(self.as_of, date):
            raise ValueError("as_of must be an ISO 8601 date")
        require_text(self.maintainer, "maintainer")
        require_text(self.repository_purpose, "repository purpose")
        if not self.sources:
            raise ValueError("manifest requires at least one source")


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonObject:
    """A single-use, location-aware view of a JSON object boundary."""

    location: str
    fields: Mapping[str, object]

    @classmethod
    def decode(
        cls,
        value: object,
        *,
        location: str,
        allowed: frozenset[str],
    ) -> JsonObject:
        if not isinstance(value, dict):
            raise ManifestError(f"{location} must be an object")
        if any(not isinstance(key, str) for key in value):
            raise ManifestError(f"{location} field names must be strings")
        fields = cast(dict[str, object], value)
        unknown = sorted(set(fields) - allowed)
        if unknown:
            names = ", ".join(repr(name) for name in unknown)
            raise ManifestError(f"{location} has unknown field(s): {names}")
        return cls(
            location=location,
            fields=MappingProxyType(dict(fields)),
        )

    def required[T](self, name: str, decode: Callable[[object, str], T]) -> T:
        if name not in self.fields:
            raise ManifestError(f"{self.location}.{name} is required")
        return decode(self.fields[name], f"{self.location}.{name}")

    def optional[T](
        self,
        name: str,
        decode: Callable[[object, str], T],
    ) -> T | None:
        value = self.fields.get(name)
        if value is None:
            return None
        return decode(value, f"{self.location}.{name}")

    def nullable[T](
        self,
        name: str,
        decode: Callable[[object, str], T],
    ) -> T | None:
        if name not in self.fields:
            raise ManifestError(f"{self.location}.{name} is required")
        value = self.fields[name]
        if value is None:
            return None
        return decode(value, f"{self.location}.{name}")

    def array[T](
        self,
        name: str,
        decode: Callable[[object, str], T],
        *,
        required: bool,
    ) -> tuple[T, ...]:
        if name not in self.fields:
            if required:
                raise ManifestError(f"{self.location}.{name} is required")
            return ()
        value = self.fields[name]
        if not isinstance(value, list):
            raise ManifestError(f"{self.location}.{name} must be an array")
        return tuple(
            decode(item, f"{self.location}.{name}[{index}]")
            for index, item in enumerate(value)
        )


def domain_value[T](location: str, construct: Callable[[], T]) -> T:
    """Attach a JSON location to a domain invariant failure."""

    try:
        return construct()
    except ManifestError:
        raise
    except (TypeError, ValueError) as error:
        raise ManifestError(f"{location}: {error}") from error


def text_value(value: object, location: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"{location} must be a string")
    return value


def boolean_value(value: object, location: str) -> bool:
    if type(value) is not bool:
        raise ManifestError(f"{location} must be a boolean")
    return value


def integer_value(value: object, location: str) -> int:
    if type(value) is not int:
        raise ManifestError(f"{location} must be an integer")
    return value


def date_value(value: object, location: str) -> date:
    text = text_value(value, location)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ManifestError(f"{location} must be an ISO 8601 date") from error


def path_value(value: object, location: str) -> PurePosixPath:
    return PurePosixPath(text_value(value, location))


def source_id_value(value: object, location: str) -> SourceId:
    return SourceId(text_value(value, location))


def status_id_value(value: object, location: str) -> StatusId:
    return StatusId(text_value(value, location))


def https_url_value(value: object, location: str) -> HttpsUrl:
    return HttpsUrl(text_value(value, location))


def sha256_value(value: object, location: str) -> Sha256Digest:
    return Sha256Digest(text_value(value, location))


def parse_link(value: object, location: str) -> SourceLink:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset({"role", "url", "archived_url", "archive_status"}),
    )
    return domain_value(
        location,
        lambda: SourceLink(
            role=record.required("role", text_value),
            url=record.optional("url", https_url_value),
            archived_url=record.optional("archived_url", https_url_value),
            archive_status=record.optional("archive_status", text_value),
        ),
    )


def parse_collection_reference(value: object, location: str) -> CollectionReference:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset({"source_id", "status_id"}),
    )
    return domain_value(
        location,
        lambda: CollectionReference(
            source_id=record.required("source_id", source_id_value),
            status_id=record.required("status_id", status_id_value),
        ),
    )


def parse_artifact(value: object, location: str) -> SnapshotArtifact:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset({"role", "path", "sha256", "upstream_path"}),
    )
    return domain_value(
        location,
        lambda: SnapshotArtifact(
            role=record.required("role", text_value),
            path=record.required("path", path_value),
            sha256=record.required("sha256", sha256_value),
            upstream_path=record.optional("upstream_path", text_value),
        ),
    )


def parse_rights(value: object, location: str) -> SnapshotRights:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset({"license", "scope", "disposition"}),
    )
    return domain_value(
        location,
        lambda: SnapshotRights(
            license=record.required("license", text_value),
            scope=record.required("scope", text_value),
            disposition=record.optional("disposition", text_value),
        ),
    )


def parse_linked_evidence(record: JsonObject) -> LinkedEvidence:
    location = record.location
    return domain_value(
        location,
        lambda: LinkedEvidence(
            links=record.array("links", parse_link, required=True),
            related_urls=record.array("related_urls", https_url_value, required=False),
            retrieval_helper=record.optional("retrieval_helper", path_value),
            collection_reference=record.optional(
                "collection_reference", parse_collection_reference
            ),
        ),
    )


def parse_snapshot_evidence(record: JsonObject) -> SnapshotEvidence:
    location = record.location
    return domain_value(
        location,
        lambda: SnapshotEvidence(
            retrieved_at=record.required("retrieved_at", date_value),
            artifacts=record.array("artifacts", parse_artifact, required=True),
            rights=record.required("rights", parse_rights),
            links=record.array("links", parse_link, required=False),
            related_urls=record.array("related_urls", https_url_value, required=False),
            pinned_revision=record.optional("pinned_revision", text_value),
        ),
    )


def parse_evidence(value: object, location: str) -> Evidence:
    if not isinstance(value, dict):
        raise ManifestError(f"{location} must be an object")
    fields = cast(dict[str, object], value)
    if "type" not in fields:
        raise ManifestError(f"{location}.type is required")
    evidence_type = text_value(fields["type"], f"{location}.type")
    variants: dict[str, tuple[frozenset[str], Callable[[JsonObject], Evidence]]] = {
        "linked": (
            frozenset(
                {
                    "type",
                    "links",
                    "related_urls",
                    "retrieval_helper",
                    "collection_reference",
                }
            ),
            parse_linked_evidence,
        ),
        "snapshot": (
            frozenset(
                {
                    "type",
                    "retrieved_at",
                    "artifacts",
                    "rights",
                    "links",
                    "related_urls",
                    "pinned_revision",
                }
            ),
            parse_snapshot_evidence,
        ),
        "repository_note": (
            frozenset({"type", "path"}),
            lambda record: domain_value(
                record.location,
                lambda: RepositoryNoteEvidence(
                    path=record.required("path", path_value)
                ),
            ),
        ),
        "private_review": (
            frozenset({"type", "access"}),
            lambda record: domain_value(
                record.location,
                lambda: PrivateReviewEvidence(
                    access=record.required("access", text_value)
                ),
            ),
        ),
    }
    variant = variants.get(evidence_type)
    if variant is None:
        raise ManifestError(f"{location}.type has unknown variant: {evidence_type!r}")
    allowed, decode = variant
    return decode(JsonObject.decode(fields, location=location, allowed=allowed))


def parse_source(value: object, location: str) -> SourceRecord:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset(
            {
                "id",
                "title",
                "date",
                "reviewed_at",
                "authors",
                "kind",
                "classification",
                "canonical",
                "review_basis",
                "duplicate_of",
                "notes",
                "evidence",
                "publisher",
                "authorship_scope",
            }
        ),
    )
    return domain_value(
        location,
        lambda: SourceRecord(
            id=record.required("id", source_id_value),
            title=record.required("title", text_value),
            date=record.nullable("date", date_value),
            reviewed_at=record.required("reviewed_at", date_value),
            authors=record.array("authors", text_value, required=True),
            kind=record.required("kind", text_value),
            classification=record.required("classification", text_value),
            canonical=record.required("canonical", boolean_value),
            review_basis=record.required("review_basis", text_value),
            duplicate_of=record.nullable("duplicate_of", source_id_value),
            notes=record.required("notes", text_value),
            evidence=record.required("evidence", parse_evidence),
            publisher=record.optional("publisher", text_value),
            authorship_scope=record.optional("authorship_scope", text_value),
        ),
    )


def parse_license(value: object, location: str) -> LicensePolicy:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=frozenset({"id", "url", "scope"}),
    )
    return domain_value(
        location,
        lambda: LicensePolicy(
            id=record.required("id", text_value),
            url=record.required("url", https_url_value),
            scope=record.required("scope", text_value),
        ),
    )


def parse_manifest_data(value: object) -> Manifest:
    record = JsonObject.decode(
        value,
        location="manifest",
        allowed=frozenset(
            {
                "schema_version",
                "as_of",
                "maintainer",
                "repository_purpose",
                "license",
                "sources",
            }
        ),
    )
    return domain_value(
        "manifest",
        lambda: Manifest(
            schema_version=record.required("schema_version", integer_value),
            as_of=record.required("as_of", date_value),
            maintainer=record.required("maintainer", text_value),
            repository_purpose=record.required("repository_purpose", text_value),
            license=record.required("license", parse_license),
            sources=record.array("sources", parse_source, required=True),
        ),
    )


def load_manifest(path: Path) -> Manifest:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError(f"could not read {path}: {error}") from error
    except UnicodeDecodeError as error:
        raise ManifestError(f"{path} is not valid UTF-8: {error}") from error
    try:
        return parse_manifest_data(json.loads(text))
    except json.JSONDecodeError as error:
        raise ManifestError(
            f"{path}:{error.lineno}:{error.colno}: {error.msg}"
        ) from error
