"""Domain errors and their HTTP translation."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class CollectiveError(Exception):
    """Base class for errors the API knows how to report."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(CollectiveError):
    status_code = 404
    code = "not_found"


class ConflictError(CollectiveError):
    status_code = 409
    code = "conflict"


class UnknownAgentError(CollectiveError):
    status_code = 400
    code = "unknown_agent"


class AgentNotConfiguredError(CollectiveError):
    """Connector exists but has no credentials / base URL."""

    status_code = 424
    code = "agent_not_configured"


class AgentLimitError(CollectiveError):
    """The agent refused the work because it hit a limit.

    Rate limits, quota exhaustion, context-window overflow — anything that
    means "this agent cannot continue, hand over to another one".
    """

    status_code = 503
    code = "agent_limit_reached"


class AgentCallError(CollectiveError):
    """The agent failed for a reason that is not a limit."""

    status_code = 502
    code = "agent_call_failed"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CollectiveError)
    async def _handle(request: Request, exc: CollectiveError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": {k: str(v) for k, v in exc.details.items()},
            },
        )
