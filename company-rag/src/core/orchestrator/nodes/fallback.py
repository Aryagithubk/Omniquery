"""
Fallback node — Handles cases where no agent could answer.
Two-stage fallback:
  1. First, try WebSearchAgent (if available) for a web-based answer
  2. If WebSearchAgent also fails, use LLM general knowledge as last resort
"""

from src.core.orchestrator.state import OmniQueryState
from src.agents.base_agent import AgentContext, AgentStatus
from src.utils.logger import setup_logger

logger = setup_logger("FallbackNode")


def make_fallback_node(llm_provider, agent_registry=None):
    """Factory that creates fallback node with LLM access and optional agent registry"""

    async def fallback_node(state: OmniQueryState) -> dict:
        """Two-stage fallback: WebSearchAgent → LLM general knowledge"""
        query = state["query"]
        user_role = state.get("user_role", "user")
        logger.info(f"Fallback triggered for query: '{query[:80]}...'")

        # ── Stage 1: Try WebSearchAgent ────────────────────────────────────────
        if agent_registry:
            web_agent = agent_registry.get_by_name("WebSearchAgent")
            if web_agent and web_agent._status == AgentStatus.READY:
                logger.info("Fallback Stage 1: Invoking WebSearchAgent...")
                try:
                    context = AgentContext(
                        query=query,
                        original_query=state.get("original_query", query),
                        intent="web_search",
                        session_id=state.get("session_id", ""),
                        user_role=user_role,
                    )
                    result = await web_agent.execute(context)

                    if result.success and result.answer:
                        # Check if the answer is actually useful (not a refusal)
                        answer = result.answer
                        is_refusal = (
                            "cannot confidently answer" in answer.lower()
                            or "cannot answer" in answer.lower()
                            or "no relevant" in answer.lower()
                            or not answer.strip()
                        )

                        if not is_refusal:
                            logger.info("Fallback: WebSearchAgent provided a useful answer.")
                            return {
                                "synthesized_answer": answer,
                                "overall_confidence": round(result.confidence, 3),
                                "final_sources": result.sources,
                                "agents_used": list(state.get("agents_used", [])) + ["WebSearchAgent"],
                            }
                        else:
                            logger.info("Fallback: WebSearchAgent returned a refusal. Proceeding to Stage 2.")
                    else:
                        logger.info(f"Fallback: WebSearchAgent failed: {result.error}. Proceeding to Stage 2.")

                except Exception as e:
                    logger.error(f"Fallback: WebSearchAgent threw exception: {e}. Proceeding to Stage 2.")
            else:
                logger.info("Fallback: WebSearchAgent not available. Proceeding to Stage 2.")

        # ── Stage 2: LLM General Knowledge ─────────────────────────────────────
        logger.info("Fallback Stage 2: Using LLM general knowledge...")
        try:
            prompt = (
                f"You are a helpful assistant. Answer this question using your general knowledge.\n\n"
                f"Question: {query}\n\n"
                f"Answer concisely and accurately."
            )

            response = await llm_provider.generate(prompt)

            disclaimer = (
                "ℹ️ This answer is from general knowledge — "
                "no matching data was found in documents, databases, or configured sources.\n\n"
            )

            return {
                "synthesized_answer": disclaimer + response.text,
                "overall_confidence": 0.2,
                "final_sources": [{
                    "agent_name": "Fallback",
                    "source_type": "general_knowledge",
                    "source_identifier": "LLM General Knowledge",
                    "relevance_score": 0.2,
                }],
                "agents_used": list(state.get("agents_used", [])) + ["Fallback"],
            }

        except Exception as e:
            logger.error(f"Fallback error: {e}")
            return {
                "synthesized_answer": "I was unable to process your question. Please try again.",
                "overall_confidence": 0.0,
                "error": str(e),
            }

    return fallback_node
