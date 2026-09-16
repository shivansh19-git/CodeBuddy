# CodeBuddy - Comprehensive Codebase Inventory & File Guide

This document details the exact function of **every file and directory** in this project, explaining why it exists, how it integrates into the architecture, and providing an explicit, categorized breakdown of files that are **useless/redundant (dead code and one-off scratch scripts)** and files that are **temporary (caches and ephemeral task artifacts)**.

---

## 1. Project Architecture Overview

**CodeBuddy** (Agentic Software Engineer) is an explainable, autonomous coding assistant for Python repositories. It parses codebases using AST, retrieves relevant context using hybrid RAG (BM25 lexical search + FAISS vector search), coordinates coding and test writing via a LangGraph state machine with provider fallback (Groq, Gemini, Mistral, HuggingFace), executes tests in an isolated sandbox with local venv fallback, and self-corrects based on pytest results.

```
                  ┌──────────────────────┐
                  │ React UI (Browser)   │
                  └──────────┬───────────┘
                             │ HTTP / SSE
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
                  │ LangGraph State Graph│
                  │ (app/agents/graph.py)│
                  └──────────┬───────────┘
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐
│  CodingAgent     ││ TestWriterAgent  ││   Reviewer       │
│(app/agents/coder)││ (test_writer.py) ││ (app/review.py) │
└─────────┬────────┘└────────┬─────────┘└──────────────────┘
          │                  │
          └─────────┬────────┘
                    ▼
          ┌──────────────────┐
          │    TestAgent     │
          │(app/agents/tester│
          └─────────┬────────┘
                    ▼
          ┌──────────────────┐
          │ Docker / Local   │
          │ Pytest Sandbox   │
          └──────────────────┘
```

---

## 2. File-by-File Guide: Purpose and Usage

### Root Configuration & Documentation

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`pyproject.toml`** | Project configuration, metadata, build system settings, dependencies (`fastapi`, `langgraph`, `mistralai`, `faiss-cpu`, `pydantic`, `pytest`, `uvicorn`, etc.), and tool configs (`pytest`, `ruff`). Configures `addopts = "-p no:cacheprovider"` to avoid cache lock issues. | Used by `uv`, `pip`, and `pytest` to configure runtime, build, and tests. | **Active** |
| **`uv.lock`** | Fully pinned, reproducible lockfile of all project dependencies and transitive packages. | Used by `uv` to ensure identical installations across dev, test, and container environments. | **Active** |
| **`.env`** | Local environment file containing runtime secrets and provider keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `HUGGINGFACE_API_KEY`, model names, limits). | Loaded by `app/config.py` using `pydantic-settings`. | **Active** |
| **`.env.example`** | Safe template demonstrating required and optional environment variables with dummy values. | Used as documentation and onboarding template without exposing secrets. | **Active** |
| **`.gitignore`** | Specifies files, build artifacts, virtual environments, caches, and secret files that Git must ignore. | Prevents committing `.venv`, caches, and ephemeral workspaces to version control. | **Active** |
| **`README.md`** | Main project documentation: architecture diagrams, setup instructions, feature highlights, and benchmark results. | Primary human-facing documentation. | **Active** |
| **`DEPLOYMENT.md`** | Production deployment guide: Docker Compose, Nginx reverse proxy, HTTPS/TLS setup, security hardening, resource limits, and monitoring. | Reference document for deploying the app in production. | **Active** |
| **`CODEBASE_INVENTORY.md`** | This document: comprehensive audit of every file, architectural role, and identification of temp/useless files. | Developer reference and codebase cleanliness guide. | **Active** |

---

