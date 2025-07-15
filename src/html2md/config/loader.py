import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from html2md.utils.logger import setup_logging

logger = setup_logging()

# Default Configuration
DEFAULT_CONFIG = {
    "domains": {},
    "domain_limits": {
        # Example domain-specific rate limits
        # "github.com": {
        #     "max_concurrent": 2,
        #     "requests_per_minute": 30,
        #     "backoff_multiplier": 2.0
        # }
    },
    "concurrent": {
        "max_concurrent_per_domain": 2,
        "max_total_concurrent": 10,
        "connection_timeout": 30,
        "backoff_strategy": "exponential",  # none, linear, exponential, fibonacci
        "initial_backoff": 1.0,
        "max_backoff": 300.0,
        "backoff_multiplier": 2.0,
        "error_threshold": 3,
        "respect_retry_after": True,
        "polite_concurrent_limit": 1,
        "polite_delay_multiplier": 2.0
    },
    "logging": {"level": "WARNING"},
    "oauth": {"CLIENT_ID": "", "CLIENT_SECRET": ""},
    "browser": {"preferred": "chrome"},
    "headers": {
        "enhanced_user_agent": True,
        "contact_email": None,
        "contact_url": None,
        "user_agent_name": "html2md",
        "user_agent_version": "1.0",
        "enable_compression": True,
        "compression_methods": "gzip, deflate, br",
        "enable_conditional_requests": True,
        "simulate_browser": False,
        "browser_type": "chrome",
        "respect_caching": True,
        "include_accept_language": True,
        "preferred_language": "en-US,en;q=0.9",
        "custom_headers": {}
    },
    "cli_defaults": {
        "batch": {
            "hierarchical": False,
            "flatten": False,
            "flatten_all": False,
            "trim": True,
            "visualize": False,
            "quiet": False
        },
        "crawl": {
            "hierarchical": False,
            "flatten": False,
            "follow": "domain-only",
            "max_depth": 3,
            "max_pages": 100,
            "delay": 0.0,
            "respect_robots": True,
            "rate_limit": None,
            "enhanced_headers": True,
            "user_agent_contact": None,
            "simulate_browser": False,
            "polite": False,
            "max_concurrent": None,
            "show_progress": True,
            "trim": True,
            "visualize": False,
            "quiet": False
        },
        "convert": {
            "browser_cookies": False,
            "no_cookies": False,
            "browser": None,
            "enhanced_headers": True,
            "user_agent_contact": None,
            "simulate_browser": False,
            "trim": True,
            "download_images": False,
            "images_dir": "images",
            "fancy": False,
            "local": False
        }
    }
}


# Determine the correct config path based on OS
def get_config_path():
    """Return the appropriate configuration file path for the user's OS."""
    if sys.platform == "win32":
        config_dir = (
            Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "html2md"
        )
    elif sys.platform == "darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support" / "html2md"
    else:  # Assume Linux/Unix
        config_dir = (
            Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "html2md"
        )

    config_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    return config_dir / "config.json"


# Allow external configuration path override
CONFIG_FILE = Path(os.getenv("HTML2MD_CONFIG_PATH", get_config_path()))
CONFIG_PATH = CONFIG_FILE  # Alias for external use

# Set the token file location according to best practice
CONFIG_DIR = CONFIG_FILE.parent
TOKENS_FILE = CONFIG_DIR / "tokens.json"

_cached_config = None  # Cached configuration


def validate_config(config_data):
    """Ensure the loaded config contains required keys, falling back if necessary."""
    if not isinstance(config_data, dict):
        logger.error("Invalid config format: Expected a JSON object.")
        return deepcopy(DEFAULT_CONFIG)

    # Start with a copy of default config and merge user config
    merged_config = deepcopy(DEFAULT_CONFIG)
    
    # Deep merge user config into default config
    def deep_merge(default_dict, user_dict):
        """Recursively merge user config into default config."""
        for key, value in user_dict.items():
            if key in default_dict and isinstance(default_dict[key], dict) and isinstance(value, dict):
                deep_merge(default_dict[key], value)
            else:
                default_dict[key] = value
    
    deep_merge(merged_config, config_data)
    
    return merged_config


def ensure_config_exists():
    """Ensure configuration file exists, creating with defaults if missing."""
    if not CONFIG_FILE.exists():
        logger.warning(
            f"Configuration file not found: {CONFIG_FILE}. Creating with defaults."
        )
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")
        return True
    return False


def load_config(force_reload=False):
    """Load configuration from a JSON file, creating it if missing."""
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config  # Use cached config

    ensure_config_exists()
    _cached_config = deepcopy(DEFAULT_CONFIG) if not CONFIG_FILE.exists() else None

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config_data = json.load(f)
            _cached_config = validate_config(config_data)
            logger.info(f"Loaded configuration from: {CONFIG_FILE}")
            return _cached_config
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(
            f"Invalid or missing config ({CONFIG_FILE}): {e}. Resetting to defaults."
        )
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")

    _cached_config = deepcopy(DEFAULT_CONFIG)
    return _cached_config
