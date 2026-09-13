from pathlib import Path

from benchmarks.fixtures import BENCHMARK_TASKS, BenchmarkTask
from benchmarks.runner import BenchmarkRunner


def test_benchmark_tasks_structure():
    assert len(BENCHMARK_TASKS) >= 5
    for task in BENCHMARK_TASKS:
        assert task.id
        assert task.category in {"bug_fixing", "feature_implementation", "test_generation", "refactoring"}
        assert len(task.files) >= 1
        assert task.target_tests in task.files


def test_benchmark_runner_metrics(tmp_path: Path):
    tasks = BENCHMARK_TASKS[:4]
    runner = BenchmarkRunner(tasks)

    def mock_executor(task: BenchmarkTask, workspace_dir: Path):
        # Let's say task 0 passes on attempt 1, task 1 passes on correction (attempt 2), task 2 fails
        if task.id == tasks[0].id:
            return True, 1, None
        elif task.id == tasks[1].id:
            return True, 2, None
        else:
            return False, 3, "Test failed after max attempts"

    summary = runner.run(mock_executor, tmp_path)
    assert summary.total_tasks == 4
    assert summary.passed_tasks == 2
    assert summary.task_success_rate == 50.0
    assert summary.self_corrected_count == 1
    assert summary.self_correction_rate == 50.0
    assert summary.average_iterations == (1 + 2 + 3 + 3) / 4

    markdown = summary.to_markdown()
    assert "# Benchmark Evaluation Results" in markdown
    assert "Task Success Rate" in markdown
    assert "Category Breakdown" in markdown
