"""
BaseLLMProvider — Abstract interface for all LLM providers.
Provides a consistent generate() API regardless of backend (Ollama, OpenAI, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Standardized LLM response"""
    text: str
    usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
    model: str = ""
    latency_ms: float = 0.0


class BaseLLMProvider(ABC):
    """Unified interface for all LLM providers"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
        **kwargs,
    ) -> LLMResponse:
        """Generate a response from the LLM"""
        ...

    def count_tokens(self, text: str) -> int:
        """Rough token count (4 chars ≈ 1 token)"""
        return len(text) // 4
