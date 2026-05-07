"""Typed workflow state shared across all agents.

Replaces the raw dict with a dataclass to provide:
- Self-documenting field definitions
- IDE autocomplete and type checking
- Protection against key name typos
"""

from dataclasses import dataclass, field


@dataclass
class WorkflowState:
    """Mutable state object passed between agents during a workflow run.

    Each agent reads the fields it needs and writes its outputs back.
    The Orchestrator uses these fields to drive the Planner decision loop.
    """

    task: str
    """Natural language description of what to build/fix."""

    focus_files: list[str] | None = None
    """Optional list of specific files to focus on (relative to workspace)."""

    modified_files: list[str] = field(default_factory=list)
    """Files that have been modified during this workflow (relative paths)."""

    patch: str = ""
    """Raw patch text from the most recent Coder run."""

    test_results: dict | None = None
    """Structured test results dict: {passed: bool, stdout: str, stderr: str, returncode: int}."""

    lint_results: dict | None = None
    """Structured lint results dict: {passed: bool, stdout: str, returncode: int}."""

    review: str = ""
    """Review output from the Reviewer agent."""

    error: str | None = None
    """Fatal error from Coder agent — workflow cannot proceed if set."""

    fix_error: str | None = None
    """Last error message from a failed fix attempt."""

    fix_applied: bool = False
    """Whether the most recent fix run applied a patch successfully."""

    last_fix_patch: str = ""
    """Raw patch text from the most recent Fixer run."""

    def to_dict(self) -> dict:
        """将 WorkflowState 转为 JSON 可序列化的字典，供 SSE 事件传递。"""
        return {
            "task": self.task,
            "focus_files": self.focus_files,
            "modified_files": self.modified_files,
            "patch": self.patch,
            "test_results": self.test_results,
            "lint_results": self.lint_results,
            "review": self.review,
            "error": self.error,
            "fix_error": self.fix_error,
            "fix_applied": self.fix_applied,
            "last_fix_patch": self.last_fix_patch,
        }
