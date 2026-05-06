"""Run tests in the workspace and return results."""

import subprocess
import os
import config


def _get_env() -> dict:
    """Return environment dict forcing UTF-8 for subprocess output."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_tests() -> dict:
    """Run pytest in the workspace and return structured results.

    Returns:
        dict with keys: passed (bool), stdout (str), stderr (str), returncode (int)
    """
    result = subprocess.run(
        ["python", "-m", "pytest", "-v", "--tb=short"],
        cwd=config.WORKSPACE,
        capture_output=True,
        text=True,
        timeout=120,
        env=_get_env(),
    )

    return {
        "passed": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def run_lint() -> dict:
    """Run flake8 in the workspace and return structured results.

    Returns:
        dict with keys: passed (bool), stdout (str), returncode (int)
    """
    result = subprocess.run(
        ["python", "-m", "flake8", "--max-line-length=120", "."],
        cwd=config.WORKSPACE,
        capture_output=True,
        text=True,
        timeout=60,
        env=_get_env(),
    )

    return {
        "passed": result.returncode == 0,
        "stdout": result.stdout,
        "returncode": result.returncode,
    }
