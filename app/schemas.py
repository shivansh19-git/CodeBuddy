"""Typed API contracts. Keeping events structured makes the UI easy to trust."""

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_PROVIDER = "needs_provider"
    FAILED = "failed"


class ActivityEvent(BaseModel):
    phase: str
    message: str
    level: str = "info"  # info, warning, error—never hidden model reasoning.


class Symbol(BaseModel):
    file: str
    name: str
    kind: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str | None = None


class RepositorySummary(BaseModel):
    name: str
    file_count: int
    python_files: int
    test_files: int
    package_files: list[str] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)


class TestResult(BaseModel):
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    runtime_seconds: float = 0
    success: bool = False
    no_tests_collected: bool = False
    output: str = "Tests have not run."


class Plan(BaseModel):
    """Public structured plan; it never contains hidden model reasoning."""

    goal: str
    steps: list[str] = Field(min_length=1, max_length=8)
    files_likely_affected: list[str] = Field(default_factory=list)
    tests_required: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    """Evidence-based final review contract."""

    approved: bool
    score: float = Field(ge=0, le=10)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class TaskRequest(BaseModel):
    repository_id: str
    description: str = Field(min_length=5, max_length=4000)
    # The initial implementation is attempt 1, so two attempts allow one repair pass.
    max_iterations: int = Field(default=5, ge=2, le=10)
    provider: str | None = None


class TaskRecord(BaseModel):
    id: str
    repository_id: str
    description: str
    status: TaskStatus
    phase: str
    provider: str | None = None
    summary: RepositorySummary | None = None
    plan: list[str] = Field(default_factory=list)
    retrieved_context: list[Symbol] = Field(default_factory=list)
    events: list[ActivityEvent] = Field(default_factory=list)
    tests: TestResult = Field(default_factory=TestResult)
    review: str = "Not reviewed yet."
    review_result: ReviewResult | None = None
    diff: str = ""
    modified_files: list[str] = Field(default_factory=list)
    iterations: int = 0
