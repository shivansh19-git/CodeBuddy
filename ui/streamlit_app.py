"""Streamlit client. The UI makes agent state visible without exposing reasoning."""

import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
st.set_page_config(page_title="Agentic Software Engineer", page_icon="🤖", layout="wide")
st.title("Agentic Software Engineer")
st.caption("A transparent Python-repository coding-agent MVP")

with st.sidebar:
    st.header("Provider status")
    st.warning("Coding provider not configured")
    st.caption(
        "Analysis works now. Implementation starts only after a real provider adapter is configured."
    )

st.header("New task")
tab_upload, tab_files, tab_github = st.tabs(["Upload ZIP", "Python files", "Public GitHub URL"])
repo_id = st.session_state.get("repository_id")
try:
    with tab_upload:
        archive = st.file_uploader("Python project (.zip)", type=["zip"])
        if archive and st.button("Analyze uploaded repository"):
            response = requests.post(
                f"{API_URL}/api/repositories/upload",
                files={"file": (archive.name, archive.getvalue(), "application/zip")},
                timeout=60,
            )
            response.raise_for_status()
            st.session_state.repository_id = response.json()["id"]
            st.rerun()
    with tab_files:
        python_files = st.file_uploader(
            "Python files (.py)",
            type=["py"],
            accept_multiple_files=True,
            help="Upload one or more source files. Each is treated as part of a temporary project.",
        )
        if python_files and st.button("Analyze Python files"):
            response = requests.post(
                f"{API_URL}/api/repositories/files",
                files=[
                    ("files", (file.name, file.getvalue(), "text/x-python"))
                    for file in python_files
                ],
                timeout=60,
            )
            response.raise_for_status()
            st.session_state.repository_id = response.json()["id"]
            st.rerun()
    with tab_github:
        url = st.text_input("Repository URL", placeholder="https://github.com/owner/repository")
        if url and st.button("Clone and analyze"):
            response = requests.post(
                f"{API_URL}/api/repositories/github", json={"url": url}, timeout=100
            )
            response.raise_for_status()
            st.session_state.repository_id = response.json()["id"]
            st.rerun()
except requests.RequestException as exc:
    st.error(f"Backend request failed: {exc}")

if repo_id:
    summary = requests.get(f"{API_URL}/api/repositories/{repo_id}", timeout=20).json()
    st.success(
        f"Ready: {summary['name']} — {summary['python_files']} Python files, {len(summary['symbols'])} symbols"
    )
    task_text = st.text_area(
        "What should the agent change?",
        placeholder="Add a DELETE /users/{id} endpoint and tests.",
        height=110,
    )
    iterations = st.slider("Maximum correction iterations", 1, 10, 5)
    if st.button("Run agent", type="primary", disabled=len(task_text) < 5):
        response = requests.post(
            f"{API_URL}/api/tasks",
            json={"repository_id": repo_id, "description": task_text, "max_iterations": iterations},
            timeout=40,
        )
        response.raise_for_status()
        st.session_state.task = response.json()

task = st.session_state.get("task")
if task:
    st.header("Agent workspace")
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Activity timeline")
        for event in task["events"]:
            icon = "⚠" if event["level"] == "warning" else "✓"
            st.write(f"{icon} **{event['phase'].title()}** — {event['message']}")
        st.subheader("Plan")
        for index, step in enumerate(task["plan"], 1):
            st.write(f"{index}. {step}")
    with right:
        st.subheader("Task status")
        st.info(task["status"].replace("_", " ").title())
        st.subheader("Retrieved code")
        for symbol in task["retrieved_context"]:
            st.code(
                f"{symbol['file']}:{symbol['start_line']}  {symbol['kind']} {symbol['name']}{symbol['signature']}",
                language="text",
            )
    st.subheader("Review")
    st.warning(task["review"])
    st.subheader("Tests")
    st.caption(
        "Tests run only in the Docker sandbox; they are never run on your computer directly."
    )
    if st.button("Run pytest in sandbox"):
        response = requests.post(f"{API_URL}/api/tasks/{task['id']}/tests", timeout=130)
        if response.ok:
            result = response.json()
            if result["success"]:
                st.success(f"Passed: {result['passed']} in {result['runtime_seconds']} seconds")
            else:
                st.error(result["output"])
        else:
            st.error(f"Could not run tests: {response.text}")
else:
    st.info(
        "Choose a repository input above. The dashboard will then display its code map and agent activity."
    )
