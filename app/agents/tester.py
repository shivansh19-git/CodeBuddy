"""Typed test agent that delegates execution to the sandbox tool."""

from app.schemas import TaskRecord, TestResult
from app.tools.execution import run_tests


class TestAgent:
    """Execute pytest and return the actual structured result."""

    def run(self, task: TaskRecord, repository_id: str) -> TestResult:
        """Run tests for the given repository.

        The ``task`` argument is accepted for API consistency with the graph
        callback signature ``(task, repository_id) -> TestResult`` but is not
        used here — all context needed for execution is the repository path.
        """
        return run_tests(repository_id)
