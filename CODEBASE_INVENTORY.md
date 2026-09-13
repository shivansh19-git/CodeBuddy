# CodeBuddy - Comprehensive Codebase Inventory & File Guide

This document details the exact function of **every file** in this project, explaining why it exists, how it integrates into the architecture, and providing an explicit list of files that are **unused (dead code)**, **ephemeral run artifacts (garbage)**, or **temporary build caches**.

---

## 1. Project Architecture Overview

**CodeBuddy** (Agentic Software Engineer) is a transparent, autonomous AI coding assistant. It accepts Python repositories or files, indexes them using AST (Abstract Syntax Tree) and hybrid RAG (BM25 + FAISS vector search), delegates coding and planning tasks to LLMs (Mistral / HuggingFace), verifies changes via Docker-isolated pytest test runs, and self-corrects using a LangGraph state machine.

```
                  ┌──────────────────────┐
                  │ Streamlit UI (8501)  │
                  └──────────┬───────────┘
                             │ HTTP
                  ┌──────────▼───────────┐
                  │  FastAPI App (8000)  │
                  │     (app/main.py)    │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   ┌─────────────────┐               ┌─────────────────┐
   │ AST & Workspace │               │ Hybrid RAG Engine│
   │ (app/repository)│               │  (app/rag/...)  │
   └────────┬────────┘               └────────┬────────┘
            │                                 │
            └────────────────┬────────────────┘
                             │
                  ┌──────────▼───────────┐
                  │ Workflow Orchestrator│
                  │   (app/workflow.py)  │
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │ LangGraph Pipeline   │
                  │ (app/agents/graph.py)│
                  └──────────┬───────────┘
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐
│  CodingAgent     ││    TestAgent     ││   Reviewer       │
│(app/agents/coder)││(app/agents/tester││ (app/review.py) │
└──────────────────┘└────────┬─────────┘└──────────────────┘
                             │
                    ┌────────▼────────┐
                    │ Docker Sandbox  │
                    │(app/sandbox/...)│
                    └─────────────────┘
```

---

## 2. File-by-File Guide: Purpose and Usage

### Root Directory

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`pyproject.toml`** | Project configuration, metadata, build system settings, dependencies (`fastapi`, `langgraph`, `mistralai`, `faiss-cpu`, `pydantic`, `pytest`, `streamlit`, `uvicorn`, etc.), and tool configs (`pytest`, `ruff`). | Used by `uv` and `pip` to resolve dependencies, run tools, and package the app. | **Active** |
| **`uv.lock`** | Fully pinned, reproducible lockfile of all project dependencies and transient packages. | Used by `uv` to ensure identical installations across dev, test, and container environments. | **Active** |
| **`.env`** | Local environment file containing sensitive runtime secrets (e.g. `MISTRAL_API_KEY`, `HUGGINGFACE_API_KEY`, ports, debug settings). | Loaded by `app/config.py` using `pydantic-settings`. | **Active** |
| **`.env.example`** | Safe template demonstrating required and optional environment variables with dummy values. | Used as documentation and onboarding template for new setups without exposing secrets. | **Active** |
| **`.gitignore`** | Specifies files, build artifacts, virtual environments, caches, and secret files that Git must ignore. | Prevents committing `.venv`, `__pycache__`, `.env`, test temp dirs, and cache files to version control. | **Active** |
| **`README.md`** | Main project documentation: architecture diagrams, setup instructions, feature highlights, baseline benchmark scores, and API usage. | Primary human-facing documentation for developers and users. | **Active** |
| **`DEPLOYMENT.md`** | Production deployment guide: Docker Compose, Nginx reverse proxy, HTTPS/TLS setup, security hardening, resource limits, and monitoring. | Reference document for deploying the app in cloud or server environments. | **Active** |
| **`incomplete_tasks.md`** | Historical task checklist tracking PRD milestones. All items are now marked completed. | Historical milestone tracking. *(See Section 3)* | **Completed / Static** |

---

