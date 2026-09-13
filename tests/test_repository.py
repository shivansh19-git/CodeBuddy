import os
import time
from pathlib import Path

import pytest

from app.repository import REPOSITORIES, _inside, cleanup_expired_workspaces, repository_root
from app.sandbox.security import UnsafeCommandError, allowed_argv
from app.tools.filesystem import ToolPathError, create_file, read_file, replace_once


def test_inside_rejects_path_traversal(tmp_path: Path):
    """The extraction guard must never permit a file outside the task root."""
    assert _inside(tmp_path, tmp_path / "safe.py")
    assert not _inside(tmp_path, tmp_path.parent / "escape.py")


def test_repository_root_restores_workspace_from_disk(tmp_path: Path, monkeypatch):
    """A backend restart can restore a workspace created with its repository ID."""
    monkeypatch.setattr("app.repository.settings.workspace_root", tmp_path)
    repo_id = "example-id"
    (tmp_path / repo_id).mkdir()
    REPOSITORIES.pop(repo_id, None)
    assert repository_root(repo_id) == tmp_path / repo_id


def test_workspace_cleanup_removes_only_expired_uuid_directories(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.repository.settings.workspace_root", tmp_path)
    monkeypatch.setattr("app.repository.settings.workspace_ttl_hours", 1)
    expired = tmp_path / "5de6d29f-3993-4387-934e-ecffb1ef7416"
    protected = tmp_path / "not-a-workspace"
    expired.mkdir()
    protected.mkdir()
    os.utime(expired, (time.time() - 7200, time.time() - 7200))
    assert cleanup_expired_workspaces() == 1
    assert not expired.exists()
    assert protected.exists()


def test_filesystem_tool_rejects_workspace_escape(tmp_path: Path):
    with pytest.raises(ToolPathError):
        create_file(tmp_path, "../outside.py", "unsafe")


def test_filesystem_tool_applies_exact_single_edit(tmp_path: Path):
    create_file(tmp_path, "example.py", "answer = 41\n")
    replace_once(tmp_path, "example.py", "41", "42")
    assert read_file(tmp_path, "example.py") == "answer = 42\n"


def test_sandbox_command_allowlist_rejects_shell_input():
    assert allowed_argv("pytest") == ["python", "-m", "pytest", "-q"]
    with pytest.raises(UnsafeCommandError):
        allowed_argv("pytest; rm -rf /")
