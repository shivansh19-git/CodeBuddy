"""Prepare a dependency image without executing repository source code."""

import hashlib
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from app.config import settings
from app.sandbox.docker import SandboxUnavailableError, docker_available

_SAFE_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_.,-]+\])?"
    r"(?:\s*(?:==|>=|<=|>|<|~=|!=)\s*[A-Za-z0-9_.+!*]+"
    r"(?:\s*,\s*(?:==|>=|<=|>|<|~=|!=)\s*[A-Za-z0-9_.+!*]+)*)?$"
)


class DependencyPreparationError(RuntimeError):
    """Dependencies cannot safely be prepared for sandbox execution."""


def extract_requirements(repository: Path) -> list[str]:
    """Read ordinary requirements.txt or PEP 621 dependencies, rejecting URLs/options."""
    requirements_file = repository / "requirements.txt"
    if requirements_file.is_file():
        entries = [
            line.split("#", 1)[0].strip()
            for line in requirements_file.read_text(encoding="utf-8").splitlines()
        ]
    else:
        pyproject = repository / "pyproject.toml"
        if not pyproject.is_file():
            return []
        try:
            entries = (
                tomllib.loads(pyproject.read_text(encoding="utf-8"))
                .get("project", {})
                .get("dependencies", [])
            )
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise DependencyPreparationError("Could not read project dependencies safely.") from exc
    requirements = [entry for entry in entries if entry]
    if not all(
        isinstance(entry, str) and _SAFE_REQUIREMENT.fullmatch(entry) for entry in requirements
    ):
        raise DependencyPreparationError(
            "Only ordinary package requirements are allowed; URLs, local paths, options, and editable installs are blocked."
        )
    return requirements


def prepare_image(repository: Path) -> str:
    """Build/cache a requirements-only Docker image and return its image name."""
    if not docker_available():
        raise SandboxUnavailableError("Docker is unavailable; repository code was not executed.")
    requirements = extract_requirements(repository)
    if not requirements:
        return settings.sandbox_image
    contents = "\n".join(sorted(requirements)) + "\n"
    image = f"agentic-python-deps:{hashlib.sha256(contents.encode()).hexdigest()[:16]}"
    exists = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, timeout=10, check=False
    )
    if exists.returncode == 0:
        return image
    dockerfile = Path("docker/Dockerfile.dependencies").resolve()
    if not dockerfile.is_file():
        raise DependencyPreparationError("Sandbox dependency Dockerfile is missing.")
    try:
        with tempfile.TemporaryDirectory(prefix="agentic-dependencies-") as temporary:
            context = Path(temporary)
            (context / "requirements.txt").write_text(contents, encoding="utf-8")
            shutil.copyfile(dockerfile, context / "Dockerfile")
            completed = subprocess.run(
                ["docker", "build", "--tag", image, str(context)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.dependency_prepare_timeout_seconds,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DependencyPreparationError(
            "Dependency image preparation timed out or could not start."
        ) from exc
    if completed.returncode:
        raise DependencyPreparationError(
            "Dependencies could not be prepared in the controlled Docker build."
        )
    return image
