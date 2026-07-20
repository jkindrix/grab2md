"""Prepare HTML documents for stable Markdown conversion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from html2md.utils.html_references import (
    SrcsetCandidate,
    parse_srcset,
    resolve_document_base,
    serialize_srcset,
)


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata fields supported by the Markdown front-matter contract."""

    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    canonical_url: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None

    def front_matter(self) -> str:
        """Serialize populated fields as deterministic YAML-compatible scalars."""
        values = (
            ("title", self.title),
            ("author", self.author),
            ("date", self.date),
            ("canonical_url", self.canonical_url),
            ("description", self.description),
            ("language", self.language),
        )
        lines = [
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in values
            if value
        ]
        body = "\n".join(lines)
        return f"---\n{body}\n---\n\n" if lines else ""


def _attribute(tag: Tag, name: str) -> Optional[str]:
    value = tag.attrs.get(name)
    if isinstance(value, str):
        normalized = " ".join(value.split())
        return normalized or None
    return None


def _meta_content(soup: BeautifulSoup, *identifiers: str) -> Optional[str]:
    wanted = {identifier.casefold() for identifier in identifiers}
    for tag in soup.find_all("meta"):
        if not isinstance(tag, Tag):
            continue
        keys = (
            _attribute(tag, "name"),
            _attribute(tag, "property"),
            _attribute(tag, "itemprop"),
        )
        if any(key and key.casefold() in wanted for key in keys):
            content = _attribute(tag, "content")
            if content:
                return content
    return None


def _is_remote(url: str) -> bool:
    return urlsplit(url).scheme.casefold() in {"http", "https"}


def _canonicalize(value: str, base_url: str) -> str:
    stripped = value.strip()
    if not stripped or stripped.startswith("#"):
        return value
    candidate = urljoin(base_url, stripped)
    return candidate if _is_remote(candidate) else value


def _canonicalize_srcset(value: str, base_url: str) -> str:
    return serialize_srcset(
        [
            SrcsetCandidate(
                _canonicalize(candidate.url, base_url), candidate.descriptor
            )
            for candidate in parse_srcset(value)
        ]
    )


def prepare_document(
    html_content: str, source_url: str
) -> tuple[str, DocumentMetadata]:
    """Canonicalize remote references and extract a fixed metadata schema.

    Local-file references deliberately remain unchanged so local image copying
    and relative links retain their source-document semantics.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    remote = _is_remote(source_url)
    document_base = resolve_document_base(soup, source_url) if remote else source_url

    if remote:
        for tag_name, attribute in (
            ("a", "href"),
            ("area", "href"),
            ("img", "src"),
            ("source", "src"),
            ("audio", "src"),
            ("video", "src"),
            ("video", "poster"),
        ):
            for tag in soup.find_all(tag_name):
                if isinstance(tag, Tag):
                    value = _attribute(tag, attribute)
                    if value:
                        tag[attribute] = _canonicalize(value, document_base)
        for tag in soup.find_all(["img", "source"], srcset=True):
            if isinstance(tag, Tag):
                srcset = _attribute(tag, "srcset")
                if srcset:
                    tag["srcset"] = _canonicalize_srcset(srcset, document_base)

    canonical = None
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    if isinstance(canonical_tag, Tag):
        canonical = _attribute(canonical_tag, "href")
        if canonical and remote:
            canonical = _canonicalize(canonical, document_base)
    if canonical is None and remote:
        canonical = source_url

    title = _meta_content(soup, "og:title", "twitter:title")
    if title is None and soup.title:
        title = " ".join(soup.title.get_text(" ", strip=True).split()) or None

    html_tag = soup.find("html")
    language = _attribute(html_tag, "lang") if isinstance(html_tag, Tag) else None
    metadata = DocumentMetadata(
        title=title,
        author=_meta_content(soup, "author", "article:author"),
        date=_meta_content(
            soup,
            "date",
            "datepublished",
            "article:published_time",
            "dc.date",
        ),
        canonical_url=canonical,
        description=_meta_content(
            soup, "description", "og:description", "twitter:description"
        ),
        language=language,
    )
    return str(soup), metadata
