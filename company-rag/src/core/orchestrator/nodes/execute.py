"""
Execute node — runs the next agent in the execution plan.
"""

from src.core.orchestrator.state import OmniQueryState
from src.agents.base_agent import AgentContext
from src.utils.logger import setup_logger

logger = setup_logger("ExecuteNode")


def make_execute_node(agent_registry):
    """Factory that creates execute node with access to agents"""

    async def execute_node(state: OmniQueryState) -> dict:
        """Execute the current agent in the plan"""
        plans = state.get("agent_plans", [])
        current_idx = state.get("current_agent_index", 0)
        agent_results = list(state.get("agent_results", []))
        failed_agents = list(state.get("failed_agents", []))
        agents_used = list(state.get("agents_used", []))

        if current_idx >= len(plans):
            logger.info("No more agents to execute.")
            return {
                "agent_results": agent_results,
                "failed_agents": failed_agents,
                "agents_used": agents_used,
                "current_agent_index": current_idx,
            }

        plan = plans[current_idx]
        agent_name = plan["agent_name"]
        agent = agent_registry.get_by_name(agent_name)

        if not agent:
            logger.error(f"Agent '{agent_name}' not found in registry.")
            failed_agents.append(agent_name)
            return {
                "agent_results": agent_results,
                "failed_agents": failed_agents,
                "agents_used": agents_used,
                "current_agent_index": current_idx + 1,
            }

        context = AgentContext(
            query=state["query"],
            original_query=state.get("original_query", state["query"]),
            intent=state.get("intent", "general"),
            session_id=state.get("session_id", ""),
            user_role=state.get("user_role", "user"),
            # Merge state-level entities + db_intent + db_fast_path so DBAgent can read them cleanly
            entities={
                **state.get("entities", {}),
                "db_intent": state.get("db_intent"),
                "db_permission_denied_reason": state.get("db_permission_denied_reason"),
                "db_fast_path": state.get("db_fast_path"),
            },
        )

        logger.info(f"Executing agent: {agent_name} (confidence: {plan['confidence']})")

        try:
            result = await agent.execute(context)

            if result.success:
                result_dict = result.model_dump()
                result_dict.setdefault("metadata", {})["agent"] = agent_name
                agent_results.append(result_dict)
                agents_used.append(agent_name)
                logger.info(f"Agent {agent_name} succeeded (confidence: {result.confidence})")
            else:
                failed_agents.append(agent_name)
                logger.warning(f"Agent {agent_name} failed: {result.error}")

        except Exception as e:
            logger.error(f"Agent {agent_name} threw exception: {e}")
            failed_agents.append(agent_name)

        return {
            "agent_results": agent_results,
            "failed_agents": failed_agents,
            "agents_used": agents_used,
            "current_agent_index": current_idx + 1,
        }

    return execute_node
