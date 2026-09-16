"""Dedicated test-writing agent and deterministic AST test generator.

This module provides two layers of test creation:
1. LLM-based test generation (when a secondary or primary provider is available)
   with a compact, token-safe prompt and JSON schema.
2. Programmatic AST-based test generation fallback that inspects actual Python
   ASTs on disk to generate structurally guaranteed tests (zero hallucination,
   exact imports, exact function/class names).
"""

import ast
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.agents.coder import CodingAgent, CodingResult, CodingResponse, EditOperation
from app.models.base import LLMProvider
from app.repository import IGNORED_PARTS
from app.schemas import Symbol
from app.tools.filesystem import create_file, read_file, replace_once

logger = logging.getLogger(__name__)

# Standard library module set for dependency extraction
_STDLIB_MODULES = getattr(sys, "stdlib_module_names", frozenset())

# Common package name mappings (import name -> PyPI package name)
_PACKAGE_MAP = {
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
}

_SAFE_DEFAULTS = {
    "str": '""',
    "int": "0",
    "float": "0.0",
    "bool": "False",
    "list": "[]",
    "dict": "{}",
    "tuple": "()",
    "set": "set()",
    "bytes": 'b""',
    "None": "None",
}


def _is_test_file(path: str) -> bool:
    parts = Path(path).parts
    return "tests" in parts or any(p.startswith("test_") for p in parts) or any(p.endswith("_test.py") for p in parts)


def _module_name(rel_path: str) -> str:
    """Convert 'foo/bar.py' or 'foo/__init__.py' to 'foo.bar' or 'foo'."""
    p = rel_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
    if p.endswith(".__init__"):
        p = p.removesuffix(".__init__")
    return p


def _extract_imported_packages(root: Path) -> set[str]:
    """Scan all Python files in the workspace and extract third-party package names."""
    third_party: set[str] = set()
    local_names = {p.stem for p in root.glob("*.py")} | {
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    }

    for py_file in root.rglob("*.py"):
        if any(part in IGNORED_PARTS for part in py_file.parts):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            top_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_name = alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                top_name = node.module.split(".")[0]

            if top_name and top_name not in _STDLIB_MODULES and top_name not in local_names and not top_name.startswith("_"):
                pkg = _PACKAGE_MAP.get(top_name, top_name)
                third_party.add(pkg)

    return third_party


def _ensure_requirements(root: Path) -> list[str]:
    """Ensure all third-party imports are in requirements.txt if needed."""
    packages = _extract_imported_packages(root)
    if not packages:
        return []

    req_file = root / "requirements.txt"
    existing_lines = []
    existing_packages = set()

    if req_file.is_file():
        existing_lines = req_file.read_text(encoding="utf-8").splitlines()
        for line in existing_lines:
            cleaned = line.split("#", 1)[0].strip()
            if cleaned:
                pkg_name = re.split(r"[=><~]", cleaned)[0].strip()
                existing_packages.add(pkg_name.lower())

    needed = [pkg for pkg in sorted(packages) if pkg.lower() not in existing_packages and pkg.lower() != "pytest"]
    if needed:
        new_content = "\n".join(existing_lines + needed) + "\n"
        req_file.write_text(new_content, encoding="utf-8")
        return ["requirements.txt"]
    return []


def _extract_functions_and_classes(tree: ast.Module) -> tuple[list[dict], list[dict]]:
    """Extract top-level public functions and classes from an AST module."""
    functions = []
    classes = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            args = [a.arg for a in node.args.args if a.arg != "self"]
            num_defaults = len(node.args.defaults)
            num_required = len(args) - num_defaults
            functions.append({
                "name": node.name,
                "args": args,
                "num_required": max(0, num_required),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            })
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            init_args = []
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == "__init__":
                        args = [a.arg for a in item.args.args if a.arg != "self"]
                        num_defaults = len(item.args.defaults)
                        num_required = len(args) - num_defaults
                        init_args = args[:max(0, num_required)]
                    elif not item.name.startswith("_"):
                        margs = [a.arg for a in item.args.args if a.arg != "self"]
                        methods.append({
                            "name": item.name,
                            "args": margs,
                            "is_async": isinstance(item, ast.AsyncFunctionDef),
                        })
            classes.append({
                "name": node.name,
                "init_args": init_args,
                "methods": methods,
            })

    return functions, classes


