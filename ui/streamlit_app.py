"""Streamlit client. The UI makes agent state visible without exposing reasoning."""

import difflib
import os
import time

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
st.set_page_config(page_title="Agentic Software Engineer", page_icon="🤖", layout="wide")
st.title("Agentic Software Engineer")
st.caption("A transparent Python-repository coding-agent MVP")

with st.sidebar:
    st.header("Provider status")
    try:
        provider_response = requests.get(f"{API_URL}/api/providers/status", timeout=5)
        provider_response.raise_for_status()
        for provider in provider_response.json():
            label = f"{provider['name']} / {provider.get('model', 'n/a')}"
            if provider["status"] == "healthy":
                st.success(label)
            else:
                st.warning(f"{label}: {provider['status']}")
    except requests.RequestException:
        st.warning("Backend unavailable")
    st.divider()
    st.header("Recent tasks")
    try:
        recent = requests.get(f"{API_URL}/api/tasks", timeout=5)
        recent.raise_for_status()
        for recent_task in recent.json()[:5]:
            st.caption(
                f"{recent_task['status'].replace('_', ' ').title()} · {recent_task['description'][:42]}"
            )
    except requests.RequestException:
        st.caption("Task history will appear once the backend is available.")

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

def is_submitted_source_file(file_path: str) -> bool:
    name = file_path.split("/")[-1].lower()
    parts = [p.lower() for p in file_path.split("/")]
    if "tests" in parts or "test" in parts:
        return False
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return False
    return True


