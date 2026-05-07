"""Apply unified diff patches to workspace files with fuzzy matching.

Key design: LLMs often produce slightly incorrect @@ line numbers.
This module uses context lines as a search key to find the correct
position in the original file, rather than trusting the line numbers.
"""

import re
import os
import config


class PatchError(Exception):
    """Raised when a patch cannot be applied."""


def apply_patch(patch_text: str) -> list[str]:
    """Apply a unified diff patch to workspace files atomically.

    Uses fuzzy context matching — line numbers in @@ headers are hints,
    but the actual match position is found by searching for context lines.
    """
    if not patch_text.strip():
        raise PatchError("Empty patch text")

    patch_text = _extract_diff(patch_text)

    # Phase 1: Parse into per-file changes, validate, compute new content
    file_changes = _parse_multi_file_diff(patch_text)

    if not file_changes:
        raise PatchError("No file changes found in patch. Ensure the patch has ---/+++ headers.")

    results = []  # (path, new_content, is_new_file)

    for change in file_changes:
        path = os.path.join(config.WORKSPACE, change["path"])
        is_new = change.get("is_new", False)

        if is_new:
            # Build new file content from hunk add lines
            new_lines = []
            for hunk in change["hunks"]:
                for op, val in hunk["sequence"]:
                    if op == "add":
                        new_lines.append(val)
            results.append((path, new_lines, True))
            continue

        if not os.path.exists(path):
            raise PatchError(
                f"File not found: {change['path']}. Use --- /dev/null and +++ b/path for new files."
            )

        with open(path, "r", encoding="utf-8") as f:
            original = f.readlines()

        new_content = _apply_hunks_fuzzy(change["path"], original, change["hunks"])
        results.append((path, new_content, False))

    # Phase 2: Write all files (atomic — all validated first)
    modified_files = []
    for path, content, is_new in results:
        if is_new:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(content)
        rel_path = os.path.relpath(path, config.WORKSPACE)
        modified_files.append(rel_path)

    return modified_files


# ---------------------------------------------------------------------------
# Diff parser (does NOT rely on unidiff — handles LLM-formatted diffs)
# ---------------------------------------------------------------------------

_HUNK_HEADER_RE = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@(.*)$")


def _parse_multi_file_diff(text: str) -> list[dict]:
    """Parse a multi-file unified diff into a list of file change dicts."""
    lines = text.splitlines(keepends=True)
    changes = []
    current = None

    for line in lines:
        # File header: --- a/path or --- /dev/null
        if line.startswith("--- "):
            if current and (current.get("hunks") or current.get("_current_hunk_lines") is not None):
                _finalize_hunk(current)
                changes.append(current)
            current = {"path": None, "hunks": [], "is_new": False}

            rest = line[4:].strip()
            if rest.startswith("/dev/null") or rest == "/dev/null":
                current["is_new"] = True
            elif rest.startswith("a/"):
                current["path"] = rest[2:]
            else:
                current["path"] = rest
            continue

        # +++ b/path (confirms the file path)
        if line.startswith("+++ ") and current is not None:
            rest = line[4:].strip()
            if rest.startswith("b/"):
                current["path"] = rest[2:]
            elif rest != "/dev/null":
                current["path"] = rest
            continue

        # Hunk header
        m = _HUNK_HEADER_RE.match(line)
        if m and current is not None:
            if current.get("_current_hunk_lines") is not None:
                _finalize_hunk(current)
            current["_src_start"] = int(m.group(1))
            current["_dst_start"] = int(m.group(3))
            current["_current_hunk_lines"] = []
            continue

        # Hunk content lines
        if current is not None and current.get("_current_hunk_lines") is not None:
            if line.startswith((" ", "+", "-")):
                current["_current_hunk_lines"].append(line)
            elif line.strip() == "" and current["_current_hunk_lines"]:
                # Blank line ends the current diff content
                _finalize_hunk(current)
            # ignore other lines (like markdown fences or comments)

    # Finalize last hunk and file
    if current is not None:
        _finalize_hunk(current)
        if current.get("hunks") or current.get("is_new"):
            changes.append(current)

    return changes


def _finalize_hunk(change: dict):
    """Convert raw hunk lines into structured hunk data."""
    raw_lines = change.pop("_current_hunk_lines", None)
    change.pop("_src_start", None)
    change.pop("_dst_start", None)
    if not raw_lines:
        return

    # Separate into context ( ), removed (-), added (+) groups
    context_before = []  # context lines before any changes
    removed = []
    added = []
    context_after = []

    # Build a simple sequence: (type, value)
    sequence = []
    for line in raw_lines:
        if line.startswith(" "):
            sequence.append(("context", line[1:]))
        elif line.startswith("-"):
            sequence.append(("remove", line[1:]))
        elif line.startswith("+"):
            sequence.append(("add", line[1:]))
        # skip other prefixes

    change["hunks"].append({"sequence": sequence})


