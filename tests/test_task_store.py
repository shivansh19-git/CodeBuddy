from app.db.repository import TaskStore
from app.schemas import TaskRecord, TaskStatus


def test_task_store_round_trips_a_task(tmp_path):
    store = TaskStore(tmp_path / "app.db")
    task = TaskRecord(
        id="task-1",
        repository_id="repo-1",
        description="Fix a bug",
        status=TaskStatus.RUNNING,
        phase="plan",
    )
    store.save(task)
    restored = store.get("task-1")
    assert restored is not None
    assert restored.description == "Fix a bug"


def test_task_store_lists_most_recent_task_first(tmp_path):
    store = TaskStore(tmp_path / "app.db")
    for identifier in ["first", "second"]:
        store.save(
            TaskRecord(
                id=identifier,
                repository_id="repo",
                description=identifier,
                status=TaskStatus.RUNNING,
                phase="plan",
            )
        )
    assert [task.id for task in store.list_recent()] == ["second", "first"]
