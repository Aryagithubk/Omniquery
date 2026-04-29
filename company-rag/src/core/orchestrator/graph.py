"""
LangGraph Orchestrator — Builds and compiles the state machine that routes
queries through preprocess → classify → execute → synthesize → format.
"""

from langgraph.graph import StateGraph, END
from src.core.orchestrator.state import OmniQueryState
from src.core.orchestrator.nodes.preprocess import preprocess_node
from src.core.orchestrator.nodes.classify import make_classify_node
from src.core.orchestrator.nodes.execute import make_execute_node
from src.core.orchestrator.nodes.synthesize import make_synthesize_node
from src.core.orchestrator.nodes.format_node import format_node
from src.core.orchestrator.nodes.fallback import make_fallback_node
from src.utils.logger import setup_logger

logger = setup_logger("OrchestratorGraph")


def route_after_classify(state: OmniQueryState) -> str:
    """
    After classify, check if RBAC denied the operation.
    If agent_plans is empty AND db_intent == 'permission_denied',
    jump straight to synthesize so the denial message is returned directly.
    Otherwise proceed to execute_agent as usual.
    """
    plans = state.get("agent_plans", [])
    db_intent = state.get("db_intent")

    if not plans and db_intent == "permission_denied":
        logger.info("RBAC short-circuit: routing directly to synthesize (no agents to run).")
        return "synthesize"

    return "execute_agent"


def route_after_execute(state: OmniQueryState) -> str:
    """Decide what to do after an agent executes"""
    plans = state.get("agent_plans", [])
    current_idx = state.get("current_agent_index", 0)
    agent_results = state.get("agent_results", [])

    # If more agents to try, keep executing
    if current_idx < len(plans):
        return "execute_more"

    # If we got at least one successful result after trying all agents, go to synthesize
    if agent_results:
        return "synthesize"

    # No agents left and no results — fallback
    return "fallback"


def route_after_fallback(state: OmniQueryState) -> str:
    """After fallback, always go to format"""
    return "format"


def build_orchestrator_graph(router, agent_registry, llm_provider) -> StateGraph:
    """Build the LangGraph orchestrator graph"""

    # Create node functions with dependencies injected
    classify_node = make_classify_node(router)
    execute_node = make_execute_node(agent_registry)
    synthesize_node = make_synthesize_node(llm_provider)
    fallback_node_fn = make_fallback_node(llm_provider, agent_registry=agent_registry)

    # Build graph
    graph = StateGraph(OmniQueryState)

    # Add nodes
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("classify", classify_node)
    graph.add_node("execute_agent", execute_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("format", format_node)
    graph.add_node("fallback", fallback_node_fn)

    # Define edges
    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "classify")

    # After classify: check for RBAC short-circuit (permission denied → synthesize directly)
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "execute_agent": "execute_agent",
            "synthesize": "synthesize",
        }
    )

    # After execution, decide next step
    graph.add_conditional_edges(
        "execute_agent",
        route_after_execute,
        {
            "execute_more": "execute_agent",
            "synthesize": "synthesize",
            "fallback": "fallback",
        }
    )

    graph.add_edge("synthesize", "format")

    graph.add_conditional_edges(
        "fallback",
        route_after_fallback,
        {
            "format": "format",
        }
    )

    graph.add_edge("format", END)

    logger.info("Orchestrator graph compiled successfully.")
    return graph.compile()
