"""Structured planning node with a deterministic fallback plan."""

import re

from pydantic import ValidationError

from app.models.base import LLMProvider
from app.schemas import Plan, Symbol


class PlannerAgent:
    """Converts a task and retrieved code into an auditable `Plan`."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def create(self, task: str, context: list[Symbol]) -> Plan:
        raw = self.provider.generate(self._prompt(task, context))
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        try:
            return Plan.model_validate_json(cleaned)
        except (ValidationError, ValueError) as exc:
            raise ValueError("Provider did not return the required structured plan JSON.") from exc

    @staticmethod
    def fallback(task: str, context: list[Symbol]) -> Plan:
        """Safe plan when no provider is configured or its JSON is invalid."""
        return Plan(
            goal=task,
            steps=[
                "Inspect retrieved code and existing tests.",
                "Apply the smallest validated implementation change.",
                "Create or update pytest coverage for the requested behavior.",
                "Run pytest in the Docker sandbox and correct actionable failures.",
                "Review the real diff and verification evidence.",
            ],
            files_likely_affected=sorted({symbol.file for symbol in context}),
            tests_required=["pytest coverage for the requested behavior"],
        )

    @staticmethod
    def _prompt(task: str, context: list[Symbol]) -> str:
        symbols = [f"{item.file}:{item.name}" for item in context[:8]]
        return f"""Create a concise coding plan for this task: {task}
Relevant symbols: {", ".join(symbols) or "none"}
Return ONLY JSON: {{"goal":"...","steps":["..."],"files_likely_affected":["..."],"tests_required":["..."]}}.
Do not include private reasoning or markdown."""