### Application Core (`app/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/__init__.py`** | Marks `app` as a Python package. | Allows modules inside `app` to be imported across the project. | **Active** |
| **`app/config.py`** | Defines `Settings` using Pydantic Settings. Loads paths (`workspace_root`, `database_path`, `vector_store_path`), API keys, timeouts, and rate limits. | Imported by `app/main.py`, `app/workflow.py`, `app/repository.py`, `app/db/repository.py`, etc. Central source of truth for configuration. | **Active** |
| **`app/main.py`** | The FastAPI HTTP server. Implements endpoints for repository uploads (ZIP/files/GitHub), task creation, status polling, diff retrieval, and health checks. | Main entry point for the backend API consumed by the Streamlit UI and external clients. | **Active** |
| **`app/repository.py`** | Manages repository lifecycles on disk: unpacking ZIPs, cloning GitHub repos, parsing Python files with AST to extract functions/classes, workspace isolation, and workspace TTL cleanup. | Called by `app/main.py` upon upload and `app/workflow.py` during repository analysis. | **Active** |
| **`app/review.py`** | Compares modified code against original code to generate unified diffs, patch files, review summaries, and changed-file statistics. | Invoked by `app/agents/graph.py` and `app/workflow.py` at the conclusion of a coding task. | **Active** |
| **`app/schemas.py`** | Core Pydantic models for data interchange: `TaskRecord`, `TaskStatus`, `ActivityEvent`, `SymbolRecord`, `PlanStep`, `TestResult`, `DiffChunk`, etc. | Fundamental type definitions imported throughout the entire backend (`app/`, `tests/`, `benchmarks/`). | **Active** |
| **`app/security.py`** | Implements API-level security: `RequestRateLimiter` (sliding-window IP throttling) and `TaskConcurrencyLimiter` (limits simultaneous active agent tasks). | Middleware in `app/main.py` to protect the server from spam and resource exhaustion. | **Active** |
| **`app/workflow.py`** | Top-level workflow orchestrator. Coordinates repository loading, RAG context retrieval, model selection, plan generation, and delegates the edit-test loop to LangGraph. | Called by `app/main.py` inside a background thread pool when a user submits a task. | **Active** |

---

### Multi-Agent Subsystem (`app/agents/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/agents/__init__.py`** | Package initialization for agent modules. | Makes `app.agents` importable. | **Active** |
| **`app/agents/coder.py`** | `CodingAgent`: Constructs the strict system prompt for coding LLMs, parses proposed modifications, enforces exact match-and-replace rules or file creation, and verifies Python syntax validity with automatic AST rollbacks. | Core agent that writes code. Called by `app/agents/graph.py` and `app/workflow.py`. | **Active** |
| **`app/agents/graph.py`** | LangGraph State Machine defining an explicit agent loop (`implement` → `test` → `debug` → `review`) with conditional transitions based on test results and iteration limits. | Orchestrates self-correction. Invoked via `run_graph()` from `app/workflow.py`. | **Active** |
| **`app/agents/planner.py`** | `PlannerAgent`: Analyzes task description and retrieved AST context to generate a structured implementation plan. Includes a deterministic fallback planner if LLM is unavailable. | Called by `app/workflow.py` before coding begins. | **Active** |
| **`app/agents/tester.py`** | `TestAgent`: Executes pytest test suites against the modified workspace inside an isolated container/subprocess and parses exit codes and output. | Called by `app/agents/graph.py` to evaluate whether edits passed or broke tests. | **Active** |

---

### Persistence Layer (`app/db/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/db/__init__.py`** | Package initialization for the database layer. | Makes `app.db` importable. | **Active** |
| **`app/db/repository.py`** | `TaskStore`: Lightweight SQLite storage engine that creates tables and saves/queries `TaskRecord` history and event timelines. | Used by `app/main.py` to persist tasks to `data/app.db` and display task history in Streamlit. | **Active** |

---

### LLM & Embedding Integrations (`app/models/` & `app/embeddings/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/models/base.py`** | Base interface `ModelProvider` and dataclass `ModelDescriptor` defining contract for chat completion providers. | Abstract base for LLM integrations. | **Active** |
| **`app/models/providers.py`** | Concrete implementations: `MistralModelProvider` and `HuggingFaceModelProvider`, including HTTP 429 rate-limit and 402 quota error handling. | Communicates with Mistral and Hugging Face APIs. | **Active** |
| **`app/models/registry.py`** | `build_model_router()` factory: inspects environment variables and registers configured LLM providers. | Instantiates model provider router in `app/workflow.py`. | **Active** |
| **`app/models/router.py`** | `ModelRouter`: Selects the best available model provider based on task requirements (e.g. tools, structured output) and tracks healthy/exhausted states. | Enables automatic fallback from primary to secondary LLM providers. | **Active** |
| **`app/embeddings/base.py`** | Base interface `EmbeddingProvider` and descriptor for vector embedding models. | Abstract base for embedding integrations. | **Active** |
| **`app/embeddings/providers.py`** | `HttpEmbeddingProvider`: Calls embedding endpoints (e.g. Mistral embeddings) to generate vector representations. | Generates dense embeddings for code chunks. | **Active** |
| **`app/embeddings/registry.py`** | `build_embedding_router()` factory that inspects environment keys to initialize embedding providers. | Used in `app/workflow.py` to configure RAG embeddings. | **Active** |
| **`app/embeddings/router.py`** | `EmbeddingRouter`: Routes text embedding requests to active providers with error handling. | Used by `HybridRetriever` to embed queries and code. | **Active** |

