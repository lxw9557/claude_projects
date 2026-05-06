"""Abstract base class for all agents in the system.

Agents inherit from AgentBase and implement name + run(state).
The Orchestrator operates on AgentBase instances, decoupling workflow
logic from concrete agent implementations.
"""

from abc import ABC, abstractmethod
from core.state import WorkflowState


class AgentBase(ABC):
    """Abstract base class for all agents.

    Every agent (coder, fixer, reviewer, and future agents) implements
    this interface. The Orchestrator operates on AgentBase instances,
    decoupling workflow logic from concrete agent implementations.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent (e.g., 'coder', 'fixer', 'reviewer')."""
        ...

    @abstractmethod
    def run(self, state: WorkflowState) -> WorkflowState:
        """Execute this agent, transforming the shared workflow state.

        Args:
            state: The typed WorkflowState. Agents read fields they need
                   and write their outputs back, mutating in place.

        Returns:
            The same WorkflowState instance (mutated in place).
        """
        ...
