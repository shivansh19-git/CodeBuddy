"""Validated filesystem operations for a repository task workspace.

These APIs are intentionally narrower than shell access: each path is checked
before reading or writing, and edits are expressed as an exact replacement.
"""

from pathlib import Path


class ToolPathError(ValueError):
    """A task attempted to access a path outside its repository."""


def _resolve(root: Path, relative_path: str) -> Path:
    """Resolve a user/model path and reject absolute paths and traversal."""
    path = Path(relative_path)
    if path.is_absolute():
        raise ToolPathError("Only repository-relative paths are allowed.")
    destination = (root / path).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolPathError("Path escapes the repository workspace.") from exc
    return destination


def read_file(root: Path, relative_path: str) -> str:
    """Read UTF-8 text only from inside the active workspace."""
    return _resolve(root, relative_path).read_text(encoding="utf-8")


def create_file(root: Path, relative_path: str, content: str) -> None:
    """Create a new text file; refusing overwrite prevents accidental loss."""
    destination = _resolve(root, relative_path)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {relative_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def replace_once(root: Path, relative_path: str, old: str, new: str) -> None:
    """Apply an exact, single replacement instead of a dangerous full rewrite."""
    destination = _resolve(root, relative_path)
    current = destination.read_text(encoding="utf-8")
    if current.count(old) != 1:
        raise ValueError("Edit requires exactly one matching source fragment.")
    destination.write_text(current.replace(old, new, 1), encoding="utf-8")
