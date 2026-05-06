"""Coding Agent — main orchestrator.

Workflow:
    1. Coder Agent: generates code patch from the task description
    2. Lint -> Fix loop (up to MAX_RETRIES)
    3. Test -> Fix loop (up to MAX_RETRIES)
    4. Reviewer Agent: final code review

Agents are AgentBase subclasses registered with the Orchestrator.
The Planner dynamically decides each step.
"""

import sys
import os

# Fix Windows encoding: stdout defaults to GBK on Chinese Windows
# which can't handle emoji/special chars from LLM responses
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from core.orchestrator import Orchestrator
from core.logging_setup import setup_logging
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


def run_workflow(task: str, focus_files: list[str] = None) -> dict:
    """Execute the full coding agent workflow.

    Args:
        task: Natural language description of what to build/fix.
        focus_files: Optional list of specific files to focus on.

    Returns:
        Final state dict with results.
    """
    setup_logging()
    orch = _build_orchestrator()
    return orch.run_workflow(task, focus_files)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python main.py <task description> [--focus file1.py file2.py]")
        print()
        print("Environment variables:")
        print("  OPENAI_API_KEY or ANTHROPIC_API_KEY  — LLM API key")
        print("  CODING_AGENT_LLM_PROVIDER            — 'openai' (default) or 'anthropic'")
        print("  CODING_AGENT_WORKSPACE               — path to workspace (default: ./workspace)")
        sys.exit(1)

    task = sys.argv[1]
    focus_files = None

    # Parse --focus flag
    if "--focus" in sys.argv:
        idx = sys.argv.index("--focus")
        focus_files = sys.argv[idx + 1:]

    run_workflow(task, focus_files)


if __name__ == "__main__":
    main()
