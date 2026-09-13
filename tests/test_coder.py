import json
from pathlib import Path

import pytest

from app.agents.coder import CodingAgent
from app.models.base import LLMProvider, ModelCapabilities, ModelDescriptor


class FakeProvider(LLMProvider):
    """Test double: makes no network request and returns deterministic JSON."""

    descriptor = ModelDescriptor("fake", "fake", 1, ModelCapabilities(coding=True))

    def generate(self, prompt: str) -> str:
        return '{"summary":"Fixes the answer.","edits":[{"action":"replace","path":"app.py","old":"answer = 41","new":"answer = 42"}]}'

    def health_check(self) -> str:
        return "healthy"


def test_coding_agent_applies_a_single_exact_replacement(tmp_path: Path):
    (tmp_path / "app.py").write_text("answer = 41\n", encoding="utf-8")
    result = CodingAgent(FakeProvider()).execute("Fix answer", tmp_path, [])
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "answer = 42\n"
    assert result.modified_files == ["app.py"]
    assert "-answer = 41" in result.diff


def test_coding_agent_explains_missing_replace_target(tmp_path: Path):
    class MissingFileProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            return '{"summary":"Bad target.","edits":[{"action":"replace","path":"script.py","old":"x","new":"y"}]}'

    (tmp_path / "app.py").write_text("answer = 41\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Available files: app.py"):
        CodingAgent(MissingFileProvider()).execute("Fix answer", tmp_path, [])


def test_coding_agent_rejects_invalid_python_and_rolls_back(tmp_path: Path):
    class InvalidProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            return json.dumps(
                {
                    "summary": "Breaks syntax.",
                    "edits": [
                        {
                            "action": "replace",
                            "path": "app.py",
                            "old": "answer = 41",
                            "new": 'for _ in range(50):\nprint("hello!")',
                        }
                    ],
                }
            )

    original = "answer = 41\n"
    (tmp_path / "app.py").write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="syntactically invalid"):
        CodingAgent(InvalidProvider()).execute("Break syntax", tmp_path, [])
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == original
