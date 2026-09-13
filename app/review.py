"""Honest deterministic final review for the MVP."""

from app.schemas import ReviewResult, TaskRecord


def build_review(task: TaskRecord) -> ReviewResult:
    """Review verifiable evidence without invented LLM analysis."""
    if task.tests.success:
        return ReviewResult(
            approved=True,
            score=9.0 if task.iterations == 1 else 8.0,
            suggestions=["Inspect the exported diff before merging."],
        )
    if task.tests.no_tests_collected:
        return ReviewResult(
            approved=False,
            score=2.0,
            issues=["Pytest collected no tests, so behavior is unverified."],
            suggestions=["Add a discoverable test_*.py file with relevant test_ functions."],
        )
    if task.tests.output.startswith("ENVIRONMENT_ERROR:"):
        return ReviewResult(
            approved=False,
            score=1.0,
            issues=["The Docker sandbox was unavailable; tests did not execute."],
            suggestions=["Start Docker Desktop and rebuild the sandbox image if required."],
        )
    return ReviewResult(
        approved=False,
        score=3.0,
        issues=["One or more pytest failures remain."],
        suggestions=["Inspect the final pytest traceback and correct the failing behavior."],
    )


def review_summary(result: ReviewResult) -> str:
    """Short presentation text derived from the typed review contract."""
    state = "approved" if result.approved else "not approved"
    detail = result.issues[0] if result.issues else "All available checks passed."
    return f"Automated review {state} (score {result.score}/10): {detail}"
