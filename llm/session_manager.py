"""
Persistent session manager for Ollama API calls.
Maintains single aiohttp session throughout entire session.
"""
import asyncio
import aiohttp
from typing import Optional
from config import get_logger

logger = get_logger(__name__)


class OllamaSessionManager:
    """
    Manages persistent aiohttp session for Ollama API calls.
    Keeps connection alive throughout research session.
    """
    
    def __init__(self, host: str, port: int = 11434):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
    
    async def __aenter__(self):
        """Start persistent session."""
        await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session on exit."""
        await self.close_session()
    
    async def start_session(self):
        """Initialize persistent session with keepalive."""
        if self.session and not self.session.closed:
            return  # Already started
        
        # Create connector with keepalive settings
        self.connector = aiohttp.TCPConnector(
            ttl_dns_cache=300,
            limit=100,
            force_close=False,  # CRITICAL: Keep connections alive
            enable_cleanup_closed=True,
            keepalive_timeout=300  # 5 minutes keepalive
        )
        
        # Create session
        self.session = aiohttp.ClientSession(connector=self.connector)
        
        logger.info(f"Started persistent Ollama session: {self.base_url}")
    
    async def close_session(self):
        """Close persistent session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed persistent Ollama session")
    
    async def is_alive(self) -> bool:
        """Check if session is alive."""
        if not self.session or self.session.closed:
            return False
        
        try:
            # Quick health check
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
        Automatically reconnects if needed.
        """
        if not self.session or self.session.closed:
            await self.start_session()
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
            }
        }
        
        logger.info(f"Sending {len(prompt)} characters to {model}")
        print(f"📤 Sending prompt to Ollama...")
        print(f"   Length: {len(prompt)} chars")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Longer timeout for LLM responses (5 minutes)
                timeout = aiohttp.ClientTimeout(
                    total=600,  # 10 minutes total (INCREASED for long LLM requests)
                    connect=30,  # 30 seconds to connect
                    sock_read=600,  # 10 minutes to read response (INCREASED)
                    sock_connect=30  # 30 seconds for socket connection
                )
                
                async with self.session.post(url, json=payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get('response', '')
                        
                        logger.info(f"Received response: {len(response)} characters")
                        print(f"✅ Received response: {len(response)} chars")
                        
                        return response
                    else:
                        error_text = await resp.text()
                        logger.error(f"API error {resp.status}: {error_text}")
                        return f"Error: API returned status {resp.status}"
                        
            except asyncio.TimeoutError:
                last_error = "Request timed out after 5 minutes"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Timeout")
                if attempt < max_retries - 1:
                    print(f"⚠️  Timeout, retrying... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    continue
                else:
                    logger.error(last_error)
                    return f"Error: {last_error}"
                    
            except aiohttp.ServerDisconnectedError:
                last_error = "Server disconnected"
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Server disconnected")
                
                # Try to restart session
                if attempt < max_retries - 1:
                    print(f"⚠️  Connection lost, reconnecting... ({attempt + 1}/{max_retries})")
                    await self.close_session()
                    await asyncio.sleep(2)
                    await self.start_session()
                    continue
                else:
                    logger.error(last_error)
                    return f"Error: {last_error}. Please check if Ollama is still running."
                    
            except aiohttp.ClientConnectorError:
                last_error = f"Cannot connect to Ollama at {self.host}:{self.port}"
                logger.error(last_error)
                
                # Try to restart session
                if attempt < max_retries - 1:
                    print(f"⚠️  Connection error, reconnecting... ({attempt + 1}/{max_retries})")
                    await self.close_session()
                    await asyncio.sleep(2)
                    await self.start_session()
                    continue
                else:
                    return f"Error: {last_error}. Check if SSH tunnel is still active."
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error sending prompt: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    print(f"⚠️  Error occurred, retrying... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(2)
                    continue
                else:
                    return f"Error: {e}"
        
        return f"Error: {last_error}"