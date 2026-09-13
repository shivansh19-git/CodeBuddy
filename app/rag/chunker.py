"""Turn Python AST symbols into semantic, line-addressable code chunks."""

from dataclasses import dataclass
from pathlib import Path

from app.schemas import Symbol


@dataclass(frozen=True)
class CodeChunk:
    file: str
    symbol: str
    kind: str
    start_line: int
    end_line: int
    source: str

    @property
    def identifier(self) -> str:
        return f"{self.file}:{self.symbol}:{self.start_line}"


def build_chunks(root: Path, symbols: list[Symbol]) -> list[CodeChunk]:
    """Extract semantic units from source; do not treat a repository as one blob."""
    chunks: list[CodeChunk] = []
    for symbol in symbols:
        path = root / symbol.file
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        chunks.append(
            CodeChunk(
                file=symbol.file,
                symbol=symbol.name,
                kind=symbol.kind,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                source="\n".join(lines[symbol.start_line - 1 : symbol.end_line]),
            )
        )
    return chunks
