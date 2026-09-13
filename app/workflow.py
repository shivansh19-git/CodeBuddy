"""The transparent MVP workflow.

No code is generated when a real provider is absent. This avoids the most
dangerous demo behaviour: pretending that an autonomous agent made a change.
"""

import re
import uuid

from app.agents.coder import CodingAgent
from app.agents.graph import run_graph
from app.agents.planner import PlannerAgent
from app.agents.tester import TestAgent
from app.config import settings
from app.embeddings.registry import build_embedding_router
from app.models.providers import (
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderRequestError,
)
from app.models.registry import build_model_router
from app.models.router import NoCompatibleProviderError
from app.rag.chunker import build_chunks
from app.rag.retriever import HybridRetriever
from app.repository import analyze_repository, repository_root
from app.review import build_review, review_summary
from app.schemas import ActivityEvent, TaskRecord, TaskStatus

TASKS: dict[str, TaskRecord] = {}
MODEL_ROUTER = build_model_router()
HYBRID_RETRIEVER = HybridRetriever(build_embedding_router(), settings.vector_store_path)
TEST_AGENT = TestAgent()


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


def _can_retry_tests(task: TaskRecord) -> bool:
    """Retry only actionable failures, never missing Docker infrastructure."""
    return (
        not task.tests.success
        and not task.tests.no_tests_collected
        and not task.tests.output.startswith("ENVIRONMENT_ERROR:")
    )


def _run_coding_with_fallback(task: TaskRecord, prompt: str, repository_id: str):
    """Use the current provider until it fails, then try compatible fallback.

    An edit is only applied after the provider has returned valid structured
    output, so changing provider here cannot leave a partial edit batch.
    """
    providers = MODEL_ROUTER.compatible(
        task_type="coding", requires_tools=True, requires_structured_output=True
    )
    if not providers:
        raise NoCompatibleProviderError("No compatible coding provider is configured.")
    failures = []
    for position, provider in enumerate(providers):
        try:
            if position:
                _event(
                    task,
                    "provider",
                    f"Fallback activated: switched to {provider.descriptor.provider}/{provider.descriptor.model}.",
                    "warning",
                )
            return CodingAgent(provider).execute(
                prompt, repository_root(repository_id), task.retrieved_context
            )
        except ProviderRateLimitError as exc:
            provider.with_availability("rate_limited")
            _event(
                task,
                "provider",
                f"{provider.descriptor.provider} rate limited (429): {exc}",
                "warning",
            )
            failures.append(f"{provider.descriptor.provider}: RateLimited")
        except ProviderQuotaExhaustedError as exc:
            provider.with_availability("quota_exhausted")
            _event(
                task,
                "provider",
                f"{provider.descriptor.provider} quota exhausted: {exc}",
                "warning",
            )
            failures.append(f"{provider.descriptor.provider}: QuotaExhausted")
        except (OSError, ProviderRequestError, UnicodeError, ValueError) as exc:
            detail = str(exc).strip() or type(exc).__name__
            failures.append(f"{provider.descriptor.provider}: {detail[:300]}")
    raise ProviderRequestError("All compatible providers failed: " + ", ".join(failures))


def run_task(
    repository_id: str, description: str, max_iterations: int, task_id: str | None = None
) -> TaskRecord:
    """Run safe local analysis; pause honestly before any unconfigured LLM work."""
    task = TaskRecord(
        id=task_id or str(uuid.uuid4()),
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
    chunks = build_chunks(repository_root(repository_id), task.summary.symbols)
    matched_chunks = HYBRID_RETRIEVER.retrieve(description, chunks)
    matched_ids = {chunk.identifier for chunk in matched_chunks}
    task.retrieved_context = [
        symbol
        for symbol in task.summary.symbols
        if f"{symbol.file}:{symbol.name}:{symbol.start_line}" in matched_ids
    ]
    _event(task, "retrieve", f"Retrieved {len(task.retrieved_context)} relevant code units.")
    fallback_plan = PlannerAgent.fallback(description, task.retrieved_context)
    task.plan = fallback_plan.steps
    _event(task, "plan", "Created a deterministic structured implementation and verification plan.")
    try:
        provider = MODEL_ROUTER.select(
            task_type="coding", requires_tools=True, requires_structured_output=True
        )
        _event(
            task,
            "provider",
            f"Selected {provider.descriptor.provider}/{provider.descriptor.model} for the coding operation.",
        )
        try:
            generated_plan = PlannerAgent(provider).create(description, task.retrieved_context)
            task.plan = generated_plan.steps
            _event(task, "plan", "Created a provider-generated structured task plan.")
        except (OSError, ProviderRequestError, UnicodeError, ValueError):
            _event(
                task,
                "plan",
                "Provider plan was unavailable; using the deterministic structured plan.",
                "warning",
            )
        # Delegate the implement → test → [debug → test]* → review loop to the
        # LangGraph correction graph.  The graph exposes the same observable
        # events and mutates ``task`` in-place via the shared GraphState dict.
        task = run_graph(
            task=task,
            description=description,
            repository_id=repository_id,
            max_iterations=max_iterations,
            run_coding_fn=_run_coding_with_fallback,
            run_tests_fn=TEST_AGENT.run,
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
    except (OSError, ProviderRequestError, UnicodeError, ValueError) as exc:
        task.status = TaskStatus.FAILED
        task.review = "The coding node did not complete; no success was claimed."
        _event(
            task, "implement", f"Coding node stopped safely: {type(exc).__name__}: {exc}", "error"
        )
    return task
