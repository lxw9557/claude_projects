"""tools/patch.py 单元测试 — 覆盖模糊匹配、diff 解析、patch 应用核心逻辑。"""

import os
import tempfile
import pytest
from tools.patch import (
    PatchError,
    _extract_diff,
    _parse_multi_file_diff,
    _fuzzy_find,
    _apply_hunks_fuzzy,
    apply_patch,
)


# ============================================================================
# _extract_diff
# ============================================================================

class TestExtractDiff:
    """测试从 LLM 响应中提取 unified diff 的逻辑。"""

    def test_plain_diff_passthrough(self):
        """纯 diff 文本原样返回。"""
        diff = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n context\n-old\n+new\n"
        assert _extract_diff(diff) == diff

    def test_strips_markdown_fence(self):
        """去除 ``` 代码块包裹。"""
        diff = "--- a/file.py\n+++ b/file.py\n"
        assert _extract_diff(f"```\n{diff}```") == diff

    def test_strips_outer_whitespace(self):
        """去掉首尾空白，保留末尾换行。"""
        assert _extract_diff("  \n  --- a/file.py\n+++ b/file.py\n  ") == "--- a/file.py\n+++ b/file.py\n"


# ============================================================================
# _parse_multi_file_diff
# ============================================================================

class TestParseMultiFileDiff:
    """测试多文件 unified diff 解析。"""

    def test_single_file(self):
        """解析单文件 diff。"""
        diff = "--- a/math.py\n+++ b/math.py\n@@ -1,3 +1,3 @@\n context\n-old\n+new\n"
        changes = _parse_multi_file_diff(diff)
        assert len(changes) == 1
        assert changes[0]["path"] == "math.py"
        assert changes[0]["is_new"] is False
        assert len(changes[0]["hunks"]) == 1
        assert len(changes[0]["hunks"][0]["sequence"]) == 3

    def test_two_files(self):
        """解析两个文件的 diff。"""
        diff = (
            "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
            "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-old2\n+new2\n"
        )
        changes = _parse_multi_file_diff(diff)
        assert len(changes) == 2
        assert changes[0]["path"] == "a.py"
        assert changes[1]["path"] == "b.py"

    def test_new_file(self):
        """识别新文件创建（--- /dev/null）。"""
        diff = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new line\n"
        changes = _parse_multi_file_diff(diff)
        assert len(changes) == 1
        assert changes[0]["is_new"] is True
        assert changes[0]["path"] == "new.py"

    def test_new_file_short_form(self):
        """新文件 — /dev/null 不带前缀。"""
        diff = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new line\n"
        changes = _parse_multi_file_diff(diff)
        assert changes[0]["is_new"] is True

    def test_path_without_prefix(self):
        """解析无 a/ b/ 前缀的文件路径。"""
        diff = "--- file.py\n+++ file.py\n@@ -1 +1 @@\n-old\n+new\n"
        changes = _parse_multi_file_diff(diff)
        assert changes[0]["path"] == "file.py"

    def test_hunk_with_context_remove_add(self):
        """正确拆分 context / remove / add 三类行。"""
        diff = "--- a/f.py\n+++ b/f.py\n@@ -1,4 +1,4 @@\n ctx1\n-rm1\n ctx2\n+add1\n"
        changes = _parse_multi_file_diff(diff)
        seq = changes[0]["hunks"][0]["sequence"]
        ops = [op for op, _ in seq]
        assert ops == ["context", "remove", "context", "add"]

    def test_empty_patch_no_hunks(self):
        """空字符串无有效 hunk。"""
        changes = _parse_multi_file_diff("")
        assert changes == []

    def test_markdown_fence_ignored(self):
        """markdown 代码块标记不会被误解析为 diff 内容。"""
        diff = '--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n```\n'
        changes = _parse_multi_file_diff(diff)
        assert len(changes) == 1  # fence line is ignored


# ============================================================================
# _fuzzy_find
# ============================================================================

class TestFuzzyFind:
    """测试模糊行匹配算法。"""

    def test_exact_match(self):
        """精确匹配 — 搜索行在原文件中连续出现。"""
        original = ["def foo():", "    return 1", "", "def bar():", "    return 2"]
        search = ["def foo():", "    return 1"]
        start, end = _fuzzy_find(original, search)
        assert start == 0
        assert end == 2  # oi 指向 match 结束位置

    def test_one_line_skip_tolerance(self):
        """允许跳过一行（模糊容错）。"""
        original = ["line1", "extra", "line2", "line3"]
        search = ["line1", "line2", "line3"]
        start, end = _fuzzy_find(original, search)
        assert start == 0
        assert end == 4

    def test_not_found(self):
        """搜索行在原文中不存在。"""
        original = ["a", "b", "c"]
        search = ["x", "y"]
        start, end = _fuzzy_find(original, search)
        assert start == -1
        assert end == -1

    def test_fallback_short_match(self):
        """fallback：只用前 3 行搜索匹配。"""
        original = ["header", "body1", "body2", "body3", "footer"]
        search = ["header", "body1", "body2", "nope"]
        start, end = _fuzzy_find(original, search)
        assert start == 0
        assert end > 0

    def test_empty_search(self):
        """空搜索返回 -1。"""
        assert _fuzzy_find(["a"], []) == (-1, -1)

    def test_empty_original(self):
        """空原文返回 -1。"""
        assert _fuzzy_find([], ["a"]) == (-1, -1)


