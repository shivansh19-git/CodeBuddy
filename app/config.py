"""Central configuration: values come from environment variables, never source code."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime limits keep a public demo predictable and safer to operate."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    max_repository_size_mb: int = 20
    max_repository_files: int = 1000
    max_agent_iterations: int = 5
    test_timeout_seconds: int = 120
    workspace_root: Path = Path("data/workspaces")
    sandbox_image: str = "agentic-python-sandbox"
    sandbox_network: bool = False
    database_path: Path = Path("data/app.db")
    huggingface_api_key: str | None = None
    huggingface_model: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    mistral_api_key: str | None = None
    mistral_model: str = "codestral-latest"
    embedding_provider_primary: str | None = None
    embedding_provider_fallback: str | None = None
    huggingface_embedding_api_key: str | None = None
    huggingface_embedding_url: str | None = None
    huggingface_embedding_model: str = ""
    vector_store_path: Path = Path("data/vector_store")
    max_concurrent_tasks: int = 2
    request_limit_per_minute: int = 120
    workspace_ttl_hours: int = 24
    dependency_prepare_timeout_seconds: int = 600


settings = Settings()
