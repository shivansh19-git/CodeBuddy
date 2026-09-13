import pytest

from app.sandbox.preparation import DependencyPreparationError, extract_requirements


def test_extract_requirements_accepts_normal_package_specifications(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "fastapi>=0.115\nuvicorn[standard]>=0.30,<1\npytest==8.3.3\n", encoding="utf-8"
    )
    assert extract_requirements(tmp_path) == [
        "fastapi>=0.115",
        "uvicorn[standard]>=0.30,<1",
        "pytest==8.3.3",
    ]


def test_extract_requirements_blocks_urls_and_editable_installs(tmp_path):
    (tmp_path / "requirements.txt").write_text("-e .\n", encoding="utf-8")
    with pytest.raises(DependencyPreparationError):
        extract_requirements(tmp_path)
