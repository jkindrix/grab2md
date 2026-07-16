"""
Tests for the enhanced header management system.
"""

import pytest
import time
from html2md.network.header_manager import (
    HeaderConfig,
    HeaderManager,
    format_http_date,
    parse_http_date,
)


class TestHeaderConfig:
    """Test HeaderConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HeaderConfig()

        assert config.use_enhanced_user_agent is True
        assert config.contact_email is None
        assert config.contact_url is None
        assert config.user_agent_name == "html2md"
        assert config.user_agent_version == "1.0"
        assert config.enable_compression is True
        assert config.compression_methods == "gzip, deflate, br"
        assert config.enable_conditional_requests is True
        assert config.simulate_browser is False
        assert config.browser_type == "chrome"
        assert config.respect_caching is True
        assert config.include_accept_language is True
        assert config.preferred_language == "en-US,en;q=0.9"
        assert config.custom_headers == {}

    def test_custom_config(self):
        """Test custom configuration values."""
        custom_headers = {"X-Custom": "test-value"}
        config = HeaderConfig(
            contact_email="test@example.com",
            contact_url="https://example.com/contact",
            simulate_browser=True,
            browser_type="firefox",
            custom_headers=custom_headers,
        )

        assert config.contact_email == "test@example.com"
        assert config.contact_url == "https://example.com/contact"
        assert config.simulate_browser is True
        assert config.browser_type == "firefox"
        assert config.custom_headers == custom_headers


class TestHeaderManager:
    """Test HeaderManager functionality."""

    def test_default_headers(self):
        """Test default header generation."""
        manager = HeaderManager()
        headers = manager.get_headers("https://example.com")

        # Check required headers
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Encoding" in headers
        assert "Accept-Language" in headers
        assert "Connection" in headers
        assert "Cache-Control" in headers
        assert "Referer" in headers

        # Check User-Agent contains html2md
        assert "html2md" in headers["User-Agent"]

        # Check compression support
        assert "gzip" in headers["Accept-Encoding"]
        assert "deflate" in headers["Accept-Encoding"]
        assert "br" in headers["Accept-Encoding"]

        # Check referer
        assert headers["Referer"] == "https://example.com/"

    def test_enhanced_user_agent(self):
        """Test enhanced User-Agent string generation."""
        config = HeaderConfig(
            contact_email="admin@example.com", contact_url="https://example.com/contact"
        )
        manager = HeaderManager(config)
        headers = manager.get_headers("https://test.com")

        user_agent = headers["User-Agent"]

        # Check basic components
        assert "html2md/1.0" in user_agent
        assert "Python/" in user_agent
        assert "Contact: admin@example.com" in user_agent
        assert "Info: https://example.com/contact" in user_agent

    def test_browser_simulation(self):
        """Test browser simulation headers."""
        config = HeaderConfig(
            use_enhanced_user_agent=False, simulate_browser=True, browser_type="chrome"
        )
        manager = HeaderManager(config)
        headers = manager.get_headers("https://test.com")

        # Should use browser User-Agent
        assert "Chrome" in headers["User-Agent"]
        assert "html2md" not in headers["User-Agent"]

        # Should have browser simulation headers
        assert "Sec-CH-UA" in headers
        assert "Sec-Fetch-Dest" in headers

    def test_firefox_simulation(self):
        """Test Firefox browser simulation."""
        config = HeaderConfig(
            use_enhanced_user_agent=False, simulate_browser=True, browser_type="firefox"
        )
        manager = HeaderManager(config)
        headers = manager.get_headers("https://test.com")

        assert "Firefox" in headers["User-Agent"]
        assert "DNT" in headers
        assert "Sec-Fetch-Dest" in headers

    def test_conditional_requests(self):
        """Test If-Modified-Since conditional requests."""
        config = HeaderConfig(enable_conditional_requests=True)
        manager = HeaderManager(config)

        # First request without last-modified
        headers1 = manager.get_headers("https://example.com")
        assert "If-Modified-Since" not in headers1

        # Update last-modified
        last_modified = "Wed, 15 Nov 2023 12:00:00 GMT"
        manager.update_last_modified("https://example.com", last_modified)

        # Second request should include If-Modified-Since
        headers2 = manager.get_headers("https://example.com")
        assert headers2["If-Modified-Since"] == last_modified

        # Third request with explicit last-modified
        new_last_modified = "Thu, 16 Nov 2023 13:00:00 GMT"
        headers3 = manager.get_headers("https://example.com", new_last_modified)
        assert headers3["If-Modified-Since"] == new_last_modified

    def test_conditional_requests_disabled(self):
        """Test disabled conditional requests."""
        config = HeaderConfig(enable_conditional_requests=False)
        manager = HeaderManager(config)

        manager.update_last_modified(
            "https://example.com", "Wed, 15 Nov 2023 12:00:00 GMT"
        )
        headers = manager.get_headers("https://example.com")

        assert "If-Modified-Since" not in headers

    def test_compression_disabled(self):
        """Test disabled compression."""
        config = HeaderConfig(enable_compression=False)
        manager = HeaderManager(config)
        headers = manager.get_headers("https://example.com")

        assert "Accept-Encoding" not in headers

    def test_custom_headers(self):
        """Test custom headers override."""
        custom_headers = {
            "X-Custom-Header": "custom-value",
            "User-Agent": "custom-user-agent",
        }
        config = HeaderConfig(custom_headers=custom_headers)
        manager = HeaderManager(config)
        headers = manager.get_headers("https://example.com")

        assert headers["X-Custom-Header"] == "custom-value"
        assert headers["User-Agent"] == "custom-user-agent"  # Overrides default

    def test_cache_management(self):
        """Test header cache management."""
        manager = HeaderManager()

        # Test last-modified cache
        manager.update_last_modified(
            "https://example.com", "Wed, 15 Nov 2023 12:00:00 GMT"
        )
        assert (
            manager.get_last_modified("https://example.com")
            == "Wed, 15 Nov 2023 12:00:00 GMT"
        )
        assert manager.get_last_modified("https://other.com") is None

        # Test cache clearing
        manager.clear_cache()
        assert manager.get_last_modified("https://example.com") is None

    def test_config_update(self):
        """Test configuration updates."""
        manager = HeaderManager()

        # Initial headers
        headers1 = manager.get_headers("https://example.com")
        assert "html2md" in headers1["User-Agent"]

        # Update config
        new_config = HeaderConfig(use_enhanced_user_agent=False, simulate_browser=True)
        manager.update_config(new_config)

        # Headers should change
        headers2 = manager.get_headers("https://example.com")
        assert "html2md" not in headers2["User-Agent"]
        assert "Chrome" in headers2["User-Agent"]

    def test_config_summary(self):
        """Test configuration summary."""
        config = HeaderConfig(
            contact_email="test@example.com", custom_headers={"X-Test": "value"}
        )
        manager = HeaderManager(config)
        manager.update_last_modified(
            "https://example.com", "Wed, 15 Nov 2023 12:00:00 GMT"
        )

        summary = manager.get_config_summary()

        assert summary["enhanced_user_agent"] is True
        assert summary["contact_email"] == "test@example.com"
        assert summary["compression_enabled"] is True
        assert summary["conditional_requests"] is True
        assert summary["browser_simulation"] is False
        assert summary["browser_type"] == "chrome"
        assert summary["custom_headers_count"] == 1
        assert summary["cached_last_modified_count"] == 1


class TestHTTPDateHandling:
    """Test HTTP date formatting and parsing."""

    def test_format_http_date_current_time(self):
        """Test formatting current time."""
        date_str = format_http_date()

        # Should be in RFC 7231 format
        assert date_str.endswith(" GMT")
        assert len(date_str.split()) == 6  # "Day, DD Mon YYYY HH:MM:SS GMT"

    def test_format_http_date_specific_time(self):
        """Test formatting specific timestamp."""
        timestamp = 1700000000  # Nov 15, 2023 02:13:20 GMT
        date_str = format_http_date(timestamp)

        assert "2023" in date_str
        assert "GMT" in date_str

    def test_parse_http_date_rfc7231(self):
        """Test parsing RFC 7231 format."""
        date_str = "Wed, 15 Nov 2023 12:00:00 GMT"
        timestamp = parse_http_date(date_str)

        assert timestamp is not None
        assert isinstance(timestamp, float)

        # Verify round-trip
        formatted = format_http_date(timestamp)
        assert "2023" in formatted

    def test_parse_http_date_rfc850(self):
        """Test parsing RFC 850 format."""
        date_str = "Wednesday, 15-Nov-23 12:00:00 GMT"
        timestamp = parse_http_date(date_str)

        assert timestamp is not None
        assert isinstance(timestamp, float)

    def test_parse_http_date_asctime(self):
        """Test parsing ANSI C asctime format."""
        date_str = "Wed Nov 15 12:00:00 2023"
        timestamp = parse_http_date(date_str)

        assert timestamp is not None
        assert isinstance(timestamp, float)

    def test_parse_http_date_invalid(self):
        """Test parsing invalid date format."""
        timestamp = parse_http_date("invalid date string")
        assert timestamp is None

    def test_http_date_roundtrip(self):
        """Test round-trip conversion."""
        original_timestamp = time.time()
        date_str = format_http_date(original_timestamp)
        parsed_timestamp = parse_http_date(date_str)

        assert parsed_timestamp is not None
        # Should be within 1 second due to formatting precision
        assert abs(original_timestamp - parsed_timestamp) < 1.0


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_professional_crawler_headers(self):
        """Test headers for professional crawling."""
        config = HeaderConfig(
            contact_email="bot@company.com",
            contact_url="https://company.com/bot-info",
            enable_compression=True,
            enable_conditional_requests=True,
        )
        manager = HeaderManager(config)

        headers = manager.get_headers("https://api.example.com/data")

        # Professional identification
        assert "html2md/1.0" in headers["User-Agent"]
        assert "bot@company.com" in headers["User-Agent"]
        assert "company.com/bot-info" in headers["User-Agent"]

        # Respectful behavior
        assert "gzip" in headers["Accept-Encoding"]
        assert headers["Connection"] == "keep-alive"
        assert "max-age=0" in headers["Cache-Control"]

    def test_stealth_crawling_headers(self):
        """Test headers for stealth crawling."""
        config = HeaderConfig(
            use_enhanced_user_agent=False,
            simulate_browser=True,
            browser_type="chrome",
            enable_compression=True,
        )
        manager = HeaderManager(config)

        headers = manager.get_headers("https://protected-site.com")

        # Browser-like appearance
        assert "Chrome" in headers["User-Agent"]
        assert "html2md" not in headers["User-Agent"]
        assert "Sec-CH-UA" in headers
        assert "Sec-Fetch-Dest" in headers

        # Still respectful
        assert "gzip" in headers["Accept-Encoding"]

    def test_conditional_request_workflow(self):
        """Test conditional request workflow."""
        config = HeaderConfig(enable_conditional_requests=True)
        manager = HeaderManager(config)

        url = "https://api.example.com/resource"

        # First request - no conditional headers
        headers1 = manager.get_headers(url)
        assert "If-Modified-Since" not in headers1

        # Simulate response with Last-Modified
        response_last_modified = "Wed, 15 Nov 2023 12:00:00 GMT"
        manager.update_last_modified(url, response_last_modified)

        # Second request - should include conditional header
        headers2 = manager.get_headers(url)
        assert headers2["If-Modified-Since"] == response_last_modified

        # Third request to different URL - no conditional header
        headers3 = manager.get_headers("https://other.com/resource")
        assert "If-Modified-Since" not in headers3

    def test_multi_domain_caching(self):
        """Test last-modified caching across multiple domains."""
        manager = HeaderManager()

        urls = [
            "https://site1.com/page",
            "https://site2.com/data",
            "https://site1.com/other",
        ]

        # Update last-modified for each URL
        for i, url in enumerate(urls):
            last_modified = f"Wed, {15 + i} Nov 2023 12:00:00 GMT"
            manager.update_last_modified(url, last_modified)

        # Verify each URL has its own cached timestamp
        assert manager.get_last_modified(urls[0]) == "Wed, 15 Nov 2023 12:00:00 GMT"
        assert manager.get_last_modified(urls[1]) == "Wed, 16 Nov 2023 12:00:00 GMT"
        assert manager.get_last_modified(urls[2]) == "Wed, 17 Nov 2023 12:00:00 GMT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
