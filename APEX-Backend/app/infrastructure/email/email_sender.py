"""Best-effort SMTP email notification for submitted support tickets.

No SMTP provider is configured by default (``settings.is_smtp_configured`` is
False until SMTP_* env vars are set) — in that case this module is a no-op.
Ticket persistence never depends on this succeeding.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_support_notification(ticket: dict[str, Any]) -> bool:
    """Attempt to email the support notification recipient. Never raises."""
    if not settings.is_smtp_configured:
        logger.info(
            "SMTP not configured; skipping support notification email for ticket %s.",
            ticket.get("ticket_id"),
        )
        return False

    try:
        message = EmailMessage()
        message["Subject"] = f"[Support:{ticket.get('category')}] {ticket.get('subject')}"
        message["From"] = settings.smtp_from_address
        message["To"] = settings.support_notification_recipient
        message["Reply-To"] = ticket.get("email", "")
        message.set_content(
            "New support ticket\n"
            f"Ticket ID: {ticket.get('ticket_id')}\n"
            f"From: {ticket.get('name')} <{ticket.get('email')}>\n"
            f"Category: {ticket.get('category')}\n"
            f"Job ID: {ticket.get('job_id') or '-'}\n\n"
            f"{ticket.get('message')}"
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception:
        logger.exception(
            "Best-effort support notification email failed for ticket %s; ticket already persisted.",
            ticket.get("ticket_id"),
        )
        return False
