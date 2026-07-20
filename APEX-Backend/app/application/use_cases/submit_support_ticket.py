"""Submit a support ticket: persist first, then a best-effort email notification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from app.infrastructure.email.email_sender import send_support_notification
from app.infrastructure.persistence.support_repository import SupportRepository
from app.schemas.support_schema import SupportTicketRequest, SupportTicketResponse


class SubmitSupportTicketUseCase:
    def __init__(
        self,
        repository: SupportRepository | None = None,
        sender: Callable[[dict], bool] = send_support_notification,
    ) -> None:
        self._repository = repository or SupportRepository()
        self._sender = sender

    def execute(self, request: SupportTicketRequest) -> SupportTicketResponse:
        ticket_id = f"ticket-{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()
        ticket = {
            "ticket_id": ticket_id,
            "created_at": created_at,
            "status": "received",
            "name": request.name,
            "email": request.email,
            "subject": request.subject,
            "message": request.message,
            "category": request.category,
            "job_id": request.job_id,
        }

        # Persist unconditionally before attempting email — the ticket must never be
        # lost because of an email/SMTP failure.
        self._repository.save_ticket(ticket_id, ticket)
        email_sent = self._sender(ticket)

        return SupportTicketResponse(
            ticket_id=ticket_id,
            created_at=created_at,
            status="received",
            email_sent=email_sent,
        )
