"""High-level test tool: converts sandbox output into the typed API schema."""

import os
import re
import subprocess
import sys
import time
import venv

from app.repository import repository_root
from app.sandbox.docker import SandboxResult, SandboxUnavailableError, run_in_sandbox
from app.sandbox.preparation import DependencyPreparationError, prepare_image
from app.schemas import TestResult

# Patterns that indicate pytest found no tests to run.
_NO_TESTS_PATTERNS = re.compile(
    r"no tests ran|collected 0 items|no tests were run|"
    r"ERROR: not found|error: not found",
    re.IGNORECASE,
)


def _is_no_tests_collected(return_code: int, output: str) -> bool:
    """Detect all pytest 'no tests found' variants robustly."""
    # pytest exit code 5 always means "no tests collected"
    if return_code == 5:
        return True
    # Some versions return 0 with explicit "no tests ran" text
    return bool(_NO_TESTS_PATTERNS.search(output))


def _count(label: str, output: str) -> int:
    """Parse a pytest summary counter from output text."""
    match = re.search(rf"(\d+) {label}\b", output)
    return int(match.group(1)) if match else 0


def _run_local_fallback(root) -> SandboxResult:
    """Run pytest in a persistent per-workspace venv when Docker is unavailable.

    The venv lives in a sibling directory (not inside the workspace) so it
    survives workspace resets and is not picked up by pytest discovery.
    Dependencies from requirements.txt are installed with an absolute path so
    they always resolve regardless of the server's working directory.
    """
    started = time.monotonic()

    # Place the venv outside the workspace so pytest never traverses into it.
    venv_dir = root.parent / f".venv_{root.name}"

    try:
        # Create venv only once; reuse on subsequent runs.
        if not venv_dir.exists():
            venv.EnvBuilder(with_pip=True).create(venv_dir)

        # Resolve interpreter and tool paths for the current OS.
        if os.name == "nt":
            pip_exe = str(venv_dir / "Scripts" / "pip.exe")
            pytest_exe = str(venv_dir / "Scripts" / "pytest.exe")
        else:
            pip_exe = str(venv_dir / "bin" / "pip")
            pytest_exe = str(venv_dir / "bin" / "pytest")

        # Ensure pytest is available in the venv.
        if not os.path.exists(pytest_exe):
            subprocess.run(
                [pip_exe, "install", "pytest"],
                capture_output=True,
                check=False,
            )

        # Install project dependencies using the *absolute* path to requirements.txt
        # so this works regardless of the server process's CWD.
        req_file = root / "requirements.txt"
        if req_file.is_file():
            subprocess.run(
                [pip_exe, "install", "-r", str(req_file)],
                capture_output=True,
                check=False,
            )

        # Build the env with PYTHONPATH pointing at the workspace root so that
        # local imports in generated code resolve correctly.
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)

        # Run pytest with the same rich flags used in the Docker sandbox.
        completed = subprocess.run(
            [
                pytest_exe,
                "--tb=short",
                "-v",
                "--rootdir=.",
                "-p", "no:cacheprovider",
            ],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return SandboxResult(
            return_code=completed.returncode,
            output=(completed.stdout + completed.stderr)[-12000:],
            runtime_seconds=round(time.monotonic() - started, 2),
        )

    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + (exc.stderr or ""))[-12000:]
        return SandboxResult(
            return_code=124,
            output=output + "\nTIMEOUT: local test execution exceeded the configured limit.",
            runtime_seconds=round(time.monotonic() - started, 2),
            timed_out=True,
        )
    except Exception as local_exc:
        raise RuntimeError(f"local pytest fallback failed: {local_exc}") from local_exc


def run_tests(repository_id: str) -> TestResult:
    """Run pytest in Docker (preferred) or a local venv fallback.

    Returns a fully populated TestResult regardless of which path was taken.
    ENVIRONMENT_ERROR prefix in ``output`` signals infrastructure problems
    (Docker unavailable AND local fallback failed) so callers can distinguish
    them from real test failures.
    """
    root = repository_root(repository_id)

    try:
        result = run_in_sandbox(root, "pytest", image=prepare_image(root))
    except (DependencyPreparationError, SandboxUnavailableError):
        # Docker not available — try a local venv instead.
        try:
            result = _run_local_fallback(root)
        except Exception as local_exc:
            return TestResult(
                errors=1,
                success=False,
                output=f"ENVIRONMENT_ERROR: local pytest fallback failed: {local_exc}",
            )

    no_tests = _is_no_tests_collected(result.return_code, result.output)

    return TestResult(
        passed=_count("passed", result.output),
        failed=_count("failed", result.output),
        errors=_count("error", result.output),
        skipped=_count("skipped", result.output),
        runtime_seconds=result.runtime_seconds,
        success=result.return_code == 0 and not result.timed_out and not no_tests,
        no_tests_collected=no_tests,
        output=result.output,
    )
