"""
Robots.txt parser for respecting website crawling policies.

This module provides functionality to:
- Fetch and parse robots.txt files
- Check if URLs are allowed to be crawled
- Extract crawl-delay directives
- Cache robots.txt content for efficiency
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

import requests

from grab2md.network.safe_http import DestinationPolicy, guarded_request
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)

# RFC 9309's formal identifier omits digits, but product names containing digits
# are common. Accept them as a conservative parsing extension so such groups are
# honored rather than silently ignored.
_PRODUCT_TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


@dataclass(frozen=True)
class RobotsFetchResult:
    """robots.txt response data needed to apply RFC 9309 failure policy."""

    content: Optional[str]
    status_code: Optional[int]


def _normalize_octets(value: str, *, encode_pattern_literals: bool = False) -> str:
    """Normalize URI octets for RFC 9309 rule comparison."""
    normalized: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if (
            character == "%"
            and index + 2 < len(value)
            and value[index + 1] in _HEX_DIGITS
            and value[index + 2] in _HEX_DIGITS
        ):
            octet = int(value[index + 1 : index + 3], 16)
            decoded = chr(octet)
            normalized.append(decoded if decoded in _UNRESERVED else f"%{octet:02X}")
            index += 3
            continue
        if encode_pattern_literals and character in {"*", "$"}:
            normalized.append(f"%{ord(character):02X}")
        elif ord(character) < 128:
            normalized.append(character)
        else:
            normalized.extend(f"%{octet:02X}" for octet in character.encode("utf-8"))
        index += 1
    return "".join(normalized)


def _octet_length(value: str) -> int:
    """Count normalized comparison octets rather than display characters."""
    length = 0
    index = 0
    while index < len(value):
        if (
            value[index] == "%"
            and index + 2 < len(value)
            and value[index + 1] in _HEX_DIGITS
            and value[index + 2] in _HEX_DIGITS
        ):
            index += 3
        else:
            index += 1
        length += 1
    return length


@dataclass(frozen=True)
class _RobotsRule:
    allow: bool
    specificity: int
    parts: tuple[str, ...]
    anchored: bool

    @classmethod
    def parse(cls, pattern: str, *, allow: bool) -> Optional["_RobotsRule"]:
        """Compile one non-empty Allow/Disallow path pattern."""
        if not pattern:
            return None
        anchored = pattern.endswith("$")
        comparable_pattern = pattern[:-1] if anchored else pattern
        parts = comparable_pattern.split("*")
        normalized_parts = [
            _normalize_octets(part, encode_pattern_literals=True) for part in parts
        ]
        return cls(
            allow=allow,
            specificity=sum(_octet_length(part) for part in normalized_parts),
            parts=tuple(normalized_parts),
            anchored=anchored,
        )

    def matches(self, path: str) -> bool:
        if len(self.parts) == 1:
            literal = self.parts[0]
            return path == literal if self.anchored else path.startswith(literal)

        position = 0
        first = self.parts[0]
        if first:
            if not path.startswith(first):
                return False
            position = len(first)

        for part in self.parts[1:-1]:
            match_at = path.find(part, position)
            if match_at < 0:
                return False
            position = match_at + len(part)

        last = self.parts[-1]
        if not last:
            return True
        if self.anchored:
            match_at = path.rfind(last, position)
            return match_at >= position and match_at + len(last) == len(path)
        return path.find(last, position) >= 0


@dataclass(frozen=True)
class _RobotsGroup:
    agents: tuple[str, ...]
    rules: tuple[_RobotsRule, ...]
    crawl_delays: tuple[str, ...]


@dataclass(frozen=True)
class _RobotsPolicy:
    """Parsed RFC 9309 access rules plus the crawl-delay extension."""

    groups: tuple[_RobotsGroup, ...] = ()
    allow_everything: bool = False
    disallow_everything: bool = False

    @classmethod
    def parse(cls, content: str) -> "_RobotsPolicy":
        groups: list[_RobotsGroup] = []
        agents: list[str] = []
        rules: list[_RobotsRule] = []
        crawl_delays: list[str] = []
        seen_record = False

        def finish_group() -> None:
            if agents:
                groups.append(
                    _RobotsGroup(
                        agents=tuple(agents),
                        rules=tuple(rules),
                        crawl_delays=tuple(crawl_delays),
                    )
                )

        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if seen_record:
                    finish_group()
                    agents.clear()
                    rules.clear()
                    crawl_delays.clear()
                    seen_record = False
                normalized_agent = value.lower()
                if normalized_agent == "*" or _PRODUCT_TOKEN.fullmatch(value):
                    agents.append(normalized_agent)
                continue
            if not agents:
                continue
            seen_record = True
            if field in {"allow", "disallow"}:
                rule = _RobotsRule.parse(value, allow=field == "allow")
                if rule is not None:
                    rules.append(rule)
            elif field == "crawl-delay":
                crawl_delays.append(value)
        finish_group()
        return cls(groups=tuple(groups))

    def _matching_groups(self, product_token: str) -> tuple[_RobotsGroup, ...]:
        exact = tuple(
            group for group in self.groups if product_token.lower() in group.agents
        )
        if exact:
            return exact
        return tuple(group for group in self.groups if "*" in group.agents)

    def can_fetch(self, product_token: str, url: str) -> bool:
        if self.allow_everything:
            return True
        if self.disallow_everything:
            return False

        parsed = urlsplit(url)
        if parsed.path == "/robots.txt":
            return True
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        normalized_target = _normalize_octets(
            target,
            encode_pattern_literals=True,
        )
        matches = [
            rule
            for group in self._matching_groups(product_token)
            for rule in group.rules
            if rule.matches(normalized_target)
        ]
        if not matches:
            return True
        best_specificity = max(rule.specificity for rule in matches)
        return any(
            rule.allow for rule in matches if rule.specificity == best_specificity
        )

    def crawl_delay(self, product_token: str) -> Optional[float]:
        for group in self._matching_groups(product_token):
            for value in group.crawl_delays:
                try:
                    delay = float(value)
                except ValueError:
                    logger.warning("Invalid crawl-delay value: %s", value)
                    continue
                if delay >= 0:
                    return delay
                logger.warning("Invalid crawl-delay value: %s", value)
        return None


class RobotsChecker:
    """
    A robots.txt parser that respects website crawling policies.

    Features:
    - Caches robots.txt content to avoid repeated fetches
    - Supports crawl-delay directives
    - Handles various edge cases (missing robots.txt, malformed content)
    - Serializes cache/session access for concurrent callers
    """

    def __init__(
        self,
        user_agent: str = "grab2md",
        session: Optional[requests.Session] = None,
        network_policy: Optional[DestinationPolicy] = None,
        allow_private_network: bool = False,
        scheduler: Any = None,
    ):
        """
        Initialize the robots checker.

        Args:
            user_agent: The user agent string to use when checking rules
            session: Optional requests session for connection pooling
        """
        self.user_agent = user_agent
        self._product_token = user_agent.split()[0].split("/", 1)[0].lower()
        self.session = session or requests.Session()
        self.network_policy = network_policy or DestinationPolicy(
            allow_private=allow_private_network
        )
        self.scheduler = scheduler
        self._cache: dict[str, tuple[_RobotsPolicy, Optional[float], float]] = {}
        self._cache_duration = 3600  # Cache robots.txt for 1 hour
        self._lock = threading.RLock()

    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _fetch_robots_txt(self, robots_url: str) -> RobotsFetchResult:
        """
        Fetch robots.txt content from a URL.

        Returns:
            Content and HTTP status, or no status for a network failure.
        """
        try:
            response = guarded_request(
                self.session,
                "GET",
                robots_url,
                policy=self.network_policy,
                timeout=10,
                max_body_bytes=1024 * 1024,
                headers={"User-Agent": self.user_agent},
                request_scheduler=self.scheduler,
            )
            if 200 <= response.status_code < 300:
                # RFC 9309 defines robots.txt as UTF-8. Do not inherit Requests'
                # ISO-8859-1 fallback for charset-less text/plain responses.
                response.encoding = "utf-8"
                return RobotsFetchResult(response.text, response.status_code)
            if 400 <= response.status_code < 500:
                logger.debug(
                    f"robots.txt unavailable at {robots_url}: HTTP {response.status_code}"
                )
                return RobotsFetchResult("", response.status_code)
            else:
                logger.warning(
                    f"Failed to fetch robots.txt from {robots_url}: HTTP {response.status_code}"
                )
                return RobotsFetchResult(None, response.status_code)
        except requests.RequestException as e:
            logger.warning(f"Error fetching robots.txt from {robots_url}: {e}")
            return RobotsFetchResult(None, None)

    def _parse_crawl_delay(self, content: str) -> Optional[float]:
        """
        Extract crawl-delay directive from robots.txt content.

        Args:
            content: The robots.txt content

        Returns:
            Crawl delay in seconds, or None if not specified
        """
        return _RobotsPolicy.parse(content).crawl_delay(self._product_token)

    def _get_cached_or_fetch(self, url: str) -> tuple[_RobotsPolicy, Optional[float]]:
        """
        Get robots.txt parser from cache or fetch if needed.

        Returns:
            Tuple of (parsed robots policy, crawl_delay)
        """
        robots_url = self._get_robots_url(url)
        with self._lock:
            if robots_url in self._cache:
                parser, crawl_delay, cached_time = self._cache[robots_url]
                if time.time() - cached_time < self._cache_duration:
                    return parser, crawl_delay

            fetch_result = self._fetch_robots_txt(robots_url)
            content = fetch_result.content

            if (
                fetch_result.status_code is not None
                and 400 <= fetch_result.status_code < 500
            ):
                # RFC 9309: an unavailable robots.txt permits access.
                policy = _RobotsPolicy(allow_everything=True)
            elif content is not None:
                policy = _RobotsPolicy.parse(content)
            else:
                # RFC 9309: unreachable or 5xx robots.txt is temporarily unavailable;
                # crawlers must assume complete disallow.
                policy = _RobotsPolicy(disallow_everything=True)

            crawl_delay = policy.crawl_delay(self._product_token)
            self._cache[robots_url] = (policy, crawl_delay, time.time())
            return policy, crawl_delay

    def can_fetch(self, url: str) -> bool:
        """
        Check if a URL can be fetched according to robots.txt.

        Args:
            url: The URL to check

        Returns:
            True if the URL can be fetched, False otherwise
        """
        try:
            policy, _ = self._get_cached_or_fetch(url)
            return policy.can_fetch(self._product_token, url)
        except Exception as e:
            logger.error(f"Error checking robots.txt for {url}: {e}")
            return False

    def get_crawl_delay(self, url: str) -> Optional[float]:
        """
        Get the crawl-delay for a given URL from robots.txt.

        Args:
            url: The URL to check

        Returns:
            Crawl delay in seconds, or None if not specified
        """
        try:
            _, crawl_delay = self._get_cached_or_fetch(url)
            return crawl_delay
        except Exception as e:
            logger.error(f"Error getting crawl-delay for {url}: {e}")
            return None

    def filter_urls(self, urls: list) -> list:
        """
        Filter a list of URLs to only include those allowed by robots.txt.

        Args:
            urls: List of URLs to filter

        Returns:
            List of allowed URLs
        """
        allowed_urls = []
        for url in urls:
            if self.can_fetch(url):
                allowed_urls.append(url)
            else:
                logger.info(f"URL disallowed by robots.txt: {url}")
        return allowed_urls

    def clear_cache(self):
        """Clear the robots.txt cache."""
        with self._lock:
            self._cache.clear()
