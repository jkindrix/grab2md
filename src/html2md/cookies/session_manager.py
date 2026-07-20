import base64
import configparser
import json
import os
import sqlite3
import sys
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

# Optional dependencies for browser cookie extraction
try:
    from Cryptodome.Cipher import AES

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from html2md.config.loader import load_config
from html2md.cookies.errors import CookieSourceError
from html2md.cookies.export import load_cookies_from_json
from html2md.cookies.http_session import (
    disable_ssl_verification,
    get_session,
    reset_session,
)
from html2md.cookies.replay import (
    CookieRecord,
    apply_cookie_records,
    cookie_domain_matches as _cookie_domain_matches,
    normalize_hostname as _normalize_hostname,
    target_hostname as _target_hostname,
)
from html2md.cookies.sources import CookieSource
from html2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger("session_manager")

__all__ = [
    "CookieRecord",
    "CookieSourceError",
    "apply_browser_cookies",
    "disable_ssl_verification",
    "get_browser_cookie_path",
    "get_chrome_cookies",
    "get_domain_cookies",
    "get_firefox_cookies",
    "get_session",
    "load_cookies_from_json",
    "reset_session",
]


# -------------------------------
# Browser Cookie Management
# -------------------------------


def _default_browser_cookie_path(
    platform: str, home: Path, browser: str
) -> Path | None:
    """Return the documented browser path without probing or configuration."""
    if platform == "win32":
        roots = {
            "chrome": home
            / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
            "firefox": home / "AppData/Roaming/Mozilla/Firefox/Profiles",
            "edge": home
            / "AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
        }
        return roots.get(browser)
    if platform == "darwin":
        roots = {
            "chrome": home
            / "Library/Application Support/Google/Chrome/Default/Cookies",
            "firefox": home / "Library/Application Support/Firefox/Profiles",
            "safari": home / "Library/Cookies/Cookies.binarycookies",
        }
        return roots.get(browser)
    if platform.startswith("linux"):
        roots = {
            "chrome": home / ".config/google-chrome/Default/Cookies",
            "firefox": home / ".mozilla/firefox",
            "edge": home / ".config/microsoft-edge/Default/Cookies",
        }
        return roots.get(browser)
    return None


def _normalized_cookie_path(raw_path: str | Path) -> Path:
    """Normalize an explicit/configured browser path, including WSL syntax."""
    custom_path_str = str(raw_path)
    if (
        sys.platform.startswith("linux")
        and not custom_path_str.startswith("/")
        and len(custom_path_str) >= 3
        and custom_path_str[1:3] in {":\\", ":/"}
    ):
        drive = custom_path_str[0].lower()
        path_without_drive = custom_path_str[3:]
        path_with_slashes = path_without_drive.replace("\\", "/")
        return Path(f"/mnt/{drive}/{path_with_slashes}")
    return Path(custom_path_str).expanduser()


def get_browser_cookie_path(
    browser: str | None = None, custom_path: str | Path | None = None
) -> Path | None:
    """Return the configured or conventional browser cookie path."""

    # Define browser and profile configurations
    config = load_config()
    browser_config = config.get("browser", {})
    preferred_browser = browser or browser_config.get("preferred", "chrome")

    if custom_path is not None:
        normalized = _normalized_cookie_path(custom_path)
        logger.info(
            "Using one-shot cookie path for %s: %s",
            preferred_browser,
            normalized,
        )
        return normalized

    # Check for custom path override in config
    custom_paths = browser_config.get("custom_path", {})
    if preferred_browser in custom_paths and custom_paths[preferred_browser]:
        # Handle Windows path in WSL
        custom_path_str = custom_paths[preferred_browser]
        custom_path = _normalized_cookie_path(custom_path_str)

        if custom_path.exists():
            logger.info(
                f"Using custom cookie path for {preferred_browser}: {custom_path}"
            )
            return custom_path
        else:
            logger.warning(
                f"Custom cookie path for {preferred_browser} not found: {custom_path}"
            )

    default_path = _default_browser_cookie_path(
        sys.platform, Path.home(), preferred_browser
    )
    if default_path is not None:
        return default_path

    logger.warning(
        f"Unsupported browser '{preferred_browser}' or platform '{sys.platform}'"
    )
    return None


