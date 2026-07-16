"""Behavior tests for exported and browser-derived cookie loading."""

import json
from unittest.mock import patch

import requests

from html2md.cookies.session_manager import (
    apply_browser_cookies,
    get_domain_cookies,
    load_cookies_from_json,
)


def test_exported_cookie_list_filters_exact_hosts_and_real_subdomains(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps(
            [
                {"name": "parent", "value": "a", "domain": ".example.com"},
                {"name": "exact", "value": "b", "domain": "docs.example.com"},
                {"name": "other", "value": "c", "domain": "notexample.com"},
            ]
        ),
        encoding="utf-8",
    )

    cookies = load_cookies_from_json(cookie_file, "https://docs.example.com/page")

    assert cookies == {"parent": "a", "exact": "b"}


def test_exported_cookie_dict_loads_all_pairs(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(json.dumps({"session": "token", "theme": "dark"}))

    assert load_cookies_from_json(cookie_file) == {
        "session": "token",
        "theme": "dark",
    }


def test_malformed_cookie_export_returns_empty_mapping(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text("not-json", encoding="utf-8")

    assert load_cookies_from_json(cookie_file, "https://example.com") == {}


def test_apply_cookie_export_preserves_domain_and_path(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps(
            [
                {
                    "name": "session",
                    "value": "secret",
                    "domain": ".example.com",
                    "path": "/docs",
                }
            ]
        ),
        encoding="utf-8",
    )
    session = requests.Session()

    returned = apply_browser_cookies(
        session, "https://docs.example.com/docs/page", cookie_file
    )

    assert returned is session
    cookie = next(iter(session.cookies))
    assert (cookie.name, cookie.value, cookie.domain, cookie.path) == (
        "session",
        "secret",
        ".example.com",
        "/docs",
    )


def test_browser_cookie_mapping_is_applied_to_target_host():
    session = requests.Session()
    with patch(
        "html2md.cookies.session_manager.get_domain_cookies",
        return_value={"session": "value"},
    ):
        apply_browser_cookies(session, "https://example.com/page")

    cookie = next(iter(session.cookies))
    assert (cookie.name, cookie.value, cookie.domain) == (
        "session",
        "value",
        "example.com",
    )


def test_browser_cookie_mapping_honors_explicit_browser():
    session = requests.Session()
    with patch(
        "html2md.cookies.session_manager.get_domain_cookies",
        return_value={"session": "value"},
    ) as extract:
        apply_browser_cookies(
            session, "https://example.com/page", browser="firefox"
        )

    extract.assert_called_once_with(
        "https://example.com/page", browser="firefox"
    )


def test_domain_cookie_loader_routes_to_configured_browser():
    with (
        patch.dict(
            "html2md.cookies.session_manager.config",
            {"browser": {"preferred": "firefox"}},
            clear=True,
        ),
        patch(
            "html2md.cookies.session_manager.get_firefox_cookies",
            return_value={"firefox": "cookie"},
        ) as firefox,
    ):
        result = get_domain_cookies("https://www.example.com/path")

    assert result == {"firefox": "cookie"}
    firefox.assert_called_once_with("example.com")