### Application Core (`app/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/__init__.py`** | Marks `app` as a Python package. | Allows modules inside `app` to be imported across the project. | **Active** |
| **`app/config.py`** | Defines `Settings` using Pydantic Settings. Loads paths (`workspace_root`, `database_path`, `vector_store_path`), API keys, timeouts, and rate limits. | Central source of truth for configuration throughout `app/`. | **Active** |
| **`app/main.py`** | The FastAPI HTTP server. Implements endpoints for repository uploads (ZIP/files/GitHub), task creation, status polling, diff retrieval, provider reloading, and health checks. | Main entry point for the backend API consumed by the UI. | **Active** |
| **`app/repository.py`** | Manages repository lifecycles on disk: unpacking ZIPs, cloning GitHub repos, parsing Python files with AST to extract functions/classes, workspace isolation, and workspace TTL cleanup. | Called upon repository upload and task initialization. | **Active** |
| **`app/review.py`** | Compares modified code against original pristine snapshot to generate unified diffs, patch files, review summaries, and changed-file statistics. | Invoked by `app/agents/graph.py` and `app/workflow.py` at the conclusion of a coding task. | **Active** |
| **`app/schemas.py`** | Core Pydantic models for data interchange: `TaskRecord`, `TaskStatus`, `ActivityEvent`, `Symbol`, `PlanStep`, `TestResult`, `CodingResponse`, `EditOperation`, etc. | Fundamental type definitions imported throughout backend and tests. | **Active** |
| **`app/security.py`** | Implements API-level security: `RequestRateLimiter` (sliding-window IP throttling) and `TaskConcurrencyLimiter` (limits simultaneous active agent tasks). | Middleware in `app/main.py` to protect server from overload. | **Active** |
| **`app/workflow.py`** | Top-level workflow orchestrator. Coordinates repository loading, RAG context retrieval, model selection, independent test-writer provider selection (`_select_test_writing_provider`), plan generation, and delegates the graph loop to LangGraph. | Called by `app/main.py` in background worker threads. | **Active** |

---

### Multi-Agent Subsystem (`app/agents/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/agents/__init__.py`** | Package initialization for agent modules. | Makes `app.agents` importable. | **Active** |
| **`app/agents/coder.py`** | `CodingAgent`: Constructs the strict system prompt for coding LLMs, parses proposed modifications, enforces exact match-and-replace rules or file creation, and verifies Python syntax validity with automatic AST rollbacks. Supports `max_tokens=8192` with fallback. | Core agent that writes code edits. Called by `app/agents/graph.py`. | **Active** |
| **`app/agents/graph.py`** | LangGraph State Machine defining a 5-node agent loop (`implement_node` → `write_tests_node` → `test_node` → `debug_node` → `review_node`). Supports flexible test-runner signatures and retry budgeting. | Orchestrates the implementation, test writing, and self-correction loop. | **Active** |
| **`app/agents/planner.py`** | `PlannerAgent`: Analyzes task description and retrieved AST context to generate a structured implementation plan. Includes a deterministic fallback planner if LLM is unavailable. | Called by `app/workflow.py` before coding begins. | **Active** |
| **`app/agents/test_writer.py`** | `TestWriterAgent`: Dedicated test generation agent. Uses a secondary independent LLM provider with token-safe compact prompts, backed by an AST-based programmatic test generator (`generate_ast_tests_for_repo`) that extracts real modules, functions, and classes with zero hallucination. Auto-detects 3rd-party imports and populates `requirements.txt`. | Invoked in `write_tests_node` to produce bulletproof tests before test execution. | **Active** |
| **`app/agents/tester.py`** | `TestAgent`: Executes pytest test suites against the modified workspace inside the sandbox or local fallback, parsing exit codes and output. | Called by `app/agents/graph.py` to evaluate whether tests passed or broke. | **Active** |

---

### Persistence Layer (`app/db/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/db/__init__.py`** | Package initialization for the database layer. | Makes `app.db` importable. | **Active** |
| **`app/db/repository.py`** | `TaskStore`: Lightweight SQLite storage engine that creates tables and saves/queries `TaskRecord` history and event timelines. | Used by `app/main.py` to persist tasks to `data/app.db`. | **Active** |

---

