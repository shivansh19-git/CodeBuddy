"""Command validation for the container execution boundary.

The model never supplies a raw shell command. It selects from a small, exact
allowlist that this module turns into an argv list—there is no shell parsing.
"""


class UnsafeCommandError(ValueError):
    """Raised when an execution request is outside the approved command list."""


ALLOWED_COMMANDS: dict[str, list[str]] = {
    "pytest": ["python", "-m", "pytest", "-q"],
    "ruff": ["ruff", "check", "."],
}


def allowed_argv(command_name: str) -> list[str]:
    """Return a fresh approved argv list, rejecting arbitrary shell input."""
    try:
        return list(ALLOWED_COMMANDS[command_name])
    except KeyError as exc:
        raise UnsafeCommandError(f"Command is not allowed: {command_name}") from exc
