"""Response schema for the unversioned local-project capabilities endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class LocalProjectCapabilitiesResponse(BaseModel):
    """Body for ``GET /api/local-project/capabilities``."""

    enabled: bool
    hosted_mode: bool
    allow_any_path: bool
    allowed_roots: list[str]
    supports_upload: bool
    message: str
