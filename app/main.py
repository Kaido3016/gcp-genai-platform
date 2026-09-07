from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agent, chat, documents, health
from app.core.config import get_settings
from app.core.exceptions import PlatformError
from app.core.logging import configure_logging, get_logger, log_event, set_request_id

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("app")

app = FastAPI(
    title="GCP GenAI Platform",
    description=(
        "Vertex AI / Gemini RAG + Agentic AI portfolio platform. "
        "See /docs for the API and the repository docs/ for architecture, "
        "RAG design, agent design, evaluation, security, and deployment."
    ),
    version="0.1.0",
)

# Secure-by-default CORS: explicit allowlist, no wildcard with credentials.
# Overridden per environment via deployment config, not hardcoded to a
# production domain here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get(settings.request_id_header, str(uuid.uuid4()))
    set_request_id(request_id)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers[settings.request_id_header] = request_id
    log_event(
        logger,
        logging.INFO,
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    """Catch-all for our own exception hierarchy that a route didn't
    explicitly translate to an HTTPException — still a deliberate,
    typed handler, not a bare `except Exception`."""
    log_event(
        logger,
        logging.ERROR,
        "unhandled_platform_error",
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(agent.router)
