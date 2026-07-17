import json
import os
import re
import sqlite3
import sys
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# Optional dependencies for browser cookie extraction
try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Protocol.KDF import PBKDF2

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


def get_browser_cookie_path(browser=None):
    """Return the path to browser cookie files based on platform and browser."""

    # Define browser and profile configurations
    config = load_config()
    browser_config = config.get("browser", {})
    preferred_browser = browser or browser_config.get("preferred", "chrome")

    # Check for custom path override in config
    custom_paths = browser_config.get("custom_path", {})
    if preferred_browser in custom_paths and custom_paths[preferred_browser]:
        # Handle Windows path in WSL
        custom_path_str = custom_paths[preferred_browser]

        # Convert Windows path to WSL path if needed
        if (
            sys.platform.startswith("linux")
            and not custom_path_str.startswith("/")
            and ":" in custom_path_str
        ):
            # Looks like Windows path (C:\...) but we're in Linux/WSL
            drive = custom_path_str[0].lower()
            path_without_drive = custom_path_str[3:]
            # Replace backslashes with forward slashes
            path_with_slashes = path_without_drive.replace("\\", "/")
            wsl_path = f"/mnt/{drive}/{path_with_slashes}"
            logger.info(
                f"Converting Windows path {custom_path_str} to WSL path {wsl_path}"
            )
            custom_path = Path(wsl_path)
        else:
            custom_path = Path(custom_path_str)

        if custom_path.exists():
            logger.info(
                f"Using custom cookie path for {preferred_browser}: {custom_path}"
            )
            return custom_path
        else:
            logger.warning(
                f"Custom cookie path for {preferred_browser} not found: {custom_path}"
            )

    home = Path.home()

    # Browser storage paths based on platform
    if sys.platform == "win32":  # Windows
        if preferred_browser == "chrome":
            return (
                home
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Default"
                / "Network"
                / "Cookies"
            )
        elif preferred_browser == "firefox":
            return home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
        elif preferred_browser == "edge":
            return (
                home
                / "AppData"
                / "Local"
                / "Microsoft"
                / "Edge"
                / "User Data"
                / "Default"
                / "Network"
                / "Cookies"
            )

    elif sys.platform == "darwin":  # macOS
        if preferred_browser == "chrome":
            return (
                home
                / "Library"
                / "Application Support"
                / "Google"
                / "Chrome"
                / "Default"
                / "Cookies"
            )
        elif preferred_browser == "firefox":
            return home / "Library" / "Application Support" / "Firefox" / "Profiles"
        elif preferred_browser == "safari":
            return home / "Library" / "Cookies" / "Cookies.binarycookies"

    else:  # Linux/Unix
        if preferred_browser == "chrome":
            return home / ".config" / "google-chrome" / "Default" / "Cookies"
        elif preferred_browser == "firefox":
            return home / ".mozilla" / "firefox"
        elif preferred_browser == "edge":
            return home / ".config" / "microsoft-edge" / "Default" / "Cookies"

    logger.warning(
        f"Unsupported browser '{preferred_browser}' or platform '{sys.platform}'"
    )
    return None


def get_chrome_encryption_key():
    """Get encryption key for Chrome cookies"""
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

            # Decode the encrypted key
            encrypted_key = local_state["os_crypt"]["encrypted_key"]
            encrypted_key = encrypted_key.encode()
            encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix

            # Decrypt the key using Windows DPAPI
            decrypted_key = win32crypt.CryptUnprotectData(
                encrypted_key, None, None, None, 0
            )[1]
            return decrypted_key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key: {e}")
            return None

    elif sys.platform == "darwin":  # macOS
        # macOS uses the keychain for encryption
        # This is a simplified implementation
        try:
            key_material = "Chrome Safe Storage"
            password = key_material.encode()
            # Use OSX keychain to get the actual password
            # This would require additional macOS-specific libraries
            salt = b"saltysalt"
            iterations = 1003
            key = PBKDF2(password, salt, dkLen=16, count=iterations)
            return key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key on macOS: {e}")
            return None

    elif "linux" in sys.platform:  # Linux
        # Linux Chrome may use different encryption based on distribution
        # Here's a basic implementation for Ubuntu/Debian
        try:
            salt = b"saltysalt"
            iterations = 1
            # Many Linux distros store this in the Gnome keyring
            # This is a simplified implementation that works on some systems
            password = "peanuts".encode()  # Default password on some Linux systems
            key = PBKDF2(password, salt, dkLen=16, count=iterations)
            return key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key on Linux: {e}")
            return None

    return None


def decrypt_chrome_cookie(encrypted_value, key):
    """Decrypt Chrome cookie value"""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install html2md-cli with its declared dependencies."
        )

    try:
        # For newer Chrome versions, cookies are encrypted with AES-256-GCM
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

        # Windows may also use DPAPI for older Chrome versions
        elif sys.platform == "win32":
            import win32crypt

            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[
                1
            ].decode()

        # Older versions or other platforms might use simple AES
        else:
            iv = b" " * 16
            cipher = AES.new(key, AES.MODE_CBC, iv)
            # Remove padding
            decrypted = cipher.decrypt(encrypted_value)
            padding_length = decrypted[-1]
            if padding_length:
                decrypted = decrypted[:-padding_length]
            return decrypted.decode()

    except Exception as e:
        logger.error(f"Cookie decryption error: {e}")
        return None


def _copy_cookie_database(source_path):
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


