"""LangGraph correction-loop state graph.

Replaces the manual ``while _can_retry_tests`` loop in ``workflow.py`` with an
explicit state machine that makes every transition observable and testable.

Node execution order:
  implement_node → write_tests_node → test_node → [debug_node → test_node]* → review_node

The conditional edge after ``test_node`` re-enters ``debug_node`` on every
actionable test failure until ``max_iterations`` is exhausted, then falls
through to ``review_node`` so the task is always resolved cleanly.
"""

import logging
from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.coder import CodingAgent, CodingResult
from app.repository import original_repository_root, repository_root
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
    run_test_writing_fn: Callable[[TaskRecord, str], object]  # -> CodingResult
    run_tests_fn: Callable[[TaskRecord, str], TestResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(task: TaskRecord, phase: str, message: str, level: str = "info") -> None:
    task.phase = phase
    task.events.append(ActivityEvent(phase=phase, message=message, level=level))


def _can_retry(task: TaskRecord) -> bool:
    """Return True if another correction attempt is warranted.

    A retry is skipped only when the test infrastructure itself is broken
    (ENVIRONMENT_ERROR). Both real test failures *and* missing test files are
    retryable — the debug prompt is tailored to each case separately.
    """
    return not task.tests.success and not task.tests.output.startswith("ENVIRONMENT_ERROR:")


def _update_total_diff(task: TaskRecord, repository_id: str) -> None:
    """Compute the total diff from the pristine workspace to the current state."""
    orig = original_repository_root(repository_id)
    curr = repository_root(repository_id)
    before = CodingAgent._snapshot(orig)
    after = CodingAgent._snapshot(curr)
    task.diff = CodingAgent._diff(before, after)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def implement_node(state: GraphState) -> GraphState:
    """Call the coding provider and apply validated edits to the workspace."""
    task = state["task"]
    
    prompt = (
        f"Goal: {state['description']}\n\n"
        f"Plan:\n" + "\n".join(f"- {step}" for step in (task.plan or [])) + "\n\n"
        "Important: You MUST write tests for your implementation inside a `tests/` directory (e.g., `tests/test_feature.py`). Pytest ignores tests in the root directory."
    ) if task.plan else state["description"]
    
    coding_result = state["run_coding_fn"](task, prompt, state["repository_id"])
    task.modified_files = coding_result.modified_files
    _update_total_diff(task, state["repository_id"])
    task.iterations = 1
    _event(
        task,
        "implement",
        f"Applied {len(coding_result.modified_files)} validated file edit(s): {coding_result.summary}",
    )
    return state


def write_tests_node(state: GraphState) -> GraphState:
    """Ask the test-writing provider to create tests that match the real implementation.

    This node runs AFTER implement_node so the test writer reads the actual
    generated code from disk — it never guesses what the implementation looks
    like. Using a separate provider from the coder gives a fresh, unbiased
    perspective on what the correct test assertions should be.
    """
    task = state["task"]
    _event(task, "test", "Writing tests against the generated implementation…")
    try:
        result = state["run_test_writing_fn"](task, state["repository_id"])
        task.modified_files = sorted(set(task.modified_files + result.modified_files))
        _update_total_diff(task, state["repository_id"])
        _event(
            task,
            "test",
            f"Test file written by secondary provider: {result.summary}",
        )
    except Exception as exc:
        # Non-fatal: if the test writer fails, fall through to the test runner
        # which will report 'no tests collected' and trigger the debug loop.
        _event(
            task,
            "test",
            f"Test writer could not produce a test file ({type(exc).__name__}); debug loop will retry.",
            "warning",
        )
    return state


def _invoke_run_tests(fn: Callable, task: TaskRecord, repo_id: str) -> TestResult:
    try:
        return fn(task, repo_id)
    except TypeError:
        return fn(repo_id)


def test_node(state: GraphState) -> GraphState:
    """Run pytest inside the sandbox and record the result as a timeline event."""
    task = state["task"]
    task.tests = _invoke_run_tests(state["run_tests_fn"], task, state["repository_id"])
    # Always emit a visible event so the activity timeline reflects test status.
    if task.tests.success:
        _event(
            task,
            "test",
            f"Tests passed: {task.tests.passed} passed"
            + (f", {task.tests.skipped} skipped" if task.tests.skipped else "")
            + f" ({task.tests.runtime_seconds:.1f}s).",
        )
    elif task.tests.no_tests_collected:
        _event(
            task,
            "test",
            "No tests were collected — the model must create a tests/test_*.py file.",
            "warning",
        )
    else:
        _event(
            task,
            "test",
            f"Tests failed: {task.tests.failed} failed, {task.tests.errors} errors"
            + (f", {task.tests.passed} passed" if task.tests.passed else "")
            + f" ({task.tests.runtime_seconds:.1f}s).",
            "warning",
        )
    return state


def debug_node(state: GraphState) -> GraphState:
    """Feed pytest output back to the provider for a targeted correction attempt.

    Two distinct prompt strategies are used:
    - ``no_tests_collected``: the model forgot to create a test file; instruct
      it to create one without touching the implementation.
    - real failures: the model's code or tests are wrong; instruct it to fix
      the specific failing assertions.
    """
    task = state["task"]
    attempt = task.iterations + 1
    _event(
        task,
        "debug",
        f"{'No tests found' if task.tests.no_tests_collected else 'Tests failed'};"
        f" launching correction attempt {attempt} of {state['max_iterations']}.",
        "warning",
    )

    if task.tests.no_tests_collected:
        # The model did not produce any discoverable tests.
        debug_prompt = (
            f"Original task: {state['description']}\n\n"
            "### CRITICAL: NO TESTS WERE FOUND\n"
            "Pytest ran but collected 0 test items. This means you did NOT create a test file,"
            " or you created it in the wrong location.\n\n"
            "### YOU MUST DO THE FOLLOWING\n"
            "1. Create a NEW file at `tests/test_<feature>.py` (e.g. `tests/test_main.py`).\n"
            "2. The file MUST contain at least one function named `def test_...()`.\n"
            "3. Each test function MUST import from the implementation and assert correct behaviour.\n"
            "4. Do NOT touch the implementation file — only create/fix the test file.\n"
            "5. Do NOT place tests in the repository root; pytest is configured to discover"
            " only inside `tests/`.\n\n"
            f"### LAST PYTEST OUTPUT\n{task.tests.output[-4000:]}"
        )
    else:
        # Tests were found but one or more assertions failed.
        debug_prompt = (
            f"Original task: {state['description']}\n\n"
            "The last implementation failed pytest. Fix the code or the test so all assertions pass.\n\n"
            "### DEBUGGING RULES (STRICT)\n"
            "1. DO NOT insert mocks, fake classes, or `MagicMock` into the implementation to force tests to pass."
            " Implementation code must remain real and correct.\n"
            "2. DEPENDENCIES: If your code uses external libraries, write them into `requirements.txt`"
            " using a `create` action. The runner installs them automatically.\n"
            "3. Do NOT refactor the implementation (e.g. wrapping in `main()`) just to satisfy tests."
            " Keep the implementation as the user requested.\n"
            "4. Check imports: does the test import from the correct module and function name?\n"
            "5. Check assertions: are the expected values correct for the implementation's behaviour?\n\n"
            f"### PYTEST OUTPUT (last 6000 chars)\n{task.tests.output[-6000:]}"
        )

    correction = state["run_coding_fn"](task, debug_prompt, state["repository_id"])
    task.iterations += 1
    task.modified_files = sorted(set(task.modified_files + correction.modified_files))
    _update_total_diff(task, state["repository_id"])
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
    graph.add_node("write_tests_node", write_tests_node)
    graph.add_node("test_node", test_node)
    graph.add_node("debug_node", debug_node)
    graph.add_node("review_node", review_node)

    graph.set_entry_point("implement_node")
    graph.add_edge("implement_node", "write_tests_node")
    graph.add_edge("write_tests_node", "test_node")
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
    run_test_writing_fn: Callable | None = None,
) -> TaskRecord:
    """Execute the correction-loop graph and return the mutated TaskRecord.

    Args:
        task: The in-progress TaskRecord (already has plan and retrieved context).
        description: Original user task description.
        repository_id: Workspace identifier passed to the coding and test runners.
        max_iterations: Maximum total attempts (initial + corrections).
        run_coding_fn: Callable matching ``(task, prompt, repository_id) -> CodingResult``.
        run_tests_fn: Callable matching ``(task, repository_id) -> TestResult``.
        run_test_writing_fn: Optional callable matching ``(task, repository_id) -> CodingResult``.
    """
    if run_test_writing_fn is None:
        run_test_writing_fn = lambda t, r: CodingResult(summary="tests verified", modified_files=[], diff="")

    initial_state: GraphState = {
        "task": task,
        "description": description,
        "repository_id": repository_id,
        "max_iterations": max_iterations,
        "run_coding_fn": run_coding_fn,
        "run_test_writing_fn": run_test_writing_fn,
        "run_tests_fn": run_tests_fn,
    }
    final_state = _get_graph().invoke(initial_state)
    return final_state["task"]
