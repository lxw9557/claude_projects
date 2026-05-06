"""Reviewer Agent: reviews code quality and provides feedback."""

from llm import call_llm
from agents.context import load_repo_context
from core.agent_base import AgentBase
from core.state import WorkflowState
from core.logging_setup import get_logger, log_duration

logger = get_logger(__name__)


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

    def run(self, state: WorkflowState) -> WorkflowState:
        """Review the current state of code.

        Reads:
            - state.task: the original task
            - state.test_results: test output
            - state.modified_files: files that were changed
        Writes:
            - state.review: review text from LLM
        """
        context = load_repo_context(focus_files=state.modified_files if state.modified_files else None)

        test_output = f"{state.test_results.get('stdout', 'No tests run')}\n{state.test_results.get('stderr', '')}" if state.test_results else "No tests run"

        prompt = f"""Repository context (focus on recent changes):
{context}

Original task:
{state.task}

Test results:
{test_output}

Review the implementation. Return:
1. Issues found (if any)
2. Suggestions for improvement
3. Overall assessment (pass/fail/needs-work)"""

        with log_duration(logger, "Reviewer LLM call"):
            review = call_llm(prompt, system=self.SYSTEM_PROMPT)

        state.review = review
        logger.info("Review complete — %d chars", len(review))
        return state
