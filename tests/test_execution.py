from app.sandbox.docker import SandboxResult
from app.tools.execution import run_tests


def test_marks_pytest_exit_code_five_as_no_tests(monkeypatch, tmp_path):
    """A project with no tests is distinct from a test assertion failure."""
    monkeypatch.setattr("app.tools.execution.repository_root", lambda _repo_id: tmp_path)
    monkeypatch.setattr("app.tools.execution.prepare_image", lambda _root: "prepared-image")
    monkeypatch.setattr(
        "app.tools.execution.run_in_sandbox",
        lambda _root, _command, image: SandboxResult(5, "no tests ran in 0.01s", 0.01),
    )
    result = run_tests("repo")
    assert not result.success
    assert result.no_tests_collected
