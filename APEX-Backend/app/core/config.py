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
    # LLM_1-authorized chat model can be swapped in without a code change.
    huggingface_api_base_url: str = "https://router.huggingface.co/v1"
    huggingface_model: str = "meta-llama/Llama-3.1-8B-Instruct:novita"
    # Read from the provider-neutral LLM_1 env var. Leave empty to disable AI
    # recommendations (the endpoint then reports itself as unavailable rather
    # than fabricating a recommendation).
    huggingface_token: str = Field(default="", alias="LLM_1")
    huggingface_request_timeout_seconds: float = 30.0

    # --- Strategy RAG chatbot (JavaApex Assistant) --------------------------
    # Primary LLM: Groq (OpenAI-compatible chat completions, streaming). Read
    # from the provider-neutral LLM_2 env var; leave empty to disable Groq and
    # fall straight through to Ollama.
    groq_api_key: str = Field(default="", alias="LLM_2")
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Fallback LLM: a local Ollama server. Used only when Groq is unavailable.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    # Sentence-embedding model (384-dim). Downloaded + cached on first use.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    # Embedded Qdrant vector store — persists to disk (no server/Docker needed).
    # Swap to server mode later by pointing the wrapper at a URL instead.
    qdrant_path: Path = BACKEND_ROOT / "storage" / "vector-store"
    qdrant_collection: str = "repo_knowledge"
    # Number of knowledge chunks retrieved per question.
    rag_top_k: int = 6
    # Timeout (seconds) for a single chat-LLM request (Groq or Ollama).
    chat_llm_request_timeout_seconds: float = 60.0

    # --- Git / clone ---------------------------------------------------------
    # Timeout (seconds) for a `git clone` during Discovery.
    git_clone_timeout_seconds: float = 300.0
    # Clone only the latest commit to keep the workspace small and fast.
    git_clone_depth: int = 1

    # --- Migration / OpenRewrite --------------------------------------------
    # Pinned OpenRewrite plugin + recipe versions (reproducible migrations).
    openrewrite_maven_plugin_version: str = "6.43.0"
    openrewrite_gradle_plugin_version: str = "7.36.0"
    rewrite_migrate_java_version: str = "3.39.0"
    rewrite_spring_version: str = "6.34.0"
    rewrite_java_dependencies_version: str = "1.57.0"
    rewrite_testing_frameworks_version: str = "3.41.0"
    openrewrite_recipe_catalog_path: Path = BACKEND_ROOT / "app" / "config" / "openrewrite_recipe_catalog.json"
    # Timeout (seconds) for a single OpenRewrite run (Maven/Gradle).
    migration_timeout_seconds: float = 1800.0
    # Identity used for the migrated-repo commit.
    migration_commit_author_name: str = "Java APEX Migration Bot"
    migration_commit_author_email: str = "migration-bot@javaapex.local"
    # Bounded diagnose-and-retry loop when the post-migration build fails
    # (see build_failure_diagnostician.py). 0 disables retries.
    migration_max_retry_attempts: int = 2

    # --- Build validation (post-migration "does it build?" check) -----------
    # Whether to compile/package the migrated code and log BUILD SUCCESS/FAILED.
    build_validation_enabled: bool = True
    # Local JDK used by Maven/Gradle subprocesses. Leave empty to inherit the
    # server environment's JAVA_HOME/PATH.
    build_java_home: str = ""
    # Local Gradle install used when a Gradle project has no Windows wrapper
    # and the backend process PATH does not include gradle.bat.
    gradle_home: str = ""
    # Maven goals: package the migrated app without compiling/running tests.
    # Some legacy projects keep Groovy/Spock/JUnit test toolchains that are not
    # Java-target compatible after migration; those should not block the basic
    # "does the migrated application package?" validation.
    build_maven_args: str = "-B,-Dmaven.test.skip=true,package"
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

    # --- Quality Gates -------------------------------------------------------
    # SonarQube/SonarCloud token. Required only when the SonarQube quality gate
    # card is active.
    sonarqube_token: str = Field(default="", alias="SONAR_TOKEN")
    # SonarQube server URL. For SonarCloud use https://sonarcloud.io.
    sonarqube_host_url: str = Field(default="http://localhost:9000", alias="SONAR_HOST_URL")
    # Optional fixed project key. Leave empty to derive one from the migration job.
    sonarqube_project_key: str = Field(default="", alias="SONAR_PROJECT_KEY")
    # Required by SonarCloud; leave empty for local SonarQube.
    sonarqube_organization: str = Field(default="", alias="SONAR_ORGANIZATION")
    sonarqube_project_key_prefix: str = "java-apex"
    sonarqube_scanner_command: str = "sonar-scanner"

    # FOSSA API key. Required only when the FOSSA quality gate card is active.
    fossa_api_key: str = Field(default="", alias="FOSSA_API_KEY")
    # Optional custom FOSSA endpoint for self-hosted/enterprise setups.
    fossa_endpoint: str = Field(default="", alias="FOSSA_ENDPOINT")
    fossa_cli_command: str = "fossa"

    # --- Storage -------------------------------------------------------------
    # Root folder where per-job artifacts (reports, etc.) are written.
    storage_dir: Path = BACKEND_ROOT / "storage" / "migration-jobs"
    # Root folder where submitted support tickets are written (Support feature).
    support_tickets_dir: Path = BACKEND_ROOT / "storage" / "support-tickets"
    # Shared GRADLE_USER_HOME used by every job's Gradle/OpenRewrite run and
    # build validation. Deliberately a sibling of storage_dir (not per-job)
    # so the (large) Gradle distribution zip and dependency/plugin caches are
    # downloaded once and reused across jobs, instead of every job re-fetching
    # them from services.gradle.org and being exposed to network timeouts.
    gradle_shared_cache_dir: Path = BACKEND_ROOT / "storage" / ".gradle-cache"

    # --- Email / SMTP (Support tickets, best-effort) --------------------------
    # All blank by default — support ticket submission always succeeds and
    # persists the ticket even with zero SMTP configuration. Set these env vars
    # to also send a notification email when a ticket is submitted.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_from_address: str = Field(default="", alias="SMTP_FROM_ADDRESS")
    support_notification_recipient: str = Field(default="", alias="SUPPORT_NOTIFICATION_RECIPIENT")

    @property
    def is_smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_address and self.support_notification_recipient)

    # --- Database --------------------------------------------------------------
    # PostgreSQL connection string using the psycopg (v3) driver, e.g.:
    # postgresql+psycopg://user:password@localhost:5432/java_apex_db
    database_url: str = ""

    # --- Authentication (JWT + cookies) -----------------------------------------
    # HMAC signing secret for access/refresh JWTs. Must be set in .env — the
    # empty default is rejected at startup by validate_auth_settings() below.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Frontend origin this deployment's auth cookies/CORS trust.
    frontend_url: str = "http://localhost:5173"

    # "development" or "production" — controls the auth cookies' Secure flag.
    environment: str = "development"

    # --- OAuth (Google / GitHub social login) ---------------------------------
    # Identity-only login (see app/infrastructure/oauth/). Deliberately separate
    # from GITHUB_TOKEN/GITHUB_TARGET_TOKEN above, which are unrelated to login
    # and used only for the Connect stage's repository read/publish access.
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/api/auth/google/callback", alias="GOOGLE_REDIRECT_URI"
    )
    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str = Field(
        default="http://localhost:8000/api/auth/github/callback", alias="GITHUB_REDIRECT_URI"
    )
    # How long a signed OAuth `state` (and, for Google, the PKCE code_verifier
    # cookie) stays valid — the window the user has to complete the provider's
    # consent screen before the login attempt must be restarted.
    oauth_state_expire_seconds: int = 600

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    def validate_auth_settings(self) -> None:
        """Fail fast at startup if a required auth setting is missing.

        Called once from ``main.py`` before the app starts serving requests —
        similar to a Spring Boot ``@PostConstruct`` sanity check. Only ever
        reports which variable NAMES are missing, never their values, so
        nothing secret reaches the startup log.
        """
        missing = [
            name
            for name, value in (
                ("DATABASE_URL", self.database_url),
                ("JWT_SECRET_KEY", self.jwt_secret_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): "
                f"{', '.join(missing)}. Set them in APEX-Backend/.env "
                "(see .env.example)."
            )

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
