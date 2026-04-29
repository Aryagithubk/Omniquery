"""
ConfluenceAgent — Atlassian Confluence knowledge base search agent.
Searches Confluence pages via REST API and summarizes results using the LLM.
"""

import time
import re
from typing import Any, Dict, List, Optional
from src.agents.base_agent import BaseAgent, AgentContext, AgentResponse, AgentStatus
from src.utils.logger import setup_logger
from src.config.prompt_loader import PromptLoader

logger = setup_logger("ConfluenceAgent")


class ConfluenceAgent(BaseAgent):
    """Agent that searches Atlassian Confluence for knowledge base articles"""

    def __init__(self, config: Dict[str, Any], llm_provider: Any):
        super().__init__(config, llm_provider)
        self._name = "ConfluenceAgent"
        self.base_url = config.get("base_url", "")
        self.username = config.get("username", "")
        self.api_token = config.get("api_token", "")
        self.spaces = config.get("spaces", [])
        self.max_results = config.get("max_results", 5)
        self._configured = False
        self.prompt_config = PromptLoader().load_prompt("confluence_agent")

    @property
    def description(self) -> str:
        return "Searches Atlassian Confluence wiki for internal knowledge base articles and documentation."

    @property
    def supported_intents(self) -> List[str]:
        return ["wiki_search", "knowledge_base", "documentation", "general"]

    async def initialize(self) -> None:
        """Check if Confluence credentials are configured"""
        if self.base_url and self.username and self.api_token:
            self._configured = True
            self._status = AgentStatus.READY
            logger.info(f"ConfluenceAgent initialized — connected to {self.base_url}")
        else:
            self._configured = False
            self._status = AgentStatus.DISABLED
            logger.info("ConfluenceAgent disabled — no credentials configured. "
                       "Set confluence.base_url, username, api_token in config.")

    async def can_handle(self, context: AgentContext) -> float:
        """Confidence scoring — boost for wiki-related keywords"""
        if not self._configured or self._status != AgentStatus.READY:
            return 0.0

        score = 0.3
        query_lower = context.query.lower()

        wiki_keywords = [
            "confluence", "wiki", "knowledge base", "documentation",
            "internal doc", "team page", "space", "article",
            "runbook", "playbook", "how to", "howto", "guide",
        ]
        matches = sum(1 for kw in wiki_keywords if kw in query_lower)
        if matches >= 2:
            score += 0.4
        elif matches == 1:
            score += 0.2

        if context.intent in ["wiki_search", "knowledge_base", "documentation"]:
            score += 0.2

        return min(score, 1.0)

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Search Confluence and summarize results"""
        start = time.time()

        if not self._configured:
            return AgentResponse(
                success=False,
                error="ConfluenceAgent is not configured. Set credentials in config.yaml.",
                execution_time_ms=(time.time() - start) * 1000,
            )

        try:
            import requests
            from requests.auth import HTTPBasicAuth

            # Build CQL search query
            cql_query = f'text ~ "{context.query}"'
            if self.spaces:
                space_filter = " OR ".join([f'space = "{s}"' for s in self.spaces])
                cql_query = f"({cql_query}) AND ({space_filter})"

            url = f"{self.base_url.rstrip('/')}/rest/api/content/search"
            params = {
                "cql": cql_query,
                "limit": self.max_results,
                "expand": "body.view,space,version",
            }

            response = requests.get(
                url,
                params=params,
                auth=HTTPBasicAuth(self.username, self.api_token),
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                return AgentResponse(
                    success=False,
                    answer=None,
                    confidence=0.0,
                    error="No Confluence pages found matching the query.",
                    execution_time_ms=(time.time() - start) * 1000,
                )

            # Extract content from pages
            pages_text = []
            sources = []
            for page in results:
                title = page.get("title", "Untitled")
                space_key = page.get("space", {}).get("key", "")
                body_html = page.get("body", {}).get("view", {}).get("value", "")
                body_text = self._strip_html(body_html)[:1500]  # Limit context
                page_url = f"{self.base_url.rstrip('/')}{page.get('_links', {}).get('webui', '')}"

                pages_text.append(f"## {title} (Space: {space_key})\n{body_text}")
                sources.append({
                    "agent_name": self.name,
                    "source_type": "confluence",
                    "source_identifier": page_url,
                    "relevance_score": 0.7,
                    "excerpt": body_text[:200] + "...",
                })

            # Summarize with LLM
            context_text = "\n\n---\n\n".join(pages_text)
            
            system_prompt = self.prompt_config.get("system_prompt", "Based on these Confluence wiki pages, answer the question.\n\nPAGES:\n{context_text}\n\nQUESTION: {query}\n\nSECURITY DIRECTIVE: The user making this request has the role of '{user_role}'. If the pages are internal department or technical specs, only 'admin' or 'superadmin' can view them. If the pages are executive roadmaps, only 'superadmin' can view them. If the user does not have adequate permissions, refuse the query by stating 'You do not have authorization to view these Wiki pages.'\n\nAnswer concisely based on the information in the pages.")
            
            prompt = system_prompt.format(
                context_text=context_text,
                query=context.query,
                user_role=context.user_role
            )

            llm_response = await self.llm.generate(prompt)

            return AgentResponse(
                success=True,
                answer=llm_response.text,
                confidence=0.75,
                sources=sources,
                token_usage=llm_response.usage,
                execution_time_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"ConfluenceAgent error: {e}")
            return AgentResponse(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start) * 1000,
            )

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags from string using BeautifulSoup"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ")
            clean = re.sub(r"\s+", " ", text)
            return clean.strip()
        except ImportError:
            # Fallback if beautifulsoup is somehow not installed
            clean = re.sub(r"<[^>]+>", " ", html)
            clean = re.sub(r"\s+", " ", clean)
            return clean.strip()
