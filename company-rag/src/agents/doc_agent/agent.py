"""
DocAgent — Document retrieval agent.
Wraps the existing RAG pipeline (loader, chunker, embedder, vector store, retriever)
to answer questions from company documents.
"""

import time
from typing import Any, Dict, List
from src.agents.base_agent import BaseAgent, AgentContext, AgentResponse, AgentStatus
from src.ingestion.embedder import Embedder
from src.vector_db.chroma import VectorStore
from src.utils.logger import setup_logger
from src.config.prompt_loader import PromptLoader

logger = setup_logger("DocAgent")

RELEVANCE_THRESHOLD = 0.35


class DocAgent(BaseAgent):
    """Agent that answers questions from company documents using RAG"""

    def __init__(self, config: Dict[str, Any], llm_provider: Any):
        super().__init__(config, llm_provider)
        self._name = "DocAgent"
        self.vector_store = None
        self.embedder = None
        self.ranker = None
        self.prompt_config = PromptLoader().load_prompt("doc_agent")

    @property
    def description(self) -> str:
        return "Retrieves and answers questions from indexed company documents (PDF, TXT, etc.)"

    @property
    def supported_intents(self) -> List[str]:
        return ["summarization", "explanation", "document_search", "general"]

    async def initialize(self) -> None:
        """Set up the vector store and embedder"""
        try:
            embedding_model = self.config.get("embedding_model", "nomic-embed-text")
            persist_dir = self.config.get("persist_directory", "./vector_store")

            self.embedder = Embedder(model_name=embedding_model)
            self.vector_store = VectorStore(
                persist_directory=persist_dir,
                embedding_function=self.embedder.get_embedding_function()
            )
            
            try:
                from flashrank import Ranker
                # Use a lightweight model for low RAM consumption
                self.ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.flashrank_cache")
                logger.info("DocAgent: Flashrank Reranker initialized.")
            except ImportError:
                self.ranker = None
                logger.warning("DocAgent: Flashrank could not be imported. Reranking disabled.")

            self._status = AgentStatus.READY
            logger.info("DocAgent initialized — vector store ready.")
        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error(f"DocAgent init failed: {e}")
            raise

    async def can_handle(self, context: AgentContext) -> float:
        """
        Confidence scoring:
        - High score for document_search intent or doc-related keywords
        - Baseline 0.5 ensures DocAgent is always considered for general queries
        """
        if self._status != AgentStatus.READY:
            return 0.0

        score = 0.5
        query_lower = context.query.lower()

        doc_keywords = [
            "document", "report", "file", "pdf", "policy", "manual",
            "guideline", "procedure", "handbook", "standard", "leave",
            "expense", "onboarding", "company", "rules", "internal",
            "benefit", "benefits", "vacation", "work from home", "wfh",
            "attendance", "code of conduct", "compliance", "regulation",
            "terms", "conditions", "health", "safety", "insurance",
            "holiday", "holidays", "pto", "sick leave", "maternity",
            "paternity", "hr policy", "compensation", "reimbursement",
            "travel policy", "dress code", "company policy",
        ]
        matches = sum(1 for kw in doc_keywords if kw in query_lower)
        if matches >= 3:
            score += 0.4
        elif matches >= 2:
            score += 0.3
        elif matches >= 1:
            score += 0.2

        if context.intent in ["summarization", "explanation", "document_search"]:
            score += 0.2

        # Extra boost if intent is specifically document_search (weighted classifier determined this)
        if context.intent == "document_search":
            score += 0.1

        return min(score, 1.0)

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Retrieve docs and generate answer"""
        start = time.time()
        try:
            # Retrieve more docs to enable reranker filtering
            fetch_k = self.config.get("top_k", 3)
            db = self.vector_store.get_db()

            # If reranker is active, fetch ALL docs in a small corpus so FlashRank
            # has full visibility. For large corpora, cap at top_k * 5.
            if self.ranker:
                total_docs = db._collection.count()
                fetch_k = total_docs if total_docs <= 100 else fetch_k * 5

            scored_results = db.similarity_search_with_relevance_scores(
                context.query, k=fetch_k
            )
            logger.debug(f"DocAgent: fetched {len(scored_results)} chunks from vector store (fetch_k={fetch_k})")

            # Optional Reranking Step
            if self.ranker and scored_results:
                try:
                    from flashrank import RerankRequest
                    passages = [
                        {
                            "id": i,
                            "text": doc.page_content,
                            "meta": {"source": doc.metadata.get("source", "Unknown"), "initial_score": score}
                        }
                        for i, (doc, score) in enumerate(scored_results)
                    ]
                    rank_request = RerankRequest(query=context.query, passages=passages)
                    reranked = self.ranker.rerank(rank_request)
                    
                    # Sort logic matches flashrank returned order, keep best top_k
                    top_docs = reranked[:self.config.get("top_k", 3)]
                    
                    # Reconstruct good_docs format (Document, relevance_score)
                    good_docs = []
                    for rt in top_docs:
                        from langchain_core.documents import Document
                        score = rt["score"]
                        # Only drop completely irrelevant docs (score ~ 0)
                        if score >= 0.01:
                            good_docs.append((
                                Document(page_content=rt["text"], metadata=rt["meta"]),
                                score
                            ))
                    logger.debug(f"DocAgent: FlashRank kept {len(good_docs)} docs after filtering")
                except Exception as e:
                    logger.error(f"DocAgent: Reranking failed natively ({e}). Falling back to vector db score.")
                    good_docs = [(doc, score) for doc, score in scored_results if score >= RELEVANCE_THRESHOLD][:self.config.get("top_k", 3)]
            else:
                # Filter by relevance threshold natively
                good_docs = [
                    (doc, score) for doc, score in scored_results
                    if score >= RELEVANCE_THRESHOLD
                ][:self.config.get("top_k", 3)]

            if not good_docs:
                return AgentResponse(
                    success=False,
                    answer=None,
                    confidence=0.0,
                    error="No relevant documents found.",
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Build context from relevant docs
            context_text = "\n\n---\n\n".join(
                [doc.page_content for doc, _ in good_docs]
            )

            system_prompt = self.prompt_config.get("system_prompt", "You are a helpful assistant answering based on company documents. Context: {context_text}. Question: {query}.")
            
            prompt = system_prompt.format(
                context_text=context_text,
                query=context.query,
                user_role=context.user_role
            )

            response = await self.llm.generate(prompt)

            # Build source citations
            sources = []
            for doc, score in good_docs:
                source_path = doc.metadata.get("source", "Unknown")
                sources.append({
                    "agent_name": self.name,
                    "source_type": "document",
                    "source_identifier": source_path,
                    "relevance_score": round(score, 3),
                    "excerpt": doc.page_content[:200] + "...",
                })

            avg_score = sum(s for _, s in good_docs) / len(good_docs)

            return AgentResponse(
                success=True,
                answer=response.text,
                confidence=round(avg_score, 3),
                sources=sources,
                token_usage=response.usage,
                execution_time_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"DocAgent execution error: {e}")
            return AgentResponse(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start) * 1000,
            )
