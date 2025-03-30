import json
import logging

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from html2md.config.loader import TOKENS_FILE, load_config

logger = logging.getLogger("session_manager")

# Load configuration
config = load_config()

# Load OAuth credentials from config
CLIENT_ID = config.get("oauth", {}).get("CLIENT_ID", "")
CLIENT_SECRET = config.get("oauth", {}).get("CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    logger.error("Missing OAuth credentials in config file.")
    raise ValueError(
        "OAuth credentials (CLIENT_ID, CLIENT_SECRET) must be set in config.json"
    )

REDIRECT_URI = "http://localhost"
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


# -------------------------------
# OAuth Token Management
# -------------------------------


def load_tokens():
    """Load OAuth tokens from a local file."""
    if not TOKENS_FILE.exists():
        logger.warning(
            f"Token file not found at {TOKENS_FILE}. Performing fresh authentication."
        )
        return None

    try:
        with TOKENS_FILE.open("r", encoding="utf-8") as f:
            token_data = json.load(f)
        logger.info(f"Loaded OAuth tokens from {TOKENS_FILE}")
        return Credentials.from_authorized_user_info(token_data)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load tokens from {TOKENS_FILE}: {e}")
        return None


def save_tokens(creds):
    """Save OAuth tokens to a local file."""
    try:
        with TOKENS_FILE.open("w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info(f"Saved OAuth tokens to {TOKENS_FILE}")
    except IOError as e:
        logger.error(f"Failed to save tokens to {TOKENS_FILE}: {e}")


def authenticate_google():
    """Authenticate using Google OAuth and obtain an access token."""
    creds = None

    # Load existing credentials if available
    creds = load_tokens()

    # Refresh the token if it's expired and refresh_token is available
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Access token refreshed using the refresh token.")
            save_tokens(creds)
            return creds
        except Exception as e:
            logger.warning(
                f"Token refresh failed: {e}. Proceeding with re-authentication."
            )
            creds = None

    # Perform fresh OAuth if no valid credentials are available
    if not creds or not creds.valid:
        try:
            # Run local server for OAuth authorization with browser
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "redirect_uris": [REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )

            creds = flow.run_local_server(port=0)
            logger.info("Google OAuth authentication successful via local server.")
            save_tokens(creds)

        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise ValueError(
                "OAuth authentication failed. No valid access token found."
            )

    return creds


def refresh_token_if_expired(creds):
    """Refresh access token if it has expired."""
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Access token refreshed using refresh token.")
            save_tokens(creds)
        except Exception as e:
            logger.error(f"Token refresh failed: {e}. Performing fresh authentication.")
            return authenticate_google()
    return creds


def get_credentials():
    """Get credentials using stored tokens or authenticate fresh."""
    creds = load_tokens()

    # Refresh or authenticate if necessary
    if not creds or not creds.valid:
        creds = authenticate_google()

    if creds.expired:
        creds = refresh_token_if_expired(creds)

    return creds


# -------------------------------
# HTTP Session Management
# -------------------------------


def get_session():
    """Return a new configured requests session."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }
    )
    logger.info("New session initialized with default headers.")
    return session


def reset_session(session):
    """Reset the session by closing and creating a new session."""
    try:
        session.close()
        logger.info("Session closed successfully.")
    except Exception as e:
        logger.warning(f"Error while closing session: {e}")

    # Return a new session
    new_session = get_session()
    logger.info("New session initialized after reset.")
    return new_session


# -------------------------------
# Utility for Testing
# -------------------------------


def test_google_authentication():
    """Test OAuth authentication and session initialization."""
    try:
        get_credentials()
        logger.info("Testing OAuth authentication. Token obtained successfully.")
    except Exception as e:
        logger.error(f"OAuth test failed: {e}")
        raise

    session = get_session()
    try:
        response = session.get(
            "https://www.googleapis.com/oauth2/v1/userinfo", timeout=5
        )
        if response.status_code == 200:
            logger.info("Test API call successful.")
        else:
            logger.warning(
                f"Test API call failed with status code: {response.status_code}"
            )
    except requests.RequestException as e:
        logger.error(f"Failed to connect to Google API: {e}")


if __name__ == "__main__":
    test_google_authentication()
