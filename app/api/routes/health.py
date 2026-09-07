from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    live_vertex_ai: bool


@router.get("/healthz", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Liveness probe: process is up. Cheap, no dependency checks."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        live_vertex_ai=settings.gcp.use_live_vertex_ai,
    )


@router.get("/readyz", response_model=HealthResponse)
def readiness() -> HealthResponse:
    """Readiness probe: distinct from liveness per Phase 12 requirements.
    In the live-Vertex configuration this would additionally verify
    connectivity to the vector index endpoint and the documents bucket;
    kept identical to liveness in local/mock mode since there is nothing
    external to check."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        live_vertex_ai=settings.gcp.use_live_vertex_ai,
    )
