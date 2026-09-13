"""Typed test agent that delegates execution to the Docker-only tool."""

from app.schemas import TestResult
from app.tools.execution import run_tests


class TestAgent:
    """Execute pytest and return the actual structured result."""

    def run(self, repository_id: str) -> TestResult:
        return run_tests(repository_id)
