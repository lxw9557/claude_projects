# Coding Agent

LLM 驱动的自动化编码代理，输入自然语言任务描述，自动完成代码修改、lint 修复、测试修复和代码审查。

## 解决的问题

- **自然语言驱动开发**：用一句话描述需求，Agent 自动生成并应用代码补丁
- **自动质量保障**：每次代码变更后自动运行 lint + 测试，失败时自动修复
- **AI 代码审查**：变更完成后由 LLM 进行最终审查，给出改进建议

## 工作流程

```
用户输入任务
      │
      ▼
┌──────────────────────────────────────────────┐
│  Step 1   Coder Agent                        │
│  根据任务描述 + 仓库上下文，生成 unified diff │
│  patch 并应用到工作区文件。                    │
│  失败则带着错误信息重试（最多 3 次）。          │
└──────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────┐
│  Step 2   Lint → Fix 循环                     │
│  运行 flake8 检查代码风格，如果失败：          │
│    → Fixer Agent 根据 lint 输出生成修复补丁     │
│    → 重新检查，最多重试 3 次                   │
└──────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────┐
│  Step 3   Test → Fix 循环                     │
│  运行 pytest，如果失败：                       │
│    → Fixer Agent 根据测试失败信息生成修复补丁    │
│    → 重新检查，最多重试 3 次                   │
└──────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────┐
│  Step 4   Reviewer Agent                     │
│  LLM 审查代码，输出：                          │
│    - 发现的问题                                │
│    - 改进建议                                  │
│    - 总体评估 (pass / fail / needs-work)      │
└──────────────────────────────────────────────┘
      │
      ▼
   输出结果摘要
```

## 项目结构

```
coding_agent/
├── main.py              # 主编排器：驱动完整工作流
├── config.py            # 配置：LLM 提供商、API key、工作区路径
├── llm.py               # LLM 抽象层：支持 DeepSeek / OpenAI / Anthropic
├── requirements.txt     # Python 依赖
├── .env                 # API key（不提交到 git）
│
├── agents/
│   ├── coder.py         # Coder Agent：根据任务生成实现代码
│   ├── fixer.py         # Fixer Agent：根据 lint/测试失败修复代码
│   ├── reviewer.py      # Reviewer Agent：代码变更的最终审查
│   └── context.py       # 仓库上下文加载：将文件内容格式化后送 LLM
│
├── tools/
│   ├── tester.py        # 运行 pytest 和 flake8
│   └── patch.py         # Unified diff 解析和应用（支持模糊行号匹配）
│
└── workspace/           # 被修改的目标仓库（默认）
    ├── math_utils.py
    └── test_math_utils.py
```

## 使用方法

```bash
# 基本用法
python main.py "add a power function to math_utils.py"

# 只关注特定文件
python main.py "fix the divide by zero handling" --focus math_utils.py

# 复杂任务
python main.py "add type hints to all public functions and update tests"
```

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

### Agent 设置

在 `config.py` 中可调整：

```python
MAX_RETRIES = 3        # Coder / Fixer 最大重试次数
TEMPERATURE = 0.2      # LLM 温度参数
MAX_CONTEXT_FILES = 10 # 送入 LLM 上下文的最大文件数
```

## Patch 模糊匹配

LLM 生成的 unified diff 行号经常不够精确。`tools/patch.py` 不信任行号，而是：

1. 从 diff 中提取上下文行（` ` 前缀）和删除行（`-` 前缀）作为搜索锚点
2. 在原文件中搜索这些锚点行，找到实际位置
3. 允许一行级别的模糊容错
4. 与 `unidiff` 库不同，此解析器能处理 LLM 常见的格式错误

## License

MIT
