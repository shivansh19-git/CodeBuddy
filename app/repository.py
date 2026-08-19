"""Safe repository ingestion and AST-based code understanding.

This module deliberately accepts only Python project files and verifies every
path before extraction. That is the first boundary between untrusted uploads
and our host machine.
"""

import ast
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.schemas import RepositorySummary, Symbol

IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
}
REPOSITORIES: dict[str, Path] = {}


def _inside(root: Path, candidate: Path) -> bool:
    """Return True only when *candidate* resolves under *root*."""
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relevant_files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*")
        if p.is_file() and not any(part in IGNORED_PARTS for part in p.parts)
    ]


def _validate_limits(root: Path) -> None:
    """Apply both file-count and *uncompressed* size limits after ingestion."""
    files = _relevant_files(root)
    if len(files) > settings.max_repository_files:
        raise HTTPException(413, "Repository exceeds configured file-count limit.")
    total_bytes = sum(file.stat().st_size for file in files)
    if total_bytes > settings.max_repository_size_mb * 1024 * 1024:
        raise HTTPException(413, "Repository exceeds configured uncompressed size limit.")


async def save_zip(upload: UploadFile) -> str:
    """Validate then extract a ZIP without allowing archive path traversal."""
    payload = await upload.read()
    if len(payload) > settings.max_repository_size_mb * 1024 * 1024:
        raise HTTPException(413, "Upload exceeds configured repository size limit.")
    repo_id, root = str(uuid.uuid4()), settings.workspace_root / str(uuid.uuid4())
    root.mkdir(parents=True, exist_ok=False)
    archive = root / "upload.zip"
    archive.write_bytes(payload)
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > settings.max_repository_files:
                raise HTTPException(413, "Archive exceeds configured file-count limit.")
            for info in infos:
                destination = root / info.filename
                if info.is_dir() or not _inside(root, destination):
                    if not info.is_dir():
                        raise HTTPException(400, "Archive contains an unsafe path.")
                    continue
                zf.extract(info, root)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(400, "File is not a valid ZIP archive.") from exc
    finally:
        archive.unlink(missing_ok=True)
    project_root = _normalise_root(root)
    try:
        _validate_limits(project_root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    REPOSITORIES[repo_id] = project_root
    return repo_id


def clone_public_github(url: str) -> str:
    """Clone only a public github.com HTTPS URL, using a constrained command."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise HTTPException(400, "Only public https://github.com URLs are supported.")
    repo_id, root = str(uuid.uuid4()), settings.workspace_root / str(uuid.uuid4())
    root.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(root)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise HTTPException(400, "Could not clone the public repository.")
    try:
        _validate_limits(root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    REPOSITORIES[repo_id] = root
    return repo_id


def _normalise_root(root: Path) -> Path:
    """ZIPs often contain one top-level folder; use it as the project root."""
    children = [p for p in root.iterdir() if p.name != "upload.zip"]
    return children[0] if len(children) == 1 and children[0].is_dir() else root


def analyze_repository(repo_id: str) -> RepositorySummary:
    if repo_id not in REPOSITORIES:
        raise HTTPException(404, "Repository was not found (it may have expired).")
    root = REPOSITORIES[repo_id]
    files = _relevant_files(root)
    py_files = [p for p in files if p.suffix == ".py"]
    symbols: list[Symbol] = []
    for file in py_files:
        relative = file.relative_to(root).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=relative)
        except (UnicodeDecodeError, SyntaxError):
            continue  # Broken source is reported later by test execution.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                args = getattr(node, "args", None)
                signature = f"({', '.join(a.arg for a in args.args)})" if args else ""
                symbols.append(
                    Symbol(
                        file=relative,
                        name=node.name,
                        kind="class" if isinstance(node, ast.ClassDef) else "function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        signature=signature,
                        docstring=ast.get_docstring(node),
                    )
                )
    return RepositorySummary(
        name=root.name,
        file_count=len(files),
        python_files=len(py_files),
        test_files=sum(1 for p in py_files if "test" in p.name.lower() or "tests" in p.parts),
        package_files=[
            p.relative_to(root).as_posix()
            for p in files
            if p.name in {"pyproject.toml", "requirements.txt", "setup.py", "README.md"}
        ],
        symbols=symbols,
    )
