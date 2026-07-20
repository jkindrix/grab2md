"""Explicit cookie-source adapters and capability selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Protocol

from grab2md.config.loader import load_config
from grab2md.cookies.errors import CookieSourceError
from grab2md.cookies.replay import CookieRecord


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
        from grab2md.cookies.export import load_cookies_from_json

        return load_cookies_from_json(self.path, url)


@dataclass(frozen=True)
class ChromeCookieSource:
    path: Path | None = None
    name: str = "chrome"

    def capability(self) -> CookieSourceCapability:
        from grab2md.cookies.browser_paths import get_browser_cookie_path
        from grab2md.cookies.chrome import (
            HAS_CRYPTO,
            get_chrome_encryption_key,
        )

        path = get_browser_cookie_path(self.name, self.path)
        supported_platform = sys.platform == "win32"
        platform_name = {
            "darwin": "macOS",
            "win32": "Windows",
        }.get(
            sys.platform, "Linux" if sys.platform.startswith("linux") else sys.platform
        )
        available = bool(HAS_CRYPTO and supported_platform and path and path.is_file())
        detail = str(path) if path else "cookie database path is unavailable"
        if not HAS_CRYPTO:
            detail = "cookie decryption dependency is unavailable"
        elif not supported_platform:
            detail = (
                f"automatic Chrome cookie decryption is unavailable on {platform_name}; "
                "use an owner-private exported cookie JSON file"
            )
        elif not path or not path.is_file():
            detail = f"Chrome cookie database not found at {path}"
        else:
            try:
                get_chrome_encryption_key()
            except (CookieSourceError, ImportError) as error:
                available = False
                detail = str(error)
        return CookieSourceCapability(self.name, available, detail)

    def load(self, url: str) -> list[CookieRecord]:
        from grab2md.cookies.chrome import get_chrome_cookies
        from grab2md.cookies.replay import target_hostname

        capability = self.capability()
        if not capability.available:
            raise CookieSourceError(
                f"Chrome cookie source is unavailable on {sys.platform}: "
                f"{capability.detail}"
            )
        return get_chrome_cookies(target_hostname(url), cookie_path=self.path)


@dataclass(frozen=True)
class FirefoxCookieSource:
    path: Path | None = None
    name: str = "firefox"

    def capability(self) -> CookieSourceCapability:
        from grab2md.cookies.browser_paths import get_browser_cookie_path

        path = get_browser_cookie_path(self.name, self.path)
        available = bool(path and path.exists())
        return CookieSourceCapability(
            self.name,
            available,
            str(path) if path else "profile path is unavailable",
        )

    def load(self, url: str) -> list[CookieRecord]:
        from grab2md.cookies.firefox import get_firefox_cookies
        from grab2md.cookies.replay import target_hostname

        return get_firefox_cookies(target_hostname(url), cookie_path=self.path)


def browser_cookie_source(
    browser: str | None = None, cookie_path: Path | None = None
) -> CookieSource:
    """Resolve one supported adapter using configuration at call time."""
    configured = load_config().get("browser", {}).get("preferred", "chrome")
    selected = browser or configured
    if selected == "chrome":
        return ChromeCookieSource(cookie_path)
    if selected == "firefox":
        return FirefoxCookieSource(cookie_path)
    raise CookieSourceError(
        "Cookie extraction is supported only for chrome and firefox, "
        f"not {selected!r}"
    )
