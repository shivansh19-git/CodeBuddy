from app.agents.planner import PlannerAgent
from app.review import build_review
from app.schemas import Symbol, TaskRecord, TaskStatus
from app.schemas import TestResult as AgentTestResult


def test_planner_fallback_produces_structured_plan():
    plan = PlannerAgent.fallback(
        "Add a user",
        [Symbol(file="users.py", name="create", kind="function", start_line=1, end_line=2)],
    )
    assert plan.goal == "Add a user"
    assert plan.files_likely_affected == ["users.py"]


def test_review_is_approved_only_with_real_passing_tests():
    task = TaskRecord(
        id="task",
        repository_id="repo",
        description="task",
        status=TaskStatus.COMPLETED,
        phase="review",
        tests=AgentTestResult(success=True, passed=2),
        iterations=1,
    )
    review = build_review(task)
    assert review.approved
    assert review.score == 9.0
