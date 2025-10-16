# ============================================================================
# src/amp_llm/llm/clients/base.py
# ============================================================================
"""
Abstract base class for LLM clients.
"""
from abc import ABC, abstractmethod
from typing import List, AsyncGenerator


class BaseLLMClient(ABC):
    """Base class for all LLM clients."""
    
    @abstractmethod
    async def list_models(self) -> List[str]:
        """List available models."""
        pass
    
    @abstractmethod
    async def generate(self, model: str, prompt: str) -> str:
        """Generate response from model."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        model: str,
        prompt: str
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response from model."""
        pass
