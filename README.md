# CodeBuddy (Agentic Software Engineer)

An explainable, safety-first MVP of an autonomous coding agent for Python repositories. It accepts a ZIP archive, loose Python files, or a public GitHub repository; maps the code with Python AST; retrieves relevant symbols via hybrid RAG (BM25 + FAISS); produces an auditable implementation plan; applies surgical code edits; generates tests using an independent secondary model or deterministic AST analysis; executes tests inside an isolated sandbox with self-correction; and presents every milestone in a responsive React/Vite workspace.

---

## What Works Today

- **Repository Ingestion & Workspace Isolation**:
  - Safe ZIP extraction with path-traversal protection.
  - Multi-file Python uploads with size and syntax validation.
  - Public HTTPS GitHub cloning with file limits.
  - Durable workspaces surviving server restarts during local development.
  - Isolated temporary workspace directories with pristine original diff baselines.

- **AST Code Intelligence & Hybrid RAG**:
  - Python AST symbol extraction (classes, functions, methods, line spans, docstrings).
  - AST boundary chunking with SHA-256 caching to avoid redundant parsing.
  - Hybrid retrieval combining BM25 lexical keyword ranking with FAISS vector similarity.

- **Multi-Model Provider Architecture & Dynamic Fallback**:
  - Supported providers: **Groq** (`openai/gpt-oss-120b`), **Google Gemini** (`gemini-2.5-flash`), **Mistral** (`codestral-2501`, `mistral-large-latest`), and **HuggingFace** (`Qwen/test`).
  - Provider interface supporting configurable `max_tokens` (up to 8192) and 120s HTTP timeouts to prevent response truncation.
  - Capability-based routing and automatic fallback on rate limit (429) or quota exhaustion (402).
  - Honest provider gate: when no model is configured, no fake edits or tests are fabricated.

- **LangGraph Correction-Loop State Machine**:
  - Explicit multi-node state graph:
    $$\text{implement\_node} \longrightarrow \text{write\_tests\_node} \longrightarrow \text{test\_node} \mathrel{\substack{\text{failed} \\ \longrightarrow \\ \text{passed} \\ \longrightarrow}} \begin{cases} \text{debug\_node} \longrightarrow \text{test\_node} \\ \text{review\_node} \longrightarrow \text{END} \end{cases}$$
  - Dedicated `write_tests_node` executing before test evaluation.
  - Bounded self-correction loop returning actionable pytest tracebacks to the coding model.

- **Robust Dual-Layer Test Generation (`TestWriterAgent`)**:
  - **Independent Test Writing Model**: Selects a secondary provider different from the coding provider to prevent the coder from writing tests biased toward its own bugs.
  - **Layer 1 (LLM Generation)**: Generates pytest tests against actual implementation code on disk with token-safe compact JSON schemas.
  - **Layer 2 (Programmatic AST Fallback)**: If LLM generation fails or hits provider limits, automatically generates structurally guaranteed pytest tests inspecting imports, functions, and class methods with zero hallucination.
  - **Automatic Dependency Extraction**: Scans workspace AST imports against standard library modules and auto-populates missing third-party packages into `requirements.txt`.
  - **Script & Mock Isolation**: Handles top-level script execution and eliminates `sys.modules` caching collisions.

- **Execution Sandbox & Local Fallback**:
  - Docker sandbox test execution with network disabled (`--network none`), read-only root, memory/PID caps, and timeout limits.
  - Controlled dependency preparation without copying or executing untrusted code during image builds.
  - Automatic persistent local virtualenv fallback (`.venv_<repo_id>`) with PYTHONPATH isolation when Docker is unavailable.

- **Auditable Diff, Review & Persistence**:
  - Strict file-tool constraints: exact replacements and file creation only (rejects unreviewable blanket rewrites).
  - Visible unified diffs and structured review summaries.
  - SQLite task persistence (`data/app.db`) for task history, activity timelines, diffs, and test outputs.

---

## Architecture

```mermaid
flowchart TD
  U[User / Browser] --> UI[React + Vite UI]
  UI --> API[FastAPI Backend]
  API --> IN[Repository Ingestion & Workspace]
  IN --> AST[AST Symbol Parser & Indexer]
  AST --> RAG[Hybrid RAG Engine (BM25 + FAISS)]
  RAG --> WF[Workflow Orchestrator]
  WF --> LG[LangGraph State Machine]
  
  subgraph LangGraph Pipeline
    LG --> IMP[implement_node: CodingAgent]
    IMP --> WT[write_tests_node: TestWriterAgent]
    WT --> TST[test_node: Sandbox / Local Pytest]
    TST -->|Test Failures| DBG[debug_node: Self-Correction Loop]
    DBG --> TST
    TST -->|Tests Pass or Iterations Exhausted| REV[review_node: Evidence-Based Review]
  end
  
  REV --> API
  API --> UI
```

---

## Quick Start

### 1. Backend Setup

```bash
# Clone and enter the repository
cd CodeBuddy

# Setup virtual environment
py -3 -m venv .venv
.\.venv\Scripts\activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```ini
# Recommended providers:
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

MISTRAL_API_KEY=your_mistral_api_key
MISTRAL_MODEL=codestral-2501
```

### 3. Frontend Setup

```bash
cd ui
npm install
npm run build
cd ..
```

### 4. Run Server

```bash
.\.venv\Scripts\uvicorn.exe app.main:app --reload --reload-dir app --port 8000
```

Open `http://localhost:8000` in your browser.

---

## Running Tests

Run the full 49-test suite:

```bash
.\.venv\Scripts\pytest.exe --basetemp=.pytest-tmp -v tests/
```

All 49 unit and integration tests execute and pass without requiring external API keys or active Docker daemon.

---

## Benchmark Results

Evaluated against **10 deterministic fixture tasks** across four engineering categories using the `benchmarks/` evaluation suite:

| Metric | Value |
| :--- | :--- |
| **Total Tasks** | 10 |
| **Task Success Rate** | 100.0% (10/10) |
| **Self-Correction Rate** | 0.0% (0 corrected) |
| **Average Iterations** | 1.00 |

Task-level breakdown: [`benchmarks/baseline_results.md`](benchmarks/baseline_results.md).
