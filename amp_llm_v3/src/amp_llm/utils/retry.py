# src/amp_llm/utils/retry.py
import asyncio
from functools import wraps
from typing import Type, Tuple

def async_retry(
    max_attempts: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    backoff: float = 2.0
):
    """Decorator for retrying async functions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff ** attempt
                        await asyncio.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator

# Usage:
@async_retry(max_attempts=3, exceptions=(aiohttp.ClientError,))
async def fetch_data(url: str):
    async with session.get(url) as resp:
        return await resp.json()