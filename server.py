"""FastAPI server for the Cursor-like Coding Agent UI.

Endpoints:
    GET  /                  Serve the SPA
    POST /api/chat          Run workflow, stream SSE events
    GET  /api/files         List workspace files
    GET  /api/files/{path}  Read a file with line numbers
    GET  /api/diff          Get git diff of workspace
    GET  /api/logs          View recent agent logs (last N lines)
"""

import asyncio
import json
import subprocess
import sys
import os
import threading
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import config
from core.logging_setup import setup_logging, get_logger, get_log_file
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from workflow_runner import run_workflow_stream

setup_logging()
logger = get_logger("server")
logger.info("Server started, log file initialized")

app = FastAPI(title="Coding Agent")

STATIC_DIR = Path(__file__).parent / "static"

# 全局锁 — 防止并发工作流损坏共享工作区。
# 当前设计为每个进程一个工作区，并发修改会导致文件冲突。
# 未来可通过 per-request 工作区副本（git worktree 或临时目录）支持并发。
_workflow_lock = threading.Lock()


@app.get("/")
async def index():
    """Serve the single-page application."""
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/chat")
async def chat(request: Request):
    """Start a coding workflow and stream progress via SSE."""
    body = await request.json()
    task = body.get("task", "").strip()
    if not task:
        raise HTTPException(400, "Task cannot be empty")

    focus_files = body.get("focus_files", None)

    # Check if another workflow is already running
    if not _workflow_lock.acquire(blocking=False):
        raise HTTPException(409, "Another workflow is already running. Please wait.")

    logger.info("API chat request — task: %s", task)

    async def event_stream():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                for event in run_workflow_stream(task, focus_files):
                    event_copy = event
                    loop.call_soon_threadsafe(
                        lambda e=event_copy: queue.put_nowait(e)
                    )
                loop.call_soon_threadsafe(lambda: queue.put_nowait(None))
            except Exception as exc:
                logger.error("Workflow stream error: %s", exc)
                loop.call_soon_threadsafe(
                    lambda: queue.put_nowait({
                        "type": "step_error",
                        "step": "workflow",
                        "error": str(exc),
                    })
                )
                loop.call_soon_threadsafe(lambda: queue.put_nowait(None))
            finally:
                _workflow_lock.release()

        # Run the sync workflow in a thread pool
        loop.run_in_executor(None, _run)

        while True:
            event = await queue.get()
            if event is None:
                break
            # Convert WorkflowState to dict for JSON serialization if needed
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/files")
async def list_files():
    """List all non-hidden code files in the workspace."""
    files = []
    workspace = Path(config.WORKSPACE)
    code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go",
                       ".java", ".c", ".cpp", ".h", ".css", ".html", ".json",
                       ".yaml", ".yml", ".toml", ".md", ".txt"}
    for item in sorted(workspace.rglob("*")):
        if item.is_file() and not any(p.startswith(".") for p in item.parts):
            if item.suffix in code_extensions or item.suffix == "":
                files.append(str(item.relative_to(workspace)).replace("\\", "/"))
    return JSONResponse({"files": files})


@app.get("/api/files/{file_path:path}")
async def read_file(file_path: str):
    """Read a workspace file with line numbers."""
    full = Path(config.WORKSPACE) / file_path
    try:
        full = full.resolve()
    except Exception:
        raise HTTPException(404, f"Invalid path: {file_path}")

    workspace_resolved = Path(config.WORKSPACE).resolve()
    if not str(full).startswith(str(workspace_resolved)):
        raise HTTPException(403, "Access denied")

    if not full.exists() or not full.is_file():
        raise HTTPException(404, f"File not found: {file_path}")

    content = full.read_text(encoding="utf-8")
    lines = content.splitlines()
    numbered = [{"num": i, "text": line} for i, line in enumerate(lines, 1)]

    return JSONResponse({
        "path": file_path,
        "content": content,
        "lines": numbered,
    })


@app.get("/api/diff")
async def get_diff():
    """Get the current git diff showing all uncommitted changes."""
    # Windows 上 subprocess 默认使用 GBK 编码，git diff 输出可能包含非 GBK 字符导致
    # UnicodeDecodeError。显式指定 UTF-8 编码避免 result.stdout 为 None。
    try:
        result = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=config.WORKSPACE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception as e:
        return JSONResponse({"diff": f"Error running git diff: {e}"})

    return JSONResponse({"diff": result.stdout or "No changes detected."})


@app.get("/api/logs")
async def view_logs(lines: int = 200):
    """Return the last N lines of the agent log file.

    Args:
        lines: Number of recent log lines to return (default 200).
    """
    log_path = get_log_file()
    if log_path is None or not log_path.exists():
        return JSONResponse({"lines": [], "message": "No log file found — logging may not be initialized."})

    try:
        content = log_path.read_text(encoding="utf-8")
        all_lines = content.strip().splitlines()
        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return JSONResponse({"lines": recent, "path": str(log_path)})
    except Exception as e:
        return JSONResponse({"lines": [], "error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