### LLM & Embedding Integrations (`app/models/` & `app/embeddings/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/models/base.py`** | Base interface `LLMProvider` and dataclass `ModelDescriptor` defining contracts for chat completion providers. Includes `max_tokens` support. | Abstract base for LLM integrations. | **Active** |
| **`app/models/providers.py`** | Concrete implementations for Groq, Gemini, Mistral, and HuggingFace, with custom HTTP clients, 120s timeouts, `max_tokens` payloads, and 429/402 error mapping. | Connects to external AI APIs. | **Active** |
| **`app/models/registry.py`** | `build_model_router()` and `reload_model_router()` factories that register available LLMs from environment variables. | Instantiates and reloads model providers in `app/workflow.py`. | **Active** |
| **`app/models/router.py`** | `ModelRouter`: Selects the best available model provider based on task requirements (tools, structured output) and tracks healthy/exhausted states. | Enables automatic fallback between models. | **Active** |
| **`app/embeddings/base.py`** | Base interface `EmbeddingProvider` and descriptor for vector embedding models. | Abstract base for embedding integrations. | **Active** |
| **`app/embeddings/providers.py`** | `HttpEmbeddingProvider`: Calls embedding endpoints to generate vector representations. | Generates dense embeddings for code chunks. | **Active** |
| **`app/embeddings/registry.py`** | `build_embedding_router()` factory that initializes embedding providers from `.env`. | Used in `app/workflow.py` to configure RAG embeddings. | **Active** |
| **`app/embeddings/router.py`** | `EmbeddingRouter`: Routes text embedding requests to active providers with fallback. | Used by `HybridRetriever` to embed queries and code. | **Active** |

---

### Retrieval Augmented Generation (`app/rag/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/rag/__init__.py`** | Package initialization for RAG components. | Makes `app.rag` importable. | **Active** |
| **`app/rag/cache.py`** | `IndexCache` & `compute_content_hash`: Caches AST symbol tables and chunk embeddings based on SHA-256 file hashes. | Speeds up repository re-indexing. | **Active** |
| **`app/rag/chunker.py`** | `build_chunks`: Splits Python source files into logical chunks based on AST function and class boundaries. | Feeds code units into the vector store and BM25 index. | **Active** |
| **`app/rag/vector_store.py`** | `FaissVectorStore`: FAISS vector index with namespace isolation per repository. | Handles semantic vector search over code snippets. | **Active** |
| **`app/rag/retriever.py`** | `HybridRetriever`: Blends BM25 lexical keyword ranking with FAISS vector similarity. | Main retrieval engine called by `app/workflow.py`. | **Active** |

---

### Sandbox & Execution Tools (`app/sandbox/` & `app/tools/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`app/sandbox/__init__.py`** | Package initialization for sandbox tools. | Makes `app.sandbox` importable. | **Active** |
| **`app/sandbox/docker.py`** | Docker container runner (`run_in_sandbox`): Runs ephemeral containers with memory, CPU, and network limits. | Called by `app/tools/execution.py` when Docker is active. | **Active** |
| **`app/sandbox/preparation.py`** | Parses and validates `requirements.txt` from user repositories, rejecting unsafe flags before building container layers. | Ensures safe dependency installation in sandbox containers. | **Active** |
| **`app/sandbox/security.py`** | Validates command-line arguments, whitelisting only safe commands (`pytest`, `python`, `ruff`) and preventing shell injection. | Called before executing container commands. | **Active** |
| **`app/tools/__init__.py`** | Package initialization for agent tools. | Makes `app.tools` importable. | **Active** |
| **`app/tools/filesystem.py`** | Safe filesystem tools: `read_file`, `create_file`, and `replace_once`. Enforces strict workspace path boundaries to prevent path traversal. | Used by `CodingAgent` and `TestWriterAgent` to apply edits. | **Active** |
| **`app/tools/execution.py`** | `run_tests`: High-level test executor bridging Docker execution and persistent local venv fallback (`_run_local_fallback`). | Used by `TestAgent` to run pytest. | **Active** |

---

