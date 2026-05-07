"""全局配置模块 — 可注入的 Config dataclass + 向后兼容的模块级别名。

使用方式：
- 生产代码: from config import get_config; cfg = get_config()
- 测试注入: from config import Config, set_config; set_config(Config(workspace="/tmp"))
- 向后兼容: from config import WORKSPACE, MAX_RETRIES  # 仍可用（快照值）
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """应用配置 — 所有字段有默认值，测试中可创建独立实例。"""

    llm_provider: str = field(
        default_factory=lambda: os.getenv("CODING_AGENT_LLM_PROVIDER", "deepseek")
    )
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("CODING_AGENT_DEEPSEEK_MODEL", "deepseek-chat")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("CODING_AGENT_OPENAI_MODEL", "gpt-4.1")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("CODING_AGENT_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    )
    deepseek_base_url: str = "https://api.deepseek.com"
    temperature: float = 0.2
    max_retries: int = 3
    max_context_files: int = 10
    workspace: str = field(
        default_factory=lambda: os.path.abspath(
            os.getenv("CODING_AGENT_WORKSPACE", "./workspace")
        )
    )


# ---------------------------------------------------------------------------
# 默认实例管理
# ---------------------------------------------------------------------------

_default_cfg: Config | None = None


def get_config() -> Config:
    """获取当前默认配置实例（懒初始化，首次调用后缓存）。

    推荐用法：
        from config import get_config
        cfg = get_config()
        print(cfg.workspace)
    """
    global _default_cfg
    if _default_cfg is None:
        _default_cfg = Config()
    return _default_cfg


def set_config(cfg: Config) -> None:
    """替换默认配置实例（测试或自定义场景）。

    注意：模块级别名（WORKSPACE 等）为导入时快照，不会随 set_config 更新。
    使用 get_config() 可获取最新实例。
    """
    global _default_cfg
    _default_cfg = cfg


# ---------------------------------------------------------------------------
# 模块级别名 — 向后兼容（导入时快照）
# ---------------------------------------------------------------------------

_default = Config()

LLM_PROVIDER = _default.llm_provider
DEEPSEEK_API_KEY = _default.deepseek_api_key
OPENAI_API_KEY = _default.openai_api_key
ANTHROPIC_API_KEY = _default.anthropic_api_key
DEEPSEEK_MODEL = _default.deepseek_model
OPENAI_MODEL = _default.openai_model
ANTHROPIC_MODEL = _default.anthropic_model
DEEPSEEK_BASE_URL = _default.deepseek_base_url
TEMPERATURE = _default.temperature
MAX_RETRIES = _default.max_retries
MAX_CONTEXT_FILES = _default.max_context_files
WORKSPACE = _default.workspace
