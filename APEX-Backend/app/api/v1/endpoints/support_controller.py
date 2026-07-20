"""Support ticket submission endpoint backing the header "Support" drawer."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.application.use_cases.submit_support_ticket import SubmitSupportTicketUseCase
from app.schemas.support_schema import SupportTicketRequest

router = APIRouter(tags=["support"])
_use_case = SubmitSupportTicketUseCase()


@router.post("/support/tickets", summary="Submit a support ticket.")
async def submit_ticket(payload: SupportTicketRequest) -> JSONResponse:
    # smtplib performs blocking socket I/O; keep it off the event loop even
    # though SMTP is unconfigured by default.
    result = await run_in_threadpool(_use_case.execute, payload)
    return JSONResponse(status_code=201, content=result.model_dump())
