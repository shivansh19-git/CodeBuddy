"""High-level test tool: converts sandbox output into the typed API schema."""

import re

from app.repository import repository_root
from app.sandbox.docker import SandboxUnavailableError, run_in_sandbox
from app.sandbox.preparation import DependencyPreparationError, prepare_image
from app.schemas import TestResult


def run_tests(repository_id: str) -> TestResult:
    """Run pytest only in Docker; report unavailable infrastructure precisely."""
    try:
        root = repository_root(repository_id)
        result = run_in_sandbox(root, "pytest", image=prepare_image(root))
    except (DependencyPreparationError, SandboxUnavailableError) as exc:
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
        # pytest uses exit code 5 when it could not discover any tests.
        no_tests_collected=result.return_code == 5 or "no tests ran" in result.output.lower(),
        output=result.output,
    )
