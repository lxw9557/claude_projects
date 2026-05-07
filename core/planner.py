"""Planner — the "brain" that decides what the workflow should do next.

Replaces the hardcoded 4-step pipeline with LLM-driven dynamic decision-making.
Looks at the current state + execution history and outputs the next step.

The planner uses a hybrid approach:
- Rule-based defaults for speed and reliability
- LLM override for nuanced decisions (skip, retry, early-exit)
"""

import json
import re
from config import Config, get_config
from llm import call_llm
from core.state import WorkflowState
from core.logging_setup import get_logger
from tools.patch import strip_markdown_fence

logger = get_logger(__name__)


class Planner:
    """LLM-powered workflow planner.

    Examines the current workflow state and execution history, then decides
    the single next step to execute. Falls back to rule-based defaults if
    the LLM response is unparseable.

    Args:
        cfg: Optional Config instance for dependency injection.
    """

    SYSTEM_PROMPT = """You are a workflow planner for an automated coding agent system.

Your job: look at the current state of a coding workflow and decide the SINGLE next step.

Available steps:
- coder    — generates code implementation from the task description
- lint     — runs static analysis (flake8) on the code
- test     — runs automated tests (pytest)
- fix      — runs the fixer agent to resolve lint or test failures
- review   — runs code reviewer for final assessment
- done     — workflow complete, stop here

Standard workflow:
  coder → lint → (fix → lint)* → test → (fix → test)* → review → done

Decision rules:
1. If coder hasn't run yet → coder
2. If coder failed with an error → done (cannot proceed without code)
3. If coder succeeded but lint hasn't run yet → lint
4. If lint failed and lint_fix_count < 3 → fix
5. If lint failed and lint_fix_count >= 3 → test (give up on lint, move on)
6. If lint passed and test hasn't run yet → test
7. If test failed and test_fix_count < 3 → fix
8. If test failed and test_fix_count >= 3 → review (give up on test, move on)
9. If both lint and test passed and review not done → review
10. If review done → done
11. If the last step was fix → re-run the check that triggered it (lint or test)

IMPORTANT:
- Do NOT skip lint or test on the first attempt.
- Each check type gets at most 3 fix attempts before moving on.
- If a fix step just ran, the NEXT step MUST be the corresponding check (lint or test).
- Output ONLY a JSON object, no other text.

Respond with exactly:
{"step": "<step_name>", "reasoning": "<one sentence explaining why>"}"""

    def __init__(self, cfg: Config = None):
        self.cfg = cfg or get_config()

    def decide(self, state: WorkflowState, history: list[dict]) -> dict:
        """Decide the next workflow step.

        Args:
            state: Current workflow state.
            history: List of executed steps with their results, e.g.:
                [{"step": "coder", "result": "success"}, ...]

        Returns:
            dict with keys: step (str), reasoning (str)
        """
        # Compute rule-based default first (always safe)
        default = self._default_next(state, history)

        # Build summary for the LLM
        summary = self._build_summary(state, history)

        try:
            response = call_llm(summary, system=self.SYSTEM_PROMPT, cfg=self.cfg)
            decision = self._parse(response)
            if decision and self._is_valid_step(decision["step"]):
                logger.debug("LLM planner chose: %s", decision["step"])
                return decision
        except Exception as e:
            logger.debug("LLM planner failed, using default: %s", e)

        logger.debug("Planner default: %s", default["step"])
        return default

    # ------------------------------------------------------------------
    # Rule-based default (fallback)
    # ------------------------------------------------------------------

    def _default_next(self, state: WorkflowState, history: list[dict]) -> dict:
        """Compute the next step using deterministic rules.

        Encodes the standard pipeline logic. Always produces a valid step.
        """
        completed = {h["step"] for h in history}

        # Count attempts
        lint_runs = sum(1 for h in history if h["step"] == "lint")
        test_runs = sum(1 for h in history if h["step"] == "test")
        lint_fix_count = sum(1 for h in history
                             if h["step"] == "fix" and h.get("trigger") == "lint")
        test_fix_count = sum(1 for h in history
                             if h["step"] == "fix" and h.get("trigger") == "test")

        last_step = history[-1]["step"] if history else None
        coder_error = state.error

        # 1. Coder must run first
        if "coder" not in completed:
            return {"step": "coder", "reasoning": "Coder has not run yet — starting implementation."}

        # 2. Coder failed — cannot proceed
        if coder_error:
            return {"step": "done", "reasoning": f"Coder failed with error: {coder_error}"}

        # 3. Lint hasn't run
        if "lint" not in completed:
            return {"step": "lint", "reasoning": "Lint check has not run yet."}

        # 4-5. Lint fix loop
        last_lint = self._last_result(history, "lint")
        if last_lint == "failed":
            if last_step == "fix":
                return {"step": "lint", "reasoning": "Fix applied, re-running lint to verify."}
            if lint_fix_count < self.cfg.max_retries:
                return {"step": "fix", "reasoning": f"Lint failed (fix attempt {lint_fix_count + 1}/{self.cfg.max_retries}).",
                        "trigger": "lint"}
            # Max lint retries — move on
            if "test" not in completed:
                return {"step": "test", "reasoning": "Lint fix retries exhausted, moving to tests."}

        # 6. Test hasn't run (and lint is resolved or given up)
        if "test" not in completed:
            return {"step": "test", "reasoning": "Tests have not run yet."}

        # 7-8. Test fix loop
        last_test = self._last_result(history, "test")
        if last_test == "failed":
            if last_step == "fix":
                return {"step": "test", "reasoning": "Fix applied, re-running tests to verify."}
            if test_fix_count < self.cfg.max_retries:
                return {"step": "fix", "reasoning": f"Tests failed (fix attempt {test_fix_count + 1}/{self.cfg.max_retries}).",
                        "trigger": "test"}
            # Max test retries — move on to review

        # 9. Both passed (or retries exhausted) → review
        if "review" not in completed:
            return {"step": "review", "reasoning": "All checks complete (or retries exhausted), running final review."}

        # 10. Review done
        return {"step": "done", "reasoning": "Review complete, workflow finished."}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_summary(self, state: WorkflowState, history: list[dict]) -> str:
        """Build a concise state summary for the LLM planner."""
        parts = [f"Task: {state.task}"]

        if history:
            parts.append("\nExecution history:")
            for h in history:
                extra = ""
                if h.get("files"):
                    extra = f" — modified: {', '.join(h['files'])}"
                elif h.get("output"):
                    extra = f" — {h['output'][:120]}"
                parts.append(f"  [{h['step']}] → {h.get('result', '?')}{extra}")
        else:
            parts.append("\nExecution history: (none yet)")

        # Counts
        lint_runs = sum(1 for h in history if h["step"] == "lint")
        test_runs = sum(1 for h in history if h["step"] == "test")
        lint_fixes = sum(1 for h in history
                         if h["step"] == "fix" and h.get("trigger") == "lint")
        test_fixes = sum(1 for h in history
                         if h["step"] == "fix" and h.get("trigger") == "test")

        parts.append(f"\nCounts: lint_runs={lint_runs}, lint_fixes={lint_fixes}, "
                      f"test_runs={test_runs}, test_fixes={test_fixes}")

        if state.error:
            parts.append(f"\nCoder error: {state.error}")

        parts.append(f"\nMax retries per check: {self.cfg.max_retries}")

        parts.append("\nWhat is the NEXT step? Respond with JSON only.")
        return "\n".join(parts)

    @staticmethod
    def _parse(response: str) -> dict | None:
        """Parse LLM response into a decision dict."""
        # Try to extract JSON from the response
        text = strip_markdown_fence(response, keepends=False)

        # Find JSON object
        match = re.search(r'\{[^{}]*"step"\s*:\s*"[^"]+"[^{}]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Broader search
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _is_valid_step(step: str) -> bool:
        """Check if a step name is one of the known valid steps."""
        return step in {"coder", "lint", "test", "fix", "review", "done"}

    @staticmethod
    def _last_result(history: list[dict], step: str) -> str | None:
        """Get the result of the last occurrence of a step in history."""
        for h in reversed(history):
            if h["step"] == step:
                return h.get("result")
        return None
