"""
reset_vector_store.py
---------------------
Clears the ChromaDB vector store and re-runs the ingestion pipeline
from scratch. Use this when you suspect duplicate embeddings.
"""
import os
import sys
import shutil

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from src.config.config_loader import load_config
from src.ingestion.loader import DocumentLoader
from src.ingestion.chunker import TextChunker
from src.ingestion.embedder import Embedder
from src.vector_db.chroma import VectorStore
from src.utils.logger import setup_logger

logger = setup_logger("ResetVectorStore")

def reset_and_reingest():
    config = load_config("config.yaml")
    persist_dir = config['vector_db']['persist_directory']

    # ── Step 1: Wipe the vector store ──────────────────────────────────────
    logger.info(f"Wiping vector store at: {persist_dir}")
    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir)
        logger.info("✅ Vector store wiped successfully.")
    else:
        logger.info("No vector store found — nothing to wipe.")

    # ── Step 2: Re-ingest from scratch ─────────────────────────────────────
    logger.info("Starting fresh ingestion...")

    loader   = DocumentLoader(config['paths']['dataset_dir'])
    chunker  = TextChunker(
        chunk_size=config['chunking']['chunk_size'],
        chunk_overlap=config['chunking']['chunk_overlap']
    )
    embedder = Embedder(model_name=config['embedding']['model'])
    store    = VectorStore(
        persist_directory=persist_dir,
        embedding_function=embedder.get_embedding_function()
    )

    docs   = loader.load_documents()
    chunks = chunker.split_documents(docs)

    logger.info(f"Ingesting {len(chunks)} chunks...")
    store.add_documents(chunks)

    logger.info("✅ Re-ingestion complete — ChromaDB is clean and duplicate-free!")

if __name__ == "__main__":
    reset_and_reingest()
