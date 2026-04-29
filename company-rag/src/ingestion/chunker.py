from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class TextChunker:
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """Splits documents into smaller chunks."""
        chunks = self.splitter.split_documents(documents)
        logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks.")
        return chunks
