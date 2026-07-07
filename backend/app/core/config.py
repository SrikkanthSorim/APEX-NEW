"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file
sitting at the backend root). Keep this module free of any business logic — it
only exposes configuration values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[2] == backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for the backend service."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -------------------------------------------------------------
    app_name: str = "Java Migration Platform API"
    api_v1_prefix: str = "/api/v1"

    # --- GitHub --------------------------------------------------------------
    github_api_base_url: str = "https://api.github.com"
    # Optional server-side token used as a fallback when the caller does not
    # supply one (e.g. to raise the unauthenticated rate limit). May be empty.
    github_token: str = ""
    github_request_timeout_seconds: float = 15.0

    # --- Git / clone ---------------------------------------------------------
    # Timeout (seconds) for a `git clone` during Discovery.
    git_clone_timeout_seconds: float = 300.0
    # Clone only the latest commit to keep the workspace small and fast.
    git_clone_depth: int = 1

    # --- Storage -------------------------------------------------------------
    # Root folder where per-job artifacts (reports, etc.) are written.
    storage_dir: Path = BACKEND_ROOT / "storage" / "migration-jobs"

    # --- CORS ----------------------------------------------------------------
    # Comma-separated list of allowed origins for the frontend dev/prod hosts.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> "Settings":
    """Return a cached ``Settings`` instance."""
    return Settings()


settings = get_settings()
