import os
from dotenv import load_dotenv

load_dotenv()

# LLM provider: "deepseek", "openai", or "anthropic"
LLM_PROVIDER = os.getenv("CODING_AGENT_LLM_PROVIDER", "deepseek")

# API keys — set in .env file or environment
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Model selection
DEEPSEEK_MODEL = os.getenv("CODING_AGENT_DEEPSEEK_MODEL", "deepseek-chat")
OPENAI_MODEL = os.getenv("CODING_AGENT_OPENAI_MODEL", "gpt-4.1")
ANTHROPIC_MODEL = os.getenv("CODING_AGENT_ANTHROPIC_MODEL", "claude-sonnet-4-6")

# DeepSeek API base URL
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Workspace path (the repo being modified)
WORKSPACE = os.path.abspath(os.getenv("CODING_AGENT_WORKSPACE", "./workspace"))

# Agent settings
MAX_RETRIES = 3
TEMPERATURE = 0.2
MAX_CONTEXT_FILES = 10  # Limit files loaded into context to avoid token blowup
