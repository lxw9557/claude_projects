"""Structured logging setup for the coding agent.

Provides:
- Unified log format with timestamps
- Per-module logger factory
- Context manager for timing LLM calls and agent steps
"""

import logging
import time
from contextlib import contextmanager

_log_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent format.

    Safe to call multiple times — only applies configuration once.
    """
    global _log_initialized
    if _log_initialized:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    _log_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name, prefixed with 'coding_agent.'."""
    return logging.getLogger(f"coding_agent.{name}")


@contextmanager
def log_duration(logger: logging.Logger, operation: str):
    """Context manager that logs the duration of an operation.

    Usage:
        with log_duration(logger, "LLM call"):
            result = call_llm(prompt)
    """
    start = time.perf_counter()
    yield
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s completed in %.0fms", operation, duration_ms)
