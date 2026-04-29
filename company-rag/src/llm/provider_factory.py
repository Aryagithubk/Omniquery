"""
LLMProviderFactory — Creates LLM providers from configuration.
"""

from typing import Dict, Any
from src.llm.base_provider import BaseLLMProvider
from src.llm.providers.ollama_provider import OllamaProvider
from src.utils.logger import setup_logger

logger = setup_logger("LLMProviderFactory")


class LLMProviderFactory:
    """Factory to create LLM providers from configuration"""

    _providers = {
        "ollama": OllamaProvider,
    }

    @classmethod
    def create(cls, config: Dict[str, Any]) -> BaseLLMProvider:
        """Create an LLM provider from config"""
        provider_name = config.get("provider", "ollama")

        if provider_name not in cls._providers:
            raise ValueError(
                f"Unknown LLM provider: '{provider_name}'. "
                f"Available: {list(cls._providers.keys())}"
            )

        provider_class = cls._providers[provider_name]
        logger.info(f"Creating LLM provider: {provider_name}")

        return provider_class(
            model=config.get("model", "llama3.2:1b"),
            base_url=config.get("base_url", "http://localhost:11434"),
            temperature=config.get("temperature", 0.1),
            max_tokens=config.get("max_tokens", 512),
        )
