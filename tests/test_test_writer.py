"""Tests for the robust TestWriterAgent and AST test generator."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from app.agents.test_writer import (
    TestWriterAgent,
    _ensure_requirements,
    _extract_imported_packages,
    generate_ast_tests_for_repo,
)
from app.models.base import LLMProvider, ModelDescriptor


def test_ast_test_generator_simple_module():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        mod_file = root / "calculator.py"
        mod_file.write_text(
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n\n"
            "class MathService:\n"
            "    def compute(self, x: int) -> int:\n"
            "        return x * 2\n",
            encoding="utf-8",
        )

        tests = generate_ast_tests_for_repo(root)
        assert "tests/test_implementation.py" in tests
        content = tests["tests/test_implementation.py"]
        assert "def test_import_calculator():" in content
        assert "def test_calculator_add_callable():" in content
        assert "def test_calculator_MathService_structure():" in content


def test_extract_imported_packages():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        code_file = root / "service.py"
        code_file.write_text(
            "import os\n"
            "import sys\n"
            "import httpx\n"
            "from pydantic import BaseModel\n",
            encoding="utf-8",
        )

        packages = _extract_imported_packages(root)
        assert "httpx" in packages
        assert "pydantic" in packages
        assert "os" not in packages
        assert "sys" not in packages


def test_ensure_requirements():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        code_file = root / "service.py"
        code_file.write_text("import mistralai\n", encoding="utf-8")

        added = _ensure_requirements(root)
        assert added == ["requirements.txt"]
        req_content = (root / "requirements.txt").read_text(encoding="utf-8")
        assert "mistralai" in req_content


def test_test_writer_agent_ast_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        code_file = root / "app.py"
        code_file.write_text("def hello(): return 'world'\n", encoding="utf-8")

        agent = TestWriterAgent(provider=None)
        result = agent.write("Write tests", root, [])

        assert len(result.modified_files) >= 1
        assert (root / "tests" / "test_implementation.py").is_file()
        test_content = (root / "tests" / "test_implementation.py").read_text(encoding="utf-8")
        assert "def test_import_app():" in test_content
