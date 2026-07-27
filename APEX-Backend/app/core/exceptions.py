"""Domain-level exceptions for the Connect flow.

These exceptions carry a user-friendly ``message`` and a stable
``access_status`` string that the API layer maps directly onto the response
contract. No internal/technical detail is ever placed on ``message``.
"""

from __future__ import annotations


class ConnectError(Exception):
    """Base class for all Connect-stage failures.

    Attributes
    ----------
    access_status:
        Stable machine-readable status returned to the frontend
        (e.g. ``INVALID_URL``, ``NOT_FOUND``, ``ACCESS_DENIED``).
    message:
        Clean, user-friendly message. Never exposes technical internals.
    http_status:
        HTTP status code the API layer should respond with.
    """

    access_status: str = "ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRepositoryUrlError(ConnectError):
    """The provided repository URL could not be parsed as a GitHub repo."""

    access_status = "INVALID_URL"
    http_status = 400

    def __init__(self, message: str = "Invalid GitHub repository URL.") -> None:
        super().__init__(message)


class RepositoryNotFoundError(ConnectError):
    """The repository does not exist (or cannot be located with the given credentials)."""

    access_status = "NOT_FOUND"
    http_status = 404

    def __init__(self, message: str = "Repository not found. Please check the URL.") -> None:
        super().__init__(message)


class RepositoryAccessDeniedError(ConnectError):
    """The repository is private and access could not be verified."""

    access_status = "ACCESS_DENIED"
    http_status = 403

    def __init__(
        self,
        message: str = "Repository is private. Please provide a valid GitHub token.",
    ) -> None:
        super().__init__(message)


class GithubServiceError(ConnectError):
    """GitHub could not be reached or returned an unexpected error."""

    access_status = "SERVICE_ERROR"
    http_status = 502

    def __init__(
        self,
        message: str = "We could not verify the repository right now. Please try again.",
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Discovery stage
# --------------------------------------------------------------------------- #


class DiscoveryError(Exception):
    """Base class for Discovery-stage failures.

    Carries a stable ``status`` string (e.g. ``CLONE_FAILED``) and a clean,
    user-friendly ``message``. The API layer maps these onto the discovery
    response contract ``{ jobId, status, message }``.
    """

    status: str = "DISCOVERY_FAILED"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConnectReportNotFoundError(DiscoveryError):
    """No connect-report.json for the job — Connect step wasn't completed."""

    status = "CONNECT_REPORT_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "Connect details not found. Please complete the Connect step first.",
    ) -> None:
        super().__init__(message)


class CloneFailedError(DiscoveryError):
    """The repository could not be cloned into the workspace."""

    status = "CLONE_FAILED"
    http_status = 502

    def __init__(
        self,
        message: str = "Repository clone failed. Please check repository access or token.",
    ) -> None:
        super().__init__(message)


class UnsupportedProjectError(DiscoveryError):
    """No Maven or Gradle build file was found in the cloned project."""

    status = "UNSUPPORTED_PROJECT"
    http_status = 422

    def __init__(
        self,
        message: str = (
            "No Maven or Gradle build file found. "
            "This project type is currently unsupported."
        ),
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Migration Config stage
# --------------------------------------------------------------------------- #


class MigrationConfigError(Exception):
    """Base class for Migration-Config-stage failures.

    Carries a stable ``status`` and a clean ``message`` that the API layer maps
    onto ``{ jobId, status, message }``.
    """

    status: str = "MIGRATION_CONFIG_FAILED"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MigrationJobNotFoundError(MigrationConfigError):
    """No job on disk for the given id (Connect step not completed)."""

    status = "JOB_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "Migration job not found. Please start from the Connect step.",
    ) -> None:
        super().__init__(message)


class InvalidMigrationConfigError(MigrationConfigError):
    """The submitted migration configuration is invalid."""

    status = "INVALID_MIGRATION_CONFIG"
    http_status = 400

    def __init__(self, message: str = "Invalid migration configuration.") -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Start Migration stage
# --------------------------------------------------------------------------- #


class MigrationExecutionError(Exception):
    """Base class for Start-Migration failures surfaced at the API boundary.

    Runtime failures during the async run are reported via the job's
    ``status:"failed"`` + ``error_message`` rather than as HTTP errors; this is
    used only for pre-flight validation on the start endpoint.
    """

    status: str = "MIGRATION_FAILED"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DiscoveryReportRequiredError(MigrationExecutionError):
    """Discovery must be completed before a migration can start."""

    status = "DISCOVERY_REQUIRED"
    http_status = 409

    def __init__(
        self,
        message: str = "Run Discovery before starting the migration.",
    ) -> None:
        super().__init__(message)


