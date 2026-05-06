# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

LLM 驱动的自动化编码代理。输入自然语言任务，自动完成代码生成、lint 修复、测试修复和代码审查。核心思路是让 LLM 输出 unified diff patch（而非完整文件），然后用模糊上下文匹配应用补丁。

## 常用命令

```bash
# CLI 运行工作流
python main.py "add a power function to math_utils.py"
python main.py "fix the divide by zero handling" --focus math_utils.py

# 启动 Web UI（FastAPI + SSE 流式推送）
python server.py
# 然后访问 http://127.0.0.1:8000

# 运行工作区测试
cd workspace && python -m pytest -v --tb=short

# 运行单个测试
cd workspace && python -m pytest -v --tb=short test_math_utils.py::TestAdd::test_positive

# Lint 检查
cd workspace && python -m flake8 --max-line-length=120 .
```

## 架构核心

### Agent 体系 (`core/agent_base.py` → `agents/`)

所有 Agent 继承 `AgentBase(ABC)`，实现 `name` 属性和 `run(state)` 方法。通过共享的 `state` dict 传递数据（约定键名：`task`, `modified_files`, `test_results`, `lint_results`, `patch`, `review` 等）。

三种 Agent：
- **CoderAgent** (`agents/coder.py`): 根据任务描述 + 仓库上下文生成 unified diff patch
- **FixerAgent** (`agents/fixer.py`): 根据 test/lint 失败信息生成修复 patch
- **ReviewerAgent** (`agents/reviewer.py`): 对变更进行代码审查

### Orchestrator + Planner (`core/orchestrator.py` + `core/planner.py`)

工作流由 `Planner` 动态决策而非硬编码步骤。`Planner.decide()` 先计算规则默认值（兜底），再尝试让 LLM 做出更灵活的决策。Orchestrator 支持两种执行模式：
- `run_workflow()` — 同步 CLI 模式
- `run_workflow_stream()` — SSE 事件流模式（Web UI 用）

### Patch 模糊匹配 (`tools/patch.py`)

**不信任 LLM 生成的 @@ 行号**。从 diff 提取上下文行（空格前缀）和删除行（减号前缀）作为搜索锚点，在原文件中模糊查找实际位置。允许一行级别的容错。可以处理 markdown 代码块包裹的 diff 和多文件 patch。新文件支持 (`--- /dev/null`)。

### LLM 抽象层 (`llm.py`)

单一入口 `call_llm(prompt, system=None)`，根据配置路由到 DeepSeek / OpenAI / Anthropic。配置在 `config.py` 中，通过 `.env` 或环境变量设置。

### Web 服务 (`server.py`)

FastAPI 应用，提供 4 个端点：`/` (SPA), `/api/chat` (SSE 流), `/api/files` (列出文件), `/api/files/{path}` (读取文件), `/api/diff` (git diff)。使用 `threading.Lock` 防止并发工作流。同步工作流在线程池中执行，通过 `asyncio.Queue` 桥接到 SSE。

## 环境变量速查

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CODING_AGENT_LLM_PROVIDER` | LLM 提供商：`deepseek` / `openai` / `anthropic` | `deepseek` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `CODING_AGENT_DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-chat` |
| `CODING_AGENT_WORKSPACE` | 工作区路径 | `./workspace` |
| `ANTHROPIC_BASE_URL` | 自定义 API 端点（用于代理/中转） | - |

## 目录说明

- `agents/`, `core/`, `tools/` — Agent 系统源代码
- `workspace/` — **被 Agent 修改的目标仓库**（示例代码），非 agent 源码的一部分；所有 patch 应用、测试、lint 均在此目录执行
- `static/` — Web UI 前端（单页 HTML）
- `coding_agent.md` — 原始设计文档，非运行时依赖

## 重要实现细节

- **状态对象是可变 dict**：Agent 直接原地修改 state，Orchestrator 读取 state 来驱动下一步决策
- **Windows 编码处理**：入口点强制 `sys.stdout` / `sys.stderr` 使用 UTF-8，并通过 `PYTHONIOENCODING` 环境变量传递给子进程
- **Agent 重试**：Coder 和 Fixer 各自内部有 `MAX_RETRIES` (3) 次 patch 应用重试；Planner 层面有额外的 lint/test 修复循环（最多 3 次），总计 `MAX_STEPS=25` 作为安全阀
- **上下文加载** (`agents/context.py`): 带行号前缀加载文件内容（用于 LLM 生成精确 diff），优先加载 `focus_files` 再加载其他代码文件，受 `MAX_CONTEXT_FILES` 限制