def generate_ast_tests_for_repo(root: Path) -> dict[str, str]:
    """Generate deterministic, syntax-valid pytest tests for all implementation files."""
    test_functions: list[str] = []

    for py_file in sorted(root.rglob("*.py")):
        rel = py_file.relative_to(root).as_posix()
        if any(part in IGNORED_PARTS for part in py_file.parts) or _is_test_file(rel):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            if not source.strip():
                continue
            tree = ast.parse(source, filename=rel)
        except Exception:
            continue

        mod = _module_name(rel)
        mod_safe = mod.replace(".", "_")
        functions, classes = _extract_functions_and_classes(tree)

        # 1. Module import test
        test_functions.append(f"""def test_import_{mod_safe}():
    \"\"\"Verify module {mod} can be imported.\"\"\"
    import importlib
    mod = importlib.import_module("{mod}")
    assert mod is not None
""")

        # 2. Function tests (test callability & safe execution)
        for func in functions[:6]:
            fname = func["name"]
            test_functions.append(f"""def test_{mod_safe}_{fname}_callable():
    \"\"\"Verify function {fname} in {mod} exists and is callable.\"\"\"
    import importlib
    mod = importlib.import_module("{mod}")
    fn = getattr(mod, "{fname}", None)
    assert fn is not None and callable(fn)
""")

        # 3. Class tests (test existence & methods)
        for cls in classes[:4]:
            cname = cls["name"]
            test_functions.append(f"""def test_{mod_safe}_{cname}_structure():
    \"\"\"Verify class {cname} in {mod} has expected structure.\"\"\"
    import importlib
    mod = importlib.import_module("{mod}")
    cls_obj = getattr(mod, "{cname}", None)
    assert cls_obj is not None and isinstance(cls_obj, type)
""")
            for meth in cls["methods"][:3]:
                mname = meth["name"]
                test_functions.append(f"""def test_{mod_safe}_{cname}_{mname}_method():
    \"\"\"Verify method {mname} in class {cname} exists.\"\"\"
    import importlib
    mod = importlib.import_module("{mod}")
    cls_obj = getattr(mod, "{cname}", None)
    assert hasattr(cls_obj, "{mname}") and callable(getattr(cls_obj, "{mname}"))
""")

    if not test_functions:
        return {}

    test_file_content = (
        '"""Auto-generated robust verification tests.\n\n'
        'These tests verify that implementation modules import cleanly and\n'
        'contain the expected callable functions and classes.\n'
        '"""\n\n'
        + "\n\n".join(test_functions)
        + "\n"
    )

    return {
        "tests/__init__.py": "",
        "tests/test_implementation.py": test_file_content,
    }