def get_chrome_cookies(domain):
    """Retrieve Chrome cookies for a specific domain"""
    cookie_records = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Chrome cookie extraction requires a valid hostname")
    cookie_path = get_browser_cookie_path("chrome")

    if not cookie_path or not cookie_path.exists():
        raise CookieSourceError(f"Chrome cookie database not found at {cookie_path}")

    # Get encryption key (specific to Chrome)
    encryption_key = get_chrome_encryption_key()
    if not encryption_key:
        raise CookieSourceError("Could not retrieve the Chrome cookie encryption key")

    temp_directory = None
    conn = None
    try:
        temp_directory, temp_db_path = _copy_cookie_database(cookie_path)
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()

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

                # If value is not set but encrypted_value is, decrypt it
                if not value and encrypted_value:
                    # Skip the 'v10' prefix for encrypted values
                    decrypted_value = decrypt_chrome_cookie(
                        encrypted_value, encryption_key
                    )
                    if decrypted_value is None:
                        raise CookieSourceError(
                            f"Could not decrypt Chrome cookie {name!r}"
                        )
                    value = decrypted_value
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
            except Exception as e:
                logger.debug(f"Error processing cookie {name}: {e}")

    except Exception as e:
        logger.error(f"Error reading Chrome cookies: {e}")
        if isinstance(e, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not read Chrome cookies: {e}") from e
    finally:
        try:
            if conn is not None:
                conn.close()
        finally:
            if temp_directory is not None:
                temp_directory.cleanup()

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def get_firefox_cookies(domain):
    """Retrieve Firefox cookies for a specific domain"""
    cookie_records = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Firefox cookie extraction requires a valid hostname")
    cookie_path = get_browser_cookie_path("firefox")

    if not cookie_path or not cookie_path.exists():
        raise CookieSourceError(f"Firefox profile directory not found at {cookie_path}")

    # Find the default profile
    profile_dir = None

    # Firefox uses a profiles.ini file to identify the default profile
    if cookie_path.is_dir():
        profiles_ini = cookie_path.parent / "profiles.ini"
        if profiles_ini.exists():
            try:
                # Parse profiles.ini to find default profile
                with open(profiles_ini, "r") as f:
                    profile_data = f.read()

                # Find the default profile section
                profile_sections = re.findall(
                    r"\[Profile\d+\].*?(?=\[|$)", profile_data, re.DOTALL
                )
                for section in profile_sections:
                    if "Default=1" in section or "IsRelative=1" in section:
                        path_match = re.search(r"Path=(.*)", section)
                        if path_match:
                            profile_name = path_match.group(1)
                            if "IsRelative=1" in section:
                                profile_dir = cookie_path.parent / profile_name
                            else:
                                profile_dir = Path(profile_name)
                            break

                # If no default found, try to find any profile
                if not profile_dir:
                    for section in profile_sections:
                        path_match = re.search(r"Path=(.*)", section)
                        if path_match:
                            profile_name = path_match.group(1)
                            if "IsRelative=1" in section:
                                profile_dir = cookie_path.parent / profile_name
                            else:
                                profile_dir = Path(profile_name)
                            break
            except Exception as e:
                raise CookieSourceError(
                    f"Could not parse Firefox profiles.ini: {e}"
                ) from e

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
    cookies_db = profile_dir / "cookies.sqlite"
    if not cookies_db.exists():
        raise CookieSourceError(f"Firefox cookies database not found at {cookies_db}")

    temp_directory = None
    conn = None
    try:
        temp_directory, temp_path = _copy_cookie_database(cookies_db)
        conn = sqlite3.connect(str(temp_path))
        cursor = conn.cursor()

        # Query cookies
        try:
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
        except sqlite3.OperationalError as e:
            logger.error(f"Error querying Firefox cookies: {e}")
            raise CookieSourceError(f"Could not query Firefox cookies: {e}") from e

    except Exception as e:
        logger.error(f"Error reading Firefox cookies: {e}")
        if isinstance(e, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not read Firefox cookies: {e}") from e
    finally:
        try:
            if conn is not None:
                conn.close()
        finally:
            if temp_directory is not None:
                temp_directory.cleanup()

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def get_domain_cookies(url, browser=None):
    """Load records through the selected browser-source adapter."""
    if not _target_hostname(url):
        logger.warning("Cannot extract cookies for a URL without a valid hostname")
        return []
    from html2md.cookies.sources import browser_cookie_source

    return browser_cookie_source(browser).load(url)


def apply_browser_cookies(session, url, cookie_json=None, browser=None):
    """Load one explicit cookie source and replay applicable records safely."""
    url_domain = _target_hostname(url)
    if not url_domain:
        raise ValueError("Cannot apply cookies to a URL without a valid hostname")
    logger.debug(f"Setting cookies for domain: {url_domain}")

    if cookie_json:
        from html2md.cookies.sources import ExportedCookieSource

        source = ExportedCookieSource(Path(cookie_json))
    else:
        from html2md.cookies.sources import browser_cookie_source

        source = browser_cookie_source(browser)
    cookies = source.load(url)

    if not cookies:
        raise CookieSourceError(
            f"No applicable cookies were found for {url_domain} in {source.name}"
        )

    session = apply_cookie_records(session, url, cookies)

    logger.debug("Applied %s cookies to session", len(session.cookies.get_dict()))
    logger.info(f"Applied cookies to session for {url}")

    return session
