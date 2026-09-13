import io
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.config import settings
from app.db.repository import TaskStore
from app.repository import (
    IGNORED_PARTS,
    analyze_repository,
    clone_public_github,
    original_repository_root,
    repository_root,
    save_python_files,
    save_zip,
)
from app.schemas import ActivityEvent, TaskRecord, TaskRequest, TaskStatus
from app.security import RequestRateLimiter, TaskConcurrencyLimiter
from app.tools.execution import run_tests
from app.tools.filesystem import _resolve, read_file
from app.workflow import MODEL_ROUTER, TASKS, run_task

app = FastAPI(title="Agentic Software Engineer", version="0.1.0")
TASK_STORE = TaskStore(settings.database_path)
RATE_LIMITER = RequestRateLimiter(settings.request_limit_per_minute)
TASK_LIMITER = TaskConcurrencyLimiter(settings.max_concurrent_tasks)
TASK_EXECUTOR = ThreadPoolExecutor(max_workers=settings.max_concurrent_tasks)


class GitHubRequest(BaseModel):
    url: str


class FileEditRequest(BaseModel):
    path: str
    content: str



@app.middleware("http")
async def rate_limit_requests(request: Request, call_next):
    """Apply per-client throttling before expensive upload/model operations."""
    client = request.client.host if request.client else "unknown"
    if not RATE_LIMITER.allow(client):
        return JSONResponse(
            status_code=429,
            content={"detail": "Request limit reached. Try again in a minute."},
        )
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/repositories/upload")
async def upload_repository(file: UploadFile = File(...)):
    repo_id = await save_zip(file)
    return {"id": repo_id, "summary": analyze_repository(repo_id)}


@app.post("/api/repositories/files")
async def upload_python_files(files: list[UploadFile] = File(...)):
    """Accept a collection of loose Python files as a temporary repository."""
    repo_id = await save_python_files(files)
    return {"id": repo_id, "summary": analyze_repository(repo_id)}


@app.post("/api/repositories/github")
def github_repository(payload: GitHubRequest):
    repo_id = clone_public_github(payload.url)
    return {"id": repo_id, "summary": analyze_repository(repo_id)}


@app.get("/api/repositories/{repository_id}")
def get_repository(repository_id: str):
    return analyze_repository(repository_id)


def _run_task_in_background(task_id: str, payload: TaskRequest) -> None:
    """Run an expensive task away from the HTTP request thread."""
    if not TASK_LIMITER.try_acquire():
        task = TASKS[task_id]
        task.status = TaskStatus.FAILED
        task.phase = "provider"
        task.review = "Task capacity is currently full. Try again shortly."
        TASK_STORE.save(task)
        return
    try:
        task = run_task(
            payload.repository_id,
            payload.description,
            payload.max_iterations,
            task_id=task_id,
        )
        TASK_STORE.save(task)
    except Exception as exc:
        task = TASKS[task_id]
        task.status = TaskStatus.FAILED
        task.phase = "error"
        task.review = "The background task stopped unexpectedly."
        task.events.append(
            ActivityEvent(phase="error", message=f"Task stopped: {type(exc).__name__}", level="error")
        )
        TASK_STORE.save(task)
    finally:
        TASK_LIMITER.release()


@app.post("/api/tasks")
def create_task(payload: TaskRequest):
    task = TaskRecord(
        id=str(uuid.uuid4()),
        repository_id=payload.repository_id,
        description=payload.description,
        status="queued",
        phase="queue",
    )
    TASKS[task.id] = task
    TASK_STORE.save(task)
    TASK_EXECUTOR.submit(_run_task_in_background, task.id, payload)
    return task


@app.get("/api/tasks")
def list_tasks():
    """Compact recent task history; source code is never exposed here."""
    return TASK_STORE.list_recent()


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id) or TASK_STORE.get(task_id)
    if task is None:
        raise HTTPException(404, "Task was not found.")
    return task


@app.post("/api/tasks/{task_id}/tests")
def execute_task_tests(task_id: str):
    """Explicit test trigger. It will never execute untrusted code on the host."""
    task = TASKS.get(task_id) or TASK_STORE.get(task_id)
    if task is None:
        raise HTTPException(404, "Task was not found.")
    task.tests = run_tests(task.repository_id)
    TASKS[task.id] = task
    TASK_STORE.save(task)
    return task.tests


@app.get("/api/tasks/{task_id}/events")
def get_task_events(task_id: str):
    return get_task(task_id).events


@app.get("/api/tasks/{task_id}/diff")
def get_task_diff(task_id: str):
    return {"diff": get_task(task_id).diff, "modified_files": get_task(task_id).modified_files}


@app.get("/api/tasks/{task_id}/review")
def get_task_review(task_id: str):
    task = get_task(task_id)
    return {"review": task.review, "result": task.review_result, "status": task.status}


@app.post("/api/repositories/{repository_id}/tests")
def execute_repository_tests(repository_id: str):
    """Run tests for a persisted workspace even when a prior task has expired."""
    repository_root(repository_id)  # Validate/restore the durable workspace first.
    return run_tests(repository_id)


@app.get("/api/repositories/{repository_id}/files")
def list_repository_files(repository_id: str):
    root = repository_root(repository_id)
    files = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not any(part in IGNORED_PARTS for part in p.parts)
    ]
    return {"files": sorted(files)}


@app.get("/api/repositories/{repository_id}/files/content")
def get_file_content(repository_id: str, path: str = Query(...), original: bool = Query(False)):
    root = original_repository_root(repository_id) if original else repository_root(repository_id)
    try:
        content = read_file(root, path)
        return {"path": path, "content": content, "is_original": original}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/repositories/{repository_id}/files/content")
def update_file_content(repository_id: str, payload: FileEditRequest):
    root = repository_root(repository_id)
    try:
        dest = _resolve(root, payload.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload.content, encoding="utf-8")
        return {"status": "success", "path": payload.path}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/repositories/{repository_id}/download")
def download_repository_archive(repository_id: str):
    root = repository_root(repository_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in root.rglob("*"):
            if p.is_file() and not any(part in IGNORED_PARTS for part in p.parts):
                arcname = p.relative_to(root).as_posix()
                zf.write(p, arcname)
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{root.name}_modified.zip"'},
    )


@app.get("/api/tasks/{task_id}/patch")
def download_patch_file(task_id: str):
    task = get_task(task_id)
    return Response(
        content=task.diff or "# No changes produced",
        media_type="text/x-diff",
        headers={"Content-Disposition": f'attachment; filename="task_{task_id[:8]}.patch"'},
    )


@app.get("/api/providers/status")
def provider_status():
    status = MODEL_ROUTER.status()
    return status or [
        {
            "name": "Coding provider",
            "status": "not configured",
            "capabilities": ["configure an adapter to enable implementation"],
        }
    ]

