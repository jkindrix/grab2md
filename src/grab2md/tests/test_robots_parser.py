"""
Comprehensive tests for robots.txt parser functionality.
"""

import pytest
import requests
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
import time

from grab2md.network.robots_parser import RobotsChecker


@pytest.fixture(autouse=True)
def route_fixtures_through_robots_boundary(monkeypatch):
    def request(session, _method, url, **kwargs):
        return session.get(
            url,
            timeout=kwargs.get("timeout"),
            headers=kwargs.get("headers"),
        )

    monkeypatch.setattr("grab2md.network.robots_parser.guarded_request", request)


class TestRobotsChecker:
    """Test suite for RobotsChecker class."""

    def test_initialization(self):
        """Test RobotsChecker initialization."""
        checker = RobotsChecker(user_agent="TestBot")
        assert checker.user_agent == "TestBot"
        assert checker._cache == {}
        assert checker._cache_duration == 3600

    def test_get_robots_url(self):
        """Test robots.txt URL generation."""
        checker = RobotsChecker()

        # Test various URL formats
        assert (
            checker._get_robots_url("https://example.com/page")
            == "https://example.com/robots.txt"
        )
        assert (
            checker._get_robots_url("http://sub.example.com/path/to/page")
            == "http://sub.example.com/robots.txt"
        )
        assert (
            checker._get_robots_url("https://example.com:8080/")
            == "https://example.com:8080/robots.txt"
        )

    @patch("requests.Session.get")
    def test_fetch_robots_txt_success(self, mock_get):
        """Test successful robots.txt fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /private/"
        mock_get.return_value = mock_response

        checker = RobotsChecker()
        result = checker._fetch_robots_txt("https://example.com/robots.txt")

        assert result.content == "User-agent: *\nDisallow: /private/"
        assert result.status_code == 200
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_fetch_robots_txt_decodes_charsetless_content_as_utf8(self, mock_get):
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "text/plain"
        response._content = "User-agent: *\nDisallow: /café".encode()
        mock_get.return_value = response

        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/café") is False

    @patch("requests.Session.get")
    def test_fetch_robots_txt_404(self, mock_get):
        """Test robots.txt fetch with 404 (no robots.txt)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        checker = RobotsChecker()
        result = checker._fetch_robots_txt("https://example.com/robots.txt")

        assert result.content == ""
        assert result.status_code == 404

    @patch("requests.Session.get")
    def test_fetch_robots_txt_error(self, mock_get):
        """Test robots.txt fetch with network error."""
        from requests.exceptions import RequestException

        mock_get.side_effect = RequestException("Network error")

        checker = RobotsChecker()
        result = checker._fetch_robots_txt("https://example.com/robots.txt")

        assert result.content is None
        assert result.status_code is None

    @patch("requests.Session.get")
    def test_unavailable_robots_txt_temporarily_disallows_crawl(self, mock_get):
        mock_response = Mock(status_code=503)
        mock_get.return_value = mock_response

        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/page") is False

    @patch("requests.Session.get")
    def test_missing_robots_txt_allows_crawl(self, mock_get):
        mock_response = Mock(status_code=404)
        mock_get.return_value = mock_response

        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/page") is True

    def test_parse_crawl_delay(self):
        """Test crawl-delay parsing from robots.txt."""
        checker = RobotsChecker(user_agent="TestBot")

        # Test with matching user agent
        content = """
User-agent: TestBot
Crawl-delay: 2.5
Disallow: /private/

User-agent: *
Crawl-delay: 5.0
"""
        assert checker._parse_crawl_delay(content) == 2.5

        # Test with wildcard only
        content = """
User-agent: *
Crawl-delay: 3.0
"""
        assert checker._parse_crawl_delay(content) == 3.0

        # Test with no crawl-delay
        content = """
User-agent: *
Disallow: /private/
"""
        assert checker._parse_crawl_delay(content) is None

    def test_parse_crawl_delay_matches_product_token_not_substrings(self):
        checker = RobotsChecker(user_agent="grab2md/1.0 (+https://example.com/bot)")
        content = """
User-agent: not-grab2md
Crawl-delay: 99

User-agent: grab2md
Crawl-delay: 2

User-agent: *
Crawl-delay: 5
"""

        assert checker._parse_crawl_delay(content) == 2

        # Test with invalid crawl-delay
        content = """
User-agent: *
Crawl-delay: invalid
"""
        assert checker._parse_crawl_delay(content) is None

    @patch("requests.Session.get")
    def test_can_fetch_allowed(self, mock_get):
        """Test can_fetch for allowed URLs."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Disallow: /private/
Disallow: /admin/
"""
        mock_get.return_value = mock_response

        checker = RobotsChecker()

        # Allowed URLs
        assert checker.can_fetch("https://example.com/") is True
        assert checker.can_fetch("https://example.com/public/page") is True
        assert checker.can_fetch("https://example.com/about") is True

    @patch("requests.Session.get")
    def test_can_fetch_disallowed(self, mock_get):
        """Test can_fetch for disallowed URLs."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Disallow: /private/
Disallow: /admin/
"""
        mock_get.return_value = mock_response

        checker = RobotsChecker()

        # Disallowed URLs
        assert checker.can_fetch("https://example.com/private/secret") is False
        assert checker.can_fetch("https://example.com/admin/panel") is False

    @patch("requests.Session.get")
    def test_get_crawl_delay(self, mock_get):
        """Test getting crawl-delay from robots.txt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Crawl-delay: 1.5
Disallow: /private/
"""
        mock_get.return_value = mock_response

        checker = RobotsChecker()
        delay = checker.get_crawl_delay("https://example.com/page")

        assert delay == 1.5

    @patch("requests.Session.get")
    def test_filter_urls(self, mock_get):
        """Test filtering URLs based on robots.txt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: *
Disallow: /private/
Disallow: /admin/
"""
        mock_get.return_value = mock_response

        checker = RobotsChecker()
        urls = [
            "https://example.com/",
            "https://example.com/public/page",
            "https://example.com/private/secret",
            "https://example.com/admin/panel",
            "https://example.com/about",
        ]

        allowed_urls = checker.filter_urls(urls)

        assert len(allowed_urls) == 3
        assert "https://example.com/" in allowed_urls
        assert "https://example.com/public/page" in allowed_urls
        assert "https://example.com/about" in allowed_urls
        assert "https://example.com/private/secret" not in allowed_urls
        assert "https://example.com/admin/panel" not in allowed_urls

    @patch("requests.Session.get")
    def test_caching(self, mock_get):
        """Test that robots.txt is cached properly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /private/"
        mock_get.return_value = mock_response

        checker = RobotsChecker()

        # First call should fetch
        checker.can_fetch("https://example.com/page1")
        assert mock_get.call_count == 1

        # Second call should use cache
        checker.can_fetch("https://example.com/page2")
        assert mock_get.call_count == 1  # Still 1, not 2

        # Different domain should fetch again
        checker.can_fetch("https://other.com/page")
        assert mock_get.call_count == 2

    def test_concurrent_cache_miss_fetches_once(self):
        session = Mock()

        def delayed_response(*args, **kwargs):
            time.sleep(0.01)
            return Mock(
                status_code=200,
                text="User-agent: *\nDisallow: /private/",
            )

        session.get.side_effect = delayed_response
        checker = RobotsChecker(session=session)

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(
                executor.map(
                    checker.can_fetch,
                    [f"https://example.com/page-{index}" for index in range(5)],
                )
            )

        assert results == [True] * 5
        session.get.assert_called_once()

    def test_clear_cache(self):
        """Test cache clearing."""
        checker = RobotsChecker()
        checker._cache = {"test": "data"}

        checker.clear_cache()
        assert checker._cache == {}

    @patch("requests.Session.get")
    def test_user_agent_specific_rules(self, mock_get):
        """Test user-agent specific rules."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
