"""FastAPI entrypoint—thin routes delegate work to focused modules."""

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.repository import analyze_repository, clone_public_github, save_zip
from app.schemas import TaskRequest
from app.tools.execution import run_tests
from app.workflow import MODEL_ROUTER, TASKS, run_task

app = FastAPI(title="Agentic Software Engineer", version="0.1.0")


class GitHubRequest(BaseModel):
    url: str


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/repositories/upload")
async def upload_repository(file: UploadFile = File(...)):
    repo_id = await save_zip(file)
    return {"id": repo_id, "summary": analyze_repository(repo_id)}


@app.post("/api/repositories/github")
def github_repository(payload: GitHubRequest):
    repo_id = clone_public_github(payload.url)
    return {"id": repo_id, "summary": analyze_repository(repo_id)}


@app.get("/api/repositories/{repository_id}")
def get_repository(repository_id: str):
    return analyze_repository(repository_id)


@app.post("/api/tasks")
def create_task(payload: TaskRequest):
    return run_task(payload.repository_id, payload.description, payload.max_iterations)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(404, "Task was not found.")
    return TASKS[task_id]


@app.post("/api/tasks/{task_id}/tests")
def execute_task_tests(task_id: str):
    """Explicit test trigger. It will never execute untrusted code on the host."""
    if task_id not in TASKS:
        raise HTTPException(404, "Task was not found.")
    task = TASKS[task_id]
    task.tests = run_tests(task.repository_id)
    return task.tests


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
