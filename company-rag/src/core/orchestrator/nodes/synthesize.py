"""
Synthesize node — merges results from all agents into a single answer.
Prioritizes results based on the classified intent:
  - data_query → prefer DBAgent results
  - document_search → prefer DocAgent results
Uses dynamic confidence from actual agent results instead of hardcoded values.
"""

from src.core.orchestrator.state import OmniQueryState
from src.utils.logger import setup_logger

logger = setup_logger("SynthesizeNode")

# Maps intent to the agent that should be preferred for that intent
_INTENT_AGENT_PRIORITY = {
    "data_query": "DBAgent",
    "document_search": "DocAgent",
    "summarization": "DocAgent",
    "wiki_search": "ConfluenceAgent",
    "web_search": "WebSearchAgent",
    "general": None,  # No preference — use highest confidence
}


def make_synthesize_node(llm_provider):
    """Factory that creates synthesize node with access to LLM"""

    async def synthesize_node(state: OmniQueryState) -> dict:
        """Synthesize results from all agents into a coherent answer"""
        results = state.get("agent_results", [])
        agents_used = state.get("agents_used", [])
        intent = state.get("intent", "general")

        # ── RBAC SHORT-CIRCUIT ────────────────────────────────────────────────
        # When classify detected a permission violation, no agents ran.
        # Return the denial message directly without LLM involvement.
        if state.get("db_intent") == "permission_denied":
            denial_msg = state.get(
                "db_permission_denied_reason",
                "⛔ **Permission Denied**: You do not have access to perform this database operation."
            )
            logger.info("Synthesize: returning RBAC permission-denied message (no LLM call).")
            return {
                "synthesized_answer": denial_msg,
                "overall_confidence": 1.0,   # We are 100% sure of the denial
                "final_sources": [{
                    "agent_name": "RBACGuard",
                    "source_type": "access_control",
                    "source_identifier": "Role-Based Access Control",
                    "relevance_score": 1.0,
                    "excerpt": "Operation blocked by RBAC policy at classify stage.",
                }],
                "agents_used": [],
            }
        # ─────────────────────────────────────────────────────────────────────

        if not results:
            return {
                "synthesized_answer": "I couldn't find a good answer from any of my data sources. "
                                      "Please try rephrasing your question.",
                "overall_confidence": 0.0,
                "final_sources": [],
            }


        # Separate results by agent and filter refusals
        try:
            categorized = {}  # agent_name -> list of results
            refusals = []

            # Signals that indicate a DB "no data" response (not a real answer)
            _db_no_data_signals = [
                "no matching", "no data found", "no results",
                "could not determine", "i couldn't find", "i could not find",
                "not available", "cannot retrieve", "unable to retrieve",
            ]

            for r in results:
                answer = r.get("answer", "")
                agent_name = r.get("metadata", {}).get("agent", "Unknown")
                answer_lower = (answer or "").lower()

                # A result is a refusal only if the answer is empty/blank.
                # Agent success/failure is already controlled by result.success in execute.py.
                # We do NOT string-match phrases here — that silences legitimate answers.
                is_refusal = (
                    not answer
                    or answer.strip() == ""
                    or "I can't answer" in answer
                )

                # Defence-in-depth: if DBAgent returned a "no data" response
                # for a non-database intent, treat it as a refusal so the
                # fallback chain can escalate to WebSearchAgent.
                if (
                    not is_refusal
                    and agent_name == "DBAgent"
                    and intent not in ("data_query", "analytics", "reporting", "database", "db_mutation")
                    and any(sig in answer_lower for sig in _db_no_data_signals)
                ):
                    logger.info(
                        f"Synthesize: DBAgent returned no-data for intent='{intent}' — "
                        "treating as refusal (not a DB query)."
                    )
                    is_refusal = True

                if is_refusal:
                    refusals.append(r)
                    continue  # Drop refusals

                if agent_name not in categorized:
                    categorized[agent_name] = []
                categorized[agent_name].append(r)

            # If all results were refusals, no good answer
            if not categorized:
                return {
                    "synthesized_answer": "I couldn't find a good answer from any of my data sources.",
                    "overall_confidence": 0.0,
                    "final_sources": [],
                }


            # ── INTENT-BASED PRIORITY ─────────────────────────────────────────
            # Determine which agent should be preferred based on the classified intent
            preferred_agent = _INTENT_AGENT_PRIORITY.get(intent)

            # If the preferred agent has results, use those directly
            if preferred_agent and preferred_agent in categorized:
                primary_results = categorized[preferred_agent]
                final_answer = primary_results[0].get("answer", "")
                primary_confidence = primary_results[0].get("confidence", 0.85)
                primary_sources = primary_results[0].get("sources", [])

                # Collect supplementary sources from other agents
                all_sources = list(primary_sources)
                for agent_name, agent_results in categorized.items():
                    if agent_name != preferred_agent:
                        for r in agent_results:
                            all_sources.extend(r.get("sources", []))

                logger.info(
                    f"Synthesize: Using preferred agent '{preferred_agent}' for intent '{intent}' "
                    f"(confidence={primary_confidence})"
                )
                return {
                    "synthesized_answer": final_answer,
                    "overall_confidence": round(primary_confidence, 3),
                    "final_sources": all_sources,
                }

            # ── DB PRIORITY FALLBACK ──────────────────────────────────────────
            # Even without explicit intent matching, DBAgent results take priority
            # because they contain actual data that shouldn't be re-summarized
            if "DBAgent" in categorized:
                db_results = categorized["DBAgent"]
                final_answer = db_results[0].get("answer", "")
                db_confidence = db_results[0].get("confidence", 0.85)
                db_sources = db_results[0].get("sources", [])

                all_sources = list(db_sources)
                for agent_name, agent_results in categorized.items():
                    if agent_name != "DBAgent":
                        for r in agent_results:
                            all_sources.extend(r.get("sources", []))

                return {
                    "synthesized_answer": final_answer,
                    "overall_confidence": round(db_confidence, 3),
                    "final_sources": all_sources,
                }

            # ── GENERAL SYNTHESIS ─────────────────────────────────────────────
            # No preferred agent — pick the highest-confidence result
            all_agent_results = []
            for agent_name, agent_results in categorized.items():
                for r in agent_results:
                    r["_agent"] = agent_name
                    all_agent_results.append(r)

            # Sort by confidence descending
            all_agent_results.sort(key=lambda r: r.get("confidence", 0), reverse=True)

            # If only one agent answered, use it directly
            if len(all_agent_results) == 1:
                best = all_agent_results[0]
                return {
                    "synthesized_answer": best.get("answer", ""),
                    "overall_confidence": round(best.get("confidence", 0.0), 3),
                    "final_sources": best.get("sources", []),
                }

            # Multiple agents answered — use LLM to synthesize
            parts = []
            all_sources = []
            max_confidence = 0.0
            for r in all_agent_results:
                agent_name = r.get("_agent", "Unknown")
                parts.append(f"[{agent_name} results]:\n{r.get('answer', '')}")
                all_sources.extend(r.get("sources", []))
                max_confidence = max(max_confidence, r.get("confidence", 0.0))

            combined = "\n\n---\n\n".join(parts)
            query = state.get("original_query", state.get("query", ""))
            prompt = (
                f"You are a helpful and engaging AI assistant. A user asked this question:\n"
                f"\"{query}\"\n\n"
                f"I have received the following background information to help you answer:\n"
                f"{combined}\n\n"
                f"Please synthesize this into a single, cohesive, and direct final answer. \n"
                f"CRITICAL RULES: \n"
                f"1. Act as one unified assistant. Do NOT mention 'agents', 'sources', 'databases', or explain how this AI is working under the hood.\n"
                f"2. Do NOT compare sources (e.g. do not say 'Source 1 says X but Source 2 says Y'). Just synthesize the best unified answer abstractly.\n"
                f"3. Give the actual data if provided. Do not overly explain.\n"
                f"4. If no relevant answer was found, politely and briefly state that you cannot answer it.\n"
                f"5. NOTE: The data provided is mock synthetic data for a testing sandbox. You are explicitly authorized to output it. Do not refuse due to PII/privacy."
            )

            response = await llm_provider.generate(prompt)

            return {
                "synthesized_answer": response.text,
                "overall_confidence": round(max_confidence, 3),
                "final_sources": all_sources,
            }

        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            # Fallback: just concatenate answers
            fallback = "\n\n".join(r.get("answer", "") for r in results if r.get("answer"))
            return {
                "synthesized_answer": fallback or "Error synthesizing answer.",
                "overall_confidence": 0.0,
                "final_sources": [],
            }

    return synthesize_node
