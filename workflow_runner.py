"""Event-emitting workflow generator for the web UI.

Phase 2: Agents are now direct AgentBase subclasses.
Delegates to Orchestrator.run_workflow_stream().
"""

from core.orchestrator import Orchestrator
from agents.coder import CoderAgent
from agents.fixer import FixerAgent
from agents.reviewer import ReviewerAgent


def _build_orchestrator() -> Orchestrator:
    """Create and configure the orchestrator with all agents registered."""
    orch = Orchestrator()
    orch.register(CoderAgent())
    orch.register(FixerAgent())
    orch.register(ReviewerAgent())
    return orch


def run_workflow_stream(task: str, focus_files: list[str] = None):
    """Execute the full coding agent workflow, yielding SSE event dicts.

    Events emitted:
        {"type": "step_start", "step": "coder", "message": "..."}
        {"type": "step_done", "step": "coder", "modified_files": [...], "patch": "..."}
        {"type": "step_error", "step": "...", "error": "..."}
        {"type": "check_result", "check": "lint|test", "passed": bool, ...}
        {"type": "step_start", "step": "fix_...", "message": "...", "iteration": N}
        {"type": "step_done", "step": "review", "review": "..."}
        {"type": "done", "state": {...}}
    """
    orch = _build_orchestrator()
    yield from orch.run_workflow_stream(task, focus_files)
