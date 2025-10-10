# ============================================================================
# src/amp_llm/llm/clients/ollama_api.py
# ============================================================================
"""
Ollama API client using HTTP interface.
Most reliable method - avoids terminal issues.
"""
import aiohttp
import json
from typing import List, Optional, AsyncGenerator
from amp_llm.config.settings import get_config 
from amp_llm.config.logging import get_logger
from .base import BaseLLMClient

logger = get_logger(__name__)
config = get_config()


class OllamaAPIClient(BaseLLMClient):
    """Ollama client using HTTP API."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        timeout: int = 300
    ):
        """
        Initialize API client.
        
        Args:
            host: Ollama host
            port: Ollama port
            timeout: Request timeout in seconds
        """
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()
    
    async def connect(self):
        """Create persistent session."""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                ttl_dns_cache=300,
                limit=100,
                force_close=False,
                enable_cleanup_closed=True,
                keepalive_timeout=300
            )
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            
            logger.info(f"Connected to Ollama API at {self.base_url}")
    
    async def disconnect(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Disconnected from Ollama API")
    
    async def list_models(self) -> List[str]:
        """List available models via API."""
        await self.connect()
        
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                resp.raise_for_status()
                data = await resp.json()
                models = [m['name'] for m in data.get('models', [])]
                logger.info(f"Found {len(models)} models")
                return models
                
        except aiohttp.ClientConnectorError:
            logger.error(f"Cannot connect to {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7
    ) -> str:
        """
        Generate complete response (non-streaming).
        
        Args:
            model: Model name
            prompt: User prompt
            temperature: Temperature parameter
            
        Returns:
            Complete response text
        """
        await self.connect()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                response = data.get('response', '')
                
                logger.info(f"Generated {len(response)} characters")
                return response
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
            raise
    
    async def generate_stream(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response.
        
        Args:
            model: Model name
            prompt: User prompt
            temperature: Temperature parameter
            
        Yields:
            Response chunks
        """
        await self.connect()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature}
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as resp:
                resp.raise_for_status()
                
                async for line in resp.content:
                    if line:
                        try:
                            chunk_data = json.loads(line)
                            text = chunk_data.get('response', '')
                            
                            if text:
                                yield text
                            
                            if chunk_data.get('done', False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"\nError: {e}"