"""Validated file inputs for target-site authentication state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from grab2md.utils.private_json import load_private_json

FORBIDDEN_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def load_private_headers(path: Path) -> dict[str, str]:
    """Return caller-supplied request headers from an owner-only JSON object."""
    payload = load_private_json(path)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Header input must be a non-empty JSON object")
    headers: dict[str, str] = {}
    for raw_name, raw_value in payload.items():
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            raise ValueError("Header names and values must be strings")
        name = raw_name.strip()
        if (
            not name
            or any(character in name for character in "\r\n:")
            or "\r" in raw_value
            or "\n" in raw_value
        ):
            raise ValueError("Header input contains an invalid name or value")
        if name.casefold() in FORBIDDEN_REQUEST_HEADERS:
            raise ValueError(f"Header input cannot override transport header: {name}")
        headers[name] = raw_value
    return headers


def load_storage_state(path: Path) -> dict[str, Any]:
    """Load private Playwright state once so the browser cannot reopen a replacement."""
    payload = load_private_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Browser storage state must be a JSON object")
    cookies = payload.get("cookies", [])
    origins = payload.get("origins", [])
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise ValueError("Browser storage state requires cookie and origin arrays")
    return payload
