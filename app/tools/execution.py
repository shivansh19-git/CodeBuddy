"""High-level test tool: converts sandbox output into the typed API schema."""

import os
import re
import subprocess
import sys
import time
import venv

from app.repository import repository_root
from app.sandbox.docker import SandboxResult
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


def _run_local_execution(root) -> SandboxResult:
    """Run pytest directly in the isolated Python environment."""
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)

    # 1. Direct execution via current Python runtime (e.g. deployed server env)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--tb=short",
                "-v",
                "--rootdir=.",
                "-p",
                "no:cacheprovider",
            ],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if "No module named pytest" not in completed.stderr:
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
    except Exception:
        pass

    # 2. Secondary fallback: create sub-venv
    venv_dir = root.parent / f".venv_{root.name}"
    try:
        if not venv_dir.exists():
            venv.EnvBuilder(with_pip=True).create(venv_dir)

        if os.name == "nt":
            pip_exe = str(venv_dir / "Scripts" / "pip.exe")
            pytest_exe = str(venv_dir / "Scripts" / "pytest.exe")
        else:
            pip_exe = str(venv_dir / "bin" / "pip")
            pytest_exe = str(venv_dir / "bin" / "pytest")

        if not os.path.exists(pytest_exe):
            subprocess.run([pip_exe, "install", "pytest"], capture_output=True, check=False)

        req_file = root / "requirements.txt"
        if req_file.is_file():
            subprocess.run([pip_exe, "install", "-r", str(req_file)], capture_output=True, check=False)

        completed = subprocess.run(
            [pytest_exe, "--tb=short", "-v", "--rootdir=.", "-p", "no:cacheprovider"],
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
    """Run pytest directly in the isolated Python environment."""
    root = repository_root(repository_id)

    try:
        result = _run_local_execution(root)
    except Exception as local_exc:
        return TestResult(
            errors=1,
            success=False,
            output=f"ENVIRONMENT_ERROR: local pytest execution failed: {local_exc}",
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
