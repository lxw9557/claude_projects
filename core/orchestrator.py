"""Orchestrator — the "brain" of the agent system.

Phase 3: Uses a Planner to dynamically decide each next step instead of
         following a hardcoded 4-step pipeline. The orchestrator runs a
         decide→execute→record loop until the Planner says "done".
"""

from core.agent_base import AgentBase
from core.planner import Planner
from tools.tester import run_tests, run_lint
from tools.patch import PatchError
import config


class Orchestrator:
    """Orchestrates agent execution through a Planner-driven decision loop.

    Agents are registered by name. The Planner examines the current state
    and execution history after each step and decides what to do next.
    Both synchronous (CLI) and streaming (Web UI) execution are supported.
    """

    # Safety limit — prevents infinite loops
    MAX_STEPS = 25

    def __init__(self):
        self._agents: dict[str, AgentBase] = {}

    # ------------------------------------------------------------------
    # Agent registry
    # ------------------------------------------------------------------

    def register(self, agent: AgentBase) -> None:
        """Register an agent instance."""
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentBase:
        """Look up a registered agent by name.

        Raises:
            KeyError: If no agent with that name is registered.
        """
        if name not in self._agents:
            raise KeyError(
                f"Agent '{name}' not registered. Available: {list(self._agents.keys())}"
            )
        return self._agents[name]

    # ------------------------------------------------------------------
    # Synchronous workflow (CLI)
    # ------------------------------------------------------------------

    def run_workflow(self, task: str, focus_files: list[str] = None) -> dict:
        """Execute the coding agent workflow with Planner-driven decisions.

        Args:
            task: Natural language description of what to build/fix.
            focus_files: Optional list of specific files to focus on.

        Returns:
            Final state dict with results.
        """
        state = {
            "task": task,
            "focus_files": focus_files,
            "modified_files": [],
        }
        history: list[dict] = []
        planner = Planner()

        print("=" * 60)
        print("CODING AGENT — Starting workflow")
        print(f"Task: {task}")
        print(f"Workspace: {config.WORKSPACE}")
        print("=" * 60)

        step_num = 0
        while step_num < self.MAX_STEPS:
            step_num += 1

            # Ask the Planner what to do next
            decision = planner.decide(state, history)
            step_name = decision["step"]
            reasoning = decision.get("reasoning", "")

            if step_name == "done":
                print(f"\n  Planner: ✓ {reasoning}")
                break

            print(f"\n[{step_num}] Planner → {step_name}")
            if reasoning:
                print(f"  Reason: {reasoning}")

            # Execute the step
            history_entry = self._execute_step(step_name, state, decision)
            history.append(history_entry)

            # If the step produced a fatal error, planner will catch it next iteration
            if history_entry.get("result") == "fatal":
                # Let the planner see this and decide (it will say "done")
                continue

        if step_num >= self.MAX_STEPS:
            print(f"\n  WARNING: Reached max steps ({self.MAX_STEPS}). Stopping.")

        # Summary
        self._print_summary(state)
        return state

    # ------------------------------------------------------------------
    # Streaming workflow (Web UI)
    # ------------------------------------------------------------------

    def run_workflow_stream(self, task: str, focus_files: list[str] = None):
        """Event-emitting version of run_workflow for the web UI.

        Yields SSE event dicts. Planner decisions are emitted as events
        so the UI can show the dynamic workflow progression.
        """
        state = {
            "task": task,
            "focus_files": focus_files,
            "modified_files": [],
        }
        history: list[dict] = []
        planner = Planner()

        yield {"type": "step_start", "step": "workflow",
               "message": f"Starting workflow for: {task}"}

        step_num = 0
        while step_num < self.MAX_STEPS:
            step_num += 1

            # Planner decision
            decision = planner.decide(state, history)
            step_name = decision["step"]
            reasoning = decision.get("reasoning", "")

            yield {"type": "planner_decision", "step": step_name,
                   "reasoning": reasoning, "iteration": step_num}

            if step_name == "done":
                break

            # Execute the step and collect history
            history_entry = yield from self._execute_step_stream(
                step_name, state, decision, history
            )
            history.append(history_entry)

            if history_entry.get("result") == "fatal":
                continue

        if step_num >= self.MAX_STEPS:
            yield {"type": "step_error", "step": "workflow",
                   "error": f"Reached max steps ({self.MAX_STEPS})"}

        yield {"type": "done", "state": state}

    # ------------------------------------------------------------------
    # Step execution (CLI)
    # ------------------------------------------------------------------

    def _execute_step(self, step_name: str, state: dict, decision: dict) -> dict:
        """Execute a single workflow step and return a history entry.

        Args:
            step_name: The step to execute (coder, lint, test, fix, review).
            state: Current workflow state (mutated in place).
            decision: The full planner decision dict (may contain trigger, etc.).

        Returns:
            History entry dict: {step, result, ...}
        """
        if step_name == "coder":
            return self._do_coder(state)
        elif step_name == "lint":
            return self._do_check(state, run_lint, "lint_results", "lint")
        elif step_name == "test":
            return self._do_check(state, run_tests, "test_results", "test")
        elif step_name == "fix":
            trigger = decision.get("trigger") or self._infer_trigger(state)
            return self._do_fix(state, trigger)
        elif step_name == "review":
            return self._do_review(state)
        else:
            return {"step": step_name, "result": "unknown_step"}

    # ------------------------------------------------------------------
    # Step execution (streaming)
    # ------------------------------------------------------------------

    def _execute_step_stream(self, step_name: str, state: dict,
                             decision: dict, history: list[dict]):
        """Event-emitting version of _execute_step. Yields SSE events.

        Args:
            history: The workflow execution history so far (for attempt counting).

        Returns:
            History entry dict (same format as _execute_step).
        """
        if step_name == "coder":
            yield {"type": "step_start", "step": "coder",
                   "message": "Generating implementation..."}
            entry = self._do_coder(state)
            if entry["result"] == "success":
                yield {"type": "step_done", "step": "coder",
                       "modified_files": state.get("modified_files", []),
                       "patch": state.get("patch", "")}
            else:
                yield {"type": "step_error", "step": "coder",
                       "error": entry.get("error", "Unknown error")}
            return entry

        elif step_name in ("lint", "test"):
            label = step_name
            check_fn = run_lint if step_name == "lint" else run_tests
            result_key = "lint_results" if step_name == "lint" else "test_results"

            attempt = sum(1 for h in history if h["step"] == step_name) + 1

            yield {"type": "step_start", "step": f"check_{label}",
                   "message": f"Running {label} check (attempt {attempt})..."}

            entry = self._do_check(state, check_fn, result_key, label)
            results = state.get(result_key, {})

            yield {"type": "check_result",
                   "check": label,
                   "passed": entry["result"] == "passed",
                   "iteration": attempt,
                   "output": results.get("stdout", "") or results.get("stderr", "")}
            return entry

        elif step_name == "fix":
            trigger = decision.get("trigger") or self._infer_trigger(state)
            label = trigger or "issue"
            fix_attempt = sum(1 for h in history if h["step"] == "fix") + 1

            yield {"type": "step_start", "step": f"fix_{label}",
                   "message": f"Running fixer for {label} failures...",
                   "iteration": fix_attempt}

            entry = self._do_fix(state, trigger)
            if entry.get("error"):
                yield {"type": "step_error", "step": f"fix_{label}",
                       "error": entry["error"]}
            return entry

        elif step_name == "review":
            yield {"type": "step_start", "step": "review",
                   "message": "Reviewing code quality..."}
            entry = self._do_review(state)
            if entry["result"] == "success":
                yield {"type": "step_done", "step": "review",
                       "review": state.get("review", "")}
            else:
                yield {"type": "step_error", "step": "review",
                       "error": entry.get("error", "Review failed")}
            return entry

        else:
            return {"step": step_name, "result": "unknown_step"}

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _do_coder(self, state: dict) -> dict:
        """Run the coder agent. Returns history entry."""
        try:
            agent = self.get("coder")
            agent.run(state)  # mutates state in place
            files = state.get("modified_files", [])
            print(f"  Coder: success — modified: {files}")
            return {"step": "coder", "result": "success",
                    "files": list(files)}
        except PatchError as e:
            state["error"] = str(e)
            print(f"  Coder: FAILED — {e}")
            return {"step": "coder", "result": "fatal",
                    "error": str(e)}

    def _do_check(self, state: dict, check_fn, result_key: str,
                  label: str) -> dict:
        """Run a check (lint or test). Returns history entry."""
        results = check_fn()
        state[result_key] = results
        passed = results.get("passed", False)

        if passed:
            print(f"  {label.capitalize()}: PASSED")
            return {"step": label, "result": "passed"}
        else:
            output = results.get("stdout", "") or results.get("stderr", "")
            preview = output[:200].replace("\n", " ")
            print(f"  {label.capitalize()}: FAILED — {preview}")
            return {"step": label, "result": "failed",
                    "output": output[:300]}

    def _do_fix(self, state: dict, trigger: str = None) -> dict:
        """Run the fixer agent. Returns history entry."""
        try:
            agent = self.get("fixer")
            agent.run(state)  # mutates state in place

            if state.get("fix_error"):
                print(f"  Fixer: FAILED — {state['fix_error']}")
                return {"step": "fix", "result": "failed",
                        "trigger": trigger,
                        "error": state["fix_error"]}

            print(f"  Fixer: applied patch")
            return {"step": "fix", "result": "success",
                    "trigger": trigger}
        except Exception as e:
            state["fix_error"] = str(e)
            print(f"  Fixer: FAILED — {e}")
            return {"step": "fix", "result": "failed",
                    "trigger": trigger, "error": str(e)}

    def _do_review(self, state: dict) -> dict:
        """Run the reviewer agent. Returns history entry."""
        try:
            agent = self.get("reviewer")
            agent.run(state)  # mutates state in place
            print("  Review: complete")
            return {"step": "review", "result": "success"}
        except Exception as e:
            print(f"  Review: WARNING — {e}")
            return {"step": "review", "result": "error",
                    "error": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_trigger(self, state: dict) -> str:
        """Infer what triggered a fix step based on most recent failures."""
        test_results = state.get("test_results", {})
        lint_results = state.get("lint_results", {})

        # If test has run and failed, it's the trigger
        if test_results and not test_results.get("passed", True):
            return "test"
        # If lint has run and failed, it's the trigger
        if lint_results and not lint_results.get("passed", True):
            return "lint"
        return "unknown"

    def _print_summary(self, state: dict) -> None:
        """Print the workflow summary."""
        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETE")
        print("=" * 60)

        test_results = state.get("test_results", {})
        lint_results = state.get("lint_results", {})

        tests_passed = test_results.get("passed", False) if test_results else False
        lint_passed = lint_results.get("passed", False) if lint_results else False

        print(f"  Tests: {'PASSED' if tests_passed else 'FAILED'}")
        print(f"  Lint:  {'PASSED' if lint_passed else 'FAILED'}")
        print(f"  Files modified: {state.get('modified_files', [])}")

        if state.get("review"):
            print(f"\n--- Review ---\n{state['review']}")
