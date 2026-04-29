from langchain_ollama import OllamaLLM
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class OllamaClient:
    def __init__(self, model_name: str, temperature: float = 0.1, base_url: str = "http://localhost:11434"):
        logger.info(f"Initializing Ollama LLM with model: {model_name}")
        self.llm = OllamaLLM(
            model=model_name,
            temperature=temperature,
            base_url=base_url
        )

    def generate(self, prompt: str) -> str:
        """Generates a response from the LLM."""
        try:
            return self.llm.invoke(prompt)
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return "I'm sorry, I encountered an error while processing your request."
