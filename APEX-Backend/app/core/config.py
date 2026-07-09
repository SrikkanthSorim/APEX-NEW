"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file
sitting at the backend root). Keep this module free of any business logic — it
only exposes configuration values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# APEX-Backend/app/core/config.py -> parents[2] == APEX-Backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = WORKSPACE_ROOT / "APEX-Frontend"


class Settings(BaseSettings):
    """Runtime configuration for the backend service."""

    model_config = SettingsConfigDict(
        # Prefer APEX-Backend/.env, but also support existing local setups that
        # placed backend keys in APEX-Frontend/.env.
        env_file=(str(FRONTEND_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -------------------------------------------------------------
    app_name: str = "Java Migration Platform API"
    api_v1_prefix: str = "/api/v1"

    # --- GitHub --------------------------------------------------------------
    github_api_base_url: str = "https://api.github.com"
    # Source-read token: fallback used when the caller doesn't supply one (raises
    # the unauthenticated rate limit, clones private source repos). May be empty.
    github_token: str = ""
    # Target/publish token: used by the Start Migration stage to create and push
    # migrated repositories under the Javaapex org. Must belong to an account
    # authorized on that org (repo scope, or fine-grained Administration +
    # Contents: write). May be empty until the Start Migration stage is used.
    github_target_token: str = ""
    # GitHub owner (org/user) that migrated repositories are published under.
    github_target_owner: str = "Javaapex"
    github_request_timeout_seconds: float = 15.0

    # --- Hugging Face LLM (Target Java Version Recommendation) --------------
    # Inference Providers router (OpenAI-compatible chat completions). Any
    # HF_TOKEN-authorized chat model can be swapped in without a code change.
    huggingface_api_base_url: str = "https://router.huggingface.co/v1"
    huggingface_model: str = "meta-llama/Llama-3.1-8B-Instruct:novita"
    # Read from the HF_TOKEN env var (the standard Hugging Face convention).
    # Leave empty to disable AI recommendations (the endpoint then reports
    # itself as unavailable rather than fabricating a recommendation).
    huggingface_token: str = Field(default="", alias="HF_TOKEN")
    huggingface_request_timeout_seconds: float = 30.0

    # --- Git / clone ---------------------------------------------------------
    # Timeout (seconds) for a `git clone` during Discovery.
    git_clone_timeout_seconds: float = 300.0
    # Clone only the latest commit to keep the workspace small and fast.
    git_clone_depth: int = 1

    # --- Migration / OpenRewrite --------------------------------------------
    # Pinned OpenRewrite plugin + recipe versions (reproducible migrations).
    openrewrite_maven_plugin_version: str = "5.44.0"
    openrewrite_gradle_plugin_version: str = "6.29.0"
    rewrite_migrate_java_version: str = "2.29.0"
    # Timeout (seconds) for a single OpenRewrite run (Maven/Gradle).
    migration_timeout_seconds: float = 1800.0
    # Identity used for the migrated-repo commit.
    migration_commit_author_name: str = "Java APEX Migration Bot"
    migration_commit_author_email: str = "migration-bot@javaapex.local"

    # --- Build validation (post-migration "does it build?" check) -----------
    # Whether to compile/package the migrated code and log BUILD SUCCESS/FAILED.
    build_validation_enabled: bool = True
    # Local JDK used by Maven/Gradle subprocesses. Leave empty to inherit the
    # server environment's JAVA_HOME/PATH.
    build_java_home: str = ""
    # Maven goals: build everything but skip running tests.
    build_maven_args: str = "-B,-DskipTests,package"
    # Gradle tasks: build but skip tests.
    build_gradle_args: str = "build,-x,test,--no-daemon"
    # Timeout (seconds) for the build.
    build_timeout_seconds: float = 1200.0

    @property
    def build_maven_args_list(self) -> list[str]:
        return [a for a in self.build_maven_args.split(",") if a]

    @property
    def build_gradle_args_list(self) -> list[str]:
        return [a for a in self.build_gradle_args.split(",") if a]

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
