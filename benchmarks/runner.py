"""Benchmark runner to execute evaluation tasks and calculate PRD metrics."""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from benchmarks.fixtures import BENCHMARK_TASKS, BenchmarkTask


@dataclass
class TaskMetricResult:
    task_id: str
    category: str
    success: bool
    iterations: int
    self_corrected: bool
    runtime_seconds: float
    error: str | None = None


@dataclass
class BenchmarkSummary:
    total_tasks: int = 0
    passed_tasks: int = 0
    task_success_rate: float = 0.0
    self_corrected_count: int = 0
    self_correction_rate: float = 0.0
    average_iterations: float = 0.0
    total_runtime_seconds: float = 0.0
    average_runtime_seconds: float = 0.0
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_results: list[TaskMetricResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Benchmark Evaluation Results",
            "",
            f"- **Total Tasks Evaluated**: {self.total_tasks}",
            f"- **Task Success Rate**: {self.task_success_rate:.1f}% ({self.passed_tasks}/{self.total_tasks})",
            f"- **Self-Correction Rate**: {self.self_correction_rate:.1f}% ({self.self_corrected_count} corrected)",
            f"- **Average Iterations**: {self.average_iterations:.2f}",
            f"- **Total Runtime**: {self.total_runtime_seconds:.2f}s (avg: {self.average_runtime_seconds:.2f}s/task)",
            "",
            "## Category Breakdown",
            "",
            "| Category | Total | Passed | Success Rate (%) |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for cat, data in self.by_category.items():
            lines.append(
                f"| {cat.replace('_', ' ').title()} | {data['total']} | {data['passed']} | {data['success_rate']:.1f}% |"
            )
        lines.append("")
        lines.append("## Task Details")
        lines.append("")
        lines.append("| Task ID | Category | Status | Iterations | Time (s) |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for res in self.task_results:
            status = "PASSED" if res.success else "FAILED"
            lines.append(
                f"| `{res.task_id}` | {res.category} | {status} | {res.iterations} | {res.runtime_seconds:.2f} |"
            )
        return "\n".join(lines)


class BenchmarkRunner:
    """Executes deterministic benchmark tasks and computes performance metrics."""

    def __init__(self, tasks: list[BenchmarkTask] | None = None):
        self.tasks = tasks or BENCHMARK_TASKS

    def run(
        self,
        executor_fn: Callable[[BenchmarkTask, Path], tuple[bool, int, str | None]],
        workspace_base: Path,
    ) -> BenchmarkSummary:
        """Run benchmark tasks using a provided runner callback.

        executor_fn takes (task, workspace_dir) and returns (success: bool, iterations: int, error_msg: str | None).
        """
        results: list[TaskMetricResult] = []
        workspace_base.mkdir(parents=True, exist_ok=True)

        for task in self.tasks:
            task_dir = workspace_base / task.id
            task_dir.mkdir(parents=True, exist_ok=True)
            for rel_path, content in task.files.items():
                dest = task_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

            start_t = time.time()
            try:
                success, iterations, err = executor_fn(task, task_dir)
            except Exception as exc:
                success, iterations, err = False, 1, str(exc)
            elapsed = time.time() - start_t

            self_corrected = success and iterations > 1
            results.append(
                TaskMetricResult(
                    task_id=task.id,
                    category=task.category,
                    success=success,
                    iterations=iterations,
                    self_corrected=self_corrected,
                    runtime_seconds=elapsed,
                    error=err,
                )
            )

        return self._compute_summary(results)

    def _compute_summary(self, results: list[TaskMetricResult]) -> BenchmarkSummary:
        total = len(results)
        if not total:
            return BenchmarkSummary()

        passed = sum(1 for r in results if r.success)
        self_corrected = sum(1 for r in results if r.self_corrected)
        total_iters = sum(r.iterations for r in results)
        total_time = sum(r.runtime_seconds for r in results)

        categories: dict[str, dict[str, Any]] = {}
        for r in results:
            if r.category not in categories:
                categories[r.category] = {"total": 0, "passed": 0}
            categories[r.category]["total"] += 1
            if r.success:
                categories[r.category]["passed"] += 1

        for cat, data in categories.items():
            data["success_rate"] = (data["passed"] / data["total"]) * 100.0 if data["total"] else 0.0

        return BenchmarkSummary(
            total_tasks=total,
            passed_tasks=passed,
            task_success_rate=(passed / total) * 100.0,
            self_corrected_count=self_corrected,
            self_correction_rate=(self_corrected / passed) * 100.0 if passed else 0.0,
            average_iterations=total_iters / total,
            total_runtime_seconds=total_time,
            average_runtime_seconds=total_time / total,
            by_category=categories,
            task_results=results,
        )
