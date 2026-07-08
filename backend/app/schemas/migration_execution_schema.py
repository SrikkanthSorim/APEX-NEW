"""Request schema for the Start Migration endpoint.

Permissive on purpose: the frontend sends the full legacy ``MigrationRequest``
(many fields). We only need a few; the rest are accepted and ignored. The saved
migration-config/discovery reports are the source of truth for the destination
and versions.
"""

from typing import Optional

from pydantic import BaseModel


class MigrationStartRequest(BaseModel):
    source_repo_url: Optional[str] = None
    target_java_version: Optional[str] = None
    source_java_version: Optional[str] = None
    build_tool: Optional[str] = None
    conversion_types: Optional[list[str]] = None

    # Accept (and ignore) any additional legacy fields the frontend sends.
    model_config = {"extra": "allow"}
