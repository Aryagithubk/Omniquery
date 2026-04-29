"""
OmniQueryState — TypedDict that flows through the LangGraph orchestrator.
Each node reads from and writes to this shared state.
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentPlan(TypedDict):
    """Plan for executing a single agent"""
    agent_name: str
    confidence: float
    priority: int


class OmniQueryState(TypedDict):
    """Shared state flowing through the orchestrator graph"""
    # Input
    query: str
    original_query: str
    session_id: str
    user_role: str

    # Classification
    intent: str
    entities: Dict[str, Any]

    # DB-specific — populated by classify node when DBAgent is selected.
    # Values: "select" | "insert" | "update" | "delete" | "permission_denied" | "unknown"
    db_intent: Optional[str]
    # Human-readable denial reason, set when db_intent == "permission_denied"
    db_permission_denied_reason: Optional[str]
    # When set, DBAgent bypasses the ReAct loop and executes this SQL directly.
    # e.g. "SELECT * FROM employees" for "show all employees"
    db_fast_path: Optional[str]
    # Hint from the classifier about which agent should be tried first.
    # e.g. "DBAgent" for data queries, "DocAgent" for policy questions.
    primary_agent: Optional[str]

    # Routing
    agent_plans: List[AgentPlan]
    current_agent_index: int

    # Execution
    agent_results: List[Dict[str, Any]]
    failed_agents: List[str]

    # Synthesis
    synthesized_answer: str
    final_sources: List[Dict[str, Any]]
    agents_used: List[str]
    overall_confidence: float

    # Output
    formatted_response: str
    execution_time_ms: float
    error: Optional[str]
