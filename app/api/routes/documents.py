from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.core.exceptions import DocumentProcessingError, DocumentValidationError
from app.dependencies import get_ingestion_pipeline
from app.schemas.documents import DocumentStatusResponse, DocumentUploadResponse
from app.services.rag.ingestion import IngestionPipeline

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    tenant_id: str | None = None,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> DocumentUploadResponse:
    content = await file.read()
    try:
        result = pipeline.ingest(
            filename=file.filename or "unnamed", content=content, tenant_id=tenant_id
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DocumentUploadResponse(
        document_id=result.metadata.document_id,
        filename=result.metadata.filename,
        status=result.metadata.status,
        message=f"Ingested {result.chunk_count} chunks.",
    )


@router.get("/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str, pipeline: IngestionPipeline = Depends(get_ingestion_pipeline)
) -> DocumentStatusResponse:
    metadata = pipeline.get_status(document_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentStatusResponse(metadata=metadata)