### Benchmarking Suite (`benchmarks/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`benchmarks/__init__.py`** | Package initialization for benchmarks. | Makes `benchmarks` importable. | **Active** |
| **`benchmarks/fixtures.py`** | Defines 10 deterministic benchmark tasks across 4 categories: Bug fixing, Feature implementation, Refactoring, and Test writing. | Test problem set for evaluating agent performance. | **Active** |
| **`benchmarks/runner.py`** | Benchmark test harness: sets up temporary workspaces, executes tasks, records iterations, and computes pass@1 and cost metrics. | Used by benchmark scripts and unit tests. | **Active** |
| **`benchmarks/run_dry.py`** | CLI runner (`python benchmarks/run_dry.py`) executing benchmarks in mock mode to verify fixture validity. | Establishes the 100% baseline reported in documentation. | **Active** |
| **`benchmarks/baseline_results.md`** | Markdown table recording baseline benchmark metrics (10/10 passing, 100% success rate). | Reference artifact for tracking agent accuracy regressions. | **Active** |

---

### Docker Infrastructure (`docker/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`docker/Dockerfile`** | Base sandbox Dockerfile with `python:3.11-slim`, `pytest`, and `ruff`. | Built as `agentic-python-sandbox` image. | **Active** |
| **`docker/Dockerfile.dependencies`** | Multi-stage Dockerfile that installs dynamic `requirements.txt` from user repositories. | Used by `app/sandbox/preparation.py`. | **Active** |
| **`docker/Dockerfile.app`** | Multi-stage production image definition for compiling the React frontend and running the FastAPI backend. | Used by `docker-compose.yml`. | **Active** |
| **`docker/docker-compose.yml`** | Container Compose spec launching the unified API service. | Used for one-command production deployments. | **Active** |

---

### Frontend User Interface (`ui/`)

| File | What it does | Why it is used / Where it is called | Status |
| :--- | :--- | :--- | :--- |
| **`ui/package.json`** | Defines npm dependencies (React, Vite, Tailwind, Lucide React) and build scripts for the frontend. | Used to build frontend assets (`npm run build`). | **Active** |
| **`ui/src/App.tsx`** | Main React application component. Provides repository upload tabs, provider status display, real-time event logs, interactive split-pane diff viewer, and API communication. | Primary frontend component rendered by the browser. | **Active** |
| **`ui/vite.config.ts`** | Configuration for Vite bundler, defining React plugins and path aliases. | Used by `npm run build` to output optimized static files into `ui/dist`. | **Active** |

---

### Test Suite (`tests/` — 49 Tests Total)

All 49 tests pass in under 10 seconds without requiring external API keys or Docker:

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
| **`tests/test_providers.py`** | HuggingFace, Mistral, Groq, and Gemini provider payload formation. |
| **`tests/test_rag.py`** | AST code chunking, BM25 retrieval, and context ranking. |
| **`tests/test_repository.py`** | Path traversal protection, workspace cloning, and TTL expiration cleanup. |
| **`tests/test_schemas.py`** | Pydantic schema validation, default factories, and serialization. |
| **`tests/test_security.py`** | Sliding-window request rate limiter and concurrent task semaphore. |
| **`tests/test_task_store.py`** | SQLite TaskStore insertion, query, and event persistence. |
| **`tests/test_test_writer.py`** | AST test generator, package auto-extraction, requirements updating, and TestWriterAgent fallback. |
| **`tests/test_vector_store.py`** | FAISS vector store creation, indexing, and repository namespace isolation. |
| **`tests/test_workflow.py`** | High-level `run_task` pipeline, retry guards, and fallback routing. |

---

## 3. Useless Files vs. Temporary Files Breakdown

Below is the definitive classification of files that can be safely deleted or cleaned up.

### Category A: Useless / Redundant Files (Dead Code & Scratch Scripts)

These files contain code or documentation that is completely unused, superseded, or obsolete:

1. **`app/tools/search.py`**
   - **Reason**: Dead code. Contains a standalone `search_code()` function that is **never imported anywhere** in `app/`, `tests/`, or `benchmarks/`. It was superseded by AST parsing and `HybridRetriever`.
   - **Action**: Safe to delete immediately.

2. **`debug_agent.py`** (Root directory)
   - **Reason**: One-off ad-hoc debugging script used to manually test `run_task` with dummy strings. Does not belong in the production codebase.
   - **Action**: Safe to delete immediately.

