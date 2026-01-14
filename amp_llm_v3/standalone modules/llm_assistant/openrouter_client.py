"""
OpenRouter Client for Cloud LLM Inference
==========================================

Provides cloud-based LLM inference via OpenRouter API.
Supports Nemotron and other models with tool calling capabilities.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Client for OpenRouter API (cloud LLM inference)"""
    
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    # Model aliases for convenience
    MODELS = {
        "nemotron": "nvidia/nemotron-3-nano-30b-a3b:free",
        "nemotron-free": "nvidia/nemotron-3-nano-30b-a3b:free",
        "nemotron-nano": "nvidia/nemotron-3-nano-30b-a3b:free",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenRouter client.
        
        Args:
            api_key: OpenRouter API key. If not provided, reads from 
                     OPENROUTER_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        
        if not self.api_key:
            logger.warning("⚠️ OPENROUTER_API_KEY not set - cloud inference unavailable")
        else:
            logger.info("✅ OpenRouter client initialized")
    
    def resolve_model(self, model: str) -> str:
        """Resolve model alias to full model name."""
        return self.MODELS.get(model.lower(), model)
    
    async def generate(
        self,
        prompt: str,
        model: str = "nemotron",
        temperature: float = 0.15,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate completion using OpenRouter API.
        
        Args:
            prompt: User prompt
            model: Model name or alias
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            
        Returns:
            Dict with 'content', 'reasoning', 'model', 'usage'
        """
        if not self.api_key:
            return {
                "error": "OPENROUTER_API_KEY not configured",
                "content": ""
            }
        
        model_name = self.resolve_model(model)
        logger.info(f"🤖 OpenRouter: Calling {model_name} (temp={temperature})")
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://amp-llm.local",  # Optional: for analytics
            "X-Title": "AMP LLM Annotation System"     # Optional: for analytics
        }
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"❌ OpenRouter error: {response.status_code} - {error_text}")
                    return {
                        "error": f"HTTP {response.status_code}: {error_text[:200]}",
                        "content": ""
                    }
                
                data = response.json()
                
                # Extract response
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")
                reasoning = message.get("reasoning", "")
                
                # Get usage stats
                usage = data.get("usage", {})
                
                logger.info(f"✅ OpenRouter response: {len(content)} chars, "
                           f"{usage.get('total_tokens', 0)} tokens")
                
                return {
                    "content": content,
                    "reasoning": reasoning,
                    "model": data.get("model", model_name),
                    "usage": usage,
                    "finish_reason": choice.get("finish_reason", "unknown")
                }
                
        except httpx.TimeoutException:
            logger.error("❌ OpenRouter request timed out")
            return {
                "error": "Request timed out (300s)",
                "content": ""
            }
        except Exception as e:
            logger.error(f"❌ OpenRouter error: {e}", exc_info=True)
            return {
                "error": str(e),
                "content": ""
            }
    
    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        model: str = "nemotron",
        temperature: float = 0.15
    ) -> Dict[str, Any]:
        """
        Generate completion with tool calling support.
        
        Args:
            prompt: User prompt
            tools: List of tool definitions (OpenAI format)
            model: Model name or alias
            temperature: Sampling temperature
            
        Returns:
            Dict with response and any tool calls
        """
        if not self.api_key:
            return {
                "error": "OPENROUTER_API_KEY not configured",
                "content": ""
            }
        
        model_name = self.resolve_model(model)
        logger.info(f"🔧 OpenRouter: Tool-enabled call to {model_name}")
        
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "tools": tools
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"❌ OpenRouter error: {response.status_code}")
                    return {
                        "error": f"HTTP {response.status_code}: {error_text[:200]}",
                        "content": ""
                    }
                
                data = response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                
                return {
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                    "model": data.get("model", model_name),
                    "usage": data.get("usage", {}),
                    "finish_reason": choice.get("finish_reason", "unknown")
                }
                
        except Exception as e:
            logger.error(f"❌ OpenRouter tool call error: {e}", exc_info=True)
            return {
                "error": str(e),
                "content": ""
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if OpenRouter API is accessible."""
        if not self.api_key:
            return {
                "status": "unconfigured",
                "error": "OPENROUTER_API_KEY not set"
            }
        
        try:
            # Make a minimal request
            result = await self.generate(
                prompt="Say 'OK'",
                model="nemotron",
                max_tokens=10
            )
            
            if "error" in result:
                return {
                    "status": "error",
                    "error": result["error"]
                }
            
            return {
                "status": "healthy",
                "model": result.get("model"),
                "response": result.get("content", "")[:50]
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


# Global instance for convenience
_client: Optional[OpenRouterClient] = None


def get_openrouter_client() -> OpenRouterClient:
    """Get or create global OpenRouter client instance."""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client