"""Docker CLI sandbox implementation with conservative isolation defaults."""

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.sandbox.security import allowed_argv


class SandboxUnavailableError(RuntimeError):
    """Docker is unavailable, so untrusted code must not be executed."""


@dataclass(frozen=True)
class SandboxResult:
    """The raw, auditable result of one sandbox command."""

    return_code: int
    output: str
    runtime_seconds: float
    timed_out: bool = False


def docker_available() -> bool:
    """Check the Docker client without executing repository code."""
    if not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_in_sandbox(repository: Path, command_name: str, image: str | None = None) -> SandboxResult:
    """Run one allowlisted command with no network and a read-write repo mount.

    The image should contain Python, pytest, and project-install support. The
    host never interpolates model text into this command and no shell is used.
    """
    if not docker_available():
        raise SandboxUnavailableError("Docker is unavailable; repository code was not executed.")
    argv = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--pids-limit",
        "128",
        "--memory",
        "768m",
        "--cpus",
        "1.0",
        "-v",
        f"{repository.resolve()}:/workspace:rw",
        "-w",
        "/workspace",
    ]
    if not settings.sandbox_network:
        argv.extend(["--network", "none"])
    argv.extend([image or settings.sandbox_image, *allowed_argv(command_name)])
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=settings.test_timeout_seconds, check=False
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
            output=output + "\nTIMEOUT: sandbox execution exceeded the configured limit.",
            runtime_seconds=round(time.monotonic() - started, 2),
            timed_out=True,
        )
