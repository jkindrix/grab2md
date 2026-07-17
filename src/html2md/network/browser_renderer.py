"""Isolated optional browser rendering for JavaScript-dependent pages."""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass, field
from typing import Mapping, Optional
from urllib.parse import urlsplit


class RenderingUnavailable(RuntimeError):
    """Raised when the optional browser runtime is not installed."""


class RenderError(RuntimeError):
    """Raised when a browser render violates policy or cannot complete."""


@dataclass(frozen=True)
class RenderedPage:
    """Rendered HTML and the browser's final document URL."""

    html: str
    final_url: str


@dataclass
class BrowserRequestPolicy:
    """Permit explicit-origin traffic and public top-level navigations only."""

    source_url: str
    allowed_origins: set[tuple[str, str, Optional[int]]] = field(default_factory=set)

    def __post_init__(self) -> None:
        origin = self._origin(self.source_url)
        if origin is None:
            raise RenderError("Browser rendering requires an HTTP(S) URL")
        self.allowed_origins.add(origin)

    @staticmethod
    def _origin(url: str) -> Optional[tuple[str, str, Optional[int]]]:
        parsed = urlsplit(url)
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"} or not parsed.hostname:
            return None
        try:
            port = parsed.port
        except ValueError as error:
            raise RenderError("Rendered URL contains an invalid port") from error
        return scheme, parsed.hostname.casefold(), port

    @staticmethod
    def _require_public(hostname: str, port: Optional[int]) -> None:
        try:
            addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise RenderError(
                f"Render navigation host cannot resolve: {hostname}"
            ) from error
        if not addresses:
            raise RenderError(f"Render navigation host has no addresses: {hostname}")
        for address in addresses:
            raw = str(address[4][0]).split("%", 1)[0]
            try:
                parsed = ipaddress.ip_address(raw)
            except ValueError as error:
                raise RenderError(
                    f"Invalid render navigation address: {raw}"
                ) from error
            if not parsed.is_global:
                raise RenderError(
                    f"Cross-origin render navigation targets a non-public address: {raw}"
                )

    def permits(self, url: str, *, navigation: bool) -> bool:
        """Return whether a browser request is inside the render boundary."""
        scheme = urlsplit(url).scheme.casefold()
        if scheme in {"about", "blob", "data"}:
            return True
        origin = self._origin(url)
        if origin is None:
            return False
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            return False
        if origin in self.allowed_origins:
            return True
        if not navigation:
            return False
        self._require_public(origin[1], origin[2])
        self.allowed_origins.add(origin)
        return True


def render_html(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    verify_ssl: bool = True,
    timeout_ms: int = 30_000,
    settle_ms: int = 500,
    max_html_bytes: int = 10 * 1024 * 1024,
    executable_path: Optional[str] = None,
) -> RenderedPage:
    """Render one URL in a fresh non-persistent Chromium context."""
    if timeout_ms <= 0 or not 0 <= settle_ms <= 5_000 or max_html_bytes <= 0:
        raise ValueError("Invalid browser rendering resource limit")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RenderingUnavailable(
            "JavaScript rendering requires 'html2md-cli[render]' and a Chromium "
            "runtime installed with 'python -m playwright install chromium'."
        ) from error

    policy = BrowserRequestPolicy(url)
    supplied_headers = dict(headers or {})
    user_agent = supplied_headers.get("User-Agent")
    safe_headers = {
        key: value
        for key, value in supplied_headers.items()
        if key.casefold() in {"accept-language", "dnt"}
    }

    try:
        with sync_playwright() as playwright:
            executable_path = executable_path or os.getenv(
                "HTML2MD_CHROMIUM_EXECUTABLE"
            )
            browser = playwright.chromium.launch(
                headless=True, executable_path=executable_path
            )
            try:
                context = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=not verify_ssl,
                    service_workers="block",
                    extra_http_headers=safe_headers,
                    user_agent=user_agent,
                )
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                def handle_route(route) -> None:
                    request = route.request
                    if request.resource_type in {"font", "image", "media"}:
                        route.abort()
                        return
                    if policy.permits(
                        request.url, navigation=request.is_navigation_request()
                    ):
                        route.continue_()
                    else:
                        route.abort()

                context.route("**/*", handle_route)
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded")
                if response is not None and response.status >= 400:
                    raise RenderError(f"Rendered page returned HTTP {response.status}")
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
                html = page.content()
                if len(html.encode("utf-8")) > max_html_bytes:
                    raise RenderError("Rendered HTML exceeds the 10 MiB limit")
                return RenderedPage(html=html, final_url=page.url)
            finally:
                browser.close()
    except PlaywrightTimeoutError as error:
        raise RenderError(
            f"Browser rendering timed out after {timeout_ms} ms"
        ) from error
    except PlaywrightError as error:
        raise RenderError(f"Browser rendering failed: {error}") from error
