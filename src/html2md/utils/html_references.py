"""Shared parsing helpers for HTML document-base and responsive references."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class SrcsetCandidate:
    """One URL and optional density/width descriptor from a `srcset` value."""

    url: str
    descriptor: str | None = None


def resolve_document_base(soup: BeautifulSoup, source_url: str) -> str:
    """Resolve the first HTTP(S) base URL, falling back to the source URL."""
    base = soup.find("base", href=True)
    if not isinstance(base, Tag):
        return source_url
    href = base.get("href")
    if not isinstance(href, str) or not href.strip():
        return source_url
    candidate = urljoin(source_url, href.strip())
    return (
        candidate
        if urlsplit(candidate).scheme.casefold() in {"http", "https"}
        else source_url
    )


def parse_srcset(value: str) -> list[SrcsetCandidate]:
    """Parse the URL/descriptor pairs used by the supported srcset contract."""
    stripped = value.strip()
    if not stripped:
        return []
    # Data URLs contain commas that are not candidate delimiters. They are not
    # downloaded or canonicalized, so preserve the complete authored value.
    if stripped.casefold().startswith("data:"):
        return [SrcsetCandidate(stripped)]
    candidates: list[SrcsetCandidate] = []
    for raw_candidate in stripped.split(","):
        parts = raw_candidate.strip().split(maxsplit=1)
        if parts:
            candidates.append(
                SrcsetCandidate(parts[0], parts[1] if len(parts) == 2 else None)
            )
    return candidates


def serialize_srcset(candidates: list[SrcsetCandidate]) -> str:
    """Serialize parsed srcset candidates deterministically."""
    return ", ".join(
        (
            f"{candidate.url} {candidate.descriptor}"
            if candidate.descriptor
            else candidate.url
        )
        for candidate in candidates
    )
