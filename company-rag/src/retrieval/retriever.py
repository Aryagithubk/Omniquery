from typing import List, Tuple
from langchain_core.documents import Document
from src.vector_db.chroma import VectorStore
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Minimum relevance score (0.0 - 1.0) a document must have to be considered a RAG hit.
# Below this threshold the query is treated as "not found in docs".
RELEVANCE_THRESHOLD = 0.35

class Retriever:
    def __init__(self, vector_store: VectorStore, top_k: int = 3):
        self.vector_store = vector_store
        self.top_k = top_k

    def retrieve(self, query: str) -> Tuple[List[Document], bool]:
        """
        Retrieves relevant documents for a given query.

        Returns:
            (docs, is_relevant_hit)
            - docs: list of Document objects that scored above the threshold
            - is_relevant_hit: True if at least one document met the relevance threshold
        """
        logger.info(f"Retrieving top {self.top_k} documents for query: {query}")
        db = self.vector_store.get_db()

        # Use scored search so we can apply a relevance threshold
        results_with_scores = db.similarity_search_with_relevance_scores(query, k=self.top_k)

        relevant_docs = []
        for doc, score in results_with_scores:
            logger.info(f"  Doc: '{doc.metadata.get('source', 'unknown')}' | Score: {score:.3f}")
            if score >= RELEVANCE_THRESHOLD:
                relevant_docs.append(doc)

        is_hit = len(relevant_docs) > 0
        logger.info(f"RAG hit: {is_hit} ({len(relevant_docs)} docs above threshold {RELEVANCE_THRESHOLD})")
        return relevant_docs, is_hit

    def format_docs(self, docs: List[Document]) -> str:
        """Formats retrieved documents into a single context string."""
        return "\n\n".join(doc.page_content for doc in docs)