---

### Retrieval Augmented Generation (`app/rag/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/rag/__init__.py`** | Package initialization for RAG components. | Makes `app.rag` importable. | **Active** |
| **`app/rag/cache.py`** | `IndexCache` & `compute_content_hash`: Caches AST symbol tables and chunk embeddings based on SHA-256 file hashes to avoid re-parsing unchanged files. | Used in `app/repository.py` to speed up repository re-indexing. | **Active** |
| **`app/rag/chunker.py`** | `build_chunks`: Splits Python source files into logical chunks based on AST function and class boundaries. | Feeds code units into the vector store and BM25 index in `app/workflow.py`. | **Active** |
| **`app/rag/vector_store.py`** | `FaissVectorStore`: In-memory and disk-persisted FAISS vector index with namespace isolation per repository. | Handles semantic vector search over code snippets. | **Active** |
| **`app/rag/retriever.py`** | `HybridRetriever`: Blends BM25 lexical keyword ranking with FAISS vector similarity to find the most relevant code for a given task. | Main retrieval engine called by `app/workflow.py` to construct context for prompts. | **Active** |

---

### Sandbox & Execution Tools (`app/sandbox/` & `app/tools/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/sandbox/__init__.py`** | Package initialization for sandbox tools. | Makes `app.sandbox` importable. | **Active** |
| **`app/sandbox/docker.py`** | Docker container runner (`run_in_sandbox`): Spawns ephemeral containers with memory, CPU, and network limits to run untrusted tests. | Called by `app/tools/execution.py` when Docker is active. | **Active** |
| **`app/sandbox/preparation.py`** | Parses and validates `requirements.txt` from user repositories, rejecting unsafe flags (e.g. editable installs, URLs) before building container layers. | Ensures safe dependency installation in sandbox containers. | **Active** |
| **`app/sandbox/security.py`** | Validates command-line arguments, whitelisting only safe commands (`pytest`, `python`, `ruff`) and preventing shell injection. | Called by `app/sandbox/docker.py` before executing commands in containers. | **Active** |
| **`app/tools/__init__.py`** | Package initialization for agent tools. | Makes `app.tools` importable. | **Active** |
| **`app/tools/filesystem.py`** | Safe filesystem tools: `read_file`, `create_file`, and `replace_once`. Enforces strict workspace path boundaries to prevent path traversal. | Used by `CodingAgent` to apply LLM code edits. | **Active** |
| **`app/tools/execution.py`** | `run_tests`: High-level test executor that bridges either Docker sandbox execution or local fallback testing. | Used by `TestAgent` to run pytest. | **Active** |
| **`app/tools/search.py`** | Lexical file scanner `search_code()`. | **DEAD CODE / UNUSED**: Superseded by AST analysis and `HybridRetriever`. Never imported anywhere. *(See Section 3)* | **Unused (Dead Code)** |

---

### Benchmarking Suite (`benchmarks/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`benchmarks/__init__.py`** | Package initialization for benchmarks. | Makes `benchmarks` importable. | **Active** |
| **`benchmarks/fixtures.py`** | Defines 10 deterministic benchmark tasks across 4 categories: Bug fixing, Feature implementation, Refactoring, and Test writing. | Test problem set for evaluating agent performance. | **Active** |
| **`benchmarks/runner.py`** | Benchmark test harness: sets up temporary workspaces, executes tasks, records iterations, and computes pass@1 and cost metrics. | Used by benchmark scripts and unit tests in `tests/test_benchmarks.py`. | **Active** |
| **`benchmarks/run_dry.py`** | CLI runner (`uv run python benchmarks/run_dry.py`) executing benchmarks in mock mode to verify fixture validity without calling external LLMs. | Establishes the 100% baseline reported in documentation. | **Active** |
| **`benchmarks/baseline_results.md`** | Markdown table recording baseline benchmark metrics (10/10 passing, 100% success rate, 0 LLM cost). | Reference artifact for tracking agent accuracy regressions. | **Active** |