# ============================================================================
# _apply_hunks_fuzzy
# ============================================================================

class TestApplyHunksFuzzy:
    """测试基于模糊匹配的 hunk 应用。"""

    def test_simple_replacement(self):
        """替换文件中的一行。"""
        original = ["line1\n", "line2\n", "line3\n"]
        hunk = {"sequence": [
            ("context", "line1\n"),
            ("remove", "line2\n"),
            ("add", "modified\n"),
        ]}
        result = _apply_hunks_fuzzy("test.py", original, [hunk])
        assert result == ["line1\n", "modified\n", "line3\n"]

    def test_add_line_only(self):
        """纯新增行（无删除）。"""
        original = ["line1\n"]
        hunk = {"sequence": [
            ("context", "line1\n"),
            ("add", "line2\n"),
        ]}
        result = _apply_hunks_fuzzy("test.py", original, [hunk])
        assert result == ["line1\n", "line2\n"]

    def test_remove_line_only(self):
        """纯删除行（无新增）。"""
        original = ["line1\n", "line2\n"]
        hunk = {"sequence": [
            ("context", "line1\n"),
            ("remove", "line2\n"),
        ]}
        result = _apply_hunks_fuzzy("test.py", original, [hunk])
        assert result == ["line1\n"]

    def test_no_anchor_raises(self):
        """无 context 和 remove 行时报错。"""
        original = ["line1\n"]
        hunk = {"sequence": [("add", "new\n")]}
        with pytest.raises(PatchError, match="no context or removal"):
            _apply_hunks_fuzzy("test.py", original, [hunk])

    def test_multiple_hunks_reverse_order(self):
        """多个 hunk — 倒序应用确保位置有效。"""
        original = ["a\n", "b\n", "c\n", "d\n", "e\n"]
        hunks = [
            {"sequence": [("context", "a\n"), ("remove", "b\n"), ("add", "B\n")]},
            {"sequence": [("context", "d\n"), ("remove", "e\n"), ("add", "E\n")]},
        ]
        result = _apply_hunks_fuzzy("test.py", original, hunks)
        assert result == ["a\n", "B\n", "c\n", "d\n", "E\n"]


# ============================================================================
# apply_patch (集成测试)
# ============================================================================

class TestApplyPatch:
    """测试完整的 patch 应用流程（需要临时文件）。"""

    def test_modify_existing_file(self):
        """修改已有文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_ws = config.WORKSPACE
            config.WORKSPACE = tmpdir

            try:
                filepath = os.path.join(tmpdir, "test.py")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("line1\nline2\nline3\n")

                diff = "--- a/test.py\n+++ b/test.py\n@@ -2 +2 @@\n-line2\n+modified\n"
                modified = apply_patch(diff)

                assert modified == ["test.py"]
                with open(filepath, "r", encoding="utf-8") as f:
                    assert f.read() == "line1\nmodified\nline3\n"
            finally:
                config.WORKSPACE = old_ws

    def test_create_new_file(self):
        """创建新文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import config
            old_ws = config.WORKSPACE
            config.WORKSPACE = tmpdir

            try:
                diff = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+hello world\n"
                modified = apply_patch(diff)

                assert modified == ["new.py"]
                new_path = os.path.join(tmpdir, "new.py")
                assert os.path.exists(new_path)
                with open(new_path, "r", encoding="utf-8") as f:
                    assert f.read() == "hello world\n"
            finally:
                config.WORKSPACE = old_ws

    def test_empty_patch_raises(self):
        """空 patch 抛出 PatchError。"""
        with pytest.raises(PatchError, match="[Ee]mpty"):
            apply_patch("")

    def test_missing_file_raises(self):
        """文件不存在时抛出 PatchError。"""
        import config
        with tempfile.TemporaryDirectory() as tmpdir:
            old_ws = config.WORKSPACE
            config.WORKSPACE = tmpdir
            try:
                with pytest.raises(PatchError, match="File not found|not found"):
                    apply_patch("--- a/missing.py\n+++ b/missing.py\n@@ -1 +1 @@\n-old\n+new\n")
            finally:
                config.WORKSPACE = old_ws
