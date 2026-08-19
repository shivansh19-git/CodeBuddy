"""API tests exercise the same multipart shape Streamlit sends."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_accepts_multiple_python_files():
    response = client.post(
        "/api/repositories/files",
        files=[
            ("files", ("maths.py", b"def add(a, b):\n    return a + b\n", "text/x-python")),
            ("files", ("test_maths.py", b"from maths import add\n", "text/x-python")),
        ],
    )
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["python_files"] == 2
    assert summary["symbols"][0]["name"] == "add"


def test_rejects_non_python_file_upload():
    response = client.post(
        "/api/repositories/files",
        files=[("files", ("notes.txt", b"not code", "text/plain"))],
    )
    assert response.status_code == 400
