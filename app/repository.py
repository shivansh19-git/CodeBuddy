"""Safe repository ingestion and AST-based code understanding.

This module deliberately accepts only Python project files and verifies every
path before extraction. That is the first boundary between untrusted uploads
and our host machine.
"""

import ast
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.rag.cache import IndexCache, compute_content_hash
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


def original_repository_root(repo_id: str) -> Path:
    """Find the pristine original workspace created upon upload/clone."""
    orig_dir = settings.workspace_root / f"{repo_id}_original"
    if orig_dir.is_dir():
        return _normalise_root(orig_dir)
    return repository_root(repo_id)


def _create_original_snapshot(repo_id: str, project_root: Path) -> None:
    """Backup pristine repository files before any agent or manual edits occur."""
    orig_dir = settings.workspace_root / f"{repo_id}_original"
    if orig_dir.exists():
        shutil.rmtree(orig_dir, ignore_errors=True)
    shutil.copytree(project_root, orig_dir, dirs_exist_ok=True)


def repository_root(repo_id: str) -> Path:
    """Find an active workspace, restoring it from disk after an API restart.

    New workspaces use the repository ID as their directory name. The in-memory
    mapping is therefore only a speed-up, not the source of truth.
    """
    if repo_id in REPOSITORIES:
        return REPOSITORIES[repo_id]
    disk_root = settings.workspace_root / repo_id
    if disk_root.is_dir():
        # Match ZIP-upload behavior, where one wrapping directory is treated
        # as the actual project root rather than an extra path level.
        restored_root = _normalise_root(disk_root)
        REPOSITORIES[repo_id] = restored_root
        return restored_root
    raise HTTPException(404, "Repository was not found (it may have expired).")


def cleanup_expired_workspaces() -> int:
    """Remove only UUID-named task workspaces older than the configured TTL."""
    root = settings.workspace_root.resolve()
    if not root.is_dir():
        return 0
    cutoff = time.time() - settings.workspace_ttl_hours * 3600
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_dir() or candidate.stat().st_mtime >= cutoff:
            continue
        try:
            uuid.UUID(candidate.name)
            candidate.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        shutil.rmtree(candidate)
        orig_candidate = settings.workspace_root / f"{candidate.name}_original"
        if orig_candidate.is_dir():
            shutil.rmtree(orig_candidate, ignore_errors=True)
        REPOSITORIES.pop(candidate.name, None)
        removed += 1
    return removed


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
    cleanup_expired_workspaces()
    payload = await upload.read()
    if len(payload) > settings.max_repository_size_mb * 1024 * 1024:
        raise HTTPException(413, "Upload exceeds configured repository size limit.")
    repo_id = str(uuid.uuid4())
    root = settings.workspace_root / repo_id
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
    _create_original_snapshot(repo_id, project_root)
    REPOSITORIES[repo_id] = project_root
    return repo_id


async def save_python_files(uploads: list[UploadFile]) -> str:
    """Create a small task repository from one or more `.py` uploads.

    Browser-uploaded filenames are reduced to their basename, so a malicious
    name such as `../../secret.py` cannot choose a host filesystem location.
    Duplicate names receive a predictable suffix instead of overwriting data.
    """
    cleanup_expired_workspaces()
    if not uploads:
        raise HTTPException(400, "Upload at least one Python file.")
    if len(uploads) > settings.max_repository_files:
        raise HTTPException(413, "Upload exceeds configured file-count limit.")
    repo_id = str(uuid.uuid4())
    root = settings.workspace_root / repo_id
    root.mkdir(parents=True, exist_ok=False)
    total_bytes = 0
    try:
        for upload in uploads:
            filename = Path(upload.filename or "").name
            if not filename or Path(filename).suffix.lower() != ".py":
                raise HTTPException(400, "Only .py files may be uploaded in this input mode.")
            payload = await upload.read()
            total_bytes += len(payload)
            if total_bytes > settings.max_repository_size_mb * 1024 * 1024:
                raise HTTPException(413, "Uploads exceed configured repository size limit.")
            destination = root / filename
            counter = 2
            while destination.exists():
                destination = root / f"{Path(filename).stem}_{counter}.py"
                counter += 1
            destination.write_bytes(payload)
        _validate_limits(root)
        _create_original_snapshot(repo_id, root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    REPOSITORIES[repo_id] = root
    return repo_id


def clone_public_github(url: str) -> str:
    """Clone only a public github.com HTTPS URL, using a constrained command."""
    cleanup_expired_workspaces()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise HTTPException(400, "Only public https://github.com URLs are supported.")
    repo_id = str(uuid.uuid4())
    root = settings.workspace_root / repo_id
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
        _create_original_snapshot(repo_id, root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    REPOSITORIES[repo_id] = root
    return repo_id


def _normalise_root(root: Path) -> Path:
    """ZIPs often contain one top-level folder; use it as the project root."""
    children = [p for p in root.iterdir() if p.name != "upload.zip"]
    return children[0] if len(children) == 1 and children[0].is_dir() else root


INDEX_CACHE = IndexCache(settings.workspace_root / ".cache" / "index_cache.json")


def analyze_repository(repo_id: str) -> RepositorySummary:
    root = repository_root(repo_id)
    files = _relevant_files(root)
    py_files = [p for p in files if p.suffix == ".py"]
    symbols: list[Symbol] = []
    for file in py_files:
        relative = file.relative_to(root).as_posix()
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        content_hash = compute_content_hash(content)
        cached_symbols = INDEX_CACHE.get_symbols(content_hash)
        if cached_symbols is not None:
            symbols.extend(
                [
                    s
                    if s.file == relative
                    else Symbol(
                        file=relative,
                        name=s.name,
                        kind=s.kind,
                        start_line=s.start_line,
                        end_line=s.end_line,
                        signature=s.signature,
                        docstring=s.docstring,
                    )
                    for s in cached_symbols
                ]
            )
            continue
        try:
            tree = ast.parse(content, filename=relative)
        except SyntaxError:
            continue  # Broken source is reported later by test execution.
        file_symbols: list[Symbol] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                args = getattr(node, "args", None)
                signature = f"({', '.join(a.arg for a in args.args)})" if args else ""
                file_symbols.append(
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
        INDEX_CACHE.set_symbols(content_hash, file_symbols)
        INDEX_CACHE.save()
        symbols.extend(file_symbols)
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
