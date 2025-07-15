"""
Tests for concurrent request control and progressive backoff.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock

from html2md.network.concurrent_controller import (
    ConcurrentController, ConcurrentConfig, DomainState, BackoffStrategy
)
from html2md.network.request_queue import RequestQueue, create_polite_queue


class TestConcurrentConfig:
    """Test ConcurrentConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ConcurrentConfig()
        
        assert config.max_concurrent_per_domain == 2
        assert config.max_total_concurrent == 10
        assert config.connection_timeout == 30
        assert config.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert config.initial_backoff == 1.0
        assert config.max_backoff == 300.0
        assert config.polite_mode is False
    
    def test_polite_mode_config(self):
        """Test polite mode configuration."""
        config = ConcurrentConfig(
            polite_mode=True,
            polite_concurrent_limit=1,
            polite_delay_multiplier=2.0
        )
        
        assert config.polite_mode is True
        assert config.polite_concurrent_limit == 1
        assert config.polite_delay_multiplier == 2.0


class TestConcurrentController:
    """Test ConcurrentController functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_request_limiting(self):
        """Test basic per-domain concurrent request limiting."""
        config = ConcurrentConfig(max_concurrent_per_domain=2)
        controller = ConcurrentController(config)
        
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        url3 = "https://example.com/page3"
        
        # First two should be allowed
        can1, wait1 = await controller.can_make_request(url1)
        assert can1 is True
        assert wait1 is None
        
        acquired1 = await controller.acquire_slot(url1)
        assert acquired1 is True
        
        can2, wait2 = await controller.can_make_request(url2)
        assert can2 is True
        
        acquired2 = await controller.acquire_slot(url2)
        assert acquired2 is True
        
        # Third should be blocked
        can3, wait3 = await controller.can_make_request(url3)
        assert can3 is False
        assert wait3 is None
        
        # Verify domain state
        domain_state = controller.domain_states["example.com"]
        assert domain_state.active_connections == 2
        
        # Release one slot
        await controller.release_slot(url1, success=True)
        
        # Now third should be allowed
        can3_retry, wait3_retry = await controller.can_make_request(url3)
        assert can3_retry is True
    
    @pytest.mark.asyncio
    async def test_global_concurrent_limit(self):
        """Test global concurrent request limit."""
        config = ConcurrentConfig(
            max_concurrent_per_domain=5,
            max_total_concurrent=3
        )
        controller = ConcurrentController(config)
        
        # Different domains
        urls = [
            "https://site1.com/page",
            "https://site2.com/page",
            "https://site3.com/page",
            "https://site4.com/page"
        ]
        
        # First three should succeed
        for i in range(3):
            acquired = await controller.acquire_slot(urls[i])
            assert acquired is True
        
        # Fourth should fail due to global limit
        can4, _ = await controller.can_make_request(urls[3])
        assert can4 is False
        
        assert controller.global_active == 3
    
    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test exponential backoff on errors."""
        config = ConcurrentConfig(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_backoff=1.0,
            backoff_multiplier=2.0,
            max_backoff=10.0,
            error_threshold_for_backoff=2
        )
        controller = ConcurrentController(config)
        
        url = "https://example.com/page"
        
        # First error - no backoff yet
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False, status_code=500)
        
        can1, wait1 = await controller.can_make_request(url)
        assert can1 is True  # No backoff after 1 error
        
        # Second error - should trigger backoff
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False, status_code=500)
        
        can2, wait2 = await controller.can_make_request(url)
        assert can2 is False
        assert wait2 is not None and wait2 > 0
        
        # Verify backoff time is approximately 1 second (initial_backoff)
        domain_state = controller.domain_states["example.com"]
        assert domain_state.backoff_until is not None
        backoff_duration = domain_state.backoff_until - time.time()
        assert 0.8 < backoff_duration < 1.2
    
    @pytest.mark.asyncio
    async def test_429_retry_after_handling(self):
        """Test handling of 429 with Retry-After header."""
        config = ConcurrentConfig(retry_after_respect=True)
        controller = ConcurrentController(config)
        
        url = "https://api.example.com/endpoint"
        
        # Simulate 429 with Retry-After
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False, status_code=429, retry_after=30)
        
        # Should be in backoff for ~30 seconds
        can, wait = await controller.can_make_request(url)
        assert can is False
        assert wait is not None and 29 < wait < 31
        
        domain_state = controller.domain_states["api.example.com"]
        assert domain_state.retry_after == 30
    
    @pytest.mark.asyncio
    async def test_queue_management(self):
        """Test request queue management."""
        config = ConcurrentConfig(
            max_concurrent_per_domain=1,
            max_queue_size_per_domain=3
        )
        controller = ConcurrentController(config)
        
        base_url = "https://example.com/page"
        
        # First request takes the slot
        acquired1 = await controller.acquire_slot(f"{base_url}1")
        assert acquired1 is True
        
        # Next 3 should be queued
        for i in range(2, 5):
            acquired = await controller.acquire_slot(f"{base_url}{i}")
            assert acquired is False
        
        domain_state = controller.domain_states["example.com"]
        assert len(domain_state.queued_requests) == 3
        
        # Fourth should trigger queue overflow
        acquired5 = await controller.acquire_slot(f"{base_url}5")
        assert acquired5 is False
        assert len(domain_state.queued_requests) == 3  # Still 3, oldest dropped
    
    @pytest.mark.asyncio
    async def test_pause_resume(self):
        """Test pause and resume functionality."""
        config = ConcurrentConfig()
        controller = ConcurrentController(config)
        
        # Pause controller
        controller.pause()
        assert not controller._pause_event.is_set()
        
        # Resume controller
        controller.resume()
        assert controller._pause_event.is_set()
    
    @pytest.mark.asyncio
    async def test_progress_tracking(self):
        """Test progress tracking."""
        config = ConcurrentConfig(enable_progress_tracking=True)
        controller = ConcurrentController(config)
        
        # Make some requests
        urls = ["https://example.com/page1", "https://example.com/page2"]
        
        for url in urls:
            await controller.acquire_slot(url)
            await controller.release_slot(url, success=True)
        
        progress = controller.get_progress()
        
        assert progress['total_completed'] == 2
        assert progress['currently_active'] == 0
        assert progress['requests_per_second'] > 0
        assert progress['is_paused'] is False
    
    @pytest.mark.asyncio
    async def test_domain_reset(self):
        """Test resetting domain error state."""
        config = ConcurrentConfig(error_threshold_for_backoff=1)
        controller = ConcurrentController(config)
        
        url = "https://example.com/page"
        
        # Trigger backoff
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False, status_code=500)
        
        # Should be in backoff
        can1, _ = await controller.can_make_request(url)
        assert can1 is False
        
        # Reset domain
        controller.reset_domain("example.com")
        
        # Should now be allowed
        can2, _ = await controller.can_make_request(url)
        assert can2 is True
    
    @pytest.mark.asyncio
    async def test_polite_mode(self):
        """Test polite mode configuration."""
        controller = ConcurrentController(ConcurrentConfig(polite_mode=True))
        
        # Should have reduced limits
        assert controller.config.max_concurrent_per_domain == controller.config.polite_concurrent_limit
        
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        
        # Only one should be allowed in polite mode
        acquired1 = await controller.acquire_slot(url1)
        assert acquired1 is True
        
        can2, _ = await controller.can_make_request(url2)
        assert can2 is False


