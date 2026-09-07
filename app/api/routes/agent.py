from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.exceptions import ModelGenerationError
from app.dependencies import get_agent
from app.schemas.agent import AgentRequest, AgentResponse
from app.services.agent.agent import Agent

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("", response_model=AgentResponse)
def run_agent(request: AgentRequest, agent: Agent = Depends(get_agent)) -> AgentResponse:
    try:
        return agent.run(request.query, tenant_id=request.tenant_id)
    except ModelGenerationError as exc:
        raise HTTPException(status_code=502, detail=f"Agent generation failed: {exc}") from exc
