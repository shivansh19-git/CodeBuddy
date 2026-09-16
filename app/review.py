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
        detail = task.tests.output.replace("ENVIRONMENT_ERROR:", "").strip()
        return ReviewResult(
            approved=False,
            score=1.0,
            issues=[f"Environment Error: {detail or 'Test runner unavailable.'}"],
            suggestions=["Verify that pytest is installed on the server environment."],
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
