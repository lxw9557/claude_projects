"""LLM abstraction layer supporting DeepSeek, OpenAI, and Anthropic.

All functions accept an optional Config instance for dependency injection.
When None, the module-level default config is used (backward compatible).
"""

from config import Config, get_config
from core.logging_setup import get_logger, log_duration

logger = get_logger(__name__)


def call_llm(prompt: str, system: str = None, cfg: Config = None) -> str:
    """Call the configured LLM and return the response text.

    Args:
        prompt: The user prompt to send.
        system: Optional system message override.
        cfg: Optional Config instance for dependency injection.
    """
    if cfg is None:
        cfg = get_config()

    logger.debug("LLM call — provider=%s, prompt_len=%d", cfg.llm_provider, len(prompt))

    with log_duration(logger, f"LLM call ({cfg.llm_provider})"):
        if cfg.llm_provider == "anthropic":
            result = _call_anthropic(prompt, system, cfg)
        elif cfg.llm_provider == "deepseek":
            result = _call_deepseek(prompt, system, cfg)
        else:
            result = _call_openai(prompt, system, cfg)

    logger.debug("LLM response — len=%d", len(result))
    return result


def _call_deepseek(prompt: str, system: str = None, cfg: Config = None) -> str:
    """Call DeepSeek API (OpenAI-compatible)."""
    from openai import OpenAI

    if cfg is None:
        cfg = get_config()

    client = OpenAI(
        api_key=cfg.deepseek_api_key,
        base_url=cfg.deepseek_base_url,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    else:
        messages.append({"role": "system", "content": "You are a senior software engineer."})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=cfg.deepseek_model,
        messages=messages,
        temperature=cfg.temperature,
    )
    return response.choices[0].message.content


def _call_openai(prompt: str, system: str = None, cfg: Config = None) -> str:
    """Call OpenAI API."""
    from openai import OpenAI

    if cfg is None:
        cfg = get_config()

    client = OpenAI(api_key=cfg.openai_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    else:
        messages.append({"role": "system", "content": "You are a senior software engineer."})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=cfg.openai_model,
        messages=messages,
        temperature=cfg.temperature,
    )
    return response.choices[0].message.content


def _call_anthropic(prompt: str, system: str = None, cfg: Config = None) -> str:
    """Call Anthropic API with thinking and prompt caching enabled."""
    import anthropic

    if cfg is None:
        cfg = get_config()

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    system_msg = system or "You are a senior software engineer."

    # System message with cache control on the last block
    system_block = [
        {"type": "text", "text": system_msg},
    ]
    system_block[-1]["cache_control"] = {"type": "ephemeral"}

    # User message with cache control on the content block
    user_block = [
        {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
    ]

    response = client.messages.create(
        model=cfg.anthropic_model,
        system=system_block,
        max_tokens=8000,
        temperature=cfg.temperature,
        thinking={"type": "enabled", "budget_tokens": 2000},
        messages=[{"role": "user", "content": user_block}],
    )
    return response.content[0].text
