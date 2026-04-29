"""
AgentRouter — Scores agents by confidence and builds an execution plan.

WebSearchAgent routing rules:
  - FALLBACK_ONLY by default (skipped from normal routing)
  - EXCEPTION: when intent is "real_time" or "web_search", it IS included
    in the normal routing path as a primary agent. This handles explicit
    web/real-time queries (stock prices, current events, Oscar winners, etc.)
    without going through DBAgent first.
"""

import asyncio
from typing import List
from src.agents.base_agent import BaseAgent, AgentContext, AgentStatus
from src.core.orchestrator.state import AgentPlan
from src.utils.logger import setup_logger

logger = setup_logger("AgentRouter")

# Intents that allow WebSearchAgent to participate in normal routing
_WEB_PRIMARY_INTENTS = {"real_time", "web_search"}


class AgentRouter:
    """Routes queries to the most confident agents"""

    def __init__(
        self,
        agents: List[BaseAgent],
        min_confidence: float = 0.3,
        max_parallel: int = 3,
    ):
        self.agents = agents
        self.min_confidence = min_confidence
        self.max_parallel = max_parallel

    # Agents that are excluded from normal routing unless intent allows it.
    FALLBACK_ONLY_AGENTS = {"WebSearchAgent"}

    async def route(self, context: AgentContext) -> List[AgentPlan]:
        """
        Score all agents and return an execution plan ordered by confidence.
        1. Ask each agent for confidence (parallel)
           - WebSearchAgent is included when intent is real_time or web_search
           - WebSearchAgent is excluded (fallback-only) for all other intents
        2. Filter below min_confidence
        3. Sort descending
        4. Take top N
        """
        is_web_intent = context.intent in _WEB_PRIMARY_INTENTS

        scoring_tasks = []
        routable_agents = []
        for agent in self.agents:
            if agent._status == AgentStatus.DISABLED:
                continue

            # WebSearchAgent: include in normal routing for real_time/web_search intents,
            # skip (fallback-only) for everything else.
            if agent.name in self.FALLBACK_ONLY_AGENTS:
                if is_web_intent:
                    logger.info(
                        f"  ✅ Including {agent.name} in routing (intent='{context.intent}' is web-primary)"
                    )
                else:
                    logger.info(
                        f"  ⏭️ Skipping {agent.name} (fallback-only for intent='{context.intent}')"
                    )
                    continue

            routable_agents.append(agent)
            scoring_tasks.append(self._score_agent(agent, context))

        scores = await asyncio.gather(*scoring_tasks, return_exceptions=True)

        plans: List[AgentPlan] = []

        for agent, score in zip(routable_agents, scores):
            if isinstance(score, Exception):
                logger.warning(f"Scoring error for {agent.name}: {score}")
                continue
            logger.info(f"  📊 {agent.name} scored {score:.3f} (min={self.min_confidence})")
            if score >= self.min_confidence:
                plans.append(AgentPlan(
                    agent_name=agent.name,
                    confidence=round(score, 3),
                    priority=0,
                ))

        # Sort by confidence descending
        plans.sort(key=lambda p: p["confidence"], reverse=True)

        # Assign priority
        for i, plan in enumerate(plans[:self.max_parallel]):
            plan["priority"] = i + 1

        selected = plans[:self.max_parallel]
        logger.info(
            f"Router selected {len(selected)} agent(s): "
            f"{[(p['agent_name'], p['confidence']) for p in selected]}"
        )
        return selected

    async def _score_agent(self, agent: BaseAgent, context: AgentContext) -> float:
        return await agent.can_handle(context)
