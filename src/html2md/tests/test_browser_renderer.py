"""Security and integration-boundary tests for optional browser rendering."""

from unittest.mock import Mock, patch

import pytest

from html2md.markdown.converter import html_to_markdown
from html2md.network.browser_renderer import (
    BrowserRequestPolicy,
    RenderError,
    RenderedPage,
)


def test_request_policy_allows_explicit_origin_and_generated_urls():
    policy = BrowserRequestPolicy("http://127.0.0.1:8080/page")

    assert policy.permits("http://127.0.0.1:8080/app.js", navigation=False)
    assert policy.permits("data:text/javascript,void(0)", navigation=False)
    assert policy.permits("blob:http://127.0.0.1:8080/id", navigation=False)


def test_request_policy_blocks_cross_origin_subresources_and_credentials():
    policy = BrowserRequestPolicy("https://example.com/page")

    assert not policy.permits("https://cdn.example.net/app.js", navigation=False)
    assert not policy.permits(
        "https://user:secret@example.com/private", navigation=False
    )
    assert not policy.permits("file:///etc/passwd", navigation=False)


def test_cross_origin_navigation_must_resolve_to_public_addresses():
    policy = BrowserRequestPolicy("https://example.com/page")
    private_dns = [(2, 1, 6, "", ("169.254.169.254", 80))]

    with patch(
        "html2md.network.browser_renderer.socket.getaddrinfo",
        return_value=private_dns,
    ):
        with pytest.raises(RenderError, match="non-public"):
            policy.permits("http://metadata.test/latest", navigation=True)


def test_rendered_conversion_uses_browser_html_and_final_url():
    rendered = RenderedPage(
        '<html><body><h1>Rendered</h1><a href="next">Next</a></body></html>',
        "https://example.com/final/page",
    )
    session = Mock()

    with patch(
        "html2md.markdown.converter.render_html", return_value=rendered
    ) as render:
        markdown = html_to_markdown(
            "https://example.com/start",
            session=session,
            headers={"User-Agent": "fixture"},
            render_js=True,
        )

    assert markdown is not None
    assert "# Rendered" in markdown
    assert "[Next](https://example.com/final/next)" in markdown
    render.assert_called_once_with(
        "https://example.com/start",
        headers={"User-Agent": "fixture"},
        verify_ssl=True,
    )
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "limits",
    [
        {"timeout_ms": 0},
        {"settle_ms": -1},
        {"settle_ms": 5_001},
        {"max_html_bytes": 0},
    ],
)
def test_invalid_resource_limits_fail_before_browser_start(limits):
    from html2md.network.browser_renderer import render_html

    with pytest.raises(ValueError, match="resource limit"):
        render_html("https://example.com", **limits)
