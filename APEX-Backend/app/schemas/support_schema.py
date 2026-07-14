"""Schemas for the header "Support" feature — contact/issue tickets."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

CATEGORY_GENERAL = "general"
CATEGORY_BUG = "bug"
CATEGORY_MIGRATION_ERROR = "migration_error"
VALID_CATEGORIES = {CATEGORY_GENERAL, CATEGORY_BUG, CATEGORY_MIGRATION_ERROR}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SupportTicketRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str
    subject: str = Field(..., min_length=1, max_length=300)
    message: str = Field(..., min_length=1, max_length=8000)
    category: str = Field(default=CATEGORY_GENERAL)
    job_id: Optional[str] = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @field_validator("name", "subject", "message")
    @classmethod
    def _strip_and_require(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip()
        if not _EMAIL_RE.match(value):
            raise ValueError("Invalid email address.")
        return value

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        normalized = (value or CATEGORY_GENERAL).strip().lower()
        return normalized if normalized in VALID_CATEGORIES else CATEGORY_GENERAL

    @field_validator("job_id")
    @classmethod
    def _clean_job_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SupportTicketResponse(BaseModel):
    ticket_id: str
    created_at: str
    status: str = "received"
    email_sent: bool = False
