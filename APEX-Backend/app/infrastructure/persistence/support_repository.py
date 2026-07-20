"""Local filesystem persistence for support tickets.

Mirrors ``JobRepository``'s style: plain JSON files under
``storage/support-tickets/<ticketId>.json``. No database is involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


class SupportRepository:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = Path(storage_dir) if storage_dir else settings.support_tickets_dir

    def save_ticket(self, ticket_id: str, ticket: dict[str, Any]) -> Path:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        ticket_path = self._storage_dir / f"{ticket_id}.json"
        ticket_path.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
        return ticket_path

    def read_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        ticket_path = self._storage_dir / f"{ticket_id}.json"
        if not ticket_path.exists():
            return None
        return json.loads(ticket_path.read_text(encoding="utf-8"))
