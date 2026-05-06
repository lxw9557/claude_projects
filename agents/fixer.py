"""Fixer Agent: fixes code based on test/lint failures."""

from llm import call_llm
from tools.patch import apply_patch, PatchError
from agents.context import load_repo_context
from core.agent_base import AgentBase
import config


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

    def run(self, state: dict) -> dict:
        """Fix code based on test/lint failures.

        State keys used:
            - test_results: dict with test output
            - lint_results: dict with lint output
            - modified_files: files changed by coder (to focus context)
        State keys updated:
            - modified_files: appended with new changes
            - fix_applied: bool
            - fix_error: cleared on entry
        """
        # Clear stale fix state from previous phases
        state.pop("fix_error", None)
        state.pop("fix_applied", None)

        test_results = state.get("test_results", {})
        lint_results = state.get("lint_results", {})
        focus_files = state.get("modified_files", None)

        context = load_repo_context(focus_files=focus_files)

        failures_text = _build_failure_prompt(test_results, lint_results)

        prompt = f"""Repository context:
{context}

Failures to fix:
{failures_text}

Generate the minimal unified diff patch to fix these failures."""

        for attempt in range(1, config.MAX_RETRIES + 1):
            patch_text = call_llm(prompt, system=self.SYSTEM_PROMPT)

            try:
                modified = apply_patch(patch_text)
                existing = state.get("modified_files", [])
                for f in modified:
                    if f not in existing:
                        existing.append(f)
                state["modified_files"] = existing
                state["fix_applied"] = True
                state["last_fix_patch"] = patch_text
                return state
            except PatchError as e:
                if attempt == config.MAX_RETRIES:
                    state["fix_error"] = str(e)
                    state["fix_applied"] = False
                    return state
                prompt = f"{prompt}\n\nPrevious fix patch failed: {e}\nFix your patch format."

        return state


def _build_failure_prompt(test_results: dict, lint_results: dict) -> str:
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
