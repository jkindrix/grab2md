"""Contract tests for shared page acquisition and conversion boundaries."""

import codecs
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
import requests

from html2md.markdown.pipeline import (
    AcquisitionFailure,
    AcquiredPage,
    PageConverter,
    acquire_http_page,
    acquire_local_page,
    acquire_rendered_page,
)
from html2md.network.browser_renderer import RenderedPage


class Utf8WithoutCharsetHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = "<h1>café — 東京</h1>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _response(
    *,
    body="<h1>Page</h1>",
    url="https://example.com/final",
    content_type="text/html; charset=iso-8859-1",
    status=200,
):
    response = requests.Response()
    response._content = body.encode("iso-8859-1")
    response.url = url
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    response.encoding = "iso-8859-1"
    return response


def test_static_acquisition_preserves_requested_and_final_representation_metadata():
    session = requests.Session()
    with patch(
        "html2md.markdown.pipeline.guarded_request", return_value=_response()
    ) as request:
        page = acquire_http_page(
            "https://example.com/start",
            session=session,
            headers={"User-Agent": "fixture"},
        )

    assert page.requested_url == "https://example.com/start"
    assert page.final_url == "https://example.com/final"
    assert page.status_code == 200
    assert page.media_type == "text/html"
    assert page.charset == "iso8859-1"
    assert request.call_args.kwargs["headers"] == {"User-Agent": "fixture"}


def test_static_acquisition_rejects_non_html_and_preserves_status_failures():
    session = requests.Session()
    with patch(
        "html2md.markdown.pipeline.guarded_request",
        return_value=_response(content_type="application/pdf"),
    ):
        with pytest.raises(AcquisitionFailure, match="Expected HTML"):
            acquire_http_page("https://example.com/file", session=session)

    response = _response(status=404)
    with patch("html2md.markdown.pipeline.guarded_request", return_value=response):
        with pytest.raises(AcquisitionFailure) as raised:
            acquire_http_page("https://example.com/missing", session=session)
    assert raised.value.status_code == 404


@pytest.mark.parametrize(
    ("body", "content_type", "expected_text", "expected_charset"),
    [
        ("café — 東京".encode(), "text/html", "café — 東京", "utf-8"),
        (
            b'<meta charset="windows-1252"><p>caf\xe9</p>',
            "text/html",
            "café",
            "cp1252",
        ),
        (
            codecs.BOM_UTF8 + "BOM café".encode(),
            "text/html",
            "BOM café",
            "utf-8-sig",
        ),
        (
            '<meta charset="utf-8"><p>olá</p>'.encode("iso-8859-1"),
            "text/html; charset=iso-8859-1",
            "olá",
            "iso8859-1",
        ),
    ],
)
def test_static_acquisition_uses_deterministic_html_charset_precedence(
    body, content_type, expected_text, expected_charset
):
    response = requests.Response()
    response._content = body
    response.url = "https://example.com/encoding"
    response.status_code = 200
    response.headers = {"Content-Type": content_type}

    with patch("html2md.markdown.pipeline.guarded_request", return_value=response):
        page = acquire_http_page(
            "https://example.com/encoding", session=requests.Session()
        )

    assert expected_text in page.html
    assert page.charset == expected_charset


def test_loopback_utf8_html_without_charset_does_not_use_requests_latin1_default():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Utf8WithoutCharsetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/page"
    try:
        page = acquire_http_page(
            url,
            session=requests.Session(),
            allow_private_network=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "café — 東京" in page.html
    assert page.charset == "utf-8"


@pytest.mark.parametrize(
    ("body", "content_type", "message"),
    [
        (b"<p>text</p>", "text/html; charset=not-a-codec", "unknown charset"),
        (b'<meta charset="not-a-codec"><p>text</p>', "text/html", "unknown charset"),
        (b"\xff", "text/html; charset=utf-8", "not valid utf-8"),
    ],
)
def test_static_acquisition_rejects_invalid_or_incorrect_charset(
    body, content_type, message
):
    response = requests.Response()
    response._content = body
    response.url = "https://example.com/encoding"
    response.status_code = 200
    response.headers = {"Content-Type": content_type}

    with patch("html2md.markdown.pipeline.guarded_request", return_value=response):
        with pytest.raises(AcquisitionFailure, match=message):
            acquire_http_page(
                "https://example.com/encoding", session=requests.Session()
            )


def test_local_and_rendered_acquisition_share_the_page_contract(tmp_path):
    source = tmp_path / "page.html"
    source.write_text("<h1>Local</h1>", encoding="utf-8")

    local = acquire_local_page(source)
    with patch(
        "html2md.markdown.pipeline.render_html",
        return_value=RenderedPage("<h1>Rendered</h1>", "https://example.com/final"),
    ):
        rendered = acquire_rendered_page("https://example.com/start")

    assert local.source_path == source.resolve()
    assert local.final_url == source.resolve().as_uri()
    assert local.charset == "utf-8"
    assert rendered.rendered is True
    assert rendered.final_url == "https://example.com/final"


def test_page_converter_is_pure_and_returns_selected_html_and_metadata():
    page = AcquiredPage(
        requested_url="https://example.com/start",
        final_url="https://example.com/final",
        html="<html><head><title>Guide</title></head><body><h1>Page</h1></body></html>",
        status_code=200,
        headers={"Content-Type": "text/html"},
        media_type="text/html",
        charset="utf-8",
    )

    converter = PageConverter()
    prepared = converter.prepare(page)
    document = converter.render(prepared, include_metadata=True)

    assert document.page is page
    assert "# Page" in document.markdown
    assert 'title: "Guide"' in document.markdown
    assert "<h1>Page</h1>" in document.selected_html
    assert document.metadata.canonical_url == "https://example.com/final"
