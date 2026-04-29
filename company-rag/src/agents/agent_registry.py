"""
AgentRegistry — Dynamic agent registration and discovery.
Manages all available agents and provides access by name or capability.
"""

from typing import Dict, List, Optional
from src.agents.base_agent import BaseAgent, AgentStatus
from src.utils.logger import setup_logger

logger = setup_logger("AgentRegistry")


class AgentRegistry:
    """Manages all registered agents"""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent"""
        self._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")

    def get_all(self) -> List[BaseAgent]:
        """Get all registered agents"""
        return list(self._agents.values())

    def get_enabled(self) -> List[BaseAgent]:
        """Get all enabled (non-disabled) agents"""
        return [
            agent for agent in self._agents.values()
            if agent._status != AgentStatus.DISABLED
        ]

    def get_by_name(self, name: str) -> Optional[BaseAgent]:
        """Get agent by name"""
        return self._agents.get(name)

    async def initialize_all(self) -> None:
        """Initialize all registered agents"""
        for agent in self._agents.values():
            try:
                await agent.initialize()
                logger.info(f"Agent '{agent.name}' initialized successfully.")
            except Exception as e:
                agent._status = AgentStatus.ERROR
                logger.error(f"Failed to initialize agent '{agent.name}': {e}")

    async def health_check_all(self) -> List[dict]:
        """Run health check on all agents"""
        results = []
        for agent in self._agents.values():
            health = await agent.health_check()
            results.append(health.model_dump())
        return results
