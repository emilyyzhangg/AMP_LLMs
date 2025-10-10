"""
Async rate limiter for API clients.
"""
import asyncio
import time
from collections import deque
from amp_llm.config import get_logger

logger = get_logger(__name__)


class AsyncRateLimiter:
    """
    Token bucket rate limiter for async operations.
    
    Example:
        >>> limiter = AsyncRateLimiter(max_requests=10, time_period=1.0)
        >>> async with limiter:
        ...     await make_api_call()
    """
    
    def __init__(self, max_requests: int, time_period: float):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed in time_period
            time_period: Time period in seconds
        """
        self.max_requests = max_requests
        self.time_period = time_period
        self.requests = deque()
        self._lock = asyncio.Lock()
        
        logger.debug(
            f"Rate limiter initialized: {max_requests} requests per {time_period}s"
        )
    
    async def __aenter__(self):
        """Enter rate limiting context."""
        async with self._lock:
            now = time.time()
            
            # Remove requests outside time window
            while self.requests and now - self.requests[0] > self.time_period:
                self.requests.popleft()
            
            # Wait if at capacity
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_period - (now - self.requests[0])
                if sleep_time > 0:
                    logger.debug(f"Rate limit reached, sleeping {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    # Remove oldest request
                    self.requests.popleft()
            
            # Record this request
            self.requests.append(time.time())
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit rate limiting context."""
        return False
    
    def reset(self):
        """Reset rate limiter state."""
        self.requests.clear()
        logger.debug("Rate limiter reset")