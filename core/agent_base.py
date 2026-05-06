"""Abstract base class for all agents in the system.

Phase 1: Existing agents are wrapped via adapters that subclass AgentBase.
Phase 2: Agents will be refactored to inherit from AgentBase directly.
"""

from abc import ABC, abstractmethod


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
    def run(self, state: dict) -> dict:
        """Execute this agent, transforming the shared workflow state.

        Args:
            state: The workflow state dict. Keys are convention-based;
                   agents read what they need and add their outputs.

        Returns:
            The updated state dict (may be the same object or a copy).
        """
        ...
