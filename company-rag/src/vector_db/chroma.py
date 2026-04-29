import os
import shutil
from langchain_chroma import Chroma
from langchain_core.documents import Document
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class VectorStore:
    def __init__(self, persist_directory: str, embedding_function):
        self.persist_directory = persist_directory
        self.embedding_function = embedding_function
        self.db = None

    def get_db(self):
        """Returns the ChromaDB instance."""
        if self.db is None:
            self.db = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embedding_function
            )
        return self.db

    def add_documents(self, documents: list[Document]):
        """Adds documents to the vector store (appends — may cause duplicates on re-run)."""
        db = self.get_db()
        logger.info(f"Adding {len(documents)} documents to Vector DB...")
        db.add_documents(documents)
        logger.info("Documents added successfully.")

    def reset_and_add(self, documents: list[Document]):
        """Wipes the collection then adds documents fresh — safe to call on re-runs."""
        self.clear()          # delete old data
        self.db = None        # force re-init so Chroma recreates the collection
        db = self.get_db()
        logger.info(f"Re-ingesting {len(documents)} documents into a clean Vector DB...")
        db.add_documents(documents)
        logger.info("Documents ingested successfully into a clean store. ✅")

    def clear(self):
        """Clears the vector store."""
        if os.path.exists(self.persist_directory):
            shutil.rmtree(self.persist_directory)
            logger.info(f"Cleared vector store at {self.persist_directory}")
        else:
            logger.info("Vector store not found, nothing to clear.")
