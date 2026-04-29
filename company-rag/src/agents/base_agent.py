"""
BaseAgent — Abstract base class that all agents must implement.
Defines the standard interface for agent lifecycle, confidence scoring, and query execution.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from enum import Enum
import time


class AgentStatus(str, Enum):
    READY = "ready"
    INITIALIZING = "initializing"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"


class HealthStatus(BaseModel):
    agent_name: str
    status: AgentStatus
    message: str = "OK"
    last_check: float
    dependencies: Dict[str, str] = {}


class AgentContext(BaseModel):
    """Context passed to every agent execution"""
    query: str
    original_query: str
    user_id: str = "default"
    user_role: str = "viewer"
    session_id: str = ""
    intent: str = "general"
    entities: Dict[str, Any] = {}
    conversation_history: List[Dict[str, str]] = []
    max_results: int = 5
    timeout_ms: int = 30000


class AgentResponse(BaseModel):
    """Standardized agent response"""
    success: bool
    answer: Optional[str] = None
    confidence: float = 0.0
    sources: List[Dict[str, Any]] = []
    raw_data: Optional[Any] = None
    token_usage: Dict[str, int] = {"prompt": 0, "completion": 0}
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class BaseAgent(ABC):
    """Abstract base class for all agents"""

    def __init__(self, config: Dict[str, Any], llm_provider: Any):
        self.config = config
        self.llm = llm_provider
        self._status = AgentStatus.INITIALIZING
        self._name = self.__class__.__name__

    @property
    def name(self) -> str:
        return self._name

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does"""
        ...

    @property
    @abstractmethod
    def supported_intents(self) -> List[str]:
        """List of query intents this agent can handle"""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """One-time setup (connect to DBs, load indices, etc.)"""
        ...

    @abstractmethod
    async def can_handle(self, context: AgentContext) -> float:
        """
        Return confidence score (0.0 - 1.0) that this agent
        can handle the given query.
        """
        ...

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResponse:
        """Execute the query and return results"""
        ...

    async def health_check(self) -> HealthStatus:
        """Check if the agent and its dependencies are healthy"""
        return HealthStatus(
            agent_name=self.name,
            status=self._status,
            last_check=time.time(),
        )

    async def shutdown(self) -> None:
        """Cleanup resources"""
        self._status = AgentStatus.DISABLED
