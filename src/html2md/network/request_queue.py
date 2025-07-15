"""
Request queue management for concurrent crawling.

This module provides a synchronous interface to the async concurrent controller,
allowing integration with the existing synchronous crawler.
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue, Empty, Full
from typing import Dict, Optional, Tuple, Any, Callable
from urllib.parse import urlparse

from html2md.network.concurrent_controller import (
    ConcurrentController, ConcurrentConfig, BackoffStrategy
)

logger = logging.getLogger("html2md")


@dataclass
class RequestResult:
    """Result of a queued request."""
    url: str
    success: bool
    status_code: Optional[int] = None
    content: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None


class RequestQueue:
    """
    Synchronous interface for concurrent request management.
    
    This class bridges the async concurrent controller with the synchronous crawler.
    """
    
    def __init__(self, config: Optional[ConcurrentConfig] = None, 
                 request_handler: Optional[Callable] = None):
        """
        Initialize the request queue.
        
        Args:
            config: Concurrent configuration
            request_handler: Function to make HTTP requests (defaults to fetch_html)
        """
        self.config = config or ConcurrentConfig()
        self.request_handler = request_handler
        
        # Thread management
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._controller: Optional[ConcurrentController] = None
        self._thread: Optional[threading.Thread] = None
        self._shutdown = False
        
        # Request/response queues
        self._request_queue: Queue[Tuple[str, Dict[str, Any], asyncio.Future]] = Queue()
        self._result_queue: Queue[RequestResult] = Queue()
        
        # Start the async event loop in a separate thread
        self._start_event_loop()
    
    def _start_event_loop(self):
        """Start the async event loop in a separate thread."""
        def run_loop():
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            
            # Create controller
            self._controller = ConcurrentController(self.config)
            
            # Run the loop
            self._event_loop.run_until_complete(self._process_requests())
        
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        
        # Wait for initialization
        while self._event_loop is None or self._controller is None:
            time.sleep(0.01)
    
    async def _process_requests(self):
        """Process requests from the queue asynchronously."""
        async with self._controller:
            tasks = []
            
            while not self._shutdown:
                try:
                    # Check for new requests
                    try:
                        url, kwargs, future = self._request_queue.get_nowait()
                        task = asyncio.create_task(self._make_request(url, **kwargs))
                        tasks.append(task)
                    except Empty:
                        pass
                    
                    # Clean up completed tasks
                    if tasks:
                        done, pending = await asyncio.wait(
                            tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                        )
                        tasks = list(pending)
                        
                        # Process completed tasks
                        for task in done:
                            try:
                                result = await task
                                self._result_queue.put(result)
                            except Exception as e:
                                logger.error(f"Task error: {e}")
                    else:
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Request processing error: {e}")
            
            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _make_request(self, url: str, **kwargs) -> RequestResult:
        """Make a request using the concurrent controller."""
        result = RequestResult(url=url, success=False)
        
        try:
            # Use the request handler if provided
            if self.request_handler:
                # Synchronous request handler - run in executor
                loop = asyncio.get_event_loop()
                response_data = await loop.run_in_executor(
                    None, self.request_handler, url, kwargs.get('session'), 
                    kwargs.get('headers')
                )
                
                if response_data:
                    result.success = True
                    result.content = response_data
                    result.status_code = 200  # Assume success
                else:
                    result.success = False
                    result.error = "No content returned"
            else:
                # Use async controller directly
                headers = kwargs.get('headers')
                response = await self._controller.make_request(url, headers=headers)
                
                if response:
                    result.success = response.status < 400
                    result.status_code = response.status
                    result.content = await response.text()
                    result.headers = dict(response.headers)
                    
                    # Check for retry-after
                    if response.status == 429:
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                result.retry_after = int(retry_after)
                            except ValueError:
                                pass
                else:
                    result.success = False
                    result.error = "Request failed"
                    
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"Request error for {url}: {e}")
        
        return result
    
    def add_request(self, url: str, session=None, headers=None, 
                   timeout: Optional[float] = None) -> Optional[RequestResult]:
        """
        Add a request to the queue and wait for result.
        
        Args:
            url: URL to request
            session: Session object (for compatibility)
            headers: Request headers
            timeout: Maximum time to wait for result
            
        Returns:
            RequestResult or None on timeout
        """
        # Create future for tracking
        future = asyncio.Future()
        
        # Add to queue
        kwargs = {
            'session': session,
            'headers': headers
        }
        
        try:
            self._request_queue.put((url, kwargs, future), timeout=1.0)
        except Full:
            logger.error(f"Request queue full, dropping request for {url}")
            return None
        
        # Wait for result
        start_time = time.time()
        timeout = timeout or self.config.queue_timeout
        
        while True:
            try:
                # Check result queue
                result = self._result_queue.get(timeout=0.1)
                if result.url == url:
                    return result
                else:
                    # Put back for other waiters
                    self._result_queue.put(result)
            except Empty:
                pass
            
            # Check timeout
            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for result: {url}")
                return None
            
            # Check if still processing
            if self._shutdown:
                return None
    
    def pause(self):
        """Pause request processing."""
        if self._controller:
            # Run in event loop
            future = asyncio.run_coroutine_threadsafe(
                self._pause_async(), self._event_loop
            )
            future.result(timeout=1.0)
    
    async def _pause_async(self):
        """Async pause helper."""
        self._controller.pause()
    
    def resume(self):
        """Resume request processing."""
        if self._controller:
            # Run in event loop
            future = asyncio.run_coroutine_threadsafe(
                self._resume_async(), self._event_loop
            )
            future.result(timeout=1.0)
    
    async def _resume_async(self):
        """Async resume helper."""
        self._controller.resume()
    
    def get_progress(self) -> Dict[str, Any]:
        """Get progress information."""
        if not self._controller:
            return {}
        
        # Run in event loop
        future = asyncio.run_coroutine_threadsafe(
            self._get_progress_async(), self._event_loop
        )
        return future.result(timeout=1.0)
    
    async def _get_progress_async(self) -> Dict[str, Any]:
        """Async progress helper."""
        return self._controller.get_progress()
    
    def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        """Get statistics for a specific domain."""
        if not self._controller:
            return {}
        
        # Run in event loop
        future = asyncio.run_coroutine_threadsafe(
            self._get_domain_stats_async(domain), self._event_loop
        )
        return future.result(timeout=1.0)
    
    async def _get_domain_stats_async(self, domain: str) -> Dict[str, Any]:
        """Async domain stats helper."""
        return self._controller.get_domain_stats(domain)
    
    def reset_domain(self, domain: str):
        """Reset error state for a domain."""
        if self._controller:
            # Run in event loop
            future = asyncio.run_coroutine_threadsafe(
                self._reset_domain_async(domain), self._event_loop
            )
            future.result(timeout=1.0)
    
    async def _reset_domain_async(self, domain: str):
        """Async reset domain helper."""
        self._controller.reset_domain(domain)
    
    def shutdown(self):
        """Shutdown the request queue."""
        self._shutdown = True
        
        # Wait for thread to finish
        if self._thread:
            self._thread.join(timeout=5.0)
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()


def create_polite_queue(max_concurrent: int = 1, 
                       delay_multiplier: float = 2.0) -> RequestQueue:
    """
    Create a request queue with polite settings.
    
    Args:
        max_concurrent: Max concurrent connections per domain
        delay_multiplier: Multiplier for delays and backoffs
        
    Returns:
        RequestQueue configured for polite crawling
    """
    config = ConcurrentConfig(
        polite_mode=True,
        polite_concurrent_limit=max_concurrent,
        polite_delay_multiplier=delay_multiplier,
        max_concurrent_per_domain=max_concurrent,
        max_total_concurrent=max(5, max_concurrent * 3),
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        initial_backoff=2.0,
        max_backoff=600.0,  # 10 minutes
        error_threshold_for_backoff=2,
        retry_after_respect=True
    )
    
    return RequestQueue(config)