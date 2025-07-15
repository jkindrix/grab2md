"""
Concurrent request control and connection management for respectful web crawling.

This module provides:
- Per-domain concurrent connection limits
- Request queue management
- Connection pooling with limits
- Progressive backoff on errors
- Polite crawling mode
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Set, Tuple, Deque, Any
from urllib.parse import urlparse
import aiohttp
from aiohttp import ClientSession, ClientTimeout, ClientError

logger = logging.getLogger("html2md")


class BackoffStrategy(Enum):
    """Backoff strategies for error handling."""
    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"


@dataclass
class DomainState:
    """State tracking for a specific domain."""
    active_connections: int = 0
    queued_requests: Deque[Tuple[str, asyncio.Future]] = field(default_factory=deque)
    last_request_time: float = 0
    consecutive_errors: int = 0
    backoff_until: Optional[float] = None
    total_requests: int = 0
    total_errors: int = 0
    last_429_time: Optional[float] = None
    retry_after: Optional[int] = None


@dataclass
class ConcurrentConfig:
    """Configuration for concurrent request control."""
    
    # Connection limits
    max_concurrent_per_domain: int = 2
    max_total_concurrent: int = 10
    connection_timeout: int = 30
    
    # Queue management
    max_queue_size_per_domain: int = 100
    queue_timeout: int = 300  # 5 minutes
    
    # Backoff configuration
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_backoff: float = 1.0
    max_backoff: float = 300.0  # 5 minutes
    backoff_multiplier: float = 2.0
    retry_after_respect: bool = True
    
    # Error thresholds
    error_threshold_for_backoff: int = 3
    reset_threshold_minutes: int = 10
    
    # Polite mode settings
    polite_mode: bool = False
    polite_concurrent_limit: int = 1
    polite_delay_multiplier: float = 2.0
    
    # Progress tracking
    enable_progress_tracking: bool = True
    progress_update_interval: float = 1.0


class ConcurrentController:
    """Manages concurrent requests with per-domain limits and backoff."""
    
    def __init__(self, config: Optional[ConcurrentConfig] = None):
        self.config = config or ConcurrentConfig()
        self.domain_states: Dict[str, DomainState] = defaultdict(DomainState)
        self.active_domains: Set[str] = set()
        self.global_active: int = 0
        self._lock = asyncio.Lock()
        self._domain_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default
        self._shutdown = False
        self._session: Optional[ClientSession] = None
        
        # Progress tracking
        self.total_urls_queued: int = 0
        self.total_urls_completed: int = 0
        self.start_time: float = time.time()
        
        # Apply polite mode adjustments
        if self.config.polite_mode:
            self.config.max_concurrent_per_domain = self.config.polite_concurrent_limit
            self.config.max_total_concurrent = max(5, self.config.polite_concurrent_limit * 3)
    
    async def __aenter__(self):
        """Async context manager entry."""
        timeout = ClientTimeout(total=self.config.connection_timeout)
        connector = aiohttp.TCPConnector(
            limit=self.config.max_total_concurrent,
            limit_per_host=self.config.max_concurrent_per_domain
        )
        self._session = ClientSession(timeout=timeout, connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self._shutdown = True
        if self._session:
            await self._session.close()
    
    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc
    
    async def can_make_request(self, url: str) -> Tuple[bool, Optional[float]]:
        """
        Check if a request can be made to the URL's domain.
        
        Returns:
            Tuple of (can_proceed, wait_time_seconds)
        """
        domain = self.get_domain(url)
        
        async with self._domain_locks[domain]:
            state = self.domain_states[domain]
            
            # Check backoff
            if state.backoff_until and time.time() < state.backoff_until:
                wait_time = state.backoff_until - time.time()
                return False, wait_time
            
            # Check concurrent limits
            max_concurrent = (self.config.polite_concurrent_limit 
                            if self.config.polite_mode 
                            else self.config.max_concurrent_per_domain)
            
            if state.active_connections >= max_concurrent:
                return False, None
            
            # Check global concurrent limit
            if self.global_active >= self.config.max_total_concurrent:
                return False, None
            
            return True, None
    
    async def acquire_slot(self, url: str) -> bool:
        """
        Acquire a slot for making a request.
        
        Returns:
            True if slot acquired, False if queued
        """
        domain = self.get_domain(url)
        
        async with self._lock:
            can_proceed, wait_time = await self.can_make_request(url)
            
            if can_proceed:
                self.domain_states[domain].active_connections += 1
                self.global_active += 1
                self.active_domains.add(domain)
                return True
            
            # Queue the request
            future = asyncio.Future()
            self.domain_states[domain].queued_requests.append((url, future))
            self.total_urls_queued += 1
            
            if len(self.domain_states[domain].queued_requests) > self.config.max_queue_size_per_domain:
                # Remove oldest request
                old_url, old_future = self.domain_states[domain].queued_requests.popleft()
                old_future.set_exception(Exception("Queue overflow"))
            
            return False
    
    async def release_slot(self, url: str, success: bool = True, 
                          status_code: Optional[int] = None,
                          retry_after: Optional[int] = None):
        """Release a slot after request completion."""
        domain = self.get_domain(url)
        
        async with self._lock:
            state = self.domain_states[domain]
            state.active_connections -= 1
            self.global_active -= 1
            state.total_requests += 1
            
            if state.active_connections == 0:
                self.active_domains.discard(domain)
            
            # Update error tracking
            if not success or (status_code and status_code >= 400):
                state.consecutive_errors += 1
                state.total_errors += 1
                
                # Handle specific error codes
                if status_code == 429:
                    state.last_429_time = time.time()
                    if retry_after and self.config.retry_after_respect:
                        state.retry_after = retry_after
                        state.backoff_until = time.time() + retry_after
                    else:
                        await self._apply_backoff(domain)
                elif status_code and status_code >= 500:
                    await self._apply_backoff(domain)
                elif state.consecutive_errors >= self.config.error_threshold_for_backoff:
                    await self._apply_backoff(domain)
            else:
                # Reset on success
                state.consecutive_errors = 0
                if state.backoff_until and time.time() > state.backoff_until:
                    state.backoff_until = None
            
            # Update completion tracking
            self.total_urls_completed += 1
            
            # Process queued requests
            await self._process_queue(domain)
    
    async def _apply_backoff(self, domain: str):
        """Apply backoff strategy to a domain."""
        state = self.domain_states[domain]
        
        if self.config.backoff_strategy == BackoffStrategy.NONE:
            return
        
        if self.config.backoff_strategy == BackoffStrategy.LINEAR:
            backoff_time = self.config.initial_backoff * state.consecutive_errors
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            backoff_time = self.config.initial_backoff * (
                self.config.backoff_multiplier ** (state.consecutive_errors - 1)
            )
        elif self.config.backoff_strategy == BackoffStrategy.FIBONACCI:
            # Fibonacci sequence for backoff
            fib = [self.config.initial_backoff, self.config.initial_backoff]
            for i in range(2, state.consecutive_errors + 1):
                fib.append(fib[-1] + fib[-2])
            backoff_time = fib[-1]
        else:
            backoff_time = self.config.initial_backoff
        
        # Apply max backoff limit
        backoff_time = min(backoff_time, self.config.max_backoff)
        
        # Apply polite mode multiplier
        if self.config.polite_mode:
            backoff_time *= self.config.polite_delay_multiplier
        
        state.backoff_until = time.time() + backoff_time
        
        logger.info(f"Applying {backoff_time:.1f}s backoff to domain {domain} "
                   f"after {state.consecutive_errors} consecutive errors")
    
    async def _process_queue(self, domain: str):
        """Process queued requests for a domain."""
        state = self.domain_states[domain]
        
        while state.queued_requests:
            can_proceed, _ = await self.can_make_request(domain)
            if not can_proceed:
                break
            
            url, future = state.queued_requests.popleft()
            state.active_connections += 1
            self.global_active += 1
            self.active_domains.add(domain)
            future.set_result(True)
    
    async def make_request(self, url: str, headers: Optional[Dict[str, str]] = None,
                          **kwargs) -> Optional[aiohttp.ClientResponse]:
        """
        Make an HTTP request with concurrent control.
        
        Args:
            url: URL to request
            headers: Optional headers
            **kwargs: Additional arguments for aiohttp request
            
        Returns:
            Response object or None on failure
        """
        # Wait for unpause
        await self._pause_event.wait()
        
        # Acquire slot
        acquired = await self.acquire_slot(url)
        if not acquired:
            # Wait for queue
            future = asyncio.Future()
            domain = self.get_domain(url)
            self.domain_states[domain].queued_requests.append((url, future))
            
            try:
                await asyncio.wait_for(future, timeout=self.config.queue_timeout)
            except asyncio.TimeoutError:
                logger.error(f"Queue timeout for URL: {url}")
                return None
        
        # Make request
        success = False
        status_code = None
        retry_after = None
        response = None
        
        try:
            async with self._session.get(url, headers=headers, **kwargs) as resp:
                status_code = resp.status
                success = resp.status < 400
                
                # Check for Retry-After header
                if resp.status == 429 or resp.status >= 500:
                    retry_after_header = resp.headers.get('Retry-After')
                    if retry_after_header:
                        try:
                            retry_after = int(retry_after_header)
                        except ValueError:
                            # Parse HTTP date
                            pass
                
                response = resp
                
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for URL: {url}")
        except ClientError as e:
            logger.error(f"Request error for URL {url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for URL {url}: {e}")
        finally:
            await self.release_slot(url, success, status_code, retry_after)
        
        return response
    
    def pause(self):
        """Pause all request processing."""
        self._pause_event.clear()
        logger.info("Request processing paused")
    
    def resume(self):
        """Resume request processing."""
        self._pause_event.set()
        logger.info("Request processing resumed")
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get progress information.
        
        Returns:
            Dictionary with progress metrics
        """
        elapsed = time.time() - self.start_time
        rate = self.total_urls_completed / elapsed if elapsed > 0 else 0
        
        # Calculate domain statistics
        active_domain_count = len(self.active_domains)
        backoff_domains = sum(1 for state in self.domain_states.values() 
                            if state.backoff_until and time.time() < state.backoff_until)
        
        # Estimate time remaining
        queued = sum(len(state.queued_requests) for state in self.domain_states.values())
        eta_seconds = queued / rate if rate > 0 else None
        
        return {
            'total_queued': self.total_urls_queued,
            'total_completed': self.total_urls_completed,
            'currently_active': self.global_active,
            'active_domains': active_domain_count,
            'domains_in_backoff': backoff_domains,
            'requests_per_second': rate,
            'elapsed_seconds': elapsed,
            'eta_seconds': eta_seconds,
            'queued_requests': queued,
            'is_paused': not self._pause_event.is_set()
        }
    
    def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        """Get statistics for a specific domain."""
        state = self.domain_states.get(domain)
        if not state:
            return {}
        
        return {
            'active_connections': state.active_connections,
            'queued_requests': len(state.queued_requests),
            'total_requests': state.total_requests,
            'total_errors': state.total_errors,
            'consecutive_errors': state.consecutive_errors,
            'in_backoff': bool(state.backoff_until and time.time() < state.backoff_until),
            'backoff_remaining': max(0, (state.backoff_until - time.time()) 
                                   if state.backoff_until else 0)
        }
    
    async def wait_for_completion(self):
        """Wait for all active and queued requests to complete."""
        while self.global_active > 0 or any(state.queued_requests 
                                          for state in self.domain_states.values()):
            await asyncio.sleep(0.1)
    
    def reset_domain(self, domain: str):
        """Reset error state for a domain."""
        if domain in self.domain_states:
            state = self.domain_states[domain]
            state.consecutive_errors = 0
            state.backoff_until = None
            logger.info(f"Reset error state for domain: {domain}")