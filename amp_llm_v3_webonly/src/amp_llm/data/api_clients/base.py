"""
Abstract base class for all API clients.
FIXED: Added async context manager support and proper rate limiting.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio
import aiohttp
from dataclasses import dataclass

from amp_llm.config import get_logger, get_config
from .rate_limiter import AsyncRateLimiter

logger = get_logger(__name__)


@dataclass
class APIConfig:
    """Configuration for API clients."""
    timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 0.34
    max_results: int = 10
    api_key: Optional[str] = None
    rate_limit_requests: int = 10
    rate_limit_period: float = 1.0


class BaseAPIClient(ABC):
    """
    Abstract base class for all API clients.
    
    Provides:
    - Consistent interface
    - Built-in retry logic
    - Rate limiting
    - Error handling
    - Async context manager support
    """
    
    def __init__(self, config: Optional[APIConfig] = None):
        # Use provided config or create from global AppConfig
        if config is None:
            try:
                app_config = get_config()
                config = APIConfig(
                    timeout=app_config.api.timeout,
                    max_retries=app_config.api.max_retries,
                    rate_limit_delay=app_config.api.rate_limit_delay,
                    max_results=app_config.api.max_results,  # ✅ Now reads from config
                    rate_limit_requests=app_config.api.rate_limit_requests,
                    rate_limit_period=app_config.api.rate_limit_period,
                )
            except Exception as e:
                logger.warning(f"Could not load from global config: {e}, using defaults")
                config = APIConfig()  # Use all defaults
        
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
        
        # Initialize rate limiter from config
        self.rate_limiter = AsyncRateLimiter(
            max_requests=self.config.rate_limit_requests,
            time_period=self.config.rate_limit_period
        )
        
        logger.debug(
            f"Initialized API client with rate limit: "
            f"{self.config.rate_limit_requests} req/{self.config.rate_limit_period}s"
        )
    
    # =========================================================================
    # ASYNC CONTEXT MANAGER SUPPORT
    # =========================================================================
    
    async def __aenter__(self):
        """Enter async context - ensure session is created."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - close session."""
        await self.close()
        return False  # Don't suppress exceptions
    
    # =========================================================================
    # ABSTRACT PROPERTIES
    # =========================================================================
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Client name for logging."""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for API."""
        pass
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
            logger.debug(f"{self.name}: Created new session")
    
    async def close(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug(f"{self.name}: Closed session")
    
    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    
    async def _rate_limit(self):
        """Enforce simple delay-based rate limiting."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        
        if elapsed < self.config.rate_limit_delay:
            await asyncio.sleep(self.config.rate_limit_delay - elapsed)
        
        self._last_request_time = time.time()
    
    # =========================================================================
    # HTTP REQUEST WITH RETRY
    # =========================================================================
    
    async def _request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Make HTTP request with retry logic and rate limiting.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL
            **kwargs: Additional arguments for request
            
        Returns:
            Response object
        """
        # Use token bucket rate limiter
        async with self.rate_limiter:
            await self._ensure_session()
            # Also apply simple delay (belt and suspenders approach)
            await self._rate_limit()
        
            for attempt in range(self.config.max_retries):
                try:
                    response = await self.session.request(method, url, **kwargs)
                    response.raise_for_status()
                    return response
                
                except aiohttp.ClientError as e:
                    if attempt == self.config.max_retries - 1:
                        logger.error(
                            f"{self.name} request failed after {self.config.max_retries} attempts: {e}"
                        )
                        raise
                    
                    logger.warning(f"{self.name} request failed (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
            # Should never reach here due to raise in loop
            raise RuntimeError(f"{self.name}: Request failed after all retries")
    
    # =========================================================================
    # ABSTRACT METHODS - Subclasses must implement
    # =========================================================================
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search API with query."""
        pass
    
    @abstractmethod
    async def fetch_by_id(self, id: str, **kwargs) -> Dict[str, Any]:
        """Fetch specific resource by ID."""
        pass