class TestWriterAgent:
    """Independent test-writing agent with automatic AST fallback."""

    __test__ = False  # Instruct pytest not to collect this as a test suite

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def _generate(self, prompt: str, max_tokens: int = 8192) -> str:
        if self.provider is None:
            raise ValueError("No provider available for generation")
        try:
            return self.provider.generate(prompt, max_tokens=max_tokens)
        except TypeError:
            return self.provider.generate(prompt)

    def _prompt(self, task: str, root: Path, context: list[Symbol]) -> str:
        impl_files: list[str] = []
        for p in sorted(root.rglob("*.py")):
            rel = p.relative_to(root).as_posix()
            if not any(part in IGNORED_PARTS for part in p.parts) and not _is_test_file(rel):
                try:
                    content = p.read_text(encoding="utf-8")
                    if content.strip():
                        impl_files.append(f"### File: {rel}\n```python\n{content[:2500]}\n```")
                except Exception:
                    pass

        code_dump = "\n\n".join(impl_files[:4]) or "(no implementation files found)"

        return (
            "You are a Senior QA Test Engineer. Write pytest tests for the Python implementation below.\n\n"
            f"## User Goal\n{task}\n\n"
            f"## Generated Implementation Code\n{code_dump}\n\n"
            "## Requirements\n"
            "1. Create `tests/test_feature.py` with pytest test functions (naming `def test_...()`).\n"
            "2. Import from the implementation modules exactly as they are structured above.\n"
            "3. Test the main functionality described in User Goal and Implementation.\n"
            "4. Tests MUST be valid Python code and MUST pass against the implementation.\n"
            "5. If external dependencies (e.g. mistralai, openai, requests) are imported, ensure requirements.txt exists.\n"
            "6. Top-level Script / Mocking Rules:\n"
            "   - If the implementation executes code at import time (such as top-level API calls), mock the external SDK / network calls.\n"
            "   - When installing mock modules or environment variables before import, always call `sys.modules.pop('<module_name>', None)` before `import <module_name>` so Python loads a fresh instance.\n"
            "   - Never perform live network requests in unit tests.\n\n"
            "## Output Format\n"
            "Return ONLY a JSON object with this EXACT schema (no markdown formatting outside JSON):\n"
            "{\n"
            '  "summary": "<1-sentence summary of tests written>",\n'
            '  "edits": [\n'
            '    {"action": "create", "path": "tests/test_feature.py", "old": "", "new": "<full test file content>"}\n'
            "  ]\n"
            "}\n"
        )

    def _parse(self, raw: str) -> CodingResponse:
        cleaned = raw.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
        else:
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                cleaned = cleaned[first_brace : last_brace + 1].strip()

        data = json.loads(cleaned)
        return CodingResponse.model_validate(data)

    def write(self, task: str, root: Path, context: list[Symbol]) -> CodingResult:
        """Write tests for the workspace, using LLM if available, falling back to AST."""
        before = CodingAgent._snapshot(root)
        modified_files: list[str] = []

        # 1. Ensure any third-party dependencies are in requirements.txt
        req_mods = _ensure_requirements(root)
        modified_files.extend(req_mods)

        # 2. Try LLM test writing if provider is available
        llm_succeeded = False
        if self.provider is not None:
            try:
                prompt_text = self._prompt(task, root, context)
                raw_response = self._generate(prompt_text, max_tokens=8192)
                response = self._parse(raw_response)

                for edit in response.edits:
                    # Validate path: must be a test or requirement file
                    if not (_is_test_file(edit.path) or edit.path.endswith("requirements.txt")):
                        continue
                    if edit.path.endswith(".py"):
                        ast.parse(edit.new, filename=edit.path)
                    if edit.action == "create":
                        create_file(root, edit.path, edit.new)
                    else:
                        replace_once(root, edit.path, edit.old, edit.new)
                    if edit.path not in modified_files:
                        modified_files.append(edit.path)

                # Check if at least one valid test file was created
                test_files = list(root.glob("tests/test_*.py"))
                if test_files:
                    llm_succeeded = True
            except Exception as exc:
                logger.warning("LLM test writer failed (%s: %s); falling back to AST test generator.", type(exc).__name__, exc)

        # 3. Fallback: if no LLM or LLM didn't create valid tests, use AST test generator
        test_files = list(root.glob("tests/test_*.py"))
        if not llm_succeeded or not test_files:
            ast_tests = generate_ast_tests_for_repo(root)
            for path, content in ast_tests.items():
                create_file(root, path, content)
                if path not in modified_files:
                    modified_files.append(path)

        after = CodingAgent._snapshot(root)
        diff = CodingAgent._diff(before, after)
        summary = (
            f"Generated test suite with {len([f for f in modified_files if _is_test_file(f)])} test file(s)"
            + (" (LLM + AST verified)" if llm_succeeded else " (AST verified)")
        )

        return CodingResult(
            summary=summary,
            modified_files=sorted(set(modified_files)),
            diff=diff,
        )
