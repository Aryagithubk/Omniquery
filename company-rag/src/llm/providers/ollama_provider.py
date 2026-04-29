"""
OllamaProvider — LLM provider implementation for local Ollama models.
"""

import time
from typing import Optional, Dict
from langchain_ollama import OllamaLLM
from src.llm.base_provider import BaseLLMProvider, LLMResponse
from src.utils.logger import setup_logger

logger = setup_logger("OllamaProvider")


class OllamaProvider(BaseLLMProvider):
    """Ollama-based LLM provider for local models"""

    def __init__(
        self,
        model: str = "llama3.2:1b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 512,
    ):
        self.model_name = model
        self.base_url = base_url
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        logger.info(f"Initializing OllamaProvider with model: {model}")
        self.llm = OllamaLLM(
            model=model,
            temperature=temperature,
            base_url=base_url,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
        **kwargs,
    ) -> LLMResponse:
        """Generate a response using Ollama"""
        start = time.time()

        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            result = self.llm.invoke(full_prompt)
            latency = (time.time() - start) * 1000

            return LLMResponse(
                text=result,
                model=self.model_name,
                latency_ms=latency,
                usage={
                    "prompt_tokens": self.count_tokens(full_prompt),
                    "completion_tokens": self.count_tokens(result),
                },
            )
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return LLMResponse(
                text=f"Error: {str(e)}",
                model=self.model_name,
                latency_ms=(time.time() - start) * 1000,
            )
