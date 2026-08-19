"""High-level test tool: converts sandbox output into the typed API schema."""

import re

from app.repository import REPOSITORIES
from app.sandbox.docker import SandboxUnavailableError, run_in_sandbox
from app.schemas import TestResult


def run_tests(repository_id: str) -> TestResult:
    """Run pytest only in Docker; report unavailable infrastructure precisely."""
    try:
        result = run_in_sandbox(REPOSITORIES[repository_id], "pytest")
    except SandboxUnavailableError as exc:
        return TestResult(errors=1, success=False, output=f"ENVIRONMENT_ERROR: {exc}")

    def count(label: str) -> int:
        match = re.search(rf"(\d+) {label}\b", result.output)
        return int(match.group(1)) if match else 0

    return TestResult(
        passed=count("passed"),
        failed=count("failed"),
        errors=count("error"),
        skipped=count("skipped"),
        runtime_seconds=result.runtime_seconds,
        success=result.return_code == 0 and not result.timed_out,
        output=result.output,
    )
