# amp_llm/src/amp_llm/llm/session_manager.py
"""
Enhanced persistent session manager with automatic SSH tunneling.
Combines the best of both old and new implementations.
"""
import asyncio
import aiohttp
from typing import Optional, List
from amp_llm.config.logging import get_logger

logger = get_logger(__name__)


class OllamaSessionManager:
    """
    Manages persistent aiohttp session for Ollama API calls.
    
    Features:
    - Automatic SSH tunnel creation if direct connection fails
    - Connection health checking
    - Smart host switching (direct -> tunnel)
    - Persistent session with keepalive
    - Automatic retry logic
    """
    
    def __init__(self, host: str, port: int = 11434, ssh_connection=None):
        """
        Initialize session manager.
        
        Args:
            host: Remote host IP/hostname
            port: Ollama API port (default: 11434)
            ssh_connection: Optional SSH connection for automatic tunneling
        """
        self.original_host = host
        self.current_host = host
        self.port = port
        self.ssh_connection = ssh_connection
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
        
        # Tunnel management
        self.tunnel_manager = None
        self._using_tunnel = False
    
    @property
    def base_url(self) -> str:
        """Get current base URL."""
        return f"http://{self.current_host}:{self.port}"
    
    async def __aenter__(self):
        """Start persistent session."""
        await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session on exit."""
        await self.close_session()
    
    async def _create_session(self):
        """Create persistent aiohttp session with optimal settings."""
        if self.session and not self.session.closed:
            return
        
        # Create connector with keepalive settings (CRITICAL for stability)
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
    
    async def _test_connection(self) -> bool:
        """Test if Ollama is accessible."""
        try:
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False
    
    async def _create_tunnel(self) -> bool:
        """Create SSH tunnel for Ollama access."""
        if not self.ssh_connection:
            logger.warning("SSH connection not available for tunneling")
            return False
        
        logger.info("Creating SSH tunnel for Ollama access...")
        
        try:
            from amp_llm.llm.tunnel_manager import OllamaTunnelManager
            
            self.tunnel_manager = OllamaTunnelManager(
                self.ssh_connection,
                local_port=self.port,
                remote_port=self.port
            )
            
            if await self.tunnel_manager.create():
                # Switch to localhost
                self.current_host = 'localhost'
                self._using_tunnel = True
                
                logger.info("SSH tunnel established successfully")
                return True
            else:
                logger.error("Failed to create SSH tunnel")
                return False
        
        except Exception as e:
            logger.error(f"Error creating tunnel: {e}", exc_info=True)
            return False
    
    async def start_session(self):
        """
        Initialize persistent session with automatic tunnel fallback.
        
        Connection strategy:
        1. Try direct connection to original_host
        2. If fails and SSH available, create tunnel and use localhost
        3. If both fail, raise ConnectionError
        """
        if self.session and not self.session.closed:
            return  # Already started
        
        # Create session
        await self._create_session()
        
        # Test direct connection
        logger.info(f"Testing connection to {self.base_url}...")
        can_connect = await self._test_connection()
        
        if can_connect:
            logger.info("Direct connection successful")
            return
        
        # Direct connection failed - try SSH tunnel
        logger.warning("Direct connection failed")
        
        if self.ssh_connection:
            logger.info("Attempting SSH tunnel fallback...")
            
            tunnel_created = await self._create_tunnel()
            
            if tunnel_created:
                # Recreate session with new host (localhost)
                await self.session.close()
                await self._create_session()
                
                # Test tunnel connection
                can_connect = await self._test_connection()
                
                if can_connect:
                    logger.info("Connection via SSH tunnel successful")
                    return
                else:
                    raise ConnectionError("Cannot connect even via SSH tunnel")
            else:
                raise ConnectionError("Failed to create SSH tunnel")
        else:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.original_host}:{self.port}. "
                f"Provide SSH connection for automatic tunneling."
            )
    
    async def close_session(self):
        """Close persistent session and cleanup tunnel."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed persistent Ollama session")
        
        if self.tunnel_manager:
            self.tunnel_manager.close()
            self.tunnel_manager = None
    
    async def is_alive(self) -> bool:
        """Check if session is alive and can connect."""
        if not self.session or self.session.closed:
            return False
        
        return await self._test_connection()
    
    async def reconnect(self):
        """Reconnect if connection was lost."""
        logger.info("Reconnecting to Ollama...")
        await self.close_session()
        await self.start_session()
    
    async def list_models(self) -> List[str]:
        """
        List available Ollama models.
        
        Returns:
            List of model names
        """
        if not self.session or self.session.closed:
            await self.start_session()
        
        try:
            async with self.session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m['name'] for m in data.get('models', [])]
                    logger.info(f"Found {len(models)} models")
                    return models
                else:
                    logger.error(f"API returned status {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    async def send_prompt(
        self, 
        model: str, 
        prompt: str, 
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_retries: int = 3
    ) -> str:
        """
        Send prompt using persistent session with retry logic.
        
        Args:
            model: Model name
            prompt: User prompt
            system: Optional system prompt
            temperature: Temperature parameter
            max_retries: Maximum retry attempts
            
        Returns:
            Model response text
        """
        if not self.session or self.session.closed:
            await self.start_session()
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if system:
            payload["system"] = system
        
        logger.info(f"Sending {len(prompt)} characters to {model}")
        print(f"📤 Sending prompt to Ollama...")
        print(f"   Length: {len(prompt)} chars")
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Longer timeout for LLM responses
                timeout = aiohttp.ClientTimeout(
                    total=600,  # 10 minutes total
                    connect=30,  # 30 seconds to connect
                    sock_read=600,  # 10 minutes to read response
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
                last_error = "Request timed out after 10 minutes"
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
                last_error = f"Cannot connect to Ollama at {self.current_host}:{self.port}"
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