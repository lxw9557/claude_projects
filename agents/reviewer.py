"""Reviewer Agent: reviews code quality and provides feedback."""

from llm import call_llm
from agents.context import load_repo_context
from core.agent_base import AgentBase


class ReviewerAgent(AgentBase):
    """Reviews code quality and provides structured feedback."""

    SYSTEM_PROMPT = """You are a senior code reviewer. Review the implementation and provide structured feedback.

RULES:
1. Be specific — reference exact files and line numbers from the context.
2. Categorize issues: bug, style, performance, security, maintainability.
3. Be constructive — suggest concrete fixes, not just complaints.
4. Focus on the changes made, not the entire codebase."""

    @property
    def name(self) -> str:
        return "reviewer"

    def run(self, state: dict) -> dict:
        """Review the current state of code.

        State keys used:
            - task: the original task
            - test_results: test output
            - modified_files: files that were changed
        State keys updated:
            - review: review text from LLM
        """
        task = state.get("task", "")
        test_results = state.get("test_results", {})
        focus_files = state.get("modified_files", None)

        context = load_repo_context(focus_files=focus_files)

        prompt = f"""Repository context (focus on recent changes):
{context}

Original task:
{task}

Test results:
{test_results.get('stdout', 'No tests run')}
{test_results.get('stderr', '')}

Review the implementation. Return:
1. Issues found (if any)
2. Suggestions for improvement
3. Overall assessment (pass/fail/needs-work)"""

        review = call_llm(prompt, system=self.SYSTEM_PROMPT)
        state["review"] = review
        return state
