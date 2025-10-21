"""
Ollama Client
=============

Client for interacting with Ollama API.
"""
import aiohttp
import json
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator
from fastapi import HTTPException

from chat_config import config
from chat_models import ModelInfo

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Override default Ollama URL
        """
        self.base_url = base_url or config.OLLAMA_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        logger.info(f"Ollama client initialized for {self.base_url}")
    
    async def initialize(self):
        """Initialize HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=config.GENERATION_TIMEOUT,
                connect=config.CONNECTION_TIMEOUT
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("Ollama client session initialized")
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Ollama client session closed")
    
    async def check_health(self) -> bool:
        """
        Check if Ollama is running.
        
        Returns:
            True if Ollama is accessible
        """
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                healthy = resp.status == 200
                logger.debug(f"Health check: {'healthy' if healthy else 'unhealthy'}")
                return healthy
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def list_models(self) -> List[ModelInfo]:
        """
        Get list of available models.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            HTTPException: If API call fails
        """
        try:
            async with self.session.get(f"{self.base_url}/api/tags") as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"Ollama API error: {error_text}"
                    )
                
                data = await resp.json()
                models = []
                
                for model_data in data.get("models", []):
                    models.append(ModelInfo(
                        name=model_data["name"],
                        size=model_data.get("size", 0),
                        modified_at=model_data.get("modified_at", ""),
                        digest=model_data.get("digest")
                    ))
                
                logger.info(f"Found {len(models)} models")
                return models
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Failed to connect to Ollama: {str(e)}"
            )
    
    async def generate_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate response from model.
        
        Args:
            model: Model name
            messages: Conversation history in OpenAI format
            temperature: Sampling temperature (0.0-2.0)
            stream: Whether to stream response
            
        Yields:
            Response chunks
            
        Raises:
            HTTPException: If generation fails
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }
        
        logger.info(f"Generating response with {model} (stream={stream})")
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat",
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(
                        status_code=503,
                        detail=f"Ollama generation error: {error_text}"
                    )
                
                if stream:
                    # Stream response line by line
                    async for line in resp.content:
                        if line:
                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError:
                                logger.warning("Failed to decode JSON chunk")
                                continue
                else:
                    # Non-streaming response
                    data = await resp.json()
                    yield data
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Generation error: {str(e)}"
            )
    
    async def verify_model(self, model_name: str) -> bool:
        """
        Verify that a model exists.
        
        Args:
            model_name: Name of model to verify
            
        Returns:
            True if model exists
        """
        try:
            models = await self.list_models()
            model_names = [m.name for m in models]
            exists = model_name in model_names
            
            if not exists:
                logger.warning(f"Model '{model_name}' not found. Available: {model_names}")
            
            return exists
        except Exception as e:
            logger.error(f"Model verification failed: {e}")
            return False