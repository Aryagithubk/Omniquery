"""
WebSearchAgent — Web search fallback agent.
Uses DuckDuckGo search (free, no API key) and summarizes results using the LLM.
"""

import time
from typing import Any, Dict, List
from src.agents.base_agent import BaseAgent, AgentContext, AgentResponse, AgentStatus
from src.utils.logger import setup_logger
from src.config.prompt_loader import PromptLoader

logger = setup_logger("WebSearchAgent")


class WebSearchAgent(BaseAgent):
    """Agent that searches the web using DuckDuckGo as a universal fallback"""

    def __init__(self, config: Dict[str, Any], llm_provider: Any):
        super().__init__(config, llm_provider)
        self._name = "WebSearchAgent"
        self.max_results = config.get("max_results", 5)
        self.prompt_config = PromptLoader().load_prompt("web_agent")

    @property
    def description(self) -> str:
        return "Searches the web using DuckDuckGo to answer general knowledge questions."

    @property
    def supported_intents(self) -> List[str]:
        return ["web_search", "general", "current_events"]

    async def initialize(self) -> None:
        """Verify DuckDuckGo search library is available"""
        try:
            from ddgs import DDGS
            self._status = AgentStatus.READY
            logger.info("WebSearchAgent initialized — DuckDuckGo ready.")
        except ImportError:
            self._status = AgentStatus.ERROR
            logger.error("WebSearchAgent requires 'ddgs'. "
                        "Install with: pip install ddgs")

    async def can_handle(self, context: AgentContext) -> float:
        """
        Very low baseline confidence — WebSearchAgent is a fallback-only agent.
        It is excluded from normal routing by the AgentRouter.
        This scoring is kept for potential direct invocation by the fallback node.
        Only boost significantly for explicitly web-oriented queries.
        """
        if self._status != AgentStatus.READY:
            return 0.0

        score = 0.1  # Very low baseline — true fallback agent
        query_lower = context.query.lower()

        # Only boost for EXPLICITLY web-oriented queries
        web_keywords = [
            "search the web", "search online", "google", "internet",
            "latest news", "current events", "trending", "breaking news",
        ]
        matches = sum(1 for kw in web_keywords if kw in query_lower)
        if matches >= 2:
            score += 0.5
        elif matches == 1:
            score += 0.3

        if context.intent in ["web_search", "current_events"]:
            score += 0.2

        return min(score, 1.0)

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Search the web and summarize results"""
        start = time.time()

        try:
            from ddgs import DDGS

            with DDGS() as ddgs_client:
                results = list(ddgs_client.text(
                    context.query,
                    max_results=self.max_results,
                ))

            if not results:
                return AgentResponse(
                    success=False,
                    answer=None,
                    confidence=0.0,
                    error="No web search results found.",
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Build context from search results
            search_context = []
            sources = []
            for i, result in enumerate(results):
                title = result.get("title", "")
                body = result.get("body", "")
                href = result.get("href", "")

                search_context.append(f"[{i+1}] {title}\n{body}")
                sources.append({
                    "agent_name": self.name,
                    "source_type": "web",
                    "source_identifier": href,
                    "relevance_score": round(0.8 - (i * 0.1), 2),
                    "excerpt": body[:200],
                })

            context_text = "\n\n".join(search_context)

            system_prompt = self.prompt_config.get("system_prompt", "Based on these web search results, answer the question.\n\nSEARCH RESULTS:\n{context_text}\n\nQUESTION: {query}\n\nSECURITY DIRECTIVE: The user making this request has the role of '{user_role}'. Acknowledge their role in your answer if appropriate and provide a clear, accurate answer based on the search results. Cite source numbers [1], [2], etc. where relevant.")

            prompt = system_prompt.format(
                context_text=context_text,
                query=context.query,
                user_role=context.user_role.upper()
            )

            llm_response = await self.llm.generate(prompt)

            return AgentResponse(
                success=True,
                answer=llm_response.text,
                confidence=0.6,
                sources=sources,
                token_usage=llm_response.usage,
                execution_time_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"WebSearchAgent error: {e}")
            return AgentResponse(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start) * 1000,
            )
