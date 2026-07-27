"""Submit a support ticket: persist first, then a best-effort email notification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from app.infrastructure.email.email_sender import send_support_notification, send_ticket_confirmation
from app.infrastructure.persistence.support_repository import SupportRepository
from app.schemas.support_schema import SupportTicketRequest, SupportTicketResponse


class SubmitSupportTicketUseCase:
    def __init__(
        self,
        repository: SupportRepository | None = None,
        sender: Callable[[dict], bool] = send_support_notification,
        confirmation_sender: Callable[[dict], bool] = send_ticket_confirmation,
    ) -> None:
        self._repository = repository or SupportRepository()
        self._sender = sender
        self._confirmation_sender = confirmation_sender

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
        self._sender(ticket)
        # `email_sent` reflects the submitter-facing confirmation, since that's what
        # the "We may follow up by email" message in the UI is promising.
        email_sent = self._confirmation_sender(ticket)

        return SupportTicketResponse(
            ticket_id=ticket_id,
            created_at=created_at,
            status="received",
            email_sent=email_sent,
        )
