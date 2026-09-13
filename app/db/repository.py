"""Minimal SQLite storage that keeps task records across API restarts.

Repository source is intentionally not stored in the database; it remains in
the temporary workspace directory and may be cleaned up separately.
"""

import sqlite3
from pathlib import Path

from app.schemas import TaskRecord


class TaskStore:
    """Persist the complete typed task record as validated JSON."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def save(self, task: TaskRecord) -> None:
        """Upsert a task after each public state transition."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks(id, repository_id, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, repository_id=excluded.repository_id",
                (task.id, task.repository_id, task.model_dump_json()),
            )

    def get(self, task_id: str) -> TaskRecord | None:
        """Load and revalidate a task record, returning None when it is absent."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return TaskRecord.model_validate_json(row[0]) if row else None

    def list_recent(self, limit: int = 10) -> list[TaskRecord]:
        """Return most recently written tasks for the dashboard/history panel."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM tasks ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TaskRecord.model_validate_json(row[0]) for row in rows]
