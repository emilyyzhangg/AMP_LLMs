"""
Abstract base class for all API clients.
Ensures consistent interface across all data sources.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio
import aiohttp
from dataclasses import dataclass

from amp_llm.config import get_logger

logger = get_logger(__name__)


@dataclass
class APIConfig:
    """Configuration for API clients."""
    timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 0.34
    max_results: int = 10
    api_key: Optional[str] = None


class BaseAPIClient(ABC):
    """
    Abstract base class for all API clients.
    
    Provides:
    - Consistent interface
    - Built-in retry logic
    - Rate limiting
    - Error handling
    """
    
    def __init__(self, config: Optional[APIConfig] = None):
        self.config = config or APIConfig()
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
    
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
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        
        if elapsed < self.config.rate_limit_delay:
            await asyncio.sleep(self.config.rate_limit_delay - elapsed)
        
        self._last_request_time = time.time()
    
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
        await self._ensure_session()
        await self._rate_limit()
        
        for attempt in range(self.config.max_retries):
            try:
                async with self.session.request(method, url, **kwargs) as resp:
                    resp.raise_for_status()
                    return resp
            
            except aiohttp.ClientError as e:
                if attempt == self.config.max_retries - 1:
                    logger.error(f"{self.name} request failed after {self.config.max_retries} attempts: {e}")
                    raise
                
                logger.warning(f"{self.name} request failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    async def close(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    # Subclasses must implement these:
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search API with query."""
        pass
    
    @abstractmethod
    async def fetch_by_id(self, id: str, **kwargs) -> Dict[str, Any]:
        """Fetch specific resource by ID."""
        pass