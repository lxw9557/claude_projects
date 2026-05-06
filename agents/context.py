"""Shared context loading for agents."""

import os
import config


def load_repo_context(max_files: int = None, focus_files: list[str] = None) -> str:
    """Load repository files into a context string for the LLM.

    Limits to MAX_CONTEXT_FILES to avoid token blowup.
    If focus_files is provided, loads those specific files first.
    """
    max_files = max_files or config.MAX_CONTEXT_FILES
    context_parts = []
    loaded = 0

    def _read_with_line_numbers(filepath: str, rel_path: str) -> str:
        """Read a file and return content prefixed with line numbers, for accurate diff headers."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            numbered = [f"{i:6d}|{line}" for i, line in enumerate(lines, start=1)]
            return f"# File: {rel_path}\n{''.join(numbered)}"
        except Exception:
            return ""

    # Load focus files first
    if focus_files:
        for fpath in focus_files:
            abs_path = os.path.join(config.WORKSPACE, fpath)
            if os.path.isfile(abs_path):
                content = _read_with_line_numbers(abs_path, fpath)
                if content:
                    context_parts.append(content)
                    loaded += 1

    # Walk remaining files
    for root, _, files in os.walk(config.WORKSPACE):
        if loaded >= max_files:
            break
        for fname in files:
            if loaded >= max_files:
                break
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, config.WORKSPACE)

            # Skip focus files (already loaded)
            if focus_files and rel_path.replace("\\", "/") in [f.replace("\\", "/") for f in focus_files]:
                continue

            # Only load code files
            if fname.endswith((".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".h")):
                content = _read_with_line_numbers(fpath, rel_path)
                if content:
                    context_parts.append(content)
                    loaded += 1

    return "\n".join(context_parts)


def get_modified_files(patched_files: list[str]) -> list[str]:
    """Return list of files that were modified (for focus in fix loops)."""
    return list(patched_files)