User-agent: BadBot
Disallow: /

User-agent: grab2md
Disallow: /restricted/
Crawl-delay: 1.0

User-agent: *
Disallow: /private/
Crawl-delay: 5.0
"""
        mock_get.return_value = mock_response

        # Test with grab2md user agent
        checker = RobotsChecker(user_agent="grab2md")
        assert checker.can_fetch("https://example.com/public") is True
        assert checker.can_fetch("https://example.com/restricted/page") is False
        assert checker.get_crawl_delay("https://example.com/") == 1.0

        # Test with different user agent
        checker2 = RobotsChecker(user_agent="GoodBot")
        assert checker2.can_fetch("https://example.com/public") is True
        assert (
            checker2.can_fetch("https://example.com/restricted/page") is True
        )  # Not restricted for GoodBot
        assert checker2.get_crawl_delay("https://example.com/") == 5.0  # Uses * rule

    @pytest.mark.parametrize("path", ["/first", "/second"])
    @patch("requests.Session.get")
    def test_duplicate_product_groups_are_combined(self, mock_get, path):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: grab2md
Disallow: /first

User-agent: grab2md
Disallow: /second
""",
        )

        assert RobotsChecker().can_fetch(f"https://example.com{path}") is False

    @patch("requests.Session.get")
    def test_exact_product_group_replaces_combined_wildcard_groups(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: *
Disallow: /wild-one

User-agent: *
Disallow: /wild-two

User-agent: grab2md
Disallow: /specific
""",
        )
        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/wild-one") is True
        assert checker.can_fetch("https://example.com/wild-two") is True
        assert checker.can_fetch("https://example.com/specific") is False

    @pytest.mark.parametrize("path", ["/wild-one", "/wild-two"])
    @patch("requests.Session.get")
    def test_duplicate_wildcard_groups_are_combined_without_exact_group(
        self, mock_get, path
    ):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: *
Disallow: /wild-one

User-agent: *
Disallow: /wild-two
""",
        )

        assert RobotsChecker().can_fetch(f"https://example.com{path}") is False

    @patch("requests.Session.get")
    def test_product_token_matching_is_exact_and_case_insensitive(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: not-grab2md
Disallow: /wrong

User-agent: GRAB2MD
Disallow: /right
""",
        )
        checker = RobotsChecker(user_agent="grab2md/0.4.2")

        assert checker.can_fetch("https://example.com/wrong") is True
        assert checker.can_fetch("https://example.com/right") is False

    @patch("requests.Session.get")
    def test_wildcards_end_anchors_and_queries_follow_rfc_9309(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: *
Disallow: /*.pdf$
Disallow: /private/*/draft
""",
        )
        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/report.pdf") is False
        assert checker.can_fetch("https://example.com/report.pdf?download=1") is True
        assert checker.can_fetch("https://example.com/report.pdfx") is True
        assert checker.can_fetch("https://example.com/private/a/b/draft") is False

    @patch("requests.Session.get")
    def test_longest_rule_wins_and_allow_wins_equivalent_tie(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: *
Disallow: /documents/
Allow: /documents/public/
Disallow: /same
Allow: /same
""",
        )
        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/documents/private") is False
        assert checker.can_fetch("https://example.com/documents/public/page") is True
        assert checker.can_fetch("https://example.com/same") is True

    @patch("requests.Session.get")
    def test_percent_encoded_octets_are_normalized_for_matching(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="""
User-agent: *
Disallow: /users/%7Eprivate
Disallow: /caf%C3%A9
Disallow: /literal-%2A
Disallow: /literal-%24
Disallow: /encoded%2Fslash
""",
        )
        checker = RobotsChecker()

        assert checker.can_fetch("https://example.com/users/~private") is False
        assert checker.can_fetch("https://example.com/café") is False
        assert checker.can_fetch("https://example.com/literal-*") is False
        assert checker.can_fetch("https://example.com/literal-$") is False
        assert checker.can_fetch("https://example.com/encoded%2fslash") is False
        assert checker.can_fetch("https://example.com/encoded/slash") is True

    @patch("requests.Session.get")
    def test_robots_txt_path_is_implicitly_allowed(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            text="User-agent: *\nDisallow: /",
        )

        assert RobotsChecker().can_fetch("https://example.com/robots.txt") is True


if __name__ == "__main__":
    pytest.main([__file__])
