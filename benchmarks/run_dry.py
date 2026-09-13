"""Dry-run benchmark CLI.

Runs the full BENCHMARK_TASKS suite with a deterministic mock executor that
does not require a live LLM provider or Docker sandbox.  Every task is marked
as passing on the first attempt because all fixtures ship with already-correct
implementations — this establishes the "fixture baseline" metrics shown in
the README.

Usage:
    uv run python benchmarks/run_dry.py
    uv run python benchmarks/run_dry.py --output results.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.fixtures import BENCHMARK_TASKS, BenchmarkTask
from benchmarks.runner import BenchmarkRunner


def _mock_executor(
    task: BenchmarkTask, workspace_dir: Path
) -> tuple[bool, int, str | None]:
    """Simulate a perfect agent that solves every fixture on the first attempt.

    All benchmark fixtures include correct implementations, so the expected
    outcome is 100 % task success with 1 iteration each.  This gives the
    deterministic lower-bound baseline: how the suite behaves when every
    fix is trivially applied without self-correction.
    """
    return True, 1, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the benchmark suite with a deterministic mock executor."
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Write Markdown results to FILE in addition to stdout.",
    )
    parser.add_argument(
        "--workspace",
        metavar="DIR",
        default=".tmp/benchmark_dry_run",
        help="Temporary workspace directory for fixture files (default: .tmp/benchmark_dry_run).",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    runner = BenchmarkRunner(BENCHMARK_TASKS)

    print(f"Running {len(BENCHMARK_TASKS)} benchmark tasks (dry-run / mock executor)…")
    summary = runner.run(_mock_executor, workspace)

    markdown = (
        "<!-- Baseline: deterministic fixture run — no live model required -->\n"
        + summary.to_markdown()
    )

    print()
    print(markdown)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
