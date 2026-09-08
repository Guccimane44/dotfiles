"""Closed typed boundary for the captured Twitter corpus."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import NewType
from urllib.parse import urlsplit

from source_manifest import (
    HttpsUrl,
    JsonObject,
    ManifestError,
    Sha256Digest,
    StatusId,
    boolean_value,
    date_value,
    domain_value,
    https_url_value,
    integer_value,
    require_https,
    require_sha256,
    sha256_value,
    status_id_value,
    text_value,
)

STATUS_PATH = re.compile(r"/status/([0-9]+)(?:/)?\Z")
ABBREVIATED_COUNT = re.compile(r"([0-9]+)([KM])?\Z")
HANDLE = re.compile(r"@[A-Za-z0-9_]{1,15}\Z")
NUMERIC_ID = re.compile(r"[0-9]+\Z")
TWITTER_EPOCH_MILLISECONDS = 1_288_834_974_657

TwitterHandle = NewType("TwitterHandle", str)
TwitterAuthorId = NewType("TwitterAuthorId", str)
type PublicDisplayTime = date | datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class UtcDateTime:
    value: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.value, datetime):
            raise ValueError("UTC datetime value must be a datetime")
        if self.value.utcoffset() != timedelta(0):
            raise ValueError("UTC datetime value must use UTC")


def require_utc_datetime(value: object, name: str) -> UtcDateTime:
    if not isinstance(value, UtcDateTime):
        raise ValueError(f"{name} must be a UtcDateTime")
    return value


ROOT_FIELDS = frozenset(
    {
        "generated_at",
        "corrected_at",
        "corrections",
        "owner",
        "scope",
        "coverage_notes",
        "post_count",
        "mld_thread",
        "posts",
        "deleted_posts",
    }
)
OWNER_FIELDS = frozenset({"name", "handle"})
MLD_FIELDS = frozenset(
    {
        "interpretation",
        "evidence",
        "originating_question",
        "ryan_post_ids_in_order",
        "clarifying_question",
        "public_caveat_replies",
        "public_caveat_note",
    }
)
MLD_EVIDENCE_FIELDS = frozenset(
    {
        "official_x_oembed_template",
        "public_thread_urls",
        "archived_x_api_urls",
    }
)
REFERENCED_POST_FIELDS = frozenset({"id", "author", "date", "summary", "url"})
ENGAGEMENT_FIELDS = frozenset({"views", "replies", "reposts", "likes", "bookmarks"})
PUBLIC_ROW_FIELDS = frozenset(
    {
        "id",
        "date",
        "text",
        "replying_to",
        "in_reply_to_status_id",
        "quoted_status_id",
        "quoted_url",
        "media_urls",
        "thread_role",
        "url",
        "public_provenance",
    }
)
DELETED_ROW_FIELDS = frozenset(
    {
        "date",
        "text",
        "status_id",
        "url",
        "archive_url",
        "archive_capture_time",
        "created_at",
        "author_id",
        "conversation_id",
        "engagement_from_screenshot",
        "screenshot_capture_date",
        "screenshot_artifact_sha256",
        "screenshot_redistributed",
        "public_provenance",
    }
)


def nonempty_text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be nonempty text")


def nonempty_texts(values: tuple[str, ...], name: str) -> None:
    if not values:
        raise ValueError(f"{name} must be nonempty")
    for value in values:
        nonempty_text(value, name)


def x_status_identity(
    url: str | None,
) -> tuple[StatusId, TwitterHandle] | None:
    if url is None:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "x.com",
        "twitter.com",
        "www.x.com",
        "www.twitter.com",
    }:
        return None
    match = STATUS_PATH.search(parsed.path)
    parts = parsed.path.strip("/").split("/")
    if match is None or len(parts) != 3 or parts[1] != "status":
        return None
    handle = TwitterHandle(f"@{parts[0]}")
    if HANDLE.fullmatch(handle) is None:
        return None
    return StatusId(match.group(1)), handle


def status_id_from_url_path(url: HttpsUrl) -> StatusId | None:
    parsed = urlsplit(url)
    match = STATUS_PATH.search(parsed.path)
    if match is None:
        return None
    return StatusId(match.group(1))


def snowflake_created_at(status_id: StatusId, name: str = "status id") -> datetime:
    if not isinstance(status_id, str) or not NUMERIC_ID.fullmatch(status_id):
        raise ValueError(f"{name} must be numeric")
    milliseconds = (int(status_id) >> 22) + TWITTER_EPOCH_MILLISECONDS
    try:
        created_at = datetime.fromtimestamp(
            milliseconds // 1_000,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError(f"{name} exceeds the supported timestamp range") from error
    return created_at.replace(microsecond=(milliseconds % 1_000) * 1_000)


def utc_datetime_value(value: object, location: str) -> UtcDateTime:
    text = text_value(value, location)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(f"{location} must be an ISO 8601 timestamp") from error
    return domain_value(location, lambda: UtcDateTime(value=parsed))


def public_display_time_value(value: object, location: str) -> PublicDisplayTime:
    text = text_value(value, location)
    try:
        if " · " in text:
            return datetime.strptime(
                text,
                "%b %d, %Y · %I:%M %p UTC",
            ).replace(tzinfo=timezone.utc)
        return datetime.strptime(text, "%b %d, %Y").date()
    except ValueError as error:
        raise ManifestError(
            f"{location} must be a supported Twitter display time"
        ) from error


def local_display_time_value(value: object, location: str) -> datetime:
    text = text_value(value, location)
    suffix = " (screenshot local time)"
    if not text.endswith(suffix):
        raise ManifestError(f"{location} must identify screenshot local time")
    try:
        return datetime.strptime(
            text.removesuffix(suffix),
            "%b %d, %Y · %I:%M %p",
        )
    except ValueError as error:
        raise ManifestError(
            f"{location} must be a supported screenshot display time"
        ) from error


def twitter_handle_value(value: object, location: str) -> TwitterHandle:
    return TwitterHandle(text_value(value, location))


def twitter_author_id_value(value: object, location: str) -> TwitterAuthorId:
    return TwitterAuthorId(text_value(value, location))


def engagement_count_value(value: object, location: str) -> int:
    if type(value) is int:
        return value
    text = text_value(value, location)
    match = ABBREVIATED_COUNT.fullmatch(text)
    if match is None:
        raise ManifestError(f"{location} has an invalid abbreviated count")
    multiplier = {None: 1, "K": 1_000, "M": 1_000_000}[match.group(2)]
    return int(match.group(1)) * multiplier


def display_time_matches(
    displayed_at: PublicDisplayTime,
    created_at: datetime,
) -> bool:
    if isinstance(displayed_at, datetime):
        return displayed_at == created_at.replace(second=0, microsecond=0)
    if isinstance(displayed_at, date):
        return displayed_at == created_at.date()
    return False


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterCorpusOwner:
    name: str
    handle: TwitterHandle

    def __post_init__(self) -> None:
        nonempty_text(self.name, "corpus owner name")
        if not isinstance(self.handle, str) or not HANDLE.fullmatch(self.handle):
            raise ValueError("corpus owner handle must be a valid X handle")


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterMLDEvidence:
    official_x_oembed_template: HttpsUrl
    public_thread_urls: tuple[HttpsUrl, ...]
    archived_x_api_urls: tuple[HttpsUrl, ...]
    _public_status_ids: tuple[StatusId, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        require_https(
            self.official_x_oembed_template,
            "official X oEmbed template",
        )
        if self.official_x_oembed_template.count("{status_id}") != 1:
            raise ValueError("official X oEmbed template requires {status_id}")
        if not self.public_thread_urls:
            raise ValueError("MLD evidence requires public thread URLs")
        public_status_ids: list[StatusId] = []
        for url in self.public_thread_urls:
            public_url = require_https(url, "public thread URL")
            status_id = status_id_from_url_path(public_url)
            if status_id is None:
                raise ValueError("public thread URL must identify a status path")
            public_status_ids.append(status_id)
        if not self.archived_x_api_urls:
            raise ValueError("MLD evidence requires archived X API URLs")
        archived_status_ids: list[StatusId] = []
        for url in self.archived_x_api_urls:
            archived_url = require_https(url, "archived X API URL")
            status_id = status_id_from_url_path(archived_url)
            if status_id is None:
                raise ValueError("archived X API URL must identify a status path")
            archived_status_ids.append(status_id)
        if not set(archived_status_ids).issubset(public_status_ids):
            raise ValueError("archived X API URLs must belong to the public thread")
        object.__setattr__(self, "_public_status_ids", tuple(public_status_ids))

    @property
    def public_status_ids(self) -> tuple[StatusId, ...]:
        return self._public_status_ids


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterReferencedPost:
    status_id: StatusId
    author: str
    displayed_at: PublicDisplayTime
    summary: str
    canonical_url: HttpsUrl

    def __post_init__(self) -> None:
        nonempty_text(self.author, "referenced-post author")
        nonempty_text(self.summary, "referenced-post summary")
        identity = x_status_identity(self.canonical_url)
        if identity is None or identity[0] != self.status_id:
            raise ValueError("referenced-post URL must match its status id")
        created_at = snowflake_created_at(
            self.status_id,
            "referenced-post status id",
        )
        if not display_time_matches(self.displayed_at, created_at):
            raise ValueError("referenced-post display time disagrees with status id")


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterMLDThread:
    interpretation: str
    evidence: TwitterMLDEvidence
    originating_question: TwitterReferencedPost
    ryan_post_ids_in_order: tuple[StatusId, ...]
    clarifying_question: TwitterReferencedPost
    public_caveat_replies: tuple[TwitterReferencedPost, ...]
    public_caveat_note: str

    def __post_init__(self) -> None:
        nonempty_text(self.interpretation, "MLD interpretation")
        nonempty_text(self.public_caveat_note, "MLD public caveat note")
        if not self.ryan_post_ids_in_order:
            raise ValueError("MLD thread requires Ryan post ids")
        if len(self.ryan_post_ids_in_order) != len(set(self.ryan_post_ids_in_order)):
            raise ValueError("MLD Ryan post ids must be unique")
        for status_id in self.ryan_post_ids_in_order:
            snowflake_created_at(status_id, "MLD Ryan post id")
        if self.evidence.public_status_ids != self.ryan_post_ids_in_order:
            raise ValueError("MLD public thread URLs must follow Ryan post order")
        if not self.public_caveat_replies:
            raise ValueError("MLD thread requires its retained public caveats")


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterEngagement:
    views: int
    replies: int
    reposts: int
    likes: int
    bookmarks: int

    def __post_init__(self) -> None:
        for name in ("views", "replies", "reposts", "likes", "bookmarks"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative count")


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicTwitterCorpusRow:
    status_id: StatusId
    canonical_url: HttpsUrl
    displayed_at: PublicDisplayTime
    text: str | None
    public_provenance: tuple[str, ...]
    replying_to: str | None
    in_reply_to_status_id: StatusId | None = None
    quoted_status_id: StatusId | None = None
    quoted_url: HttpsUrl | None = None
    media_urls: tuple[HttpsUrl, ...] = ()
    thread_role: str | None = None
    _created_at: datetime = field(init=False, repr=False, compare=False)
    _author_handle: TwitterHandle = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        identity = x_status_identity(self.canonical_url)
        if identity is None or identity[0] != self.status_id:
            raise ValueError("public Twitter row URL must match its status id")
        created_at = snowflake_created_at(self.status_id)
        if not display_time_matches(self.displayed_at, created_at):
            raise ValueError("Twitter display time disagrees with its status id")
        if self.text is not None:
            nonempty_text(self.text, "Twitter post text")
        nonempty_texts(self.public_provenance, "public_provenance")
        if self.replying_to is not None:
            nonempty_text(self.replying_to, "replying_to")
        if self.in_reply_to_status_id is not None:
            snowflake_created_at(
                self.in_reply_to_status_id,
                "in-reply-to status id",
            )
        if self.quoted_status_id is not None:
            snowflake_created_at(self.quoted_status_id, "quoted status id")
        quoted_identity = None
        if self.quoted_url is not None:
            quoted_identity = x_status_identity(self.quoted_url)
            if quoted_identity is None:
                raise ValueError("quoted URL must identify an HTTPS X status")
        if (
            self.quoted_status_id is not None
            and quoted_identity is not None
            and quoted_identity[0] != self.quoted_status_id
        ):
            raise ValueError("quoted status id disagrees with quoted URL")
        for media_url in self.media_urls:
            require_https(media_url, "media URL")
        relation_ids = (
            self.in_reply_to_status_id,
            self.quoted_status_id,
        )
        has_owned_relation = any(status_id is not None for status_id in relation_ids)
        if has_owned_relation and self.thread_role is None:
            raise ValueError("thread_role is required for a retained thread relation")
        if self.thread_role is not None:
            nonempty_text(self.thread_role, "thread_role")
            if not has_owned_relation:
                raise ValueError("thread_role requires a retained thread relation")
        if (
            self.text is None
            and self.quoted_status_id is None
            and self.quoted_url is None
            and not self.media_urls
        ):
            raise ValueError("public Twitter row requires text, quote, or media")
        object.__setattr__(self, "_created_at", created_at)
        object.__setattr__(self, "_author_handle", identity[1])

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def author_handle(self) -> TwitterHandle:
        return self._author_handle


@dataclass(frozen=True, slots=True, kw_only=True)
class DeletedTwitterCorpusRow:
    status_id: StatusId
    canonical_url: HttpsUrl
    displayed_at_local: datetime
    text: str
    public_provenance: tuple[str, ...]
    created_at_utc: UtcDateTime
    archive_url: HttpsUrl
    archive_captured_at_utc: UtcDateTime
    author_id: TwitterAuthorId
    conversation_id: StatusId
    engagement_at_capture: TwitterEngagement
    screenshot_capture_date: date
    screenshot_sha256: Sha256Digest
    screenshot_redistributed: bool
    _author_handle: TwitterHandle = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        identity = x_status_identity(self.canonical_url)
        if identity is None or identity[0] != self.status_id:
            raise ValueError("deleted Twitter row URL must match its status id")
        snowflake_time = snowflake_created_at(self.status_id)
        created_at = require_utc_datetime(
            self.created_at_utc,
            "deleted creation time",
        ).value
        if created_at.replace(microsecond=0) != snowflake_time.replace(microsecond=0):
            raise ValueError("deleted creation time disagrees with its status id")
        if self.displayed_at_local.tzinfo is not None:
            raise ValueError("screenshot display time must remain local and naive")
        nonempty_text(self.text, "deleted Twitter post text")
        nonempty_texts(self.public_provenance, "public_provenance")
        require_https(self.archive_url, "deleted Twitter archive URL")
        archive_captured_at = require_utc_datetime(
            self.archive_captured_at_utc,
            "archive capture time",
        ).value
        if archive_captured_at < created_at:
            raise ValueError("archive capture cannot precede post creation")
        if not isinstance(self.author_id, str) or not NUMERIC_ID.fullmatch(
            self.author_id
        ):
            raise ValueError("Twitter author id must be numeric")
        snowflake_created_at(self.conversation_id, "conversation id")
        if self.conversation_id != self.status_id:
            raise ValueError("conversation id must match the retained root post")
        if self.screenshot_capture_date < created_at.date():
            raise ValueError("screenshot capture cannot precede post creation")
        require_sha256(self.screenshot_sha256, "screenshot artifact SHA-256")
        if type(self.screenshot_redistributed) is not bool:
            raise ValueError("screenshot_redistributed must be a boolean")
        if self.screenshot_redistributed:
            raise ValueError("redistributed screenshot requires an owned artifact path")
        object.__setattr__(self, "_author_handle", identity[1])

    @property
    def author_handle(self) -> TwitterHandle:
        return self._author_handle

    @property
    def created_at(self) -> datetime:
        return self.created_at_utc.value

    @property
    def archive_captured_at(self) -> datetime:
        return self.archive_captured_at_utc.value


type TwitterCorpusRow = PublicTwitterCorpusRow | DeletedTwitterCorpusRow


@dataclass(frozen=True, slots=True, kw_only=True)
class TwitterCorpus:
    generated_at_utc: UtcDateTime
    corrected_at_utc: UtcDateTime | None
    corrections: tuple[str, ...]
    owner: TwitterCorpusOwner
    scope: str
    coverage_notes: tuple[str, ...]
    post_count: int
    mld_thread: TwitterMLDThread
    posts: tuple[PublicTwitterCorpusRow, ...]
    deleted_posts: tuple[DeletedTwitterCorpusRow, ...]

    def __post_init__(self) -> None:
        generated_at = require_utc_datetime(
            self.generated_at_utc,
            "corpus generation time",
        ).value
        corrected_at = (
            None
            if self.corrected_at_utc is None
            else require_utc_datetime(
                self.corrected_at_utc,
                "corpus correction time",
            ).value
        )
        if corrected_at is not None:
            if corrected_at < generated_at:
                raise ValueError("corpus correction cannot precede generation")
        if (corrected_at is not None) != bool(self.corrections):
            raise ValueError("correction time and notes must appear together")
        for correction in self.corrections:
            nonempty_text(correction, "correction note")
        nonempty_text(self.scope, "corpus scope")
        nonempty_texts(self.coverage_notes, "coverage_notes")
        rows = self.rows
        status_ids = [row.status_id for row in rows]
        if len(status_ids) != len(set(status_ids)):
            raise ValueError("social corpus has duplicate status ids")
        if type(self.post_count) is not int or self.post_count != len(self.posts):
            raise ValueError("post_count must equal the number of public posts")
        if any(row.author_handle != self.owner.handle for row in rows):
            raise ValueError("every corpus row must belong to the declared owner")
        originating_id = self.mld_thread.originating_question.status_id
        clarifying_id = self.mld_thread.clarifying_question.status_id
        mld_relation_targets = {
            *self.mld_thread.ryan_post_ids_in_order,
            originating_id,
            clarifying_id,
        }
        thread_rows = [row for row in self.posts if row.thread_role is not None]
        thread_row_ids = tuple(row.status_id for row in thread_rows)
        if thread_row_ids != self.mld_thread.ryan_post_ids_in_order:
            raise ValueError("curated thread rows must match Ryan post order")
        thread_roles = [row.thread_role for row in thread_rows]
        if len(thread_roles) != len(set(thread_roles)):
            raise ValueError("MLD thread roles must be unique")
        if any(
            relation_id not in mld_relation_targets
            for row in thread_rows
            for relation_id in (
                row.in_reply_to_status_id,
                row.quoted_status_id,
            )
            if relation_id is not None
        ):
            raise ValueError("MLD thread relation points outside retained context")
        if not any(row.in_reply_to_status_id == originating_id for row in self.posts):
            raise ValueError("MLD originating question lacks its Ryan reply")
        if not any(row.in_reply_to_status_id == clarifying_id for row in self.posts):
            raise ValueError("MLD clarifying question lacks its Ryan reply")

    @property
    def effective_at(self) -> datetime:
        return self.corrected_at or self.generated_at

    @property
    def generated_at(self) -> datetime:
        return self.generated_at_utc.value

    @property
    def corrected_at(self) -> datetime | None:
        if self.corrected_at_utc is None:
            return None
        return self.corrected_at_utc.value

    @property
    def rows(self) -> tuple[TwitterCorpusRow, ...]:
        return (*self.posts, *self.deleted_posts)

    def row(self, status_id: StatusId) -> TwitterCorpusRow | None:
        return next((row for row in self.rows if row.status_id == status_id), None)

    @classmethod
    def from_json(
        cls,
        value: object,
        location: str = "twitter corpus",
    ) -> TwitterCorpus:
        record = JsonObject.decode(value, location=location, allowed=ROOT_FIELDS)
        return domain_value(
            location,
            lambda: cls(
                generated_at_utc=record.required(
                    "generated_at",
                    utc_datetime_value,
                ),
                corrected_at_utc=record.nullable(
                    "corrected_at",
                    utc_datetime_value,
                ),
                corrections=record.array(
                    "corrections",
                    text_value,
                    required=True,
                ),
                owner=record.required("owner", parse_owner),
                scope=record.required("scope", text_value),
                coverage_notes=record.array(
                    "coverage_notes",
                    text_value,
                    required=True,
                ),
                post_count=record.required("post_count", integer_value),
                mld_thread=record.required("mld_thread", parse_mld_thread),
                posts=record.array(
                    "posts",
                    parse_public_twitter_row,
                    required=True,
                ),
                deleted_posts=record.array(
                    "deleted_posts",
                    parse_deleted_twitter_row,
                    required=True,
                ),
            ),
        )


def parse_owner(value: object, location: str) -> TwitterCorpusOwner:
    record = JsonObject.decode(value, location=location, allowed=OWNER_FIELDS)
    return domain_value(
        location,
        lambda: TwitterCorpusOwner(
            name=record.required("name", text_value),
            handle=record.required("handle", twitter_handle_value),
        ),
    )


def parse_mld_evidence(value: object, location: str) -> TwitterMLDEvidence:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=MLD_EVIDENCE_FIELDS,
    )
    return domain_value(
        location,
        lambda: TwitterMLDEvidence(
            official_x_oembed_template=record.required(
                "official_x_oembed_template",
                https_url_value,
            ),
            public_thread_urls=record.array(
                "public_thread_urls",
                https_url_value,
                required=True,
            ),
            archived_x_api_urls=record.array(
                "archived_x_api_urls",
                https_url_value,
                required=True,
            ),
        ),
    )


def parse_referenced_post(value: object, location: str) -> TwitterReferencedPost:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=REFERENCED_POST_FIELDS,
    )
    return domain_value(
        location,
        lambda: TwitterReferencedPost(
            status_id=record.required("id", status_id_value),
            author=record.required("author", text_value),
            displayed_at=record.required("date", public_display_time_value),
            summary=record.required("summary", text_value),
            canonical_url=record.required("url", https_url_value),
        ),
    )


def parse_mld_thread(value: object, location: str) -> TwitterMLDThread:
    record = JsonObject.decode(value, location=location, allowed=MLD_FIELDS)
    return domain_value(
        location,
        lambda: TwitterMLDThread(
            interpretation=record.required("interpretation", text_value),
            evidence=record.required("evidence", parse_mld_evidence),
            originating_question=record.required(
                "originating_question",
                parse_referenced_post,
            ),
            ryan_post_ids_in_order=record.array(
                "ryan_post_ids_in_order",
                status_id_value,
                required=True,
            ),
            clarifying_question=record.required(
                "clarifying_question",
                parse_referenced_post,
            ),
            public_caveat_replies=record.array(
                "public_caveat_replies",
                parse_referenced_post,
                required=True,
            ),
            public_caveat_note=record.required(
                "public_caveat_note",
                text_value,
            ),
        ),
    )


def parse_engagement(value: object, location: str) -> TwitterEngagement:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=ENGAGEMENT_FIELDS,
    )
    return domain_value(
        location,
        lambda: TwitterEngagement(
            views=record.required("views", engagement_count_value),
            replies=record.required("replies", engagement_count_value),
            reposts=record.required("reposts", engagement_count_value),
            likes=record.required("likes", engagement_count_value),
            bookmarks=record.required("bookmarks", engagement_count_value),
        ),
    )


def parse_public_twitter_row(
    value: object,
    location: str,
) -> PublicTwitterCorpusRow:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=PUBLIC_ROW_FIELDS,
    )
    return domain_value(
        location,
        lambda: PublicTwitterCorpusRow(
            status_id=record.required("id", status_id_value),
            canonical_url=record.required("url", https_url_value),
            displayed_at=record.required("date", public_display_time_value),
            text=record.nullable("text", text_value),
            public_provenance=record.array(
                "public_provenance",
                text_value,
                required=True,
            ),
            replying_to=record.nullable("replying_to", text_value),
            in_reply_to_status_id=record.optional(
                "in_reply_to_status_id",
                status_id_value,
            ),
            quoted_status_id=record.optional(
                "quoted_status_id",
                status_id_value,
            ),
            quoted_url=record.optional("quoted_url", https_url_value),
            media_urls=record.array(
                "media_urls",
                https_url_value,
                required=False,
            ),
            thread_role=record.optional("thread_role", text_value),
        ),
    )


def parse_deleted_twitter_row(
    value: object,
    location: str,
) -> DeletedTwitterCorpusRow:
    record = JsonObject.decode(
        value,
        location=location,
        allowed=DELETED_ROW_FIELDS,
    )
    return domain_value(
        location,
        lambda: DeletedTwitterCorpusRow(
            status_id=record.required("status_id", status_id_value),
            canonical_url=record.required("url", https_url_value),
            displayed_at_local=record.required("date", local_display_time_value),
            text=record.required("text", text_value),
            public_provenance=record.array(
                "public_provenance",
                text_value,
                required=True,
            ),
            created_at_utc=record.required("created_at", utc_datetime_value),
            archive_url=record.required("archive_url", https_url_value),
            archive_captured_at_utc=record.required(
                "archive_capture_time",
                utc_datetime_value,
            ),
            author_id=record.required("author_id", twitter_author_id_value),
            conversation_id=record.required(
                "conversation_id",
                status_id_value,
            ),
            engagement_at_capture=record.required(
                "engagement_from_screenshot",
                parse_engagement,
            ),
            screenshot_capture_date=record.required(
                "screenshot_capture_date",
                date_value,
            ),
            screenshot_sha256=record.required(
                "screenshot_artifact_sha256",
                sha256_value,
            ),
            screenshot_redistributed=record.required(
                "screenshot_redistributed",
                boolean_value,
            ),
        ),
    )