---

### Docker Infrastructure (`docker/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`docker/Dockerfile`** | Base sandbox Dockerfile with `python:3.11-slim`, `pytest`, and `ruff`. | Built as `agentic-python-sandbox` image for executing test suites safely. | **Active** |
| **`docker/Dockerfile.dependencies`** | Multi-stage Dockerfile that installs dynamic `requirements.txt` from user repositories without copying code. | Used by `app/sandbox/preparation.py` when user projects need custom packages. | **Active** |
| **`docker/Dockerfile.app`** | Production image definition for running the FastAPI backend and Streamlit UI with `uv`. | Used by `docker-compose.yml` to build production containers. | **Active** |
| **`docker/docker-compose.yml`** | Multi-container Compose spec launching the FastAPI backend service (`app`) and Streamlit frontend service (`ui`). | Used for one-command production deployments (`docker compose up`). | **Active** |

---

### Frontend User Interface (`ui/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`ui/streamlit_app.py`** | Full-featured Streamlit web application. Provides repository upload tabs (ZIP, loose files, GitHub), provider status display, real-time event logs, interactive diff viewer, and patch export. | Primary GUI interface for end users interacting with CodeBuddy (`uv run streamlit run ui/streamlit_app.py`). | **Active** |

---

### Test Suite (`tests/`)

All test files are actively run by pytest (`uv run pytest`) and test core functionality:

| File | Component Tested |
| :--- | :--- |
| **`tests/test_agents.py`** | PlannerAgent fallback planning and TestAgent output parsing. |
| **`tests/test_api_uploads.py`** | FastAPI endpoints for ZIP, file upload, and GitHub clone validation. |
| **`tests/test_benchmarks.py`** | Benchmark runner setup, execution, and metrics calculations. |
| **`tests/test_caching.py`** | SHA-256 AST symbol cache roundtrip and invalidation logic. |
| **`tests/test_coder.py`** | CodingAgent single-replacement rules, syntax rollback, and error reporting. |
| **`tests/test_execution.py`** | Sandbox test execution and pytest exit code handling. |
| **`tests/test_graph.py`** | LangGraph correction state machine, node transitions, retry loops, and limits. |
| **`tests/test_model_router.py`** | Capability filtering, availability tracking, and provider fallback order. |
| **`tests/test_preparation.py`** | Requirement spec validation and blocking of malicious pip flags. |
| **`tests/test_providers.py`** | HuggingFace and Mistral provider payload formation and error mapping. |
| **`tests/test_rag.py`** | AST code chunking, BM25 retrieval, and context ranking. |
| **`tests/test_repository.py`** | Path traversal protection, workspace cloning, and TTL expiration cleanup. |
| **`tests/test_schemas.py`** | Pydantic schema validation, default factories, and serialization. |
| **`tests/test_security.py`** | Sliding-window request rate limiter and concurrent task semaphore. |
| **`tests/test_task_store.py`** | SQLite TaskStore insertion, query, and event persistence. |
| **`tests/test_vector_store.py`** | FAISS vector store creation, indexing, and repository namespace isolation. |
| **`tests/test_workflow.py`** | High-level `run_task` pipeline, retry guards, and fallback routing. |

---

### Data Directory (`data/`)

| Path | Description | Status |
| :--- | :--- | :--- |
| **`data/app.db`** | SQLite database file holding task records, states, and timeline logs. | **Active Data** (Persists task history across restarts) |
| **`data/workspaces/.cache/index_cache.json`** | Cache of AST symbol hashes for indexed repositories. | **Active Cache** (Speeds up repeated repository indexing) |
| **`data/workspaces/<uuid>/`** | Ephemeral working directories cloned for past agent task runs. | **Stale Run Artifacts / Garbage** *(See Section 3)* |
| **`data/workspaces/<uuid>_original/`** | Pristine original snapshots of past user task repositories. | **Stale Run Artifacts / Garbage** *(See Section 3)* |

---

## 3. List of Files NOT In Use ("Garbage" & Dead Code)