# ---------------------------------------------------------------------------
# Fuzzy hunk application
# ---------------------------------------------------------------------------

def _apply_hunks_fuzzy(filepath: str, original: list[str], hunks: list[dict]) -> list[str]:
    """Apply hunks to original using fuzzy context matching.

    For each hunk, we extract the context lines (and removed lines that
    must exist in original) to form a search key. We then find the best
    match in the original file, starting from the approximate position
    given in the @@ header (if available).
    """
    result = list(original)

    # Apply hunks in reverse order so positions stay valid
    for hunk in reversed(hunks):
        seq = hunk["sequence"]

        # Extract search pattern: context lines and lines to remove
        search_lines = []
        for op, val in seq:
            if op in ("context", "remove"):
                search_lines.append(val.rstrip("\n"))

        if not search_lines:
            raise PatchError(
                f"Cannot apply hunk in {filepath}: no context or removal lines to anchor on."
            )

        # Find the matching position
        match_start, match_end = _fuzzy_find(original, search_lines)

        if match_start == -1:
            # Build error with context
            search_preview = "".join(search_lines[:5])
            raise PatchError(
                f"Cannot find anchor in {filepath}. "
                f"Searched for:\n{search_preview}"
            )

        # Build replacement
        replacement = []
        for op, val in seq:
            if op in ("context", "add"):
                replacement.append(val)

        # Apply: original[match_start:match_end] → replacement
        result = result[:match_start] + replacement + result[match_end:]
        original = result  # keep original updated for next reversed hunk

    return result


def _fuzzy_find(original: list[str], search: list[str]) -> tuple[int, int]:
    """Find `search` lines in `original` using fuzzy matching.

    Returns (start_index, end_index) in original, or (-1, -1) if not found.

    The search lines are those that must exist in original
    (context + removed lines). We try to find a contiguous match,
    allowing for lines between search entries (for removed lines in diff).
    """
    if not search or not original:
        return (-1, -1)

    # Strip newlines for comparison
    orig_stripped = [l.rstrip("\n") for l in original]
    search_stripped = [l.rstrip("\n") for l in search]

    # Try to match the first search line to find candidate starts
    first = search_stripped[0]

    for start in range(len(orig_stripped)):
        if orig_stripped[start] != first:
            continue

        # Found first line — try to match remaining search lines contiguously
        oi = start + 1
        si = 1
        while si < len(search_stripped) and oi < len(orig_stripped):
            if orig_stripped[oi] == search_stripped[si]:
                oi += 1
                si += 1
            else:
                # Allow skipping one original line (fuzzy tolerance)
                oi += 1
                # But only one skip — if next also doesn't match, break
                if oi < len(orig_stripped) and orig_stripped[oi] == search_stripped[si]:
                    oi += 1
                    si += 1
                else:
                    break

        if si == len(search_stripped):
            return (start, oi)

    # Fallback: try matching just the first 3 context lines
    if len(search_stripped) > 3:
        short_search = search_stripped[:3]
        for start in range(len(orig_stripped)):
            end = start + len(short_search)
            if end <= len(orig_stripped) and orig_stripped[start:end] == short_search:
                # Found partial match, return match for the full search
                # but only the short part is guaranteed
                end_full = min(start + len(search_stripped), len(orig_stripped))
                return (start, end_full)

    return (-1, -1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_markdown_fence(text: str, keepends: bool = True) -> str:
    """去除 markdown 代码块包裹，返回纯内容。

    Args:
        text: 可能被 ``` 包裹的文本。
        keepends: True 时保留行尾换行符（用于 diff 解析），False 时去除。

    Returns:
        去除代码块标记后的纯文本。
    """
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines(keepends=keepends)
        content_lines = lines[1:]  # skip opening fence
        if content_lines and content_lines[-1].strip().startswith("```"):
            content_lines = content_lines[:-1]
        text = "".join(content_lines) if keepends else "\n".join(
            l.rstrip("\n") for l in content_lines
        )

    # Ensure diff ends with a newline (.strip() above may have removed it)
    if keepends and text and not text.endswith("\n"):
        text += "\n"

    return text


def _extract_diff(text: str) -> str:
    """从可能包含 markdown 代码块的文本中提取 unified diff（内部使用）。"""
    return strip_markdown_fence(text, keepends=True)