3. **`fuzzy_test.py`** (Root directory)
   - **Reason**: One-off scratch test script for regex/fuzzy line replacement. Redundant; tests in `tests/test_coder.py` cover this officially.
   - **Action**: Safe to delete immediately.

4. **`test.py`** (Root directory)
   - **Reason**: Temporary 4-line scratch script used to remove a directory.
   - **Action**: Safe to delete immediately.

5. **`incomplete_tasks.md`** (Root directory)
   - **Reason**: Obsolete historical tracking list where all tasks are already marked completed (`[x]`). Active features are fully documented in `README.md`.
   - **Action**: Safe to delete or archive.

6. **`test_dir/`** (Root directory)
   - **Reason**: Residual directory containing a dummy `test.txt` file created during testing.
   - **Action**: Safe to delete.

7. **`workspace/`** (Root directory)
   - **Reason**: Leftover scratch directory containing an old `.test_venv`. The real task workspaces live under `data/workspaces/`.
   - **Action**: Safe to delete.

8. **`.bolt/`** (Root directory)
   - **Reason**: Leftover scaffolding configuration from a previous web IDE template (`prompt` and `config.json`). Not used by CodeBuddy.
   - **Action**: Safe to delete.

---

### Category B: Temporary Files (Caches & Ephemeral Run Data)

These files and folders are created dynamically during development, test runs, or user tasks. None of them contain source code, and all can be safely purged:

1. **`.pytest-tmp/` and `pytest_tmp/`**
   - **What it is**: Temporary workspace and fixture directories created during pytest runs.
   - **Safety**: Safe to purge; automatically recreated during test runs.

2. **`.pytest_cache/`**
   - **What it is**: Pytest internal execution and failure-tracking cache.
   - **Safety**: Safe to delete; automatically recreated.

3. **`.ruff_cache/`**
   - **What it is**: Ruff linter internal analysis cache.
   - **Safety**: Safe to delete; automatically recreated.

4. **`.uv-cache/`**
   - **What it is**: Local package wheels and index cache created by `uv`.
   - **Safety**: Safe to delete to free disk space.

5. **`.tmp/`**
   - **What it is**: Scratch directory used for temporary file operations and benchmarks.
   - **Safety**: Safe to delete.

6. **`data/workspaces/<uuid>/` and `data/workspaces/<uuid>_original/`**
   - **What it is**: Ephemeral working directories cloned for past agent runs.
   - **Safety**: Safe to delete all UUID subfolders inside `data/workspaces/`. (Keep `data/app.db` and `data/workspaces/.cache/`).

---

## 4. One-Click Cleanup Commands

### PowerShell (Windows)

```powershell
# 1. Remove dead code and scratch files
Remove-Item -Path "app\tools\search.py", "debug_agent.py", "fuzzy_test.py", "test.py", "incomplete_tasks.md" -Force -ErrorAction SilentlyContinue

# 2. Remove scratch directories
Remove-Item -Recurse -Force "test_dir", "workspace", ".bolt" -ErrorAction SilentlyContinue

# 3. Remove temporary test caches
Remove-Item -Recurse -Force ".pytest-tmp", "pytest_tmp", ".tmp", ".pytest_cache", ".ruff_cache", ".uv-cache" -ErrorAction SilentlyContinue

# 4. Clean up stale workspaces (preserving index_cache.json and database)
Get-ChildItem -Path "data\workspaces" -Directory | Where-Object { $_.Name -ne ".cache" } | Remove-Item -Recurse -Force
```

### Bash / Linux / macOS

```bash
# 1. Remove dead code and scratch files
rm -f app/tools/search.py debug_agent.py fuzzy_test.py test.py incomplete_tasks.md

# 2. Remove scratch directories
rm -rf test_dir workspace .bolt

# 3. Remove temporary test caches
rm -rf .pytest-tmp pytest_tmp .tmp .pytest_cache .ruff_cache .uv-cache

# 4. Clean up stale workspaces (preserving index_cache.json)
find data/workspaces -mindepth 1 -maxdepth 1 -not -name ".cache" -exec rm -rf {} +
```
