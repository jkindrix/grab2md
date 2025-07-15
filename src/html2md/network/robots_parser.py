"""
Robots.txt parser for respecting website crawling policies.

This module provides functionality to:
- Fetch and parse robots.txt files
- Check if URLs are allowed to be crawled
- Extract crawl-delay directives
- Cache robots.txt content for efficiency
"""

import logging
import re
import time
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger("html2md")


class RobotsChecker:
    """
    A robots.txt parser that respects website crawling policies.
    
    Features:
    - Caches robots.txt content to avoid repeated fetches
    - Supports crawl-delay directives
    - Handles various edge cases (missing robots.txt, malformed content)
    - Thread-safe for concurrent operations
    """
    
    def __init__(self, user_agent: str = "html2md", session: Optional[requests.Session] = None):
        """
        Initialize the robots checker.
        
        Args:
            user_agent: The user agent string to use when checking rules
            session: Optional requests session for connection pooling
        """
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self._cache: Dict[str, Tuple[RobotFileParser, Optional[float], float]] = {}
        self._cache_duration = 3600  # Cache robots.txt for 1 hour
        
    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    def _fetch_robots_txt(self, robots_url: str) -> Optional[str]:
        """
        Fetch robots.txt content from a URL.
        
        Returns:
            The robots.txt content, or None if fetch failed
        """
        try:
            response = self.session.get(
                robots_url, 
                timeout=10,
                headers={'User-Agent': self.user_agent}
            )
            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                logger.debug(f"No robots.txt found at {robots_url}")
                return ""  # Empty robots.txt means everything is allowed
            else:
                logger.warning(f"Failed to fetch robots.txt from {robots_url}: HTTP {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.warning(f"Error fetching robots.txt from {robots_url}: {e}")
            return None
    
    def _parse_crawl_delay(self, content: str) -> Optional[float]:
        """
        Extract crawl-delay directive from robots.txt content.
        
        Args:
            content: The robots.txt content
            
        Returns:
            Crawl delay in seconds, or None if not specified
        """
        if not content:
            return None
            
        # Look for crawl-delay directives for our user agent or *
        lines = content.lower().split('\n')
        current_agent = None
        crawl_delay = None
        
        for line in lines:
            line = line.strip()
            
            # Check for user-agent directive
            if line.startswith('user-agent:'):
                agent = line.split(':', 1)[1].strip()
                if agent == '*' or self.user_agent.lower() in agent:
                    current_agent = agent
                else:
                    current_agent = None
            
            # Check for crawl-delay directive
            elif line.startswith('crawl-delay:') and current_agent is not None:
                try:
                    delay_str = line.split(':', 1)[1].strip()
                    crawl_delay = float(delay_str)
                    break  # Use the first matching crawl-delay
                except (ValueError, IndexError):
                    logger.warning(f"Invalid crawl-delay value: {line}")
        
        return crawl_delay
    
    def _get_cached_or_fetch(self, url: str) -> Tuple[RobotFileParser, Optional[float]]:
        """
        Get robots.txt parser from cache or fetch if needed.
        
        Returns:
            Tuple of (RobotFileParser, crawl_delay)
        """
        robots_url = self._get_robots_url(url)
        
        # Check cache
        if robots_url in self._cache:
            parser, crawl_delay, cached_time = self._cache[robots_url]
            if time.time() - cached_time < self._cache_duration:
                return parser, crawl_delay
        
        # Fetch and parse robots.txt
        content = self._fetch_robots_txt(robots_url)
        
        # Create parser
        parser = RobotFileParser()
        parser.set_url(robots_url)
        
        if content is not None:
            parser.parse(content.split('\n'))
        else:
            # If fetch failed, assume everything is allowed to avoid blocking crawl
            parser.parse([])
        
        # Extract crawl delay
        crawl_delay = self._parse_crawl_delay(content) if content else None
        
        # Cache the result
        self._cache[robots_url] = (parser, crawl_delay, time.time())
        
        return parser, crawl_delay
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if a URL can be fetched according to robots.txt.
        
        Args:
            url: The URL to check
            
        Returns:
            True if the URL can be fetched, False otherwise
        """
        try:
            parser, _ = self._get_cached_or_fetch(url)
            return parser.can_fetch(self.user_agent, url)
        except Exception as e:
            logger.error(f"Error checking robots.txt for {url}: {e}")
            # On error, default to allowing fetch to avoid blocking crawl
            return True
    
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
        self._cache.clear()