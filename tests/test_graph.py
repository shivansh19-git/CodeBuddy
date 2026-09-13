"""Tests for the LangGraph correction-loop state graph (app/agents/graph.py).

All tests use lightweight stubs so they run without any LLM provider,
Docker sandbox, or network access.
"""

from dataclasses import dataclass

import pytest

from app.agents.graph import (
    GraphState,
    _can_retry,
    _route_after_test,
    build_correction_graph,
    run_graph,
)
from app.schemas import ActivityEvent, TaskRecord, TaskStatus, TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(**overrides) -> TaskRecord:
    defaults = dict(
        id="t1",
        repository_id="repo",
        description="fix it",
        status=TaskStatus.RUNNING,
        phase="implement",
    )
    defaults.update(overrides)
    return TaskRecord(**defaults)


@dataclass
class _FakeCodingResult:
    summary: str = "fake edit"
    modified_files: list = None
    diff: str = "--- a/f.py\n+++ b/f.py\n"

    def __post_init__(self):
        if self.modified_files is None:
            self.modified_files = ["f.py"]


def _make_state(
    task: TaskRecord,
    run_coding_fn=None,
    run_tests_fn=None,
    max_iterations: int = 3,
) -> GraphState:
    return GraphState(
        task=task,
        description="fix it",
        repository_id="repo",
        max_iterations=max_iterations,
        run_coding_fn=run_coding_fn or (lambda t, p, r: _FakeCodingResult()),
        run_tests_fn=run_tests_fn or (lambda r: TestResult(success=True, passed=1)),
    )


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------


def test_can_retry_actionable_failure():
    task = _make_task(tests=TestResult(failed=1, output="1 failed"))
    assert _can_retry(task) is True


def test_can_retry_no_on_environment_error():
    task = _make_task(tests=TestResult(output="ENVIRONMENT_ERROR: Docker unavailable"))
    assert _can_retry(task) is False



def test_can_retry_no_when_success():
    task = _make_task(tests=TestResult(success=True, passed=3))
    assert _can_retry(task) is False


# ---------------------------------------------------------------------------
# Unit tests — routing
# ---------------------------------------------------------------------------


def test_route_to_debug_when_retryable():
    task = _make_task(tests=TestResult(failed=1, output="1 failed"), iterations=1)
    state = _make_state(task, max_iterations=3)
    assert _route_after_test(state) == "debug_node"


def test_route_to_review_when_max_iterations_reached():
    task = _make_task(tests=TestResult(failed=1, output="1 failed"), iterations=3)
    state = _make_state(task, max_iterations=3)
    assert _route_after_test(state) == "review_node"


def test_route_to_review_when_tests_pass():
    task = _make_task(tests=TestResult(success=True, passed=2), iterations=1)
    state = _make_state(task, max_iterations=3)
    assert _route_after_test(state) == "review_node"


# ---------------------------------------------------------------------------
# Integration tests — full graph execution
# ---------------------------------------------------------------------------


def test_graph_success_path():
    """Graph completes on first attempt when tests pass immediately."""
    task = _make_task()
    result = run_graph(
        task=task,
        description="fix it",
        repository_id="repo",
        max_iterations=3,
        run_coding_fn=lambda t, p, r: _FakeCodingResult(),
        run_tests_fn=lambda r: TestResult(success=True, passed=2),
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.iterations == 1
    assert result.tests.passed == 2
    phases = [e.phase for e in result.events]
    assert "implement" in phases
    assert "test" in phases
    assert "debug" not in phases


def test_graph_self_correction_path():
    """Graph corrects once then succeeds on second attempt."""
    call_counts = {"tests": 0}

    def flaky_tests(repo_id: str) -> TestResult:
        call_counts["tests"] += 1
        # First run fails; second run succeeds.
        if call_counts["tests"] == 1:
            return TestResult(failed=1, output="1 failed")
        return TestResult(success=True, passed=1)

    task = _make_task()
    result = run_graph(
        task=task,
        description="fix it",
        repository_id="repo",
        max_iterations=3,
        run_coding_fn=lambda t, p, r: _FakeCodingResult(),
        run_tests_fn=flaky_tests,
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.iterations == 2
    debug_events = [e for e in result.events if e.phase == "debug"]
    assert len(debug_events) >= 1


def test_graph_exhausts_iterations():
    """Graph transitions to FAILED after max_iterations without passing tests."""
    task = _make_task()
    result = run_graph(
        task=task,
        description="fix it",
        repository_id="repo",
        max_iterations=2,
        run_coding_fn=lambda t, p, r: _FakeCodingResult(),
        run_tests_fn=lambda r: TestResult(failed=1, output="persistent failure"),
    )
    assert result.status == TaskStatus.FAILED
    assert result.iterations == 2


def test_graph_no_tests_collected():
    """FAILED with a specific message when pytest collects nothing."""
    task = _make_task()
    result = run_graph(
        task=task,
        description="fix it",
        repository_id="repo",
        max_iterations=3,
        run_coding_fn=lambda t, p, r: _FakeCodingResult(),
        run_tests_fn=lambda r: TestResult(no_tests_collected=True),
    )
    assert result.status == TaskStatus.FAILED
    assert any("no tests" in e.message.lower() for e in result.events)


def test_build_correction_graph_is_compilable():
    """build_correction_graph() must return a callable compiled graph."""
    graph = build_correction_graph()
    assert callable(graph.invoke)
