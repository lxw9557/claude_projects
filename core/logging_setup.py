"""Structured logging setup for the coding agent.

Provides:
- Unified log format with timestamps
- Dual output: console (real-time) + file (persistent)
- Per-module logger factory
- Context manager for timing LLM calls and agent steps
"""

import logging
import time
from pathlib import Path
from contextlib import contextmanager

_log_initialized = False
LOG_FILE: Path | None = None


def setup_logging(level: int = logging.INFO, log_dir: str = None) -> None:
    """Configure root logger with console + file output.

    Args:
        level: Logging level (default INFO).
        log_dir: Directory for log files. Defaults to ./logs relative to project root.

    Safe to call multiple times — only applies configuration once per process.
    """
    global _log_initialized, LOG_FILE
    if _log_initialized:
        return

    if log_dir is None:
        log_dir = str(Path(__file__).parent.parent / "logs")

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    LOG_FILE = log_path / "agent.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # File handler — persistent, UTF-8 encoded
    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setFormatter(fmt)

    # Configure root logger with both handlers
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    _log_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name, prefixed with 'coding_agent.'."""
    return logging.getLogger(f"coding_agent.{name}")


def get_log_file() -> Path | None:
    """Return the path to the current log file, or None if logging is not initialized."""
    return LOG_FILE


@contextmanager
def log_duration(logger: logging.Logger, operation: str):
    """Context manager that logs the duration of an operation."""
    start = time.perf_counter()
    yield
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s completed in %.0fms", operation, duration_ms)
