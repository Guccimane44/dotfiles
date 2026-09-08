#!/usr/bin/env -S uv run --locked --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "httpx==0.28.1",
#   "stamina==26.1.0",
# ]
# ///

"""Fetch the OpenAI harness-engineering essay as readable text."""

from __future__ import annotations

import re
import sys
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path

import httpx  # ty: ignore[unresolved-import]
import stamina  # ty: ignore[unresolved-import]

from source_manifest import LinkedEvidence, SourceId, SourceRecord, load_manifest

SOURCE_ID = SourceId("openai-harness")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "sources/sources.json"
RETRY_TIMEOUT = timedelta(seconds=90)
REQUEST_TIMEOUT = timedelta(seconds=45)
CONNECT_TIMEOUT = timedelta(seconds=10)


def retryable(exc: Exception) -> bool | timedelta:
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            retry_after = exc.response.headers.get("Retry-After", "").strip()
            return (
                timedelta(seconds=int(retry_after)) if retry_after.isdecimal() else True
            )
        return exc.response.status_code in {408, 425, 500, 502, 503, 504}
    return isinstance(exc, httpx.TransportError)


@stamina.retry(on=retryable, attempts=4, timeout=RETRY_TIMEOUT)
def get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def source_record() -> SourceRecord:
    manifest = load_manifest(MANIFEST_PATH)
    for source in manifest.sources:
        if source.id == SOURCE_ID:
            return source
    raise RuntimeError(f"{SOURCE_ID!r} is missing from the source manifest")


def fetch_candidates(source: SourceRecord) -> tuple[str, str]:
    if not isinstance(source.evidence, LinkedEvidence):
        raise ValueError(f"{SOURCE_ID!r} must use linked evidence")
    canonical = next(link for link in source.evidence.links if link.role == "canonical")
    if canonical.url is None or canonical.archived_url is None:
        raise ValueError(f"{SOURCE_ID!r} requires canonical and archived URLs")
    return canonical.url, canonical.archived_url


class MainText(HTMLParser):
    """Extract readable blocks from the document's main landmark."""

    ignored = {"footer", "header", "nav", "script", "style", "svg"}
    blocks = {"blockquote", "div", "h1", "h2", "h3", "h4", "li", "p", "pre"}

    def __init__(self) -> None:
        super().__init__()
        self.in_main = 0
        self.ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "main":
            self.in_main += 1
        if self.in_main and tag in self.ignored:
            self.ignored_depth += 1
        if self.in_main and not self.ignored_depth:
            if tag in self.blocks:
                self.parts.append("\n\n")
            elif tag == "br":
                self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.in_main and tag in self.ignored and self.ignored_depth:
            self.ignored_depth -= 1
        if self.in_main and not self.ignored_depth and tag in self.blocks:
            self.parts.append("\n\n")
        if tag == "main":
            self.in_main -= 1

    def handle_data(self, data: str) -> None:
        if self.in_main and not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[\t\r\f\v ]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text.partition("\n\nKeep reading\n\n")[0]


def fetch_text(client: httpx.Client, source: SourceRecord) -> tuple[str, str]:
    for candidate in fetch_candidates(source):
        try:
            response = get(client, candidate)
        except httpx.HTTPError:
            continue
        parser = MainText()
        parser.feed(response.text)
        text = parser.text()
        if source.title in text:
            return text, candidate

    raise RuntimeError("canonical and archived copies were unavailable")


def main() -> None:
    source = source_record()
    timeout = httpx.Timeout(
        REQUEST_TIMEOUT.total_seconds(),
        connect=CONNECT_TIMEOUT.total_seconds(),
    )
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        text, fetched_from = fetch_text(client, source)

    print(f"Fetched from {fetched_from}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