def get_chrome_encryption_key() -> bytes:
    """Return a supported Chrome key or fail before cookie decryption."""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install html2md-cli with its declared dependencies."
        )

    if sys.platform == "win32":  # Windows
        import win32crypt

        try:
            local_state_path = (
                Path.home()
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Local State"
            )
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.loads(f.read())

            encoded_key = local_state["os_crypt"]["encrypted_key"]
            encrypted_key = base64.b64decode(encoded_key, validate=True)
            if not encrypted_key.startswith(b"DPAPI"):
                raise CookieSourceError(
                    "Chrome Local State uses an unsupported Windows key format"
                )

            # Decrypt the key using Windows DPAPI
            decrypted_key = win32crypt.CryptUnprotectData(
                encrypted_key[5:], None, None, None, 0
            )[1]
            return decrypted_key
        except CookieSourceError:
            raise
        except Exception as error:
            raise CookieSourceError(
                "Could not retrieve Chrome's Windows DPAPI encryption key; "
                "use an owner-private exported cookie JSON file"
            ) from error

    elif sys.platform == "darwin":  # macOS
        raise CookieSourceError(
            "Automatic Chrome cookie decryption is unavailable on macOS because "
            "html2md does not access the Chrome Safe Storage Keychain secret. "
            "Export cookies to an owner-private JSON file instead."
        )

    elif sys.platform.startswith("linux"):
        raise CookieSourceError(
            "Automatic Chrome cookie decryption is unavailable on Linux because "
            "html2md does not access the desktop keyring. Export cookies to an "
            "owner-private JSON file instead."
        )

    raise CookieSourceError(
        f"Automatic Chrome cookie decryption is unsupported on {sys.platform}; "
        "use an owner-private exported cookie JSON file"
    )


def decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a recognized Chrome cookie representation."""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install html2md-cli with its declared dependencies."
        )

    try:
        if encrypted_value.startswith(b"v20"):
            raise CookieSourceError(
                "Chrome app-bound (v20) cookie encryption is unsupported; use an "
                "owner-private exported cookie JSON file"
            )

        # Supported Local-State-key Chrome representations use AES-GCM.
        if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
            # Extract required values
            nonce = encrypted_value[3 : 3 + 12]
            ciphertext = encrypted_value[3 + 12 : -16]
            tag = encrypted_value[-16:]

            # Create cipher
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

            # Decrypt
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted.decode()

        if sys.platform == "win32":
            import win32crypt

            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[
                1
            ].decode()

        raise CookieSourceError(
            f"Unsupported Chrome cookie encryption format on {sys.platform}"
        )
    except CookieSourceError:
        raise
    except Exception as error:
        raise CookieSourceError("Chrome cookie decryption failed") from error


def _copy_cookie_database(
    source_path: str | Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Copy a locked browser database into unpredictable owner-only storage."""
    temp_directory = tempfile.TemporaryDirectory(prefix="html2md-cookies-")
    if os.name == "posix":
        os.chmod(temp_directory.name, 0o700)
    destination = Path(temp_directory.name) / "cookies.sqlite"
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with open(source_path, "rb") as source, os.fdopen(fd, "wb") as target:
            shutil.copyfileobj(source, target)
        if os.name == "posix":
            os.chmod(destination, 0o600)
        return temp_directory, destination
    except BaseException:
        temp_directory.cleanup()
        raise


