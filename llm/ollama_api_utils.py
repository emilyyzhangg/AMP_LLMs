"""
Ollama HTTP API utilities for more reliable LLM communication.
Uses Ollama's REST API instead of interactive shell.
"""
import aiohttp
import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()


class OllamaAPIClient:
    """Client for Ollama HTTP API."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=config.llm.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def list_models(self) -> List[str]:
        """List available models via API."""
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                resp.raise_for_status()
                data = await resp.json()
                models = [m['name'] for m in data.get('models', [])]
                logger.info(f"Found {len(models)} models via API")
                return models
        except Exception as e:
            logger.error(f"Error listing models via API: {e}")
            return []
    
    async def generate_stream(
        self, 
        model: str, 
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Generate response with streaming.
        Yields chunks of text as they're generated.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature
            }
        }
        
        if system:
            payload["system"] = system
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as resp:
                resp.raise_for_status()
                
                # Stream response line by line
                async for line in resp.content:
                    if line:
                        try:
                            chunk_data = json.loads(line)
                            if 'response' in chunk_data:
                                yield chunk_data['response']
                            
                            # Check if done
                            if chunk_data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
        
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
    
    async def generate(
        self, 
        model: str, 
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Generate complete response (non-streaming).
        Returns full response text.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        if system:
            payload["system"] = system
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get('response', '')
        
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise


async def setup_ollama_tunnel(ssh, remote_port: int = 11434, local_port: int = 11435):
    """
    Create SSH tunnel to forward Ollama's API from remote to local.
    Uses port 11435 locally to avoid conflicts with local Ollama.
    
    Args:
        ssh: AsyncSSH connection
        remote_port: Port where Ollama runs on remote server (default: 11434)
        local_port: Local port to forward to (default: 11435 to avoid conflicts)
        
    Returns:
        Listener object (keep alive for tunnel to work)
    """
    try:
        logger.info(f"Creating SSH tunnel: localhost:{local_port} -> remote:{remote_port}")
        
        listener = await ssh.forward_local_port(
            '127.0.0.1',
            local_port,
            '127.0.0.1',
            remote_port
        )
        
        logger.info(f"✅ SSH tunnel established on localhost:{local_port}")
        return listener
        
    except Exception as e:
        logger.error(f"Failed to create SSH tunnel: {e}")
        raise


async def list_remote_models_api(ssh) -> List[str]:
    """
    List Ollama models using API over SSH tunnel.
    More reliable than running shell commands.
    """
    listener = None
    try:
        # Create SSH tunnel
        listener = await setup_ollama_tunnel(ssh)
        
        # Give tunnel a moment to establish
        await asyncio.sleep(1)
        
        # Query via API - use port 11435 locally
        async with OllamaAPIClient(base_url="http://localhost:11435") as client:
            models = await client.list_models()
            return models
    
    except Exception as e:
        logger.error(f"Error listing models via API: {e}")
        return []
    
    finally:
        if listener:
            listener.close()
            await asyncio.sleep(0.5)


async def chat_with_ollama(
    ssh,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    stream: bool = True
) -> AsyncGenerator[str, None]:
    """
    Chat with Ollama via API with SSH tunnel.
    
    Args:
        ssh: AsyncSSH connection
        model: Model name
        prompt: User prompt
        system: Optional system prompt
        stream: Whether to stream response
        
    Yields:
        Response chunks (if streaming) or full response
    """
    listener = None
    try:
        # Create SSH tunnel
        listener = await setup_ollama_tunnel(ssh)
        await asyncio.sleep(1)
        
        # Generate response - use port 11435 locally
        async with OllamaAPIClient(base_url="http://localhost:11435") as client:
            if stream:
                async for chunk in client.generate_stream(model, prompt, system):
                    yield chunk
            else:
                response = await client.generate(model, prompt, system)
                yield response
    
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise
    
    finally:
        if listener:
            listener.close()