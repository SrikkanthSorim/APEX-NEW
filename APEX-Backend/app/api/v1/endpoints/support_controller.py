"""Support ticket submission endpoint backing the header "Support" drawer."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user
from app.application.use_cases.submit_support_ticket import SubmitSupportTicketUseCase
from app.infrastructure.persistence.models import User
from app.schemas.support_schema import SupportTicketRequest

router = APIRouter(tags=["support"])
_use_case = SubmitSupportTicketUseCase()


@router.post("/support/tickets", summary="Submit a support ticket.")
async def submit_ticket(
    payload: SupportTicketRequest,
    _current_user: User = Depends(get_current_user),
) -> JSONResponse:
    # Requires login (a support request is tied to a person, not anonymous).
    # `_current_user` is intentionally unused beyond gating access — the
    # ticket itself still uses payload.name/email as before; wiring
    # current_user.id into stored tickets is a small follow-up if ticket
    # ownership/filtering is needed later (see SubmitSupportTicketUseCase).
    #
    # smtplib performs blocking socket I/O; keep it off the event loop even
    # though SMTP is unconfigured by default.
    result = await run_in_threadpool(_use_case.execute, payload)
    return JSONResponse(status_code=201, content=result.model_dump())