@contextmanager
def _copied_cookie_connection(source_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a disposable cookie-database copy and always release its resources."""
    temp_directory, copied_path = _copy_cookie_database(source_path)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(copied_path))
        yield connection
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            temp_directory.cleanup()


def get_chrome_cookies(
    domain: str, *, cookie_path: str | Path | None = None
) -> list[CookieRecord]:
    """Retrieve Chrome cookies for a specific domain"""
    cookie_records: list[CookieRecord] = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Chrome cookie extraction requires a valid hostname")
    cookie_path = get_browser_cookie_path("chrome", cookie_path)

    if not cookie_path or not cookie_path.exists():
        raise CookieSourceError(f"Chrome cookie database not found at {cookie_path}")

    # Get encryption key (specific to Chrome)
    encryption_key = get_chrome_encryption_key()
    if not encryption_key:
        raise CookieSourceError("Could not retrieve the Chrome cookie encryption key")

    try:
        with _copied_cookie_connection(cookie_path) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT name, value, encrypted_value, host_key, expires_utc, path,
                       is_secure, is_httponly
                  FROM cookies
                 WHERE host_key = ?
                    OR (
                        substr(host_key, 1, 1) = '.'
                        AND (
                            ltrim(host_key, '.') = ?
                            OR ? LIKE '%.' || ltrim(host_key, '.')
                        )
                    )
                """,
                (target_hostname, target_hostname, target_hostname),
            )

            # Current time for expiration check
            now = int(datetime.now(timezone.utc).timestamp())

            for (
                name,
                value,
                encrypted_value,
                host_key,
                expires_utc,
                path,
                is_secure,
                is_httponly,
            ) in cursor.fetchall():
                try:
                    host_only = not str(host_key).startswith(".")
                    if not _cookie_domain_matches(
                        target_hostname, host_key, host_only=host_only
                    ):
                        continue

                    # Chromium stores microseconds since 1601-01-01 UTC.
                    expires = (
                        int(expires_utc / 1_000_000 - 11_644_473_600)
                        if expires_utc
                        else None
                    )

                    # Skip expired cookies
                    if expires is not None and expires <= now:
                        continue

                    if not value and encrypted_value:
                        value = decrypt_chrome_cookie(encrypted_value, encryption_key)
                    else:
                        value = str(value)

                    if value:
                        cookie_records.append(
                            CookieRecord(
                                name=str(name),
                                value=value,
                                domain=str(host_key),
                                path=str(path or "/"),
                                expires=expires,
                                secure=bool(is_secure),
                                http_only=bool(is_httponly),
                                host_only=host_only,
                            )
                        )
                except CookieSourceError:
                    raise
                except Exception as error:
                    logger.debug(f"Error processing cookie {name}: {error}")

    except Exception as error:
        logger.error(f"Error reading Chrome cookies: {error}")
        if isinstance(error, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not read Chrome cookies: {error}") from error

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def _resolve_firefox_profile_path(
    firefox_root: Path,
    section: configparser.SectionProxy,
    option: str,
) -> Path | None:
    raw_path = (section.get(option, fallback="") or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if section.name.casefold().startswith("profile"):
        relative = section.getboolean("IsRelative", fallback=True)
    else:
        relative = not candidate.is_absolute()
    return firefox_root / candidate if relative else candidate


def _find_firefox_profile(firefox_root: Path) -> Path | None:
    """Resolve Firefox's install-selected or explicitly default profile."""
    parsed: list[tuple[configparser.ConfigParser, bool]] = []
    for ini_path in (firefox_root / "profiles.ini", firefox_root / "installs.ini"):
        if not ini_path.exists():
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with ini_path.open("r", encoding="utf-8") as ini_file:
                parser.read_file(ini_file)
        except (OSError, configparser.Error, UnicodeError) as error:
            raise CookieSourceError(
                f"Could not parse Firefox profile configuration {ini_path}: {error}"
            ) from error
        parsed.append((parser, ini_path.name == "installs.ini"))

    install_defaults: list[Path] = []
    profile_defaults: list[Path] = []
    profile_fallbacks: list[Path] = []
    for parser, install_file in parsed:
        for section_name in parser.sections():
            section = parser[section_name]
            if install_file or section_name.casefold().startswith("install"):
                candidate = _resolve_firefox_profile_path(
                    firefox_root, section, "Default"
                )
                if candidate is not None:
                    install_defaults.append(candidate)
            elif section_name.casefold().startswith("profile"):
                candidate = _resolve_firefox_profile_path(firefox_root, section, "Path")
                if candidate is None:
                    continue
                profile_fallbacks.append(candidate)
                if section.getboolean("Default", fallback=False):
                    profile_defaults.append(candidate)

    for candidate in install_defaults + profile_defaults + profile_fallbacks:
        if candidate.is_dir():
            return candidate
    return None


def get_firefox_cookies(
    domain: str, *, cookie_path: str | Path | None = None
) -> list[CookieRecord]:
    """Retrieve Firefox cookies for a specific domain"""
    cookie_records: list[CookieRecord] = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Firefox cookie extraction requires a valid hostname")
    cookie_path = get_browser_cookie_path("firefox", cookie_path)

    if not cookie_path or not cookie_path.exists():
        raise CookieSourceError(f"Firefox profile directory not found at {cookie_path}")

    # Find the selected profile, or accept an explicit cookies.sqlite path.
    profile_dir = cookie_path.parent if cookie_path.is_file() else None
    cookies_db = cookie_path if cookie_path.is_file() else None

    # Firefox uses a profiles.ini file to identify the default profile. Linux
    # returns the Firefox root; Windows/macOS return its Profiles directory.
    if cookie_path.is_dir():
        firefox_root = (
            cookie_path.parent if cookie_path.name == "Profiles" else cookie_path
        )
        profile_dir = _find_firefox_profile(firefox_root)

    # If still no profile found, check if there's only one subdirectory
    if not profile_dir and cookie_path.is_dir():
        profiles = [
            p
            for p in cookie_path.iterdir()
            if p.is_dir() and p.name.endswith(".default")
        ]
        if len(profiles) == 1:
            profile_dir = profiles[0]
        else:
            # Try any .default profile directory
            for p in cookie_path.iterdir():
                if p.is_dir() and ".default" in p.name:
                    profile_dir = p
                    break

    if not profile_dir or not profile_dir.exists():
        raise CookieSourceError("Could not find a valid Firefox profile")

    # Locate cookies.sqlite in the profile
    cookies_db = cookies_db or profile_dir / "cookies.sqlite"
    if not cookies_db.exists():
        raise CookieSourceError(f"Firefox cookies database not found at {cookies_db}")

    try:
        with _copied_cookie_connection(cookies_db) as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT name, value, host, expiry, path, isSecure, isHttpOnly
                  FROM moz_cookies
                 WHERE host = ?
                    OR (
                        substr(host, 1, 1) = '.'
                        AND (
                            ltrim(host, '.') = ?
                            OR ? LIKE '%.' || ltrim(host, '.')
                        )
                    )
                """,
                (target_hostname, target_hostname, target_hostname),
            )

            # Current time for expiration check
            now = int(datetime.now().timestamp())

            for (
                name,
                value,
                host,
                expiry,
                path,
                is_secure,
                is_httponly,
            ) in cursor.fetchall():
                host_only = not str(host).startswith(".")
                if not _cookie_domain_matches(
                    target_hostname, host, host_only=host_only
                ):
                    continue
                # Skip expired cookies
                if expiry < now and expiry != 0:
                    continue

                cookie_records.append(
                    CookieRecord(
                        name=str(name),
                        value=str(value),
                        domain=str(host),
                        path=str(path or "/"),
                        expires=int(expiry) if expiry else None,
                        secure=bool(is_secure),
                        http_only=bool(is_httponly),
                        host_only=host_only,
                    )
                )

    except sqlite3.OperationalError as error:
        logger.error(f"Error querying Firefox cookies: {error}")
        raise CookieSourceError(f"Could not query Firefox cookies: {error}") from error
    except Exception as error:
        logger.error(f"Error reading Firefox cookies: {error}")
        if isinstance(error, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not read Firefox cookies: {error}") from error

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def get_domain_cookies(
    url: str,
    browser: str | None = None,
    cookie_path: Path | None = None,
) -> list[CookieRecord]:
    """Load records through the selected browser-source adapter."""
    if not _target_hostname(url):
        logger.warning("Cannot extract cookies for a URL without a valid hostname")
        return []
    from html2md.cookies.sources import browser_cookie_source

    return cast(
        list[CookieRecord], browser_cookie_source(browser, cookie_path).load(url)
    )


def apply_browser_cookies(
    session, url, cookie_json=None, browser=None, cookie_path=None
):
    """Load one explicit cookie source and replay applicable records safely."""
    url_domain = _target_hostname(url)
    if not url_domain:
        raise ValueError("Cannot apply cookies to a URL without a valid hostname")
    logger.debug(f"Setting cookies for domain: {url_domain}")

    source: CookieSource
    if cookie_json:
        from html2md.cookies.sources import ExportedCookieSource

        source = ExportedCookieSource(Path(cookie_json))
    else:
        from html2md.cookies.sources import browser_cookie_source

        source = browser_cookie_source(browser, cookie_path)
    cookies = source.load(url)

    if not cookies:
        raise CookieSourceError(
            f"No applicable cookies were found for {url_domain} in {source.name}"
        )

    session = apply_cookie_records(session, url, cookies)

    logger.debug("Applied %s cookies to session", len(session.cookies.get_dict()))
    logger.info(f"Applied cookies to session for {url}")

    return session