Below is the definitive list of files and folders that are **not in use**, **dead code**, or **leftover temporary artifacts**:

### 1. Dead Code in Source Files
* **`app/tools/search.py`**
  * **Why it is garbage:** Contains a standalone function `search_code()`. This function is **never imported or called** anywhere in `app/`, `tests/`, or `benchmarks/`. The project replaced naive lexical file scanning with AST parsing (`app/repository.py`) and hybrid BM25 + FAISS retrieval (`app/rag/retriever.py`).
  * **Recommendation:** Safe to delete.

### 2. Ephemeral Workspaces & Stale Task Folders
When tasks are executed via the API or Streamlit, temporary workspaces are generated under `data/workspaces/`. Many have accumulated from previous testing sessions and contain obsolete code, test output, and nested `.pytest_cache` folders:
* `data/workspaces/0e6a6008-a771-40c5-982d-5040b516f980/` and `..._original/`
* `data/workspaces/280be729-5b13-4925-9cb3-2202942df1e2/` and `..._original/`
* `data/workspaces/32ea0ab5-b780-44a8-8eaf-09a63740347e/` and `..._original/`
* `data/workspaces/3bbc986f-87f6-4668-be55-c506b052bda7/` and `..._original/`
* `data/workspaces/4c46e85e-9d3b-4a90-b27a-cc60c9d6961d/` and `..._original/`
* `data/workspaces/5dcd17df-a7cf-4ffc-b716-d67df2800cbf/` and `..._original/`
* `data/workspaces/85ff5604-4d3f-440a-bef8-0c7c212842b1/` and `..._original/`
* `data/workspaces/afaa10be-ddb5-48d0-ba17-941513f7415d/` and `..._original/`
* `data/workspaces/b1a630e6-d316-488f-81bd-55c8a7e484e8/` and `..._original/`
* `data/workspaces/b61f3204-391e-42de-be11-45dcc4cdaf9b/` and `..._original/`
* `data/workspaces/b8260622-f981-4029-b5c9-e1f57881b312/` and `..._original/`
* `data/workspaces/c3712060-f7a5-471b-9eb0-80c880da8acc/` and `..._original/`
* `data/workspaces/c3bde697-f271-480a-a652-5fcf87e7fc16/` and `..._original/`
* `data/workspaces/c868c3a1-5e32-4cdd-89f9-28a6c5675f5a/` and `..._original/`
* `data/workspaces/e8363481-6a47-4c6a-851b-f284279bf69f/` and `..._original/`
* `data/workspaces/fa5882a2-bc45-4fb2-8aff-9116ad282dae/` and `..._original/`
  * **Why it is garbage:** These are leftover scratch directories from past interactive task executions (`check.py`, `hello.py`, `maths.py`).
  * **Recommendation:** Safe to delete all UUID subfolders inside `data/workspaces/` (keep `data/workspaces/.cache/` and `data/app.db`).

### 3. Temporary Test & Cache Directories
* **`.pytest-tmp/`**: Leftover temporary directory from previous pytest runs.
* **`.tmp/`**: Temporary benchmark dry runs and lock file scratch tests.
* **`.pytest_cache/`**: Pytest internal run cache.
* **`.ruff_cache/`**: Ruff linter internal cache.
* **`.uv-cache/`**: Package wheel cache generated by `uv`.
  * **Why it is garbage:** None of these contain source code; they are automatically recreated as needed by development tools.
  * **Recommendation:** Safe to delete to reclaim disk space.

### 4. Obsolete / Completed Checklist Document
* **`incomplete_tasks.md`**
  * **Why it is redundant:** Every milestone listed in this file is marked complete (`[x]`). The current system capabilities and milestones are already documented in `README.md`.
  * **Recommendation:** Can be archived or deleted if you only want active documentation.

---

## 4. Summary Cleanup Command (PowerShell)

If you wish to clean up all temporary garbage and dead code, you can run:

```powershell
# Remove dead code tool
Remove-Item -Path "app\tools\search.py" -Force

# Remove temporary test caches and scratch directories
Remove-Item -Recurse -Force .pytest-tmp, .tmp, .pytest_cache, .ruff_cache, .uv-cache -ErrorAction SilentlyContinue

# Clean up stale workspace run directories (preserving index_cache.json)
Get-ChildItem -Path "data\workspaces" -Directory | Where-Object { $_.Name -ne ".cache" } | Remove-Item -Recurse -Force
```
