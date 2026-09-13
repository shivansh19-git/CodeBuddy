import pytest
from pydantic import ValidationError

from app.schemas import TaskRequest


def test_task_requires_room_for_an_initial_attempt_and_one_retry():
    with pytest.raises(ValidationError):
        TaskRequest(repository_id="repo", description="A valid task", max_iterations=1)
    request = TaskRequest(repository_id="repo", description="A valid task", max_iterations=2)
    assert request.max_iterations == 2
