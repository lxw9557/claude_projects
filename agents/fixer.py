"""Fixer Agent: fixes code based on test/lint failures."""

from llm import call_llm
from tools.patch import apply_patch, PatchError
from agents.context import load_repo_context
from core.agent_base import AgentBase
from core.state import WorkflowState
from core.logging_setup import get_logger, log_duration
import config

logger = get_logger(__name__)


class FixerAgent(AgentBase):
    """Fixes code based on test or lint failures."""

    SYSTEM_PROMPT = """You are an expert debugger. Your ONLY output format is a unified diff patch.

CRITICAL — LINE NUMBERS:
The repository context shows each line prefixed with its line number (e.g., "    42|    return a + b").
You MUST use these exact line numbers in your @@ -start,len +start,len @@ headers.
Count context lines carefully: "len" = context lines + removed lines (old) or context + added (new).

RULES:
1. Output ONLY the unified diff patch. No explanations.
2. Read the test failures carefully and fix the ROOT CAUSE, not symptoms.
3. Make minimal changes — do not rewrite entire files.
4. Preserve code style and conventions.
5. Context lines must match the original EXACTLY, character for character.
6. Verify line numbers against the context provided."""

    @property
    def name(self) -> str:
        return "fixer"

    def run(self, state: WorkflowState) -> WorkflowState:
        """Fix code based on test/lint failures.

        Reads:
            - state.test_results: test output dict
            - state.lint_results: lint output dict
            - state.modified_files: files changed by coder (to focus context)
        Writes:
            - state.modified_files: appended with new changes
            - state.fix_applied: whether fix was applied successfully
            - state.fix_error: error message if fix failed
            - state.last_fix_patch: raw patch text from this fix
        """
        # Clear stale fix state from previous phases
        state.fix_error = None
        state.fix_applied = False

        context = load_repo_context(focus_files=state.modified_files if state.modified_files else None)

        failures_text = _build_failure_prompt(state.test_results, state.lint_results)

        logger.info("Fixer starting — test_passed=%s, lint_passed=%s",
                     state.test_results.get("passed") if state.test_results else "N/A",
                     state.lint_results.get("passed") if state.lint_results else "N/A")

        prompt = f"""Repository context:
{context}

Failures to fix:
{failures_text}

Generate the minimal unified diff patch to fix these failures."""

        for attempt in range(1, config.MAX_RETRIES + 1):
            logger.info("Fixer attempt %d/%d", attempt, config.MAX_RETRIES)

            with log_duration(logger, "Fixer LLM call"):
                patch_text = call_llm(prompt, system=self.SYSTEM_PROMPT)

            try:
                modified = apply_patch(patch_text)
                existing = state.modified_files
                for f in modified:
                    if f not in existing:
                        existing.append(f)
                state.modified_files = existing
                state.fix_applied = True
                state.last_fix_patch = patch_text
                logger.info("Fixer success — patch applied to %d file(s)", len(modified))
                return state
            except PatchError as e:
                logger.warning("Fixer patch failed (attempt %d): %s", attempt, e)
                if attempt == config.MAX_RETRIES:
                    state.fix_error = str(e)
                    state.fix_applied = False
                    return state
                prompt = f"{prompt}\n\nPrevious fix patch failed: {e}\nFix your patch format."

        return state


def _build_failure_prompt(test_results: dict | None, lint_results: dict | None) -> str:
    """Build a clear failure description from test and lint results."""
    parts = []

    if test_results and not test_results.get("passed", True):
        parts.append("--- TEST FAILURES ---")
        parts.append(test_results.get("stdout", ""))
        parts.append(test_results.get("stderr", ""))

    if lint_results and not lint_results.get("passed", True):
        parts.append("--- LINT ISSUES ---")
        parts.append(lint_results.get("stdout", ""))

    if not parts:
        parts.append("No specific failures provided. Review the code for potential issues.")

    return "\n".join(parts)
