"""Coder Agent: generates code patches to implement a given task."""

from llm import call_llm
from tools.patch import apply_patch, PatchError
from agents.context import load_repo_context
from core.agent_base import AgentBase
from core.state import WorkflowState
from core.logging_setup import get_logger, log_duration
import config

logger = get_logger(__name__)


class CoderAgent(AgentBase):
    """Generates code patches from natural language task descriptions."""

    SYSTEM_PROMPT = """You are an expert software engineer. Your ONLY output format is a unified diff patch.

CRITICAL — LINE NUMBERS:
The repository context shows each line prefixed with its line number (e.g., "    42|    return a + b").
You MUST use these exact line numbers in your @@ -start,len +start,len @@ headers.
Count context lines carefully: the "len" is the total lines in the hunk (context + removed lines).
The new "len" is context lines + added lines (do NOT count removed lines).

RULES:
1. Output ONLY the unified diff patch. No explanations.
2. Make minimal, surgical changes — do not refactor unrelated code.
3. Preserve the existing code style and conventions (indentation, naming).
4. Include proper file headers: --- a/relative/path and +++ b/relative/path.
5. Every hunk header MUST use the exact line numbers from the context.
6. Context lines (unchanged lines) must match the original EXACTLY, including whitespace.
7. To append at end of file, use the last line number from context as the hunk start.
8. For new files: --- /dev/null, +++ b/newfile.py, and all lines are added lines (+) with no context lines."""

    @property
    def name(self) -> str:
        return "coder"

    def run(self, state: WorkflowState) -> WorkflowState:
        """Generate code to implement a task.

        Reads:
            - state.task: description of what to build/fix
            - state.focus_files (optional): list of files to focus on
        Writes:
            - state.modified_files: list of files changed
            - state.patch: the raw patch text
        """
        context = load_repo_context(focus_files=state.focus_files)

        prompt = f"""Repository context:
{context}

Task:
{state.task}

Generate the minimal unified diff patch to implement this task."""

        for attempt in range(1, config.MAX_RETRIES + 1):
            logger.info("Coder attempt %d/%d", attempt, config.MAX_RETRIES)

            with log_duration(logger, "Coder LLM call"):
                patch_text = call_llm(prompt, system=self.SYSTEM_PROMPT)

            try:
                modified = apply_patch(patch_text)
                state.modified_files = modified
                state.patch = patch_text
                logger.info("Coder success — modified %d file(s): %s", len(modified), modified)
                return state
            except PatchError as e:
                logger.warning("Coder patch failed (attempt %d): %s", attempt, e)
                if attempt == config.MAX_RETRIES:
                    raise
                prompt = f"{prompt}\n\nPrevious attempt failed with error: {e}\nPlease fix your patch format and try again."

        return state
