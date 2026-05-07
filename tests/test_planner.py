"""core/planner.py 单元测试 — 覆盖规则引擎决策树和 JSON 解析。"""

from core.planner import Planner
from core.state import WorkflowState


class TestDefaultNext:
    """测试规则决策引擎 _default_next() 的每条分支。"""

    def setup_method(self):
        self.planner = Planner()

    def _state(self, **kwargs):
        s = WorkflowState(task="test task")
        for k, v in kwargs.items():
            setattr(s, k, v)
        return s

    # --- Rule 1: Coder must run first ---

    def test_first_step_is_coder(self):
        """空历史 → 第一步必须是 coder。"""
        result = self.planner._default_next(self._state(), [])
        assert result["step"] == "coder"

    # --- Rule 2: Coder failed → done ---

    def test_coder_error_stops_workflow(self):
        """Coder 出错后直接结束。"""
        result = self.planner._default_next(
            self._state(error="PatchError: bad diff"),
            [{"step": "coder", "result": "fatal"}],
        )
        assert result["step"] == "done"

    # --- Rule 3: Coder success → lint ---

    def test_after_coder_runs_lint(self):
        """Coder 成功后下一步是 lint。"""
        result = self.planner._default_next(
            self._state(),
            [{"step": "coder", "result": "success"}],
        )
        assert result["step"] == "lint"

    # --- Rule 4-5: Lint fix loop ---

    def test_lint_failed_triggers_fix(self):
        """Lint 失败 → 触发 fix。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "failed"},
            ],
        )
        assert result["step"] == "fix"
        assert result.get("trigger") == "lint"

    def test_fix_followed_by_lint_rerun(self):
        """Fix 后重新运行 lint。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "failed"},
                {"step": "fix", "result": "success", "trigger": "lint"},
            ],
        )
        assert result["step"] == "lint"

    def test_lint_max_retries_moves_to_test(self):
        """Lint 修复次数耗尽 → 转向 test。"""
        history = [{"step": "coder", "result": "success"}]
        for i in range(3):
            history.append({"step": "lint", "result": "failed"})
            history.append({"step": "fix", "result": "success", "trigger": "lint"})
        # After 3 fix attempts, the last lint is still failed
        history.append({"step": "lint", "result": "failed"})

        result = self.planner._default_next(self._state(), history)
        assert result["step"] == "test"

    # --- Rule 6: Test hasn't run ---

    def test_lint_passed_proceeds_to_test(self):
        """Lint 通过 → 下一步 test。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "passed"},
            ],
        )
        assert result["step"] == "test"

    # --- Rule 7-8: Test fix loop ---

    def test_test_failed_triggers_fix(self):
        """Test 失败 → 触发 fix。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "passed"},
                {"step": "test", "result": "failed"},
            ],
        )
        assert result["step"] == "fix"
        assert result.get("trigger") == "test"

    def test_test_fix_reruns_test(self):
        """Test fix 后重新运行 test。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "passed"},
                {"step": "test", "result": "failed"},
                {"step": "fix", "result": "success", "trigger": "test"},
            ],
        )
        assert result["step"] == "test"

    # --- Rule 9: Both passed → review ---

    def test_all_passed_proceeds_to_review(self):
        """Lint 和 test 都通过 → review。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "passed"},
                {"step": "test", "result": "passed"},
            ],
        )
        assert result["step"] == "review"

    # --- Rule 10: Review done → done ---

    def test_review_done_workflow_finished(self):
        """Review 完成 → 流程结束。"""
        result = self.planner._default_next(
            self._state(),
            [
                {"step": "coder", "result": "success"},
                {"step": "lint", "result": "passed"},
                {"step": "test", "result": "passed"},
                {"step": "review", "result": "success"},
            ],
        )
        assert result["step"] == "done"


class TestParse:
    """测试 LLM 响应 JSON 解析。"""

    def test_valid_json(self):
        """正常 JSON 解析成功。"""
        result = Planner._parse('{"step": "lint", "reasoning": "need to check"}')
        assert result == {"step": "lint", "reasoning": "need to check"}

    def test_json_with_markdown_fence(self):
        """去除 markdown 代码块后解析。"""
        result = Planner._parse('```\n{"step": "coder", "reasoning": "start"}\n```')
        assert result == {"step": "coder", "reasoning": "start"}

    def test_json_embedded_in_text(self):
        """从多余文本中提取 JSON 对象。"""
        result = Planner._parse('Some text {"step": "done", "reasoning": "all good"} more text')
        assert result == {"step": "done", "reasoning": "all good"}

    def test_invalid_json_returns_none(self):
        """无效 JSON 返回 None。"""
        assert Planner._parse("not json at all") is None

    def test_empty_response_returns_none(self):
        """空字符串返回 None。"""
        assert Planner._parse("") is None


class TestIsValidStep:
    """测试步骤名验证。"""

    def test_all_valid_steps(self):
        for step in ["coder", "lint", "test", "fix", "review", "done"]:
            assert Planner._is_valid_step(step) is True

    def test_invalid_step(self):
        assert Planner._is_valid_step("unknown") is False
        assert Planner._is_valid_step("") is False


class TestLastResult:
    """测试历史查找工具方法。"""

    def test_find_last_in_history(self):
        history = [
            {"step": "lint", "result": "passed"},
            {"step": "test", "result": "failed"},
        ]
        assert Planner._last_result(history, "lint") == "passed"
        assert Planner._last_result(history, "test") == "failed"

    def test_not_found_returns_none(self):
        assert Planner._last_result([], "lint") is None
        assert Planner._last_result([{"step": "coder", "result": "ok"}], "lint") is None
