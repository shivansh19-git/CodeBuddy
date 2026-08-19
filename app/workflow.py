"""The transparent MVP workflow.

No code is generated when a real provider is absent. This avoids the most
dangerous demo behaviour: pretending that an autonomous agent made a change.
"""

import re
import uuid

from app.models.registry import build_model_router
from app.models.router import NoCompatibleProviderError
from app.repository import analyze_repository
from app.schemas import ActivityEvent, TaskRecord, TaskStatus

TASKS: dict[str, TaskRecord] = {}
MODEL_ROUTER = build_model_router()


def _event(task: TaskRecord, phase: str, message: str, level: str = "info") -> None:
    task.phase = phase
    task.events.append(ActivityEvent(phase=phase, message=message, level=level))


def _retrieve(task_text: str, symbols):
    """Small, dependency-free lexical retrieval baseline, replaceable by RAG later."""
    words = set(re.findall(r"[a-zA-Z_]{3,}", task_text.lower()))

    def score(symbol):
        haystack = f"{symbol.file} {symbol.name} {symbol.docstring or ''}".lower()
        return sum(word in haystack for word in words)

    return sorted(symbols, key=score, reverse=True)[:8]


def run_task(repository_id: str, description: str, max_iterations: int) -> TaskRecord:
    """Run safe local analysis; pause honestly before any unconfigured LLM work."""
    task = TaskRecord(
        id=str(uuid.uuid4()),
        repository_id=repository_id,
        description=description,
        status=TaskStatus.RUNNING,
        phase="validate",
    )
    TASKS[task.id] = task
    _event(task, "analyze", "Repository validated; analyzing Python files with AST.")
    task.summary = analyze_repository(repository_id)
    _event(
        task,
        "index",
        f"Code index loaded: {len(task.summary.symbols)} functions and classes discovered.",
    )
    task.retrieved_context = _retrieve(description, task.summary.symbols)
    _event(task, "retrieve", f"Retrieved {len(task.retrieved_context)} relevant code units.")
    task.plan = [
        "Inspect retrieved symbols and existing tests.",
        "Implement the smallest safe change.",
        "Add or update pytest coverage.",
        "Run tests in the configured sandbox.",
        "Review the resulting Git diff.",
    ]
    _event(task, "plan", "Created a structured implementation and verification plan.")
    try:
        provider = MODEL_ROUTER.select(
            task_type="coding", requires_tools=True, requires_structured_output=True
        )
        _event(
            task,
            "provider",
            f"Selected {provider.descriptor.provider}/{provider.descriptor.model} for the coding operation.",
        )
        task.status = TaskStatus.FAILED
        _event(
            task,
            "provider",
            "A provider was selected, but the coding node has not been implemented yet.",
            "warning",
        )
        task.review = (
            "Provider routing is ready; implement the coding node and Docker executor next."
        )
    except NoCompatibleProviderError:
        task.status = TaskStatus.NEEDS_PROVIDER
        _event(
            task,
            "provider",
            "No compatible coding provider is configured. Analysis is complete; no edits or test claims were fabricated.",
            "warning",
        )
        task.review = "Waiting for a configured model provider before implementation and review."
    return task
