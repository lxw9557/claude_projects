# Coding Agent

LLM 驱动的自动化编码代理，输入自然语言任务描述，自动完成代码修改、lint 修复、测试修复和代码审查。提供 CLI 和 Web UI 两种使用方式。

## 解决的问题

- **自然语言驱动开发**：用一句话描述需求，Agent 自动生成并应用代码补丁
- **自动质量保障**：每次代码变更后自动运行 lint + 测试，失败时自动修复
- **AI 代码审查**：变更完成后由 LLM 进行最终审查，给出改进建议

## 工作流程

工作流由 **Planner** 动态决策，不再硬编码固定步骤。Planner 综合当前状态和历史执行记录，结合规则兜底 + LLM 智能决策，选择每一步应该执行什么操作。

```
用户输入任务
      │
      ▼
┌──────────────────────────────────────────────┐
│  Planner 动态决策循环                          │
│  根据 state + history 决定下一步：              │
│    coder → lint → (fix → lint)*               │
│              → test → (fix → test)*           │
│              → review → done                  │
│  每个检查最多 3 次修复尝试，总计上限 25 步       │
└──────────────────────────────────────────────┘
      │
      ▼
   输出结果摘要
```

### 各 Agent 职责

| Agent | 文件 | 职责 |
|-------|------|------|
| **Coder** | `agents/coder.py` | 根据任务描述 + 仓库上下文，生成 unified diff patch 并应用（最多重试 3 次）|
| **Fixer** | `agents/fixer.py` | 根据 lint/测试失败信息，生成修复 patch 并应用（最多重试 3 次）|
| **Reviewer** | `agents/reviewer.py` | 对变更进行代码审查，输出问题、建议和总体评估 |

## 项目结构

```
coding_agent/
├── main.py              # CLI 入口：构建 Orchestrator 并运行工作流
├── server.py            # FastAPI Web 服务：6 个端点，SSE 流式推送工作流进度
├── workflow_runner.py   # 流式工作流包装器，供 server 调用
├── config.py            # 配置：LLM 提供商、API key、工作区路径、重试参数
├── llm.py               # LLM 抽象层：支持 DeepSeek / OpenAI / Anthropic
├── requirements.txt     # Python 依赖
├── .env                 # API key（不提交到 git）
├── CLAUDE.md            # Claude Code 使用指南
├── coding_agent.md      # 原始设计文档
│
├── tests/               # Agent 系统单元测试
│   ├── test_patch.py    # Patch 模糊匹配测试
│   ├── test_planner.py  # Planner 决策树测试
│   └── test_state.py    # WorkflowState 测试
│
├── core/
│   ├── agent_base.py    # Agent 抽象基类（ABC），定义 name + run(state) 接口
│   ├── orchestrator.py  # 主编排器：注册 Agent，执行 Planner 决策循环
│   ├── planner.py       # 工作流规划器：规则兜底 + LLM 智能决策
│   ├── state.py         # WorkflowState dataclass：11 个字段的类型化状态对象
│   └── logging_setup.py # 结构化日志：控制台 + 文件双输出
│
├── agents/
│   ├── coder.py         # Coder Agent：根据任务生成实现代码
│   ├── fixer.py         # Fixer Agent：根据 lint/测试失败修复代码
│   ├── reviewer.py      # Reviewer Agent：代码变更的最终审查
│   └── context.py       # 仓库上下文加载：将文件内容带行号格式化后送 LLM
│
├── tools/
│   ├── tester.py        # 运行 pytest 和 flake8
│   └── patch.py         # Unified diff 解析和应用（模糊上下文匹配，不信任行号）
│
├── static/
│   └── index.html       # Web UI 前端（单页应用）
│
└── workspace/           # 被修改的目标仓库（示例代码，非 agent 源码）
    ├── math_utils.py
    └── test_math_utils.py
```

## 使用方法

### CLI

```bash
# 基本用法
python main.py "add a power function to math_utils.py"

# 只关注特定文件
python main.py "fix the divide by zero handling" --focus math_utils.py

# 复杂任务
python main.py "add type hints to all public functions and update tests"
```

### Web UI

```bash
# 启动服务后访问 http://127.0.0.1:8000
python server.py
```

Web UI 通过 SSE 实时展示工作流进度：每一步的 Planner 决策、执行结果、lint/test 状态。

## 配置

### LLM 提供商

通过环境变量或 `.env` 文件配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CODING_AGENT_LLM_PROVIDER` | LLM 提供商：`deepseek` / `openai` / `anthropic` | `deepseek` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `CODING_AGENT_DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-chat` |
| `CODING_AGENT_WORKSPACE` | 工作区路径 | `./workspace` |
| `ANTHROPIC_BASE_URL` | 自定义 API 端点（用于代理/中转） | - |

### Config 配置类

配置通过 `Config` dataclass 管理，支持依赖注入（测试中可创建独立实例）：

```python
from config import Config, get_config

cfg = get_config()  # 获取默认实例
print(cfg.workspace)

# 测试中注入自定义配置
from config import set_config
set_config(Config(workspace="/tmp/test", max_retries=1))
```

核心参数：`MAX_RETRIES=3`（Coder/Fixer 重试）、`TEMPERATURE=0.2`、`MAX_CONTEXT_FILES=10`（上下文文件上限）。`core/orchestrator.py` 中 `MAX_STEPS=25` 是整个工作流的安全阀上限。

### Anthropic 高级特性

使用 Anthropic 后端时自动启用：
- **扩展思考（thinking）**：2000 token 预算，提高代码生成质量
- **Prompt Caching**：对系统消息和用户上下文启用 ephemeral 缓存，减少重复 token 消耗

## Patch 模糊匹配

LLM 生成的 unified diff 行号经常不够精确。`tools/patch.py` 不信任行号，而是：

1. 从 diff 中提取上下文行（` ` 前缀）和删除行（`-` 前缀）作为搜索锚点
2. 在原文件中搜索这些锚点行，找到实际位置
3. 允许一行级别的模糊容错
4. 完全自建解析器，不依赖 `unidiff` 库，能处理 LLM 常见的格式错误（如 markdown 代码块包裹的 diff）

## License

MIT
