"""Constrained coding node driven by a provider's structured response.

This node deliberately supports only creating a file or replacing one exact
source fragment. That makes every model action explainable and rejects broad,
unreviewable file rewrites.
"""

import ast
import json
import re
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.models.base import LLMProvider
from app.schemas import Symbol
from app.tools.filesystem import create_file, read_file, replace_once

MAX_EDITS = 8
MAX_CONTENT_LENGTH = 40_000
ALLOWED_SUFFIXES = {".py", ".md", ".toml", ".txt"}


class EditOperation(BaseModel):
    """One narrow edit requested by the model."""

    action: Literal["create", "replace"]
    path: str = Field(min_length=1, max_length=260)
    old: str = ""  # Required for replace and ignored for create.
    new: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)


class CodingResponse(BaseModel):
    """The only response shape accepted from a coding provider."""

    summary: str = Field(min_length=1, max_length=1000)
    edits: list[EditOperation] = Field(min_length=1, max_length=MAX_EDITS)


@dataclass(frozen=True)
class CodingResult:
    """Public result of a coding node; it contains no private model reasoning."""

    summary: str
    modified_files: list[str]
    diff: str


class CodingAgent:
    """Ask a selected provider for edits and apply them through safe tools."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def execute(self, task: str, root: Path, context: list[Symbol]) -> CodingResult:
        """Generate, validate, and apply one bounded batch of requested edits."""
        response = self._parse(self.provider.generate(self._prompt(task, root, context)))
        before = self._snapshot(root)
        modified_files: list[str] = []
        try:
            for edit in response.edits:
                self._validate_edit(root, edit)
                if edit.action == "create":
                    create_file(root, edit.path, edit.new)
                else:
                    if not edit.old:
                        raise ValueError("A replace operation must include its exact old text.")
                    replace_once(root, edit.path, edit.old, edit.new)
                modified_files.append(edit.path)
            self._validate_python_sources(root)
        except Exception:
            self._restore_snapshot(root, before)
            raise
        after = self._snapshot(root)
        return CodingResult(
            summary=response.summary,
            modified_files=sorted(set(modified_files)),
            diff=self._diff(before, after),
        )

    @staticmethod
    def _parse(raw: str) -> CodingResponse:
        """Accept JSON or a fenced JSON block, then enforce the Pydantic schema."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        try:
            return CodingResponse.model_validate_json(cleaned)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Provider did not return the required structured edit JSON.") from exc

    @staticmethod
    def _validate_edit(root: Path, edit: EditOperation) -> None:
        """Reject unsupported targets and replacements for files that do not exist."""
        if Path(edit.path).suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"Editing this file type is not allowed: {edit.path}")
        if edit.action == "replace":
            try:
                read_file(root, edit.path)
            except FileNotFoundError as exc:
                available = ", ".join(CodingAgent._file_inventory(root)) or "(none)"
                raise ValueError(
                    f"Model requested a replace edit for missing file '{edit.path}'. "
                    f"Available files: {available}. Use create for a new file."
                ) from exc

    @staticmethod
    def _validate_python_sources(root: Path) -> None:
        """Reject a batch that leaves any Python source syntactically invalid."""
        for path in root.rglob("*.py"):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise ValueError(f"Edit left Python file syntactically invalid: {path.name}") from exc

    @staticmethod
    def _restore_snapshot(root: Path, snapshot: dict[str, str]) -> None:
        """Restore the text-file snapshot after a rejected edit batch."""
        current = CodingAgent._snapshot(root)
        for path, content in snapshot.items():
            (root / path).write_text(content, encoding="utf-8")
        for path in set(current) - set(snapshot):
            (root / path).unlink(missing_ok=True)

    @staticmethod
    def _snapshot(root: Path) -> dict[str, str]:
        """Capture text files for a human-readable unified diff after editing."""
        return {
            file.relative_to(root).as_posix(): file.read_text(encoding="utf-8")
            for file in root.rglob("*")
            if file.is_file() and file.suffix.lower() in ALLOWED_SUFFIXES
        }

    @staticmethod
    def _file_inventory(root: Path) -> list[str]:
        """Return a small, deterministic list of safe text files for the prompt."""
        return sorted(
            file.relative_to(root).as_posix()
            for file in root.rglob("*")
            if file.is_file() and file.suffix.lower() in ALLOWED_SUFFIXES
        )[:30]

    @staticmethod
    def _diff(before: dict[str, str], after: dict[str, str]) -> str:
        lines: list[str] = []
        for path in sorted(set(before) | set(after)):
            lines.extend(
                unified_diff(
                    before.get(path, "").splitlines(keepends=True),
                    after.get(path, "").splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        return "".join(lines)

    @staticmethod
    def _prompt(task: str, root: Path, context: list[Symbol]) -> str:
        """Send relevant code plus an inventory, never an entire repository."""
        sections = []
        for symbol in context[:8]:
            try:
                source = read_file(root, symbol.file)
            except (OSError, UnicodeDecodeError):
                continue
            lines = source.splitlines()
            excerpt = "\n".join(lines[symbol.start_line - 1 : symbol.end_line])
            sections.append(
                f"FILE: {symbol.file}\nSYMBOL: {symbol.name}\n```python\n{excerpt}\n```"
            )
        # A file with no function/class does not appear in AST symbol context.
        # Include a bounded excerpt so the model can still edit small scripts.
        if not sections:
            for path in CodingAgent._file_inventory(root)[:8]:
                if Path(path).suffix != ".py":
                    continue
                try:
                    excerpt = "\n".join(read_file(root, path).splitlines()[:160])
                except (OSError, UnicodeDecodeError):
                    continue
                sections.append(f"FILE: {path}\n```python\n{excerpt}\n```")
        return f"""You are an expert Python coding agent. Complete this task: {task}

### OUTPUT FORMAT
Return ONLY valid JSON exactly matching this schema:
{{"summary":"short public summary", "edits":[{{"action":"replace", "path":"relative.py", "old":"exact existing text", "new":"replacement text"}}]}}

### REPOSITORY CONTEXT
Available files: {", ".join(CodingAgent._file_inventory(root)) or "(none)"}

### CODING STANDARDS
1. Write complete, fully implemented, working code. Do NOT write outlines, skeletons, or placeholder implementations. Make smart decisions for variables, models, and API usage.
2. Write production-ready code. Do NOT write "example usage" blocks (even commented out), interactive `input()` loops, or print statements unless explicitly requested. Write clean, modular, robust, and reusable functions or classes.
3. Edit Intelligently: If the task implies 'ADD', integrate your changes seamlessly into the existing code without deleting what is already there. If it implies 'CHANGE', modify only the necessary chunks unless a complete rewrite is genuinely required by the task.

### EDITING RULES (STRICT)
1. Allowed actions are "replace" and "create". Use "replace" if the file already exists in the Available files list. Use "create" ONLY for entirely new files. Use at most {MAX_EDITS} edits.
2. For "replace", the `old` text must appear exactly once in the file. Include enough surrounding context to ensure uniqueness. The `old` text MUST be a perfect, character-for-character match with the existing file, including all whitespace and indentation.
3. To ADD code to an existing file, use "replace": put the existing anchor lines (e.g., the code you want to insert after) in `old`, and output those SAME anchor lines alongside your new code in `new`. NEVER delete existing code when adding new features.
4. Paths must be relative and end in .py, .md, .toml, or .txt.
5. Do not delete files or use shell commands.

### TESTING RULES (STRICT)
1. SEPARATION OF CONCERNS: The implementation code MUST remain real and production-ready. NEVER insert mocks, fake classes, placeholders, or `MagicMock` into implementation files. Do NOT add `subprocess` installations or alter the intended code structure just to make tests pass.
2. MOCKING: All mocking MUST be done inside the test files. To prevent tests from crashing on import due to top-level execution or missing dependencies, mock the required modules using `sys.modules` (e.g., `sys.modules['mistralai'] = MagicMock()`) INSIDE the test file BEFORE importing the target script.
3. TEST CREATION: Testing is mandatory for behavior changes. Create or update a `test_*.py` file. Pytest is configured to only discover tests inside the `tests/` directory, so all new test files MUST be created inside `tests/` (e.g., `tests/test_feature.py`).

### CRITICAL WARNINGS
1. NEVER DELETE EXISTING CODE! When using "replace" to add new code, you MUST include the existing anchor lines in your `new` block. If you only put the new code in the `new` block, the old code is DELETED.
2. NO EXAMPLE USAGE! Do not write `if __name__ == '__main__':` blocks, commented-out examples, or interactive loops unless explicitly requested.
3. NO SKELETONS! Your code must be fully implemented and working (e.g., if writing a chatbot, ensure it accepts and passes the API key correctly).

### RELEVANT CODE
{chr(10).join(sections) or "No code symbols were retrieved."}"""