class PushFailedError(MigrationExecutionError):
    """Creating the target repo or pushing the migrated code failed."""

    status = "PUSH_FAILED"
    http_status = 502

    def __init__(
        self,
        message: str = "Failed to publish the migrated repository. Check the target token/permissions.",
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Target Java Version Recommendation (Hugging Face LLM)
# --------------------------------------------------------------------------- #


class JavaVersionRecommendationError(Exception):
    """Base class for Target Java Version Recommendation failures.

    Carries a stable ``status`` and a clean ``message`` the API layer maps onto
    ``{ status, message }``, mirroring the other stage exception groups.
    """

    status: str = "RECOMMENDATION_FAILED"
    http_status: int = 502

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidJavaVersionError(JavaVersionRecommendationError):
    """The supplied source Java version could not be parsed."""

    status = "INVALID_SOURCE_VERSION"
    http_status = 400

    def __init__(self, message: str = "A valid detected source Java version is required.") -> None:
        super().__init__(message)


class LLMNotConfiguredError(JavaVersionRecommendationError):
    """No Hugging Face token is configured — the feature is unavailable, not faked."""

    status = "LLM_NOT_CONFIGURED"
    http_status = 503

    def __init__(
        self,
        message: str = "Hugging Face API token is not configured (set HF_TOKEN).",
    ) -> None:
        super().__init__(message)


class LLMServiceError(JavaVersionRecommendationError):
    """The Hugging Face API could not be reached or returned an error.

    ``provider_status_code`` carries the raw HTTP status the provider
    returned (e.g. 402 Payment Required, 401 Unauthorized), when the failure
    came from a non-200 response rather than a transport error -- callers
    that retry (like the unit-test generation repair loop) use it to tell a
    one-off bad response (worth retrying) apart from an account-level
    failure that will recur identically on every retry.
    """

    status = "LLM_SERVICE_ERROR"
    http_status = 502

    def __init__(
        self,
        message: str = "The Hugging Face model could not be reached. Please try again.",
        provider_status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_status_code = provider_status_code

    @property
    def is_account_level_failure(self) -> bool:
        """True for auth/billing failures (401/402/403) that won't resolve on retry."""
        return self.provider_status_code in (401, 402, 403)


class LLMResponseInvalidError(JavaVersionRecommendationError):
    """The model responded, but not with a usable recommendation."""

    status = "LLM_RESPONSE_INVALID"
    http_status = 502

    def __init__(
        self,
        message: str = "The Hugging Face model returned an unusable response.",
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Repository file browser (Discovery stage "Repository Files" panel)
# --------------------------------------------------------------------------- #


class RepositoryBrowseError(Exception):
    """Base class for repository file-browsing failures.

    Carries a stable ``status`` and a clean ``message`` the API layer maps onto
    ``{ jobId, status, message }``, mirroring the other stage exception groups.
    """

    status: str = "REPOSITORY_BROWSE_FAILED"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RepositoryWorkspaceNotFoundError(RepositoryBrowseError):
    """No cloned ``original-repo`` for this job — Discovery hasn't run yet."""

    status = "WORKSPACE_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "Repository workspace not found. Please run Discovery first.",
    ) -> None:
        super().__init__(message)


class RepositoryPathNotFoundError(RepositoryBrowseError):
    """The requested file/folder path does not exist in the cloned repo."""

    status = "PATH_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "The requested path was not found in the repository.",
    ) -> None:
        super().__init__(message)


class RepositoryPathInvalidError(RepositoryBrowseError):
    """The path escapes the workspace, or doesn't match the expected kind (file/dir)."""

    status = "INVALID_PATH"
    http_status = 400

    def __init__(self, message: str = "Invalid file path.") -> None:
        super().__init__(message)


class RepositoryFileTooLargeError(RepositoryBrowseError):
    """The file exceeds the preview size limit."""

    status = "FILE_TOO_LARGE"
    http_status = 413

    def __init__(
        self,
        message: str = "File is too large to preview.",
    ) -> None:
        super().__init__(message)


class RepositoryFileNotTextError(RepositoryBrowseError):
    """The file is not valid UTF-8 text (binary content)."""

    status = "FILE_NOT_TEXT"
    http_status = 415

    def __init__(
        self,
        message: str = "This file can't be previewed as text.",
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Unit test analysis / generation / execution / coverage
# --------------------------------------------------------------------------- #


class UnitTestError(Exception):
    """Base class for the automatic unit-test pipeline's failures.

    Carries a stable ``status`` and a clean ``message`` the API layer maps
    onto ``{ jobId, status, message }``, mirroring the other stage exception
    groups. A unit-test failure is reported on the unit-test report's own
    status -- it must never be allowed to fail the overall migration.
    """

    status: str = "UNIT_TEST_FAILED"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnitTestWorkspaceNotFoundError(UnitTestError):
    """No cloned/migrated repo exists yet for this job."""

    status = "WORKSPACE_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "Repository workspace not found. Please run Discovery (and Start Migration) first.",
    ) -> None:
        super().__init__(message)


class UnitTestToolUnavailableError(UnitTestError):
    """The OpenRewrite inventory jar hasn't been built, or no JDK is available."""

    status = "TOOL_UNAVAILABLE"
    http_status = 503

    def __init__(
        self,
        message: str = (
            "The OpenRewrite test-inventory tool is not available. Build it with "
            "`mvn -f tools/rewrite-test-inventory/pom.xml package`."
        ),
    ) -> None:
        super().__init__(message)


class UnitTestUnsupportedProjectError(UnitTestError):
    """Multi-module projects, or build tools other than Maven/Gradle, are not
    yet supported for generation/execution."""

    status = "UNSUPPORTED_PROJECT"
    http_status = 422

    def __init__(
        self,
        message: str = (
            "Automatic unit test generation/execution currently supports single-module "
            "Maven or Gradle projects only."
        ),
    ) -> None:
        super().__init__(message)


class UnitTestGenerationFailedError(UnitTestError):
    """The LLM test-generation step could not produce a usable result."""

    status = "GENERATION_FAILED"
    http_status = 502

    def __init__(self, message: str = "Unit test generation failed.") -> None:
        super().__init__(message)


class UnitTestReportNotFoundError(UnitTestError):
    """No unit-test-report.json exists yet for this job."""

    status = "REPORT_NOT_FOUND"
    http_status = 404

    def __init__(
        self,
        message: str = "No unit test report is available yet for this job.",
    ) -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #


class AuthError(Exception):
    """Base class for all authentication failures.

    Attributes
    ----------
    status:
        Stable machine-readable status returned to the frontend.
    message:
        Clean, user-friendly message. Never exposes technical internals
        (no stack traces, database errors, or secrets).
    http_status:
        HTTP status code the API layer should respond with.
    """

    status: str = "AUTH_ERROR"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmailAlreadyRegisteredError(AuthError):
    """Signup was attempted with an email that already has an account."""

    status = "EMAIL_ALREADY_REGISTERED"
    http_status = 409

    def __init__(self, message: str = "An account with this email already exists.") -> None:
        super().__init__(message)


class InvalidCredentialsError(AuthError):
    """Login failed: unknown email OR wrong password.

    Deliberately the SAME error for both cases — the caller must never be
    able to tell which one happened (prevents attackers from discovering
    which emails are registered).
    """

    status = "INVALID_CREDENTIALS"
    http_status = 401

    def __init__(self, message: str = "Invalid email or password.") -> None:
        super().__init__(message)


class AccountDisabledError(AuthError):
    """The account exists and the password was correct, but is_active is False."""

    status = "ACCOUNT_DISABLED"
    http_status = 403

    def __init__(self, message: str = "This account has been disabled. Please contact support.") -> None:
        super().__init__(message)


class NotAuthenticatedError(AuthError):
    """No valid access token was presented (missing/expired/malformed cookie)."""

    status = "NOT_AUTHENTICATED"
    http_status = 401

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class InvalidRefreshTokenError(AuthError):
    """The refresh token is missing, malformed, expired, revoked, or reused."""

    status = "INVALID_REFRESH_TOKEN"
    http_status = 401

    def __init__(self, message: str = "Refresh token is invalid or has expired.") -> None:
        super().__init__(message)


# --------------------------------------------------------------------------- #
# OAuth (Google / GitHub social login)
# --------------------------------------------------------------------------- #


class OAuthNotConfiguredError(AuthError):
    """The requested provider has no client id/secret configured on the server."""

    status = "OAUTH_NOT_CONFIGURED"
    http_status = 503

    def __init__(self, message: str = "This sign-in method is not available right now.") -> None:
        super().__init__(message)


class OAuthCancelledError(AuthError):
    """The user declined/cancelled the provider's consent screen."""

    status = "OAUTH_CANCELLED"
    http_status = 400

    def __init__(self, message: str = "Sign-in was cancelled.") -> None:
        super().__init__(message)


class OAuthStateInvalidError(AuthError):
    """The `state` callback parameter is missing, unsigned, expired, or for the wrong provider."""

    status = "OAUTH_INVALID_STATE"
    http_status = 400

    def __init__(
        self,
        message: str = "Your sign-in session expired or is invalid. Please try again.",
    ) -> None:
        super().__init__(message)


class OAuthProviderError(AuthError):
    """Google/GitHub could not be reached, or returned an unexpected response."""

    status = "OAUTH_PROVIDER_ERROR"
    http_status = 502

    def __init__(
        self,
        message: str = "We couldn't complete sign-in right now. Please try again.",
    ) -> None:
        super().__init__(message)


class OAuthEmailMissingError(AuthError):
    """The provider returned no verified email address to identify the user by."""

    status = "OAUTH_EMAIL_MISSING"
    http_status = 400

    def __init__(
        self,
        message: str = (
            "We couldn't get a verified email from your account. "
            "Please use a different sign-in method."
        ),
    ) -> None:
        super().__init__(message)


class OAuthAccountConflictError(AuthError):
    """An account with this email already exists and cannot be safely auto-linked.

    Raised when the provider's email is NOT verified (auto-linking to an
    existing account on an unverified email would let an attacker who
    merely controls an OAuth app take over any local account by claiming
    its email address).
    """

    status = "OAUTH_ACCOUNT_CONFLICT"
    http_status = 409

    def __init__(
        self,
        message: str = (
            "An account with this email already exists. "
            "Please sign in with your password instead."
        ),
    ) -> None:
        super().__init__(message)
