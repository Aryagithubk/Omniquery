import os
from typing import List
from langchain_community.document_loaders import PyPDFLoader, TextLoader, JSONLoader
from langchain_core.documents import Document
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class DocumentLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def load_documents(self) -> List[Document]:
        """Loads documents from the data directory."""
        documents = []
        if not os.path.exists(self.data_dir):
            logger.warning(f"Data directory {self.data_dir} does not exist.")
            return []

        for root, _, files in os.walk(self.data_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    if file.lower().endswith(".pdf"):
                        loader = PyPDFLoader(file_path)
                        documents.extend(loader.load())
                        logger.info(f"Loaded PDF: {file}")
                    elif file.lower().endswith(".txt"):
                        loader = TextLoader(file_path, encoding='utf-8')
                        documents.extend(loader.load())
                        logger.info(f"Loaded TXT: {file}")
                    # Add more loaders as needed
                except Exception as e:
                    logger.error(f"Failed to load {file}: {e}")
        
        return documents
