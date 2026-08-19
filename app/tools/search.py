"""Bounded lexical search used by the agent's repository tools."""

from pathlib import Path


def search_code(root: Path, query: str, limit: int = 30) -> list[dict[str, object]]:
    """Return a bounded list of text matches; binary and ignored files are skipped."""
    if not query.strip():
        return []
    matches: list[dict[str, object]] = []
    for file in root.rglob("*.py"):
        if any(
            part.startswith(".") or part in {"__pycache__", "venv", ".venv"} for part in file.parts
        ):
            continue
        try:
            for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if query.lower() in line.lower():
                    matches.append(
                        {
                            "file": file.relative_to(root).as_posix(),
                            "line": line_no,
                            "text": line.strip(),
                        }
                    )
                    if len(matches) >= limit:
                        return matches
        except UnicodeDecodeError:
            continue
    return matches
