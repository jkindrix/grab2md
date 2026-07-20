"""Structural discovery and materialization of selected document assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from html2md.network.image_downloader import ImageDownloader
from html2md.utils.html_references import (
    SrcsetCandidate,
    parse_srcset,
    serialize_srcset,
)

STYLE_URL = re.compile(
    r"(?P<prefix>background-image\s*:\s*url\(\s*['\"]?)"
    r"(?P<url>[^'\"()]+)(?P<suffix>['\"]?\s*\))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssetResult:
    """Selected HTML after successful references were made local."""

    html: str
    url_mapping: dict[str, str]


class AssetPipeline:
    """Discover image references in HTML, acquire them, then rewrite the DOM."""

    def __init__(self, downloader: ImageDownloader) -> None:
        self.downloader = downloader

    def materialize(self, html: str, base_url: str, output_dir: Path) -> AssetResult:
        soup = BeautifulSoup(html, "html.parser")
        urls = self._discover(soup, base_url)
        mapping = self.downloader.download_images(urls, output_dir)
        if mapping:
            self._rewrite(soup, base_url, mapping)
        return AssetResult(str(soup), mapping)

    @staticmethod
    def _discover(soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        for tag in soup.find_all(["img", "source"]):
            if not isinstance(tag, Tag):
                continue
            for attribute in ("src",):
                value = tag.get(attribute)
                if isinstance(value, str) and value.strip():
                    urls.append(urljoin(base_url, value.strip()))
            srcset = tag.get("srcset")
            if isinstance(srcset, str):
                urls.extend(
                    urljoin(base_url, candidate.url)
                    for candidate in parse_srcset(srcset)
                    if not candidate.url.casefold().startswith("data:")
                )
        for tag in soup.find_all(style=True):
            if not isinstance(tag, Tag):
                continue
            style = tag.get("style")
            if isinstance(style, str):
                urls.extend(
                    urljoin(base_url, match.group("url").strip())
                    for match in STYLE_URL.finditer(style)
                )
        return list(dict.fromkeys(urls))

    @staticmethod
    def _rewrite(soup: BeautifulSoup, base_url: str, mapping: dict[str, str]) -> None:
        for tag in soup.find_all(["img", "source"]):
            if not isinstance(tag, Tag):
                continue
            src = tag.get("src")
            if isinstance(src, str):
                replacement = mapping.get(urljoin(base_url, src.strip()))
                if replacement:
                    tag["src"] = replacement
            srcset = tag.get("srcset")
            if isinstance(srcset, str):
                tag["srcset"] = serialize_srcset(
                    [
                        SrcsetCandidate(
                            mapping.get(
                                urljoin(base_url, candidate.url), candidate.url
                            ),
                            candidate.descriptor,
                        )
                        for candidate in parse_srcset(srcset)
                    ]
                )
        for tag in soup.find_all(style=True):
            if not isinstance(tag, Tag):
                continue
            style = tag.get("style")
            if not isinstance(style, str):
                continue

            def replace(match: re.Match[str]) -> str:
                absolute = urljoin(base_url, match.group("url").strip())
                replacement = mapping.get(absolute)
                if replacement is None:
                    return match.group(0)
                return f"{match.group('prefix')}{replacement}{match.group('suffix')}"

            tag["style"] = STYLE_URL.sub(replace, style)
