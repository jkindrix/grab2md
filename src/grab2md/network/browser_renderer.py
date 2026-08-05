"""Isolated optional browser rendering for JavaScript-dependent pages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, cast
from urllib.parse import urlsplit

from grab2md.network.safe_http import (
    SAFE_CROSS_ORIGIN_HEADERS,
    DestinationPolicy,
    UnsafeNetworkTarget,
)
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


class RenderingUnavailable(RuntimeError):
    """Raised when the optional browser runtime is not installed."""


class RenderError(RuntimeError):
    """Raised when a browser render violates policy or cannot complete."""


@dataclass(frozen=True)
class SelectorMatch:
    """One explicit browser selector and its match count."""

    selector: str
    count: int


@dataclass(frozen=True)
class RenderDiagnostics:
    """Safe, bounded facts about one completed browser render."""

    request_count: int = 0
    transfer_bytes: int = 0
    blocked_origins: tuple[str, ...] = ()
    blocked_websockets: int = 0
    selector_matches: tuple[SelectorMatch, ...] = ()


@dataclass(frozen=True)
class RenderedPage:
    """Rendered HTML, final URL, and browser diagnostics."""

    html: str
    final_url: str
    diagnostics: RenderDiagnostics = field(default_factory=RenderDiagnostics)


@dataclass
class BrowserRequestPolicy:
    """Validate, pin, and authorize each explicit browser origin."""

    source_url: str
    allow_private_network: bool = False
    additional_origins: Iterable[str] = field(default_factory=tuple)
    allowed_origins: set[tuple[str, str, Optional[int]]] = field(default_factory=set)
    pinned_hosts: dict[str, str] = field(default_factory=dict)
    pinned_address: str = field(init=False)

    def __post_init__(self) -> None:
        policy = DestinationPolicy(allow_private=self.allow_private_network)
        source_origin = self._authorize(self.source_url, policy)
        self.pinned_address = self.pinned_hosts[source_origin[1]]
        for url in self.additional_origins:
            self._authorize(url, policy)

    def _authorize(
        self, url: str, policy: DestinationPolicy
    ) -> tuple[str, str, Optional[int]]:
        origin = self._origin(url)
        if origin is None:
            raise RenderError(f"Invalid browser render origin: {url}")
        try:
            addresses = policy.addresses_for(url)
        except UnsafeNetworkTarget as error:
            raise RenderError(str(error)) from error
        address = addresses[0]
        existing = self.pinned_hosts.get(origin[1])
        if existing is not None and existing != address:
            raise RenderError(f"Conflicting validated addresses for {origin[1]}")
        self.pinned_hosts[origin[1]] = address
        self.allowed_origins.add(origin)
        return origin

    @staticmethod
    def _origin(url: str) -> Optional[tuple[str, str, Optional[int]]]:
        try:
            scheme, hostname, port = DestinationPolicy._origin(url)
        except UnsafeNetworkTarget:
            return None
        return scheme, hostname, port

    def permits(self, url: str, *, navigation: bool) -> bool:
        """Return whether a browser request is inside the render boundary."""
        scheme = urlsplit(url).scheme.casefold()
        if scheme == "about":
            return not navigation and url.casefold() == "about:blank"
        if scheme == "data":
            return not navigation
        if scheme == "blob":
            return not navigation and self._origin(url[5:]) in self.allowed_origins
        origin = self._origin(url)
        if origin is None:
            return False
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            return False
        if navigation:
            return origin == self._origin(self.source_url)
        return origin in self.allowed_origins

    def headers_for(
        self,
        url: str,
        browser_headers: Mapping[str, str],
        supplied_headers: Mapping[str, str],
    ) -> dict[str, str]:
        """Apply caller headers only where their credential context is valid."""
        headers = dict(browser_headers)
        origin = self._origin(url)
        source_origin = self._origin(self.source_url)
        if origin == source_origin:
            headers.update(supplied_headers)
            return headers
        sensitive = {"authorization", "cookie", "proxy-authorization"}
        headers = {
            name: value
            for name, value in headers.items()
            if name.casefold() not in sensitive
        }
        headers.update(
            {
                name: value
                for name, value in supplied_headers.items()
                if name.casefold() in SAFE_CROSS_ORIGIN_HEADERS
            }
        )
        return headers

    def host_resolver_rules(self) -> str:
        """Map the source hostname to its validated IP and fail all other DNS."""
        origin = self._origin(self.source_url)
        if origin is None:  # guarded by __post_init__
            raise RenderError("Browser rendering requires an HTTP(S) URL")
        rules = []
        for hostname, address in sorted(self.pinned_hosts.items()):
            rendered_hostname = f"[{hostname}]" if ":" in hostname else hostname
            rendered_address = f"[{address}]" if ":" in address else address
            rules.append(f"MAP {rendered_hostname} {rendered_address}")
        return ", ".join([*rules, "MAP * ~NOTFOUND"])


def render_html(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    verify_ssl: bool = True,
    timeout_ms: int = 30_000,
    settle_ms: int = 500,
    max_html_bytes: int = 10 * 1024 * 1024,
    executable_path: Optional[str] = None,
    allow_private_network: bool = False,
    storage_state: Optional[Mapping[str, Any]] = None,
    allowed_origins: Iterable[str] = (),
    click_selectors: Iterable[str] = (),
    wait_until: str = "domcontentloaded",
    wait_for_selector: Optional[str] = None,
    max_clicks: int = 25,
    max_requests: int = 250,
    max_transfer_bytes: int = 50 * 1024 * 1024,
    blocked_resource_types: Iterable[str] = ("font", "image", "media"),
) -> RenderedPage:
    """Render one URL in a fresh non-persistent Chromium context."""
    allowed_origins = tuple(allowed_origins)
    click_selectors = tuple(click_selectors)
    readiness_modes = {"commit", "domcontentloaded", "load", "networkidle"}
    if (
        timeout_ms <= 0
        or not 0 <= settle_ms <= 5_000
        or max_html_bytes <= 0
        or max_clicks <= 0
        or max_requests <= 0
        or max_transfer_bytes <= 0
        or wait_until not in readiness_modes
        or wait_for_selector == ""
        or any(not selector.strip() for selector in click_selectors)
    ):
        raise ValueError("Invalid browser rendering resource limit")
    transfer_limit_exceeded = False
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RenderingUnavailable(
            "JavaScript rendering requires 'grab2md[render]' and a Chromium "
            "runtime installed with 'python -m playwright install chromium'."
        ) from error

    policy = BrowserRequestPolicy(
        url,
        allow_private_network=allow_private_network,
        additional_origins=allowed_origins,
    )
    supplied_headers = dict(headers or {})
    user_agent = supplied_headers.get("User-Agent")
    browser_managed_headers = {
        "accept-encoding",
        "connection",
        "content-length",
        "cookie",
        "host",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "user-agent",
    }
    safe_headers = {
        key: value
        for key, value in supplied_headers.items()
        if key.casefold() not in browser_managed_headers
    }

    try:
        with sync_playwright() as playwright:
            executable_path = executable_path or os.getenv(
                "GRAB2MD_CHROMIUM_EXECUTABLE"
            )
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=executable_path,
                args=[
                    f"--host-resolver-rules={policy.host_resolver_rules()}",
                    "--no-proxy-server",
                ],
            )
            try:
                context = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=not verify_ssl,
                    service_workers="block",
                    user_agent=user_agent,
                    storage_state=cast(
                        Any, dict(storage_state) if storage_state else None
                    ),
                )
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                request_count = 0
                request_limit_exceeded = False
                interaction_phase = False
                blocked_interaction_navigation = False
                blocked_method: Optional[str] = None
                blocked_origins: set[str] = set()
                blocked_websockets = 0
                blocked_types = set(blocked_resource_types)

                def origin_label(request_url: str) -> str:
                    origin = policy._origin(request_url)
                    if origin is None:
                        scheme = urlsplit(request_url).scheme.casefold()
                        return f"{scheme or 'invalid'}:"
                    scheme, hostname, port = origin
                    default_port = 443 if scheme == "https" else 80
                    suffix = f":{port}" if port not in {None, default_port} else ""
                    return f"{scheme}://{hostname}{suffix}"

                def handle_route(route) -> None:
                    nonlocal blocked_method
                    nonlocal blocked_interaction_navigation
                    nonlocal request_count, request_limit_exceeded
                    request = route.request
                    request_count += 1
                    if request_count > max_requests:
                        request_limit_exceeded = True
                        route.abort()
                        return
                    request_method = request.method.upper()
                    if request_method not in {"GET", "HEAD", "OPTIONS"}:
                        blocked_method = request_method
                        route.abort()
                        return
                    if interaction_phase and request.is_navigation_request():
                        blocked_interaction_navigation = True
                        route.abort()
                        return
                    if request.resource_type in blocked_types:
                        route.abort()
                        return
                    if policy.permits(
                        request.url, navigation=request.is_navigation_request()
                    ):
                        route.continue_(
                            headers=policy.headers_for(
                                request.url, request.headers, safe_headers
                            )
                        )
                    else:
                        blocked_origins.add(origin_label(request.url))
                        route.abort()

                def handle_websocket(websocket_route) -> None:
                    nonlocal blocked_websockets
                    # Routed WebSockets do not connect to a server unless the
                    # handler explicitly calls connect_to_server(). Leaving
                    # this route unconnected blocks the network handshake.
                    blocked_websockets += 1

                context.route("**/*", handle_route)
                context.route_web_socket("**/*", handle_websocket)
                page = context.new_page()
                transfer_bytes = 0
                cdp_session = context.new_cdp_session(page)
                cdp_session.send("Network.enable")

                def count_transfer(params: Mapping[str, Any]) -> None:
                    nonlocal transfer_bytes, transfer_limit_exceeded
                    chunk_bytes = max(
                        int(params.get("dataLength", 0)),
                        int(params.get("encodedDataLength", 0)),
                    )
                    transfer_bytes += chunk_bytes
                    if (
                        transfer_bytes > max_transfer_bytes
                        and not transfer_limit_exceeded
                    ):
                        transfer_limit_exceeded = True
                        try:
                            cdp_session.send("Page.stopLoading")
                        except PlaywrightError:
                            pass

                cdp_session.on("Network.dataReceived", count_transfer)
                response = page.goto(url, wait_until=cast(Any, wait_until))
                if blocked_method is not None:
                    raise RenderError(
                        "Browser rendering attempted a blocked "
                        f"{blocked_method} request"
                    )
                if transfer_limit_exceeded:
                    raise RenderError(
                        "Browser rendering exceeded the "
                        f"{max_transfer_bytes}-byte transfer limit"
                    )
                if response is not None and response.status >= 400:
                    raise RenderError(f"Rendered page returned HTTP {response.status}")
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, state="attached")
                    except PlaywrightTimeoutError as error:
                        raise RenderError(
                            "Browser wait selector did not appear: "
                            f"{wait_for_selector}"
                        ) from error
                if click_selectors and settle_ms:
                    page.wait_for_timeout(settle_ms)
                total_clicks = 0
                selector_matches: list[SelectorMatch] = []
                for click_selector in click_selectors:
                    locator = page.locator(click_selector)
                    matched = locator.count()
                    selector_matches.append(SelectorMatch(click_selector, matched))
                    if matched == 0:
                        raise RenderError(
                            "Browser click selector matched no elements: "
                            f"{click_selector}"
                        )
                    total_clicks += matched
                    if total_clicks > max_clicks:
                        raise RenderError(
                            f"Browser interactions exceeded the {max_clicks}-click limit"
                        )
                    interaction_phase = True
                    for index in range(matched):
                        locator.nth(index).click()
                        if blocked_interaction_navigation:
                            raise RenderError(
                                "Browser interaction attempted a blocked navigation"
                            )
                        if blocked_method is not None:
                            raise RenderError(
                                "Browser rendering attempted a blocked "
                                f"{blocked_method} request"
                            )
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
                if blocked_interaction_navigation:
                    raise RenderError(
                        "Browser interaction attempted a blocked navigation"
                    )
                if blocked_method is not None:
                    raise RenderError(
                        "Browser rendering attempted a blocked "
                        f"{blocked_method} request"
                    )
                if transfer_limit_exceeded:
                    raise RenderError(
                        "Browser rendering exceeded the "
                        f"{max_transfer_bytes}-byte transfer limit"
                    )
                if request_limit_exceeded:
                    raise RenderError(
                        f"Browser rendering exceeded the {max_requests}-request limit"
                    )
                html = page.content()
                if transfer_limit_exceeded:
                    raise RenderError(
                        "Browser rendering exceeded the "
                        f"{max_transfer_bytes}-byte transfer limit"
                    )
                if len(html.encode("utf-8")) > max_html_bytes:
                    raise RenderError("Rendered HTML exceeds the 10 MiB limit")
                diagnostics = RenderDiagnostics(
                    request_count=request_count,
                    transfer_bytes=transfer_bytes,
                    blocked_origins=tuple(sorted(blocked_origins)),
                    blocked_websockets=blocked_websockets,
                    selector_matches=tuple(selector_matches),
                )
                logger.info(
                    "Browser render completed: requests=%d transfer_bytes=%d "
                    "blocked_origins=%s blocked_websockets=%d selector_matches=%s",
                    diagnostics.request_count,
                    diagnostics.transfer_bytes,
                    diagnostics.blocked_origins,
                    diagnostics.blocked_websockets,
                    tuple(
                        (match.selector, match.count)
                        for match in diagnostics.selector_matches
                    ),
                )
                return RenderedPage(
                    html=html,
                    final_url=page.url,
                    diagnostics=diagnostics,
                )
            finally:
                browser.close()
    except PlaywrightTimeoutError as error:
        if transfer_limit_exceeded:
            raise RenderError(
                "Browser rendering exceeded the "
                f"{max_transfer_bytes}-byte transfer limit"
            ) from error
        raise RenderError(
            f"Browser rendering timed out after {timeout_ms} ms"
        ) from error
    except PlaywrightError as error:
        if transfer_limit_exceeded:
            raise RenderError(
                "Browser rendering exceeded the "
                f"{max_transfer_bytes}-byte transfer limit"
            ) from error
        raise RenderError(f"Browser rendering failed: {error}") from error