if repo_id:
    try:
        summary_response = requests.get(f"{API_URL}/api/repositories/{repo_id}", timeout=20)
        summary_response.raise_for_status()
        summary = summary_response.json()
        if not {"name", "python_files", "symbols"}.issubset(summary):
            raise ValueError("The backend returned an invalid repository summary.")
    except (requests.RequestException, ValueError) as exc:
        st.warning("Your temporary repository is no longer available. Upload it again to continue.")
        st.caption(f"Reason: {exc}")
        st.session_state.pop("repository_id", None)
        st.session_state.pop("task", None)
        st.stop()

    st.success(
        f"Ready: {summary['name']} — {summary['python_files']} Python files, {len(summary['symbols'])} symbols"
    )

    task_text = st.text_area(
        "What should the agent change?",
        placeholder="Add a DELETE /users/{id} endpoint and tests.",
        height=110,
    )
    iterations = st.slider(
        "Maximum agent attempts",
        2,
        10,
        5,
        help="The first attempt implements the task. Set 2 or more to allow automatic test-failure correction.",
    )
    if st.button("Run agent", type="primary", disabled=len(task_text) < 5):
        try:
            response = requests.post(
                f"{API_URL}/api/tasks",
                json={"repository_id": repo_id, "description": task_text, "max_iterations": iterations},
                timeout=10,
            )
            response.raise_for_status()
            st.session_state.task = response.json()
            task_id = st.session_state.task["id"]
            progress = st.empty()
            deadline = time.monotonic() + 600
            while st.session_state.task["status"] in {"queued", "running"} and time.monotonic() < deadline:
                progress.info(
                    f"Agent is working: {st.session_state.task.get('phase', 'queue').title()}..."
                )
                time.sleep(1)
                task_response = requests.get(f"{API_URL}/api/tasks/{task_id}", timeout=10)
                task_response.raise_for_status()
                st.session_state.task = task_response.json()
            progress.empty()
            if st.session_state.task["status"] in {"queued", "running"}:
                st.warning("The task is still running. Refresh the page to check its progress.")
        except requests.RequestException as exc:
            st.error(f"Could not start or monitor the task: {exc}")

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
        st.caption(f"Agent attempts: {task.get('iterations', 0)}")
        st.subheader("Retrieved code")
        for symbol in task["retrieved_context"]:
            st.code(
                f"{symbol['file']}:{symbol['start_line']}  {symbol['kind']} {symbol['name']}{symbol['signature']}",
                language="text",
            )
    st.subheader("Review")
    st.warning(task["review"])
    if task.get("review_result"):
        review = task["review_result"]
        st.metric("Review score", f"{review['score']}/10")
        if review["issues"]:
            st.write("Issues: " + "; ".join(review["issues"]))
        if review["suggestions"]:
            st.write("Suggestions: " + "; ".join(review["suggestions"]))
    if task["diff"]:
        st.subheader("Code changes")
        st.caption("This is the actual diff produced by the validated edit tools.")
        st.code(task["diff"], language="diff")

        st.download_button(
            label="📄 Download Patch (.patch)",
            data=task["diff"],
            file_name=f"task_{task.get('id', 'patch')[:8]}.patch",
            mime="text/x-diff",
            use_container_width=True,
        )

    # Document & File Workspace (Available after processing is done)
    st.divider()
    st.header("📄 Document & File Workspace")
    st.caption("Inspect, compare, and edit submitted source files or download repository archives.")

    all_files = sorted(list({s["file"] for s in summary["symbols"]}.union(set(summary.get("package_files", [])))))
    submitted_sources = [f for f in all_files if is_submitted_source_file(f)]

    if not submitted_sources:
        try:
            files_resp = requests.get(
                f"{API_URL}/api/repositories/{repo_id}/files", timeout=10
            )
            files_resp.raise_for_status()
            fallback_files = files_resp.json().get("files", [])
            submitted_sources = [f for f in fallback_files if is_submitted_source_file(f)]
        except requests.RequestException:
            submitted_sources = []

    if submitted_sources:
        file_col, view_col, height_col = st.columns([3, 3, 2])
        with file_col:
            selected_src = st.selectbox("Select File", submitted_sources, key="post_proc_select")
        with view_col:
            view_mode = st.radio(
                "View Mode",
                ["✏️ Split View (Original vs Editor)", "🔀 Unified Diff", "📄 Pristine Original File", "📝 Full Editor"],
                horizontal=True,
                key="workspace_view_mode",
            )
        with height_col:
            editor_height = st.slider("Viewer Height (px)", min_value=300, max_value=1200, value=600, step=100, help="Adjust viewer size for large files (1000+ lines)")

        if selected_src:
            try:
                # 1. Fetch current content (possibly edited by user or agent)
                current_resp = requests.get(
                    f"{API_URL}/api/repositories/{repo_id}/files/content",
                    params={"path": selected_src, "original": False},
                    timeout=10,
                )
                current_resp.raise_for_status()
                current_src_text = current_resp.json().get("content", "")

                # 2. Fetch PRISTINE original content directly from backend
                orig_resp = requests.get(
                    f"{API_URL}/api/repositories/{repo_id}/files/content",
                    params={"path": selected_src, "original": True},
                    timeout=10,
                )
                if orig_resp.ok:
                    orig_src_text = orig_resp.json().get("content", "")
                else:
                    orig_src_text = current_src_text

                orig_lines = orig_src_text.splitlines()
                curr_lines = current_src_text.splitlines()
                is_modified = orig_src_text != current_src_text

                # Display file info bar
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Original Lines", len(orig_lines))
                m2.metric("Current Lines", len(curr_lines))
                m3.metric("Size", f"{len(current_src_text.encode('utf-8')) / 1024:.1f} KB")
                m4.metric("Status", "Modified ⚠️" if is_modified else "Unmodified ✓")

                # View Modes
                if view_mode == "✏️ Split View (Original vs Editor)":
                    col_orig, col_edit = st.columns(2)
                    with col_orig:
                        st.markdown(f"**📄 Pristine Original (`{selected_src}`)**")
                        st.code(orig_src_text, language="python", line_numbers=True)
                    with col_edit:
                        st.markdown(f"**📝 Editable Version (`{selected_src}`)**")
                        edited_src_text = st.text_area(
                            "Source File Editor",
                            value=current_src_text,
                            height=editor_height,
                            key=f"editor_src_{selected_src}",
                            label_visibility="collapsed",
                        )

                elif view_mode == "🔀 Unified Diff":
                    st.markdown(f"**🔀 Differences from Pristine Original (`{selected_src}`)**")
                    diff_lines = list(difflib.unified_diff(
                        orig_lines, curr_lines,
                        fromfile=f"a/{selected_src}",
                        tofile=f"b/{selected_src}",
                        lineterm=""
                    ))
                    diff_text = "\n".join(diff_lines) if diff_lines else "# No changes detected between original and current version."
                    st.code(diff_text, language="diff", line_numbers=True)
                    edited_src_text = current_src_text

                elif view_mode == "📄 Pristine Original File":
                    st.markdown(f"**📄 Pristine Original File (`{selected_src}`) — {len(orig_lines)} Lines**")
                    st.code(orig_src_text, language="python", line_numbers=True)
                    edited_src_text = current_src_text

                else:  # "📝 Full Editor"
                    st.markdown(f"**📝 Full Width Source Editor (`{selected_src}`) — {len(curr_lines)} Lines**")
                    edited_src_text = st.text_area(
                        "Full Source File Editor",
                        value=current_src_text,
                        height=editor_height,
                        key=f"full_editor_src_{selected_src}",
                        label_visibility="collapsed",
                    )

                # Action toolbar
                btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
                filename_only = selected_src.split("/")[-1]

                with btn_c1:
                    if st.button("💾 Apply & Save Edits", type="primary", key=f"save_src_{selected_src}", use_container_width=True):
                        save_resp = requests.post(
                            f"{API_URL}/api/repositories/{repo_id}/files/content",
                            json={"path": selected_src, "content": edited_src_text},
                            timeout=10,
                        )
                        if save_resp.ok:
                            st.success(f"Saved edits to {selected_src}!")
                            st.rerun()
                        else:
                            st.error(f"Failed to save: {save_resp.text}")

                with btn_c2:
                    if st.button("↺ Reset to Original", key=f"reset_src_{selected_src}", use_container_width=True, disabled=not is_modified):
                        reset_resp = requests.post(
                            f"{API_URL}/api/repositories/{repo_id}/files/content",
                            json={"path": selected_src, "content": orig_src_text},
                            timeout=10,
                        )
                        if reset_resp.ok:
                            st.success(f"Reset {selected_src} to original version!")
                            st.rerun()
                        else:
                            st.error(f"Failed to reset: {reset_resp.text}")

                with btn_c3:
                    st.download_button(
                        label=f"📥 Download Edited ({filename_only})",
                        data=edited_src_text,
                        file_name=filename_only,
                        mime="text/x-python" if filename_only.endswith(".py") else "text/plain",
                        key=f"dl_single_edited_{selected_src}",
                        use_container_width=True,
                    )

                with btn_c4:
                    st.download_button(
                        label=f"📄 Download Original ({filename_only})",
                        data=orig_src_text,
                        file_name=f"original_{filename_only}",
                        mime="text/x-python" if filename_only.endswith(".py") else "text/plain",
                        key=f"dl_single_orig_{selected_src}",
                        use_container_width=True,
                    )

            except requests.RequestException as exc:
                st.error(f"Could not load source file: {exc}")
    else:
        st.warning(
            "No non-test source files could be identified in the workspace. "
            "You can still download the full repository archive below."
        )

    # Always offer a full-repo ZIP download regardless of the source-file list.
    st.divider()
    try:
        archive_resp = requests.get(
            f"{API_URL}/api/repositories/{repo_id}/download", timeout=30
        )
        archive_resp.raise_for_status()
        st.download_button(
            label="📦 Download Full Modified Repository (.zip)",
            data=archive_resp.content,
            file_name=f"{repo_id[:8]}_modified.zip",
            mime="application/zip",
            use_container_width=True,
        )
    except requests.RequestException as exc:
        st.error(f"Could not prepare repository archive: {exc}")

    st.divider()
    st.subheader("Tests")
    st.caption(
        "Tests run only in the Docker sandbox; they are never run on your computer directly."
    )
    result = task.get("tests", {})
    if result and result.get("output") != "Tests have not run.":
        test_columns = st.columns(5)
        for column, label, value in zip(
            test_columns,
            ["Passed", "Failed", "Errors", "Skipped", "Runtime"],
            [
                result.get("passed", 0),
                result.get("failed", 0),
                result.get("errors", 0),
                result.get("skipped", 0),
                f"{result.get('runtime_seconds', 0)}s",
            ],
            strict=True,
        ):
            column.metric(label, value)
        with st.expander("Test output"):
            st.code(result.get("output", ""), language="text")
    if st.button("Run pytest in sandbox"):
        response = requests.post(f"{API_URL}/api/repositories/{repo_id}/tests", timeout=130)
        if response.ok:
            result = response.json()
            st.session_state.task["tests"] = result
            if result["success"]:
                st.success(f"Passed: {result['passed']} in {result['runtime_seconds']} seconds")
            elif result["no_tests_collected"]:
                st.warning(
                    "Pytest found no tests. Add a file named test_<feature>.py with test_ functions, then run the agent again."
                )
                st.code(result["output"], language="text")
            else:
                st.error(result["output"])
        else:
            st.error(f"Could not run tests: {response.text}")
else:
    st.info(
        "Choose a repository input above. The dashboard will then display its code map and agent activity."
    )

