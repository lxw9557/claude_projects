好，这一步才是关键：把“假 Agent”升级成**真正可用的 Coding Agent（接 LLM + 多文件编辑 + diff patch）**。我给你一版**工程可跑 + 接近生产设计**的实现思路和核心代码。

------

# 一、先说结论（你要实现的能力）

升级后的系统必须具备：

✅ 调用真实 LLM（OpenAI / Anthropic 等）
✅ 支持**多文件修改**（不是只写一个文件）
✅ 使用 **diff patch（最重要）** 而不是整文件覆盖
✅ 有“失败→修复→再测试”的闭环

------

# 二、核心升级点（和刚才 MVP 的区别）

## ❌ MVP问题

- 每次覆盖整个文件
- 不理解已有代码
- 不可控（容易乱改）

------

## ✅ 升级版核心

👉 **让 LLM 输出 patch，而不是代码**

```diff
--- a/solution.py
+++ b/solution.py
@@
-def solution():
-    return None
+def solution():
+    return "Hello World"
```

👉 这是 coding agent 的关键能力

------

# 三、接入 LLM（示例用 OpenAI）

## 安装

```bash
pip install openai
```

------

## LLM封装

```python
# llm.py
from openai import OpenAI

client = OpenAI()

def call_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4.1",  # 或你用的模型
        messages=[
            {"role": "system", "content": "You are a senior software engineer."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content
```

------

# 四、实现 diff patch（核心🔥）

## 安装

```bash
pip install unidiff
```

------

## patch工具

```python
# tools/patch.py
from unidiff import PatchSet
import os

WORKSPACE = "./workspace"

def apply_patch(patch_text: str):
    patch = PatchSet(patch_text.splitlines(keepends=True))

    for file in patch:
        path = os.path.join(WORKSPACE, file.path)

        if not os.path.exists(path):
            continue

        with open(path, "r") as f:
            original = f.readlines()

        new_lines = []
        i = 0

        for hunk in file:
            new_lines.extend(original[i:hunk.source_start - 1])
            i = hunk.source_start - 1

            for line in hunk:
                if line.is_added:
                    new_lines.append(line.value)
                elif line.is_removed:
                    i += 1
                else:
                    new_lines.append(line.value)
                    i += 1

        new_lines.extend(original[i:])

        with open(path, "w") as f:
            f.writelines(new_lines)
```

------

# 五、升级 Coder Agent（真正版本）

```python
# agents/coder.py
from llm import call_llm
from tools.patch import apply_patch
import os

WORKSPACE = "./workspace"

def load_repo_context():
    context = ""
    for root, _, files in os.walk(WORKSPACE):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path) as file:
                    content = file.read()
                    context += f"\n# File: {path}\n{content}\n"
    return context


def coder_agent(state):
    context = load_repo_context()

    prompt = f"""
You are an expert software engineer.

Task:
{state['task']}

Repository context:
{context}

IMPORTANT:
- Output ONLY a unified diff patch
- Do NOT output full files
- Keep changes minimal
"""

    patch = call_llm(prompt)

    apply_patch(patch)

    return state
```

------

# 六、升级 Fix Agent（自动修复）

```python
# agents/fixer.py
from llm import call_llm
from tools.patch import apply_patch
from agents.coder import load_repo_context

def fixer_agent(state):
    context = load_repo_context()

    prompt = f"""
Fix the code based on test failures.

Test results:
{state['test_results']}

Repository:
{context}

Return ONLY diff patch.
"""

    patch = call_llm(prompt)
    apply_patch(patch)

    return state
```

------

# 七、升级 Reviewer（更真实）

```python
# agents/reviewer.py
from llm import call_llm

def reviewer_agent(state):
    prompt = f"""
Review the code quality.

Test results:
{state['test_results']}

Return:
- issues
- suggestions
"""

    state["review"] = call_llm(prompt)
    return state
```

------

# 八、关键优化（非常重要）

## 1️⃣ 限制上下文（否则爆token）

👉 不要加载整个 repo
改成：

```python
只加载：
- 最近修改的文件
- 与 task 相关的文件
```

------

## 2️⃣ 强约束输出格式

在 prompt 里写死：

```text
If you do not output valid diff, the system will crash.
```

👉 很有效

------

## 3️⃣ 加 retry（必须）

```python
for _ in range(3):
    try:
        apply_patch(patch)
        break
    except:
        patch = call_llm("Fix your patch format")
```

------

## 4️⃣ 加静态分析（强烈建议）

```bash
pip install flake8
```

然后：

```python
def run_lint():
    return subprocess.run(["flake8"], capture_output=True, text=True)
```

👉 把 lint 结果喂给 fixer agent

------

# 九、现在你的系统能力

这个版本已经可以：

✅ 修改真实项目代码
✅ 自动修 bug
✅ 基于测试驱动开发
✅ 多轮迭代优化

👉 已经接近 Cursor 的核心能力了

------

# 十、下一步进化方向（建议）

## 🚀 1. 加 RAG（理解大项目）

- 用向量数据库存代码
- 按需检索上下文

------

## 🚀 2. 加 Git Agent

- 自动 commit
- 自动 PR

------

## 🚀 3. 加 UI（变成产品）

- 文件树
- diff viewer
- 手动 approve

------

## 🚀 4. 多 Agent 协作优化

- Planner 更智能（动态选 agent）
- 引入 Critic agent

------

# 最后给你一个现实判断

做到这里：

👉 你已经超过 90% “AI coding 工具 demo”水平
👉 但距离生产级还有差距在：

- 稳定性（最难）
- 上下文选择
- patch正确率

------

如果你下一步想继续，我可以帮你做：

👉 **“类 Cursor UI + 后端 agent 完整系统”**
👉 或 **“支持大项目（10k+文件）的RAG coding agent”**

直接说你要哪个方向，我给你下一层架构 👍