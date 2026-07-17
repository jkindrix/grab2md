"""Cookie scope model and replay policy for HTTP sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import DefaultCookiePolicy
from typing import Any, Iterable, Mapping, Optional, cast
from urllib.parse import urlparse

import requests


def normalize_hostname(value: str) -> str:
    hostname = value.strip().lstrip(".").rstrip(".")
    if not hostname:
        return ""
    try:
        return hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return ""


def target_hostname(url: str) -> str:
    return normalize_hostname(urlparse(url).hostname or "")


def cookie_domain_matches(hostname: str, domain: str, *, host_only: bool) -> bool:
    normalized_host = normalize_hostname(hostname)
    normalized_domain = normalize_hostname(domain)
    if not normalized_host or not normalized_domain:
        return False
    if host_only:
        return normalized_host == normalized_domain
    return normalized_host == normalized_domain or normalized_host.endswith(
        "." + normalized_domain
    )


@dataclass(frozen=True)
class CookieRecord:
    """One cookie with the complete scope needed for safe replay."""

    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[int] = None
    secure: bool = False
    http_only: bool = False
    same_site: Optional[str] = None
    host_only: bool = False

    def applies_to(self, hostname: str) -> bool:
        return cookie_domain_matches(hostname, self.domain, host_only=self.host_only)


class _ScopedCookiePolicy(DefaultCookiePolicy):
    def return_ok(self, cookie, request):
        if cookie.get_nonstandard_attr("HostOnly"):
            if target_hostname(request.get_full_url()) != normalize_hostname(
                cookie.domain
            ):
                return False
        return super().return_ok(cookie, request)


def _path_matches(request_path: str, cookie_path: str) -> bool:
    normalized_cookie_path = cookie_path if cookie_path.startswith("/") else "/"
    if request_path == normalized_cookie_path:
        return True
    if not request_path.startswith(normalized_cookie_path):
        return False
    return normalized_cookie_path.endswith("/") or request_path[
        len(normalized_cookie_path) :
    ].startswith("/")


class ScopedCookieSession(requests.Session):
    """A requests session enforcing host-only, path, secure, and expiry scope."""

    def prepare_request(self, request):
        prepared = super().prepare_request(request)
        prepared.headers.pop("Cookie", None)
        hostname = target_hostname(prepared.url or "")
        parsed = urlparse(prepared.url or "")
        request_path = parsed.path or "/"
        now = int(datetime.now(timezone.utc).timestamp())
        applicable = []
        for cookie in prepared._cookies:
            host_only = bool(cookie.get_nonstandard_attr("HostOnly")) or not bool(
                cookie.domain_specified
            )
            if not cookie_domain_matches(hostname, cookie.domain, host_only=host_only):
                continue
            if cookie.secure and parsed.scheme.casefold() != "https":
                continue
            if cookie.expires is not None and cookie.expires <= now:
                continue
            if not _path_matches(request_path, cookie.path):
                continue
            applicable.append(cookie)
        applicable.sort(key=lambda item: len(item.path or "/"), reverse=True)
        if applicable:
            prepared.headers["Cookie"] = "; ".join(
                f"{cookie.name}={cookie.value}" for cookie in applicable
            )
        return prepared


def as_scoped_session(session: requests.Session) -> ScopedCookieSession:
    if isinstance(session, ScopedCookieSession):
        return session
    scoped = ScopedCookieSession()
    scoped.headers.clear()
    scoped.headers.update(session.headers)
    scoped.cookies.update(session.cookies)
    scoped.auth = session.auth
    scoped.verify = session.verify
    scoped.cert = session.cert
    scoped.params = dict(cast(Mapping[str, Any], session.params))
    scoped.trust_env = session.trust_env
    return scoped


def _coerce_records(
    cookies: Iterable[CookieRecord] | dict[str, str], hostname: str
) -> list[CookieRecord]:
    if isinstance(cookies, dict):
        return [
            CookieRecord(name, value, hostname, host_only=True)
            for name, value in cookies.items()
        ]
    return list(cookies)


def _set_record(session: requests.Session, cookie: CookieRecord) -> None:
    rest: dict[str, Any] = {"HostOnly": cookie.host_only}
    if cookie.http_only:
        rest["HttpOnly"] = True
    if cookie.same_site:
        rest["SameSite"] = cookie.same_site
    normalized_domain = normalize_hostname(cookie.domain)
    stored_domain = normalized_domain if cookie.host_only else "." + normalized_domain
    session.cookies.set(
        cookie.name,
        cookie.value,
        domain=stored_domain,
        path=cookie.path or "/",
        expires=cookie.expires,
        secure=cookie.secure,
        rest=rest,
    )


def apply_cookie_records(
    session: requests.Session,
    url: str,
    cookies: Iterable[CookieRecord] | dict[str, str],
) -> ScopedCookieSession:
    """Replace target-domain cookies and apply only records valid for that host."""
    scoped = as_scoped_session(session)
    hostname = target_hostname(url)
    if not hostname:
        raise ValueError("Cannot apply cookies to a URL without a valid hostname")
    scoped.cookies.set_policy(_ScopedCookiePolicy())
    for existing in list(cast(Any, scoped.cookies)):
        host_only = bool(existing.get_nonstandard_attr("HostOnly"))
        if cookie_domain_matches(hostname, existing.domain, host_only=host_only):
            scoped.cookies.clear(existing.domain, existing.path, existing.name)
    for cookie in _coerce_records(cookies, hostname):
        if cookie.applies_to(hostname):
            _set_record(scoped, cookie)
    return scoped
