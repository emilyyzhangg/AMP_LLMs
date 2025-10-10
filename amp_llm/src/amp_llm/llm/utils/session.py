# ============================================================================
# src/amp_llm/llm/utils/session.py
# ============================================================================
"""
Persistent session manager for Ollama API connections.
"""
import asyncio
import aiohttp
from typing import Optional
from amp_llm.config.logging import get_logger

logger = get_logger(__name__)


class OllamaSessionManager:
    """Manages persistent HTTP session for Ollama API."""
    
    def __init__(self, host: str, port: int = 11434):
        """
        Initialize session manager.
        
        Args:
            host: Ollama host
            port: Ollama port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close_session()
    
    async def start_session(self):
        """Initialize persistent session with keepalive."""
        if self.session and not self.session.closed:
            return
        
        self.connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            limit=100,
            force_close=False,
            enable_cleanup_closed=True,
            keepalive_timeout=300
        )
        
        self.session = aiohttp.ClientSession(connector=self.connector)
        logger.info(f"Started persistent session: {self.base_url}")
    
    async def close_session(self):
        """Close persistent session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed persistent session")
    
    async def is_alive(self) -> bool:
        """Check if session is alive."""
        if not self.session or self.session.closed:
            return False
        
        try:
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except:
            return False
    
    async def send_prompt(
        self,
        model: str,
        prompt: str,
        max_retries: int = 3
    ) -> str:
        """
        Send prompt using persistent session.
        
        Args:
            model: Model name
            prompt: User prompt
            max_retries: Number of retry attempts
            
        Returns:
            Model response
        """
        if not self.session or self.session.closed:
            await self.start_session()
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7}
        }
        
        logger.info(f"Sending {len(prompt)} chars to {model}")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(
                    total=600,
                    connect=30,
                    sock_read=600,
                    sock_connect=30
                )
                
                async with self.session.post(
                    url,
                    json=payload,
                    timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get('response', '')
                        
                        logger.info(f"Received {len(response)} chars")
                        return response
                    else:
                        error_text = await resp.text()
                        logger.error(f"API error {resp.status}: {error_text}")
                        return f"Error: API returned status {resp.status}"
            
            except asyncio.TimeoutError:
                last_error = "Request timed out"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Timeout")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                else:
                    return f"Error: {last_error}"
            
            except aiohttp.ServerDisconnectedError:
                last_error = "Server disconnected"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Disconnected")
                
                if attempt < max_retries - 1:
                    await self.close_session()
                    await asyncio.sleep(2)
                    await self.start_session()
                    continue
                else:
                    return f"Error: {last_error}"
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Send error: {e}", exc_info=True)
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                else:
                    return f"Error: {e}"
        
        return f"Error: {last_error}"