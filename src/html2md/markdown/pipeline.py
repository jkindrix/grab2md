"""Typed acquisition and conversion contracts shared by every source path."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import requests
from markdownify import markdownify

from html2md.markdown.assets import AssetPipeline
from html2md.markdown.content_extractor import (
    ContentExtractionError,
    ContentMode,
    extract_content_html,
)
from html2md.markdown.document import DocumentMetadata, prepare_document
from html2md.network.browser_renderer import render_html
from html2md.network.image_downloader import ImageDownloader
from html2md.network.safe_http import (
    DEFAULT_MAX_BODY_BYTES,
    DestinationPolicy,
    guarded_request,
)
from html2md.utils.formatter import format_markdown

logger = logging.getLogger("html2md")

HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})


class AcquisitionFailure(RuntimeError):
    """A source could not produce a valid HTML page."""

    def __init__(
        self,
        source: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(message)


class ConversionFailure(RuntimeError):
    """An acquired page could not produce a Markdown document."""


@dataclass(frozen=True)
class AcquiredPage:
    """HTML plus the identity and representation metadata used to acquire it."""

    requested_url: str
    final_url: str
    html: str
    status_code: int | None
    headers: Mapping[str, str]
    media_type: str
    charset: str
    source_path: Path | None = None
    rendered: bool = False

    @property
    def is_remote(self) -> bool:
        return self.source_path is None


@dataclass(frozen=True)
class ConvertedDocument:
    """A converted page and the selected HTML that produced its Markdown."""

    page: AcquiredPage
    markdown: str
    selected_html: str
    metadata: DocumentMetadata


@dataclass(frozen=True)
class PreparedDocument:
    """Selected, canonicalized HTML ready for optional asset processing."""

    page: AcquiredPage
    selected_html: str
    metadata: DocumentMetadata


def _content_type(headers: Mapping[str, str]) -> tuple[str, str | None]:
    raw_value = next(
        (value for name, value in headers.items() if name.casefold() == "content-type"),
        "",
    )
    parts = [part.strip() for part in raw_value.split(";")]
    media_type = parts[0].casefold()
    charset = None
    for part in parts[1:]:
        name, separator, value = part.partition("=")
        if separator and name.strip().casefold() == "charset":
            charset = value.strip().strip('"') or None
    return media_type, charset


def acquire_http_page(
    url: str,
    *,
    session: requests.Session,
    headers: Mapping[str, str] | None = None,
    network_policy: DestinationPolicy | None = None,
    allow_private_network: bool = False,
    max_html_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> AcquiredPage:
    """Acquire one static HTTP(S) HTML page through the guarded transport."""
    try:
        response = guarded_request(
            session,
            "GET",
            url,
            policy=network_policy
            or DestinationPolicy(allow_private=allow_private_network),
            headers=headers,
            timeout=30,
            max_body_bytes=max_html_bytes,
        )
        response.raise_for_status()
    except requests.exceptions.SSLError as error:
        raise AcquisitionFailure(
            url,
            f"SSL certificate verification failed for {url}: {error}. "
            "If you trust this host, retry with --insecure.",
        ) from error
    except requests.exceptions.ConnectionError as error:
        raise AcquisitionFailure(
            url, f"Connection error while retrieving {url}: {error}"
        ) from error
    except requests.RequestException as error:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        raise AcquisitionFailure(
            url,
            f"Unable to retrieve content from {url}: {error}",
            status_code=status_code,
        ) from error

    response_headers = dict(response.headers)
    media_type, declared_charset = _content_type(response_headers)
    if media_type and media_type not in HTML_MEDIA_TYPES:
        raise AcquisitionFailure(
            url,
            f"Expected HTML from {url}, received {media_type}",
            status_code=response.status_code,
        )
    if response.encoding is None:
        response.encoding = declared_charset or "utf-8"
    html = response.text
    if not html.strip():
        raise AcquisitionFailure(
            url,
            f"Empty HTML response from {url}",
            status_code=response.status_code,
        )
    response_url = getattr(response, "url", None)
    final_url = response_url if isinstance(response_url, str) and response_url else url
    return AcquiredPage(
        requested_url=url,
        final_url=final_url,
        html=html,
        status_code=response.status_code,
        headers=response_headers,
        media_type=media_type or "text/html",
        charset=response.encoding or declared_charset or "utf-8",
    )


def acquire_rendered_page(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    verify_ssl: bool = True,
    allow_private_network: bool = False,
    max_html_bytes: int = DEFAULT_MAX_BODY_BYTES,
    storage_state: Mapping[str, object] | None = None,
) -> AcquiredPage:
    """Acquire an HTML snapshot through the optional isolated browser."""
    try:
        rendered = render_html(
            url,
            headers=headers,
            verify_ssl=verify_ssl,
            allow_private_network=allow_private_network,
            max_html_bytes=max_html_bytes,
            storage_state=storage_state,
        )
    except Exception as error:
        raise AcquisitionFailure(
            url, f"Unable to render content from {url}: {error}"
        ) from error
    if not rendered.html.strip():
        raise AcquisitionFailure(url, f"Rendered page from {url} was empty")
    return AcquiredPage(
        requested_url=url,
        final_url=rendered.final_url,
        html=rendered.html,
        status_code=None,
        headers={},
        media_type="text/html",
        charset="utf-8",
        rendered=True,
    )


def acquire_local_page(file_path: str | Path) -> AcquiredPage:
    """Read one UTF-8 local HTML document with explicit failure semantics."""
    path = Path(file_path).expanduser().resolve()
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise AcquisitionFailure(
            str(path), f"Unable to read local HTML file {path}: {error}"
        ) from error
    if not html.strip():
        raise AcquisitionFailure(str(path), f"Local HTML file is empty: {path}")
    uri = path.as_uri()
    return AcquiredPage(
        requested_url=uri,
        final_url=uri,
        html=html,
        status_code=None,
        headers={},
        media_type="text/html",
        charset="utf-8",
        source_path=path,
    )


class PageConverter:
    """Pure HTML-to-Markdown conversion with no acquisition or file writes."""

    def prepare(
        self,
        page: AcquiredPage,
        *,
        content_mode: ContentMode = ContentMode.FULL,
        selector: str | None = None,
    ) -> PreparedDocument:
        """Canonicalize and select HTML without serializing or writing assets."""
        try:
            prepared_html, metadata = prepare_document(page.html, page.final_url)
            selected_html = extract_content_html(
                prepared_html, mode=content_mode, selector=selector
            )
            return PreparedDocument(page, selected_html, metadata)
        except ContentExtractionError as error:
            raise ConversionFailure(str(error)) from error
        except Exception as error:
            raise ConversionFailure(
                f"Unable to prepare HTML from {page.final_url}: {error}"
            ) from error

    def render(
        self, prepared: PreparedDocument, *, include_metadata: bool = False
    ) -> ConvertedDocument:
        """Serialize prepared HTML to Markdown without external side effects."""
        try:
            markdown = format_markdown(
                markdownify(prepared.selected_html, heading_style="ATX")
            )
        except Exception as error:
            raise ConversionFailure(
                f"Unable to convert HTML from {prepared.page.final_url}: {error}"
            ) from error
        if not markdown.strip():
            raise ConversionFailure(
                f"Conversion produced no Markdown for {prepared.page.final_url}"
            )
        if include_metadata:
            markdown = prepared.metadata.front_matter() + markdown
        return ConvertedDocument(
            prepared.page, markdown, prepared.selected_html, prepared.metadata
        )

    def convert(
        self,
        page: AcquiredPage,
        *,
        content_mode: ContentMode = ContentMode.FULL,
        selector: str | None = None,
        include_metadata: bool = False,
    ) -> ConvertedDocument:
        prepared = self.prepare(page, content_mode=content_mode, selector=selector)
        return self.render(prepared, include_metadata=include_metadata)


class PagePipeline:
    """Compose pure conversion with the current optional asset materializer."""

    def __init__(self, converter: PageConverter | None = None) -> None:
        self.converter = converter or PageConverter()

    def convert(
        self,
        page: AcquiredPage,
        *,
        content_mode: ContentMode = ContentMode.FULL,
        selector: str | None = None,
        include_metadata: bool = False,
        download_images: bool = False,
        output_dir: Path | None = None,
        images_dir: str = "images",
        session: requests.Session | None = None,
        allow_private_network: bool = False,
        request_scheduler=None,
    ) -> ConvertedDocument:
        prepared = self.converter.prepare(
            page,
            content_mode=content_mode,
            selector=selector,
        )
        if not download_images or output_dir is None:
            return self.converter.render(prepared, include_metadata=include_metadata)
        downloader = ImageDownloader(
            session=session,
            images_dir=images_dir,
            local_root=page.source_path.parent if page.source_path else None,
            allow_private_network=allow_private_network,
            scheduler=request_scheduler,
        )
        assets = AssetPipeline(downloader).materialize(
            prepared.selected_html,
            page.final_url,
            Path(output_dir),
        )
        prepared = PreparedDocument(page, assets.html, prepared.metadata)
        return self.converter.render(prepared, include_metadata=include_metadata)
