"""Explicit cookie-source adapters and capability selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from html2md.config.loader import load_config
from html2md.cookies.errors import CookieSourceError
from html2md.cookies.replay import CookieRecord


@dataclass(frozen=True)
class CookieSourceCapability:
    name: str
    available: bool
    detail: str


class CookieSource(Protocol):
    @property
    def name(self) -> str: ...

    def capability(self) -> CookieSourceCapability: ...

    def load(self, url: str) -> list[CookieRecord] | dict[str, str]: ...


@dataclass(frozen=True)
class ExportedCookieSource:
    path: Path
    name: str = "exported JSON"

    def capability(self) -> CookieSourceCapability:
        available = self.path.is_file()
        return CookieSourceCapability(
            self.name,
            available,
            str(self.path) if available else f"file not found: {self.path}",
        )

    def load(self, url: str) -> list[CookieRecord]:
        from html2md.cookies.export import load_cookies_from_json

        return load_cookies_from_json(self.path, url)


@dataclass(frozen=True)
class ChromeCookieSource:
    name: str = "chrome"

    def capability(self) -> CookieSourceCapability:
        from html2md.cookies.session_manager import HAS_CRYPTO, get_browser_cookie_path

        path = get_browser_cookie_path(self.name)
        available = bool(HAS_CRYPTO and path and path.is_file())
        detail = str(path) if path else "cookie database path is unavailable"
        if not HAS_CRYPTO:
            detail = "cookie decryption dependency is unavailable"
        return CookieSourceCapability(self.name, available, detail)

    def load(self, url: str) -> list[CookieRecord]:
        from html2md.cookies.session_manager import get_chrome_cookies
        from html2md.cookies.replay import target_hostname

        return get_chrome_cookies(target_hostname(url))


@dataclass(frozen=True)
class FirefoxCookieSource:
    name: str = "firefox"

    def capability(self) -> CookieSourceCapability:
        from html2md.cookies.session_manager import get_browser_cookie_path

        path = get_browser_cookie_path(self.name)
        available = bool(path and path.exists())
        return CookieSourceCapability(
            self.name,
            available,
            str(path) if path else "profile path is unavailable",
        )

    def load(self, url: str) -> list[CookieRecord]:
        from html2md.cookies.session_manager import get_firefox_cookies
        from html2md.cookies.replay import target_hostname

        return get_firefox_cookies(target_hostname(url))


def browser_cookie_source(browser: str | None = None) -> CookieSource:
    """Resolve one supported adapter using configuration at call time."""
    configured = load_config().get("browser", {}).get("preferred", "chrome")
    selected = browser or configured
    if selected == "chrome":
        return ChromeCookieSource()
    if selected == "firefox":
        return FirefoxCookieSource()
    raise CookieSourceError(
        "Cookie extraction is supported only for chrome and firefox, "
        f"not {selected!r}"
    )
