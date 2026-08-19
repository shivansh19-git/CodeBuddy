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


settings = Settings()
