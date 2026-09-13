# Agentic Software Engineer - Incomplete Tasks Checklist

Based on the Definition of Done in the `Agentic_Software_Engineer_Revised_PRD.md` and the "Next implementation milestones" in the `README.md`, here is the updated status of tasks:

### Remaining Tasks
_All tasks completed — see Completed Milestones below._

### Completed Milestones
- [x] **LLM Provider Adapters**: Real provider adapters for HuggingFace and Mistral APIs with capability-aware router.
- [x] **Provider Rate-Limit & Quota Handling**: Granular HTTP 429/402/403 status handling with retry-after header parsing and dynamic availability tracking.
- [x] **Embeddings & Vector Store**: Hybrid lexical + semantic retrieval with isolated FAISS namespaces.
- [x] **Coding Node & Self-Correction**: Constrained file editing tools with single-replacement validation and Docker-isolated test loop.
- [x] **Database Persistence**: SQLite storage for tasks, state history, and timeline events.
- [x] **Diff & Patch Export**: Downloadable `.patch` and full repository archive downloads in both API and Streamlit UI.
- [x] **Evaluation & Benchmarking Suite**: Deterministic benchmark fixtures across 4 categories with automated metrics runner (`benchmarks/`).
- [x] **Incremental RAG Caching**: SHA-256 content-hash caching for AST symbols and chunk embeddings.
- [x] **Security & Rate Limiting**: Per-IP request throttling and concurrent task acquisition limits.
- [x] **LangGraph Correction Nodes**: Modular state-graph refactor (`app/agents/graph.py`) replacing the `while` loop in `workflow.py` with an explicit implement → test → debug → review pipeline. 13 tests in `tests/test_graph.py` verify all paths including self-correction and iteration exhaustion.
- [x] **Public Deployment Instructions**: `DEPLOYMENT.md` covers prerequisites, secret management, sandbox image build, Docker Compose quickstart, Nginx/HTTPS setup, resource limits, security checklist, and update/rollback procedure. `docker/docker-compose.yml` and `docker/Dockerfile.app` added.
- [x] **Record Benchmark Results in Docs**: Fixture-baseline run (10/10 tasks, 100% success rate) recorded in `README.md` and `benchmarks/baseline_results.md`. Reproducible via `uv run python benchmarks/run_dry.py`.


uv run uvicorn app.main:app --reload --reload-dir app
uv run streamlit run ui/streamlit_app.py
