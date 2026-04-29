import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config_loader import load_config
from src.ingestion.loader import DocumentLoader
from src.ingestion.chunker import TextChunker
from src.ingestion.embedder import Embedder
from src.vector_db.chroma import VectorStore
from src.utils.logger import setup_logger

logger = setup_logger("IngestionPipeline")

def run_pipeline():
    logger.info("Starting Ingestion Pipeline...")
    
    try:
        config = load_config("config.yaml")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    loader = DocumentLoader(config['paths']['dataset_dir'])
    chunker = TextChunker(
        chunk_size=config['chunking']['chunk_size'],
        chunk_overlap=config['chunking']['chunk_overlap']
    )
    embedder = Embedder(model_name=config['embedding']['model'])
    
    vector_store = VectorStore(
        persist_directory=config['vector_db']['persist_directory'],
        embedding_function=embedder.get_embedding_function()
    )

    logger.info("Loading Documents...")
    docs = loader.load_documents()
    if not docs:
        logger.warning("No documents found.")
        return

    logger.info("Chunking Documents...")
    chunks = chunker.split_documents(docs)

    logger.info("Storing in Vector DB (wiping old data first to prevent duplicates)...")
    vector_store.reset_and_add(chunks)

    logger.info("Ingestion Pipeline Completed Successfully! 🚀")

if __name__ == "__main__":
    run_pipeline()