class TestRequestQueue:
    """Test RequestQueue synchronous interface."""
    
    def test_basic_queue_operations(self):
        """Test basic queue operations."""
        with RequestQueue() as queue:
            # Queue should be initialized
            assert queue._event_loop is not None
            assert queue._controller is not None
    
    def test_polite_queue_creation(self):
        """Test creating a polite queue."""
        queue = create_polite_queue(max_concurrent=1, delay_multiplier=3.0)
        
        assert queue.config.polite_mode is True
        assert queue.config.polite_concurrent_limit == 1
        assert queue.config.polite_delay_multiplier == 3.0
        
        queue.shutdown()
    
    @patch('html2md.network.request_queue.asyncio.run_coroutine_threadsafe')
    def test_pause_resume(self, mock_run_coro):
        """Test pause/resume through sync interface."""
        mock_future = Mock()
        mock_run_coro.return_value = mock_future
        
        with RequestQueue() as queue:
            queue.pause()
            assert mock_run_coro.called
            
            queue.resume()
            assert mock_run_coro.call_count == 2
    
    @patch('html2md.network.request_queue.asyncio.run_coroutine_threadsafe')
    def test_get_progress(self, mock_run_coro):
        """Test getting progress through sync interface."""
        mock_future = Mock()
        mock_future.result.return_value = {
            'total_completed': 10,
            'currently_active': 2
        }
        mock_run_coro.return_value = mock_future
        
        with RequestQueue() as queue:
            progress = queue.get_progress()
            
            assert progress['total_completed'] == 10
            assert progress['currently_active'] == 2


class TestBackoffStrategies:
    """Test different backoff strategies."""
    
    @pytest.mark.asyncio
    async def test_linear_backoff(self):
        """Test linear backoff strategy."""
        config = ConcurrentConfig(
            backoff_strategy=BackoffStrategy.LINEAR,
            initial_backoff=2.0,
            error_threshold_for_backoff=1
        )
        controller = ConcurrentController(config)
        
        url = "https://example.com/page"
        
        # First error
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False)
        
        # Second error
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False)
        
        # Third error - backoff should be 6 seconds (2.0 * 3)
        await controller.acquire_slot(url)
        await controller.release_slot(url, success=False)
        
        domain_state = controller.domain_states["example.com"]
        backoff_time = domain_state.backoff_until - time.time()
        assert 5.5 < backoff_time < 6.5
    
    @pytest.mark.asyncio
    async def test_fibonacci_backoff(self):
        """Test Fibonacci backoff strategy."""
        config = ConcurrentConfig(
            backoff_strategy=BackoffStrategy.FIBONACCI,
            initial_backoff=1.0,
            error_threshold_for_backoff=1
        )
        controller = ConcurrentController(config)
        
        url = "https://example.com/page"
        
        # Generate errors to test Fibonacci sequence
        expected_backoffs = [1, 1, 2, 3, 5]  # Fibonacci sequence
        
        for i, expected in enumerate(expected_backoffs[:3]):
            await controller.acquire_slot(url)
            await controller.release_slot(url, success=False)
            
            if i == 2:  # After 3rd error
                domain_state = controller.domain_states["example.com"]
                backoff_time = domain_state.backoff_until - time.time()
                # Third Fibonacci number is 2
                assert 1.8 < backoff_time < 2.2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])