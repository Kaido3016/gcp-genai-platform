from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.exceptions import ModelGenerationError, RetrievalError
from app.dependencies import get_rag_pipeline
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag.pipeline import RagPipeline

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, pipeline: RagPipeline = Depends(get_rag_pipeline)) -> ChatResponse:
    try:
        return pipeline.answer(request.query, tenant_id=request.tenant_id)
    except RetrievalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelGenerationError as exc:
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}") from exc
