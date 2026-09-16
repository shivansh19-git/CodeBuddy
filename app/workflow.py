"""The transparent MVP workflow.

No code is generated when a real provider is absent. This avoids the most
dangerous demo behaviour: pretending that an autonomous agent made a change.
"""

import re
import uuid

from app.agents.coder import CodingAgent
from app.agents.graph import run_graph
from app.agents.planner import PlannerAgent
from app.agents.test_writer import TestWriterAgent
from app.agents.tester import TestAgent
from app.config import settings
from app.embeddings.registry import build_embedding_router
from app.models.providers import (
    ProviderQuotaExhaustedError,
    ProviderRateLimitError,
    ProviderRequestError,
)
from app.models.registry import build_model_router, reload_model_router
from app.models.router import ModelRouter, NoCompatibleProviderError
from app.rag.chunker import build_chunks
from app.rag.retriever import HybridRetriever
from app.repository import analyze_repository, repository_root
from app.review import build_review, review_summary
from app.schemas import ActivityEvent, TaskRecord, TaskStatus

TASKS: dict[str, TaskRecord] = {}

# Build the initial router at startup. This can be replaced at runtime via
# reload_router() whenever .env is updated without restarting the server.
MODEL_ROUTER: ModelRouter = build_model_router()
HYBRID_RETRIEVER = HybridRetriever(build_embedding_router(), settings.vector_store_path)
TEST_AGENT = TestAgent()


def reload_router() -> ModelRouter:
    """Re-read .env and rebuild MODEL_ROUTER in-place.

    Call this (or hit POST /api/providers/reload) after updating .env so that
    any new model names or API keys take effect immediately.
    """
    global MODEL_ROUTER
    MODEL_ROUTER = reload_model_router()
    return MODEL_ROUTER


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


def _select_test_writing_provider(coding_provider_name: str):
    """Pick the best available provider that is DIFFERENT from the coding provider.

    Using a different model to write tests prevents the coding model from simply
    writing tests that pass its own (potentially wrong) implementation. A fresh
    perspective from a second model produces more reliable, unbiased tests.

    Falls back to the same provider if only one is configured.
    """
    all_providers = MODEL_ROUTER.compatible(
        task_type="coding",
        requires_tools=True,
        requires_structured_output=True,
    )
    # Prefer a provider whose name differs from the coder's provider.
    others = [
        p for p in all_providers
        if p.descriptor.provider.lower() != coding_provider_name.lower()
    ]
    if others:
        return others[0]
    # Fallback: only one provider configured — reuse it.
    return all_providers[0] if all_providers else None


def _run_coding_with_fallback(task: TaskRecord, prompt: str, repository_id: str):
    """Use the current provider until it fails, then try compatible fallback.

    An edit is only applied after the provider has returned valid structured
    output, so changing provider here cannot leave a partial edit batch.
    """
    providers = MODEL_ROUTER.compatible(
        task_type="coding", requires_tools=True, requires_structured_output=True,
        preferred_provider=task.provider
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


def _run_tests_safe(task: TaskRecord, repository_id: str):
    return TEST_AGENT.run(task, repository_id)


def run_task(
    repository_id: str,
    description: str,
    max_iterations: int = 5,
    *,
    task_id: str | None = None,
    provider: str | None = None,
) -> TaskRecord:
    """Run safe local analysis; pause honestly before any unconfigured LLM work."""
    task = TaskRecord(
        id=task_id or str(uuid.uuid4()),
        repository_id=repository_id,
        description=description,
        status=TaskStatus.RUNNING,
        phase="validate",
        provider=provider,
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
        selected_provider = MODEL_ROUTER.select(
            task_type="coding", requires_tools=True, requires_structured_output=True,
            preferred_provider=provider
        )
        _event(
            task,
            "provider",
            f"Selected {selected_provider.descriptor.provider}/{selected_provider.descriptor.model} for the coding operation.",
        )

        # Select a DIFFERENT provider for test writing (avoids the coder
        # writing tests that are biased towards its own implementation).
        test_provider = _select_test_writing_provider(selected_provider.descriptor.provider)
        if test_provider and test_provider.descriptor.provider != selected_provider.descriptor.provider:
            _event(
                task,
                "provider",
                f"Selected {test_provider.descriptor.provider}/{test_provider.descriptor.model} as the independent test-writing provider.",
            )
        else:
            test_provider = selected_provider
            _event(
                task,
                "provider",
                "Only one provider configured — using the same provider for test writing.",
                "warning",
            )

        try:
            generated_plan = PlannerAgent(selected_provider).create(description, task.retrieved_context)
            task.plan = generated_plan.steps
            _event(
                task,
                "plan",
                "Created a dynamic structured implementation and verification plan.",
            )
        except Exception as exc:
            _event(
                task,
                "plan",
                f"Dynamic planning failed ({type(exc).__name__}), falling back to deterministic plan.",
                "warning",
            )

        def safe_coding_run(task: TaskRecord, prompt: str, repo: str):
            return _run_coding_with_fallback(task, prompt, repo)

        def safe_test_writing_run(task: TaskRecord, repo: str):
            """Write tests using the secondary provider against the real implementation."""
            root = repository_root(repo)
            try:
                return TestWriterAgent(test_provider).write(
                    description, root, task.retrieved_context
                )
            except (ProviderRateLimitError, ProviderQuotaExhaustedError, ProviderRequestError) as exc:
                raise  # Re-raise provider errors so callers can handle them.
            except Exception as exc:
                raise ValueError(f"Test writer failed: {exc}") from exc

        task = run_graph(
            task=task,
            description=description,
            repository_id=repository_id,
            max_iterations=max_iterations,
            run_coding_fn=safe_coding_run,
            run_test_writing_fn=safe_test_writing_run,
            run_tests_fn=_run_tests_safe,
        )
        return task
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
