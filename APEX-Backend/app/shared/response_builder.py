"""Helpers to build clean, consistent API responses for the Connect flow.

The frontend only ever sees the shapes produced here — never raw exceptions or
internal technical detail.
"""

from __future__ import annotations

from typing import Any


def build_connect_success(
    *,
    job_id: str,
    repo_url: str,
    owner: str,
    repo_name: str,
    repo_visibility: str,
    access_status: str,
    message: str,
) -> dict[str, Any]:
    """Build the success payload returned after a repository is verified."""
    return {
        "jobId": job_id,
        "repoUrl": repo_url,
        "owner": owner,
        "repoName": repo_name,
        "repoVisibility": repo_visibility,
        "accessStatus": access_status,
        "message": message,
    }


def build_connect_error(*, access_status: str, message: str) -> dict[str, Any]:
    """Build the error payload for a failed connect attempt."""
    return {
        "accessStatus": access_status,
        "message": message,
    }
