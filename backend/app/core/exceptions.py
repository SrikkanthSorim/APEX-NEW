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
