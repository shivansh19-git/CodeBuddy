from app.schemas import TaskRecord, TaskStatus
from app.schemas import TestResult as AgentTestResult
from app.workflow import _can_retry_tests


def _task_with_tests(result: AgentTestResult) -> TaskRecord:
    return TaskRecord(
        id="task",
        repository_id="repo",
        description="task",
        status=TaskStatus.RUNNING,
        phase="test",
        tests=result,
    )


def test_retry_only_for_actionable_test_failures():
    assert _can_retry_tests(_task_with_tests(AgentTestResult(failed=1, output="1 failed")))
    assert not _can_retry_tests(_task_with_tests(AgentTestResult(no_tests_collected=True)))
    assert not _can_retry_tests(
        _task_with_tests(AgentTestResult(output="ENVIRONMENT_ERROR: Docker unavailable"))
    )
