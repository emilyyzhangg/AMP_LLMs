"""
Rate Limiter for NCT API Calls
==============================

Provides token bucket rate limiting and concurrency control for external API calls.
Prevents hitting rate limits on external services like PubMed, ClinicalTrials.gov, etc.

Configuration (via .env):
- NCT_MAX_CONCURRENT_REQUESTS: Maximum simultaneous API calls (default: 3)
- NCT_RATE_LIMIT_PER_SECOND: Requests per second limit (default: 2)
- NCT_BURST_SIZE: Maximum burst of requests (default: 5)
"""

import os
import asyncio
import time
import logging
from pathlib import Path
from typing import Dict, Any
from collections import defaultdict

from dotenv import load_dotenv

# Load .env from current dir and parent
load_dotenv()
_script_dir = Path(__file__).parent.resolve()
_root_env = _script_dir.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

NCT_MAX_CONCURRENT_REQUESTS = int(os.getenv("NCT_MAX_CONCURRENT_REQUESTS", "3"))
NCT_RATE_LIMIT_PER_SECOND = float(os.getenv("NCT_RATE_LIMIT_PER_SECOND", "2"))
NCT_BURST_SIZE = int(os.getenv("NCT_BURST_SIZE", "5"))

# Per-API rate limits (some APIs have stricter limits)
API_RATE_LIMITS = {
    "pubmed": {"rate": 3, "burst": 5},      # NCBI: 3/sec with key, 1/sec without
    "pmc": {"rate": 3, "burst": 5},
    "clinicaltrials": {"rate": 3, "burst": 10},
    "europepmc": {"rate": 5, "burst": 10},
    "semantic_scholar": {"rate": 1, "burst": 3},  # 100 req/5min = ~0.33/sec
    "crossref": {"rate": 10, "burst": 20},  # Polite pool is generous
    "openfda": {"rate": 5, "burst": 10},
    "duckduckgo": {"rate": 1, "burst": 2},  # Be conservative
    "default": {"rate": NCT_RATE_LIMIT_PER_SECOND, "burst": NCT_BURST_SIZE}
}


# =============================================================================
# Token Bucket Rate Limiter
# =============================================================================

class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for API calls.

    Allows bursts of requests up to burst_size, then limits to rate_per_second.
    """

    def __init__(self, rate_per_second: float = 2.0, burst_size: int = 5, name: str = "default"):
        self.rate = rate_per_second
        self.burst_size = burst_size
        self.name = name
        self.tokens = float(burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> bool:
        """
        Acquire a token for making a request.

        Args:
            timeout: Maximum time to wait for a token

        Returns:
            True if token acquired, False if timeout
        """
        start_time = time.monotonic()

        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Replenish tokens
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= 1:
                    self.tokens -= 1
                    return True

                # Calculate wait time
                wait_time = (1 - self.tokens) / self.rate

            # Check timeout
            if time.monotonic() - start_time + wait_time > timeout:
                logger.warning(f"Rate limiter '{self.name}' timeout after {timeout}s")
                return False

            # Wait outside the lock
            await asyncio.sleep(min(wait_time, 0.5))

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the rate limiter."""
        return {
            "name": self.name,
            "tokens": round(self.tokens, 2),
            "rate_per_second": self.rate,
            "burst_size": self.burst_size
        }


# =============================================================================
# Global Rate Limiter Registry
# =============================================================================

class RateLimiterRegistry:
    """
    Registry of rate limiters for different APIs.

    Each API gets its own rate limiter with appropriate limits.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._global_semaphore = asyncio.Semaphore(NCT_MAX_CONCURRENT_REQUESTS)
        self._request_counts = defaultdict(int)
        self._lock = asyncio.Lock()

        logger.info(f"📊 NCT Rate Limiter initialized:")
        logger.info(f"   - Max concurrent: {NCT_MAX_CONCURRENT_REQUESTS}")
        logger.info(f"   - Default rate: {NCT_RATE_LIMIT_PER_SECOND}/s")

    def get_limiter(self, api_name: str) -> TokenBucketRateLimiter:
        """Get or create a rate limiter for an API."""
        api_key = api_name.lower().replace("-", "_").replace(" ", "_")

        if api_key not in self._limiters:
            config = API_RATE_LIMITS.get(api_key, API_RATE_LIMITS["default"])
            self._limiters[api_key] = TokenBucketRateLimiter(
                rate_per_second=config["rate"],
                burst_size=config["burst"],
                name=api_key
            )

        return self._limiters[api_key]

    async def acquire(self, api_name: str, timeout: float = 30.0) -> bool:
        """
        Acquire permission to make an API call.

        This enforces both:
        1. Global concurrent request limit
        2. Per-API rate limit

        Args:
            api_name: Name of the API being called
            timeout: Maximum wait time

        Returns:
            True if permission granted, False if timeout
        """
        # First, acquire global semaphore
        try:
            await asyncio.wait_for(
                self._global_semaphore.acquire(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Global semaphore timeout for {api_name}")
            return False

        # Then, acquire per-API rate limit
        limiter = self.get_limiter(api_name)
        if not await limiter.acquire(timeout):
            self._global_semaphore.release()
            return False

        # Track request
        async with self._lock:
            self._request_counts[api_name] += 1

        return True

    def release(self):
        """Release the global semaphore after request completes."""
        self._global_semaphore.release()

    def get_status(self) -> Dict[str, Any]:
        """Get status of all rate limiters."""
        return {
            "max_concurrent": NCT_MAX_CONCURRENT_REQUESTS,
            "active_requests": NCT_MAX_CONCURRENT_REQUESTS - self._global_semaphore._value,
            "request_counts": dict(self._request_counts),
            "limiters": {
                name: limiter.get_status()
                for name, limiter in self._limiters.items()
            }
        }


# =============================================================================
# Context Manager for Rate-Limited API Calls
# =============================================================================

class RateLimitedAPICall:
    """
    Async context manager for rate-limited API calls.

    Usage:
        async with RateLimitedAPICall("pubmed"):
            # Make API call here
            response = await session.get(url)
    """

    def __init__(self, api_name: str, timeout: float = 30.0):
        self.api_name = api_name
        self.timeout = timeout
        self.registry = get_rate_limiter_registry()
        self._acquired = False

    async def __aenter__(self):
        self._acquired = await self.registry.acquire(self.api_name, self.timeout)
        if not self._acquired:
            raise RateLimitExceeded(f"Rate limit exceeded for {self.api_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._acquired:
            self.registry.release()


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded and timeout occurs."""
    pass


# =============================================================================
# Singleton Accessor
# =============================================================================

_registry_instance: RateLimiterRegistry = None

def get_rate_limiter_registry() -> RateLimiterRegistry:
    """Get the singleton rate limiter registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = RateLimiterRegistry()
    return _registry_instance


def rate_limited(api_name: str, timeout: float = 30.0) -> RateLimitedAPICall:
    """
    Convenience function to create a rate-limited API call context.

    Usage:
        async with rate_limited("pubmed"):
            response = await session.get(url)
    """
    return RateLimitedAPICall(api_name, timeout)
