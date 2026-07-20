"""Security and integration-boundary tests for optional browser rendering."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from grab2md.markdown.converter import html_to_markdown
from grab2md.network.browser_renderer import (
    BrowserRequestPolicy,
    RenderError,
    RenderedPage,
    RenderingUnavailable,
    render_html,
)


def test_request_policy_allows_explicit_origin_and_generated_urls():
    policy = BrowserRequestPolicy(
        "http://127.0.0.1:8080/page", allow_private_network=True
    )

    assert policy.permits("http://127.0.0.1:8080/app.js", navigation=False)
    assert policy.permits("data:text/javascript,void(0)", navigation=False)
    assert policy.permits("blob:http://127.0.0.1:8080/id", navigation=False)
    assert not policy.permits("data:text/html,redirect", navigation=True)


def test_request_policy_blocks_cross_origin_subresources_and_credentials():
    policy = BrowserRequestPolicy("https://example.com/page")

    assert not policy.permits("https://cdn.example.net/app.js", navigation=False)
    assert not policy.permits(
        "https://user:secret@example.com/private", navigation=False
    )
    assert not policy.permits("file:///etc/passwd", navigation=False)


def test_cross_origin_navigation_is_blocked_without_a_second_resolution():
    with patch(
        "socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]
    ) as dns:
        policy = BrowserRequestPolicy("https://example.com/page")
        assert not policy.permits("https://example.net/final", navigation=True)
    dns.assert_called_once()


def test_explicit_cross_origin_is_validated_pinned_and_authorized():
    records = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=records) as dns:
        policy = BrowserRequestPolicy(
            "https://example.com/page",
            additional_origins=["https://cdn.example.net/"],
        )

    assert policy.permits("https://cdn.example.net/app.js", navigation=False)
    assert policy.host_resolver_rules() == (
        "MAP cdn.example.net 93.184.216.34, "
        "MAP example.com 93.184.216.34, MAP * ~NOTFOUND"
    )
    assert dns.call_count == 2


def test_cross_origin_headers_drop_credentials_and_custom_context():
    records = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=records):
        policy = BrowserRequestPolicy(
            "https://example.com/page",
            additional_origins=["https://cdn.example.net/"],
        )

    headers = policy.headers_for(
        "https://cdn.example.net/app.js",
        {"authorization": "browser secret", "cookie": "session=secret"},
        {
            "Authorization": "Bearer secret",
            "X-Tenant": "private",
            "Accept-Language": "en-US",
        },
    )

    assert "authorization" not in headers
    assert "cookie" not in headers
    assert "Authorization" not in headers
    assert "X-Tenant" not in headers
    assert headers["Accept-Language"] == "en-US"


def test_browser_source_is_pinned_and_all_other_dns_fails_closed():
    with patch(
        "socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]
    ):
        policy = BrowserRequestPolicy("https://example.com/page")

    assert policy.host_resolver_rules() == (
        "MAP example.com 93.184.216.34, MAP * ~NOTFOUND"
    )


def test_browser_rejects_private_source_without_explicit_authorization():
    private_dns = [(2, 1, 6, "", ("169.254.169.254", 443))]
    with patch("socket.getaddrinfo", return_value=private_dns):
        with pytest.raises(RenderError, match="non-public"):
            BrowserRequestPolicy("https://metadata.test/latest")


def test_rendered_conversion_uses_browser_html_and_final_url():
    rendered = RenderedPage(
        '<html><body><h1>Rendered</h1><a href="next">Next</a></body></html>',
        "https://example.com/final/page",
    )
    session = Mock()

    with patch(
        "grab2md.markdown.pipeline.render_html", return_value=rendered
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
        allow_private_network=False,
        max_html_bytes=10 * 1024 * 1024,
        storage_state=None,
    )
    session.get.assert_not_called()


@pytest.mark.parametrize(
    "limits",
    [
        {"timeout_ms": 0},
        {"settle_ms": -1},
        {"settle_ms": 5_001},
        {"max_html_bytes": 0},
        {"max_requests": 0},
        {"wait_until": "eventually"},
        {"wait_for_selector": ""},
    ],
)
def test_invalid_resource_limits_fail_before_browser_start(limits):
    with pytest.raises(ValueError, match="resource limit"):
        render_html("https://example.com", **limits)


class FakePlaywrightError(Exception):
    pass


class FakePlaywrightTimeout(FakePlaywrightError):
    pass


class FakeRoute:
    def __init__(self, url, resource_type="document", navigation=True):
        self.request = SimpleNamespace(
            url=url,
            resource_type=resource_type,
            headers={"Accept": "text/html"},
            is_navigation_request=lambda: navigation,
        )
        self.aborted = False
        self.continued_headers = None

    def abort(self):
        self.aborted = True

    def continue_(self, *, headers):
        self.continued_headers = headers


class FakePage:
    def __init__(self, context, *, status=200, html="<h1>Rendered</h1>"):
        self.context = context
        self.status = status
        self.html = html
        self.url = "https://example.com/final"
        self.waited_for = None

    def goto(self, url, **_kwargs):
        for route in self.context.routes:
            self.context.route_handler(route)
        return SimpleNamespace(status=self.status) if self.status is not None else None

    def wait_for_selector(self, selector, **_kwargs):
        self.waited_for = selector

    def wait_for_timeout(self, _milliseconds):
        return None

    def content(self):
        return self.html


class FakeBrowserContext:
    def __init__(self, routes, **options):
        self.routes = routes
        self.options = options
        self.route_handler = None
        self.page = FakePage(self)
        self.timeouts = []

    def set_default_timeout(self, value):
        self.timeouts.append(value)

    def set_default_navigation_timeout(self, value):
        self.timeouts.append(value)

    def route(self, _pattern, handler):
        self.route_handler = handler

    def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, routes):
        self.context = None
        self.routes = routes
        self.closed = False

    def new_context(self, **options):
        self.context = FakeBrowserContext(self.routes, **options)
        return self.context

    def close(self):
        self.closed = True


def fake_playwright_module(browser):
    chromium = SimpleNamespace(launch=Mock(return_value=browser))
    playwright = SimpleNamespace(chromium=chromium)

    class Manager:
        def __enter__(self):
            return playwright

        def __exit__(self, *_args):
            return None

    return (
        SimpleNamespace(
            Error=FakePlaywrightError,
            TimeoutError=FakePlaywrightTimeout,
            sync_playwright=lambda: Manager(),
        ),
        chromium,
    )


def test_missing_render_extra_fails_with_install_guidance():
    with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
        with pytest.raises(RenderingUnavailable, match=r"grab2md\[render\]"):
            render_html("https://example.com")


def test_browser_runtime_applies_policy_limits_and_closes_cleanly():
    route = FakeRoute("https://example.com/page")
    blocked = FakeRoute(
        "https://example.com/image.png", resource_type="image", navigation=False
    )
    browser = FakeBrowser([route, blocked])
    module, chromium = fake_playwright_module(browser)
    records = [(2, 1, 6, "", ("93.184.216.34", 443))]
    with (
        patch.dict(sys.modules, {"playwright.sync_api": module}),
        patch("socket.getaddrinfo", return_value=records),
    ):
        rendered = render_html(
            "https://example.com/page",
            headers={"User-Agent": "fixture", "X-Context": "safe"},
            settle_ms=0,
            wait_for_selector="main",
            storage_state={"cookies": []},
        )

    assert rendered == RenderedPage("<h1>Rendered</h1>", "https://example.com/final")
    assert route.continued_headers["X-Context"] == "safe"
    assert blocked.aborted is True
    assert browser.context.page.waited_for == "main"
    assert browser.context.timeouts == [30_000, 30_000]
    assert browser.context.options["storage_state"] == {"cookies": []}
    assert browser.closed is True
    assert "--no-proxy-server" in chromium.launch.call_args.kwargs["args"]


def test_browser_runtime_rejects_http_errors_and_request_budget(tmp_path):
    del tmp_path
    records = [(2, 1, 6, "", ("93.184.216.34", 443))]
    for routes, status, max_requests, message in (
        ([FakeRoute("https://example.com")], 503, 10, "HTTP 503"),
        (
            [
                FakeRoute("https://example.com"),
                FakeRoute("https://example.com/app.js", navigation=False),
            ],
            200,
            1,
            "1-request limit",
        ),
    ):
        browser = FakeBrowser(routes)
        module, _chromium = fake_playwright_module(browser)
        with (
            patch.dict(sys.modules, {"playwright.sync_api": module}),
            patch("socket.getaddrinfo", return_value=records),
        ):
            browser_context = browser
            original_new_context = browser_context.new_context

            def new_context(**options):
                context = original_new_context(**options)
                context.page.status = status
                return context

            browser_context.new_context = new_context
            with pytest.raises(RenderError, match=message):
                render_html(
                    "https://example.com", settle_ms=0, max_requests=max_requests
                )
        assert browser.closed is True
