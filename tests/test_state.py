"""core/state.py 单元测试 — 验证 WorkflowState dataclass 行为。"""

from core.state import WorkflowState


class TestWorkflowState:
    """测试 WorkflowState 的创建、默认值和字段修改。"""

    def test_create_with_required_fields(self):
        """仅必填字段 task 即可创建。"""
        state = WorkflowState(task="add a function")
        assert state.task == "add a function"
        assert state.modified_files == []
        assert state.patch == ""
        assert state.review == ""
        assert state.error is None
        assert state.fix_error is None
        assert state.fix_applied is False
        assert state.last_fix_patch == ""
        assert state.test_results is None
        assert state.lint_results is None
        assert state.focus_files is None

    def test_create_with_focus_files(self):
        """可选字段 focus_files 可正常传入。"""
        state = WorkflowState(task="fix bug", focus_files=["a.py", "b.py"])
        assert state.focus_files == ["a.py", "b.py"]

    def test_mutable_fields_are_mutable(self):
        """list 字段可原地修改。"""
        state = WorkflowState(task="test")
        state.modified_files.append("foo.py")
        assert "foo.py" in state.modified_files

    def test_error_field_set(self):
        """error 字段可设为字符串。"""
        state = WorkflowState(task="test")
        state.error = "something went wrong"
        assert state.error == "something went wrong"

    def test_test_results_dict(self):
        """test_results 可存储结构化 dict。"""
        state = WorkflowState(task="test")
        state.test_results = {"passed": True, "stdout": "3 passed", "returncode": 0}
        assert state.test_results["passed"] is True

    def test_lint_results_dict(self):
        """lint_results 可存储结构化 dict。"""
        state = WorkflowState(task="test")
        state.lint_results = {"passed": False, "stdout": "F401", "returncode": 1}
        assert state.lint_results["passed"] is False
