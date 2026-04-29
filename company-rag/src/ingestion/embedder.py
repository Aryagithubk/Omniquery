from langchain_ollama import OllamaEmbeddings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class Embedder:
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        logger.info(f"Initializing Ollama Embeddings with model: {model_name}")
        self.embeddings = OllamaEmbeddings(
            model=model_name,
            base_url=base_url
        )
    
    def get_embedding_function(self):
        return self.embeddings
