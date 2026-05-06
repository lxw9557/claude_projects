"""LLM abstraction layer supporting DeepSeek, OpenAI, and Anthropic."""

import config


def call_llm(prompt: str, system: str = None) -> str:
    """Call the configured LLM and return the response text."""
    if config.LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, system)
    elif config.LLM_PROVIDER == "deepseek":
        return _call_deepseek(prompt, system)
    else:
        return _call_openai(prompt, system)


def _call_deepseek(prompt: str, system: str = None) -> str:
    """Call DeepSeek API (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    else:
        messages.append({"role": "system", "content": "You are a senior software engineer."})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=config.TEMPERATURE,
    )
    return response.choices[0].message.content


def _call_openai(prompt: str, system: str = None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    else:
        messages.append({"role": "system", "content": "You are a senior software engineer."})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
        temperature=config.TEMPERATURE,
    )
    return response.choices[0].message.content


def _call_anthropic(prompt: str, system: str = None) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    system_msg = system or "You are a senior software engineer."

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        system=system_msg,
        max_tokens=8000,
        temperature=config.TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
