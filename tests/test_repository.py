from pathlib import Path

import pytest

from app.repository import _inside
from app.sandbox.security import UnsafeCommandError, allowed_argv
from app.tools.filesystem import ToolPathError, create_file, read_file, replace_once


def test_inside_rejects_path_traversal(tmp_path: Path):
    """The extraction guard must never permit a file outside the task root."""
    assert _inside(tmp_path, tmp_path / "safe.py")
    assert not _inside(tmp_path, tmp_path.parent / "escape.py")


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
