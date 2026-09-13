"""LangGraph correction-loop state graph.

Replaces the manual ``while _can_retry_tests`` loop in ``workflow.py`` with an
explicit state machine that makes every transition observable and testable.

Node execution order:
  implement_node → test_node → [debug_node → test_node]* → review_node

The conditional edge after ``test_node`` re-enters ``debug_node`` on every
actionable test failure until ``max_iterations`` is exhausted, then falls
through to ``review_node`` so the task is always resolved cleanly.
"""

import logging
from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from app.review import build_review, review_summary
from app.schemas import ActivityEvent, TaskRecord, TaskStatus, TestResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class GraphState(TypedDict):
    """Shared mutable state threaded through every graph node."""

    task: TaskRecord
    description: str
    repository_id: str
    max_iterations: int
    # Callables injected at graph-build time so the graph itself has no
    # direct dependency on LLM providers or the Docker sandbox.
    run_coding_fn: Callable[[TaskRecord, str, str], object]  # -> CodingResult
    run_tests_fn: Callable[[str], TestResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(task: TaskRecord, phase: str, message: str, level: str = "info") -> None:
    task.phase = phase
    task.events.append(ActivityEvent(phase=phase, message=message, level=level))


def _can_retry(task: TaskRecord) -> bool:
    """Mirror the guard used in the original workflow loop."""
    return (
        not task.tests.success
        and not task.tests.output.startswith("ENVIRONMENT_ERROR:")
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def implement_node(state: GraphState) -> GraphState:
    """Call the coding provider and apply validated edits to the workspace."""
    task = state["task"]
    coding_result = state["run_coding_fn"](task, state["description"], state["repository_id"])
    task.modified_files = coding_result.modified_files
    task.diff = coding_result.diff
    task.iterations = 1
    _event(
        task,
        "implement",
        f"Applied {len(coding_result.modified_files)} validated file edit(s): {coding_result.summary}",
    )
    return state


def test_node(state: GraphState) -> GraphState:
    """Run pytest inside the Docker sandbox and record the result."""
    task = state["task"]
    task.tests = state["run_tests_fn"](state["repository_id"])
    return state


def debug_node(state: GraphState) -> GraphState:
    """Feed pytest failure output back to the provider for a correction attempt."""
    task = state["task"]
    _event(
        task,
        "debug",
        f"Tests failed; analyzing feedback before correction attempt {task.iterations + 1}"
        f" of {state['max_iterations']}.",
        "warning",
    )
    debug_prompt = (
        f"Original task: {state['description']}\n\n"
        "The last implementation failed pytest. Correct the implementation or its test so it matches the original task.\n\n"
        "### DEBUGGING RULES (STRICT)\n"
        "1. DO NOT insert mocks, fake classes, placeholders, or `MagicMock` into the actual implementation code to force tests to pass. Implementation code must remain real.\n"
        "2. All mocking MUST be done inside the test files. To prevent tests from crashing on import due to top-level execution or missing dependencies, mock the required modules using `sys.modules` INSIDE the test file BEFORE importing the target script.\n"
        "3. Do NOT refactor the implementation code (e.g., wrapping in `main()`) or add `subprocess` installations just to make tests pass. Keep the implementation file exactly as requested by the user.\n"
        "4. Did you accidentally modify the wrong file or variable? Ensure your test code correctly targets the implementation.\n"
        "5. If Pytest found no tests (collected 0 items), you MUST create a discoverable test file inside the `tests/` directory (e.g., `tests/test_*.py`) with at least one `test_` function. Pytest is configured to ignore tests in the root directory.\n\n"
        f"### PYTEST OUTPUT\n{task.tests.output[-6000:]}"
    )
    correction = state["run_coding_fn"](task, debug_prompt, state["repository_id"])
    task.iterations += 1
    task.modified_files = sorted(set(task.modified_files + correction.modified_files))
    task.diff += correction.diff
    _event(task, "debug", f"Applied correction {task.iterations}: {correction.summary}")
    return state


def review_node(state: GraphState) -> GraphState:
    """Build the evidence-based review and set the final task status."""
    task = state["task"]
    task.review_result = build_review(task)
    task.review = review_summary(task.review_result)
    if task.tests.success:
        task.status = TaskStatus.COMPLETED
        _event(
            task,
            "test",
            f"{task.tests.passed} test(s) passed in the Docker sandbox after"
            f" {task.iterations} attempt(s).",
        )
    elif task.tests.no_tests_collected:
        task.status = TaskStatus.FAILED
        _event(
            task,
            "test",
            "Pytest found no tests. Add or generate a test_*.py file.",
            "warning",
        )
    else:
        task.status = TaskStatus.FAILED
        _event(
            task,
            "test",
            f"Sandbox tests still failed after {task.iterations} attempt(s).",
            "warning",
        )
    return state


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_after_test(state: GraphState) -> str:
    """Return the next node name based on whether a retry is warranted."""
    task = state["task"]
    if _can_retry(task) and task.iterations < state["max_iterations"]:
        return "debug_node"
    return "review_node"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_correction_graph() -> StateGraph:
    """Construct and compile the correction-loop state graph."""
    graph = StateGraph(GraphState)

    graph.add_node("implement_node", implement_node)
    graph.add_node("test_node", test_node)
    graph.add_node("debug_node", debug_node)
    graph.add_node("review_node", review_node)

    graph.set_entry_point("implement_node")
    graph.add_edge("implement_node", "test_node")
    graph.add_conditional_edges(
        "test_node",
        _route_after_test,
        {"debug_node": "debug_node", "review_node": "review_node"},
    )
    graph.add_edge("debug_node", "test_node")
    graph.add_edge("review_node", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_COMPILED_GRAPH = None


def _get_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_correction_graph()
    return _COMPILED_GRAPH


def run_graph(
    task: TaskRecord,
    description: str,
    repository_id: str,
    max_iterations: int,
    run_coding_fn: Callable,
    run_tests_fn: Callable,
) -> TaskRecord:
    """Execute the correction-loop graph and return the mutated TaskRecord.

    Args:
        task: The in-progress TaskRecord (already has plan and retrieved context).
        description: Original user task description.
        repository_id: Workspace identifier passed to the coding and test runners.
        max_iterations: Maximum total attempts (initial + corrections).
        run_coding_fn: Callable matching ``(task, prompt, repository_id) -> CodingResult``.
        run_tests_fn: Callable matching ``(repository_id) -> TestResult``.
    """
    initial_state: GraphState = {
        "task": task,
        "description": description,
        "repository_id": repository_id,
        "max_iterations": max_iterations,
        "run_coding_fn": run_coding_fn,
        "run_tests_fn": run_tests_fn,
    }
    final_state = _get_graph().invoke(initial_state)
    return final_state["task"]
