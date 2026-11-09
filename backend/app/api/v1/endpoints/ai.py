import asyncio
import hashlib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.ai_assistant import ai_assistant
from app.core.database import get_db_session
from app.core.tenant_context import get_current_tenant
from app.core.vector_store import vector_store
from app.domain.user.models import User, UserRole
from app.services.coo_agent import COOAgent

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


class QueryRequest(BaseModel):
    query: str
    context: Optional[list[dict]] = None


class QueryResponse(BaseModel):
    response: str


class AnalysisRequest(BaseModel):
    total_bookings: int
    completion_rate: float
    avg_value: float
    peak_hours: list[str]


@router.post("/query", response_model=QueryResponse)
async def query_assistant(request: QueryRequest, current_user: User = Depends(get_current_user)):
    """Query AI assistant with RAG"""
    tenant_id = get_current_tenant()

    response = await ai_assistant.generate_response(
        query=request.query,
        context=request.context,
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    return QueryResponse(response=response)


@router.post("/analyze/bookings", response_model=Dict[str, Any])
async def analyze_bookings(request: AnalysisRequest, current_user: User = Depends(get_current_user)):
    """Analyze booking patterns"""
    tenant_id = get_current_tenant()

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    analysis = await ai_assistant.analyze_booking_patterns(
        tenant_id=str(tenant_id),
        data=request.model_dump(),
    )

    return analysis


class COORequest(BaseModel):
    question: str


class COOResponse(BaseModel):
    answer: str
    tools_used: list[str]
    data: Dict[str, Any]


@router.post("/coo", response_model=COOResponse)
async def ask_coo(
    request: COORequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.PROVIDER])),
    db: AsyncSession = Depends(get_db_session),
):
    """Ask the Virtual COO a business question, answered from this tenant's real data.

    The agent selects data tools (revenue, bookings, demand forecast, peak hours),
    runs them tenant-scoped, then synthesises a concise answer via the local LLM.
    """
    agent = COOAgent(db)
    result = await agent.ask(request.question)
    return COOResponse(**result)


# ---------------------------------------------------------------------------
# Business document ingestion
# ---------------------------------------------------------------------------


class IngestDocument(BaseModel):
    content: str
    title: str
    tags: Optional[List[str]] = None


class IngestRequest(BaseModel):
    documents: List[IngestDocument]


class IngestResponse(BaseModel):
    ingested: int
    skipped: int
    message: str


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    payload: IngestRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Ingest business knowledge documents into the RAG vector store (admin only).

    Documents are deduplicated by a SHA-256 hash of their content so re-uploading
    the same text is safe (ChromaDB upsert semantics via add with the same id).
    """
    if not vector_store.collection:
        raise HTTPException(status_code=503, detail="Vector store unavailable (ChromaDB not configured)")

    docs, metas, ids = [], [], []
    tenant_id = str(current_user.tenant_id)

    for doc in payload.documents:
        doc_id = hashlib.sha256(doc.content.encode()).hexdigest()[:32]
        docs.append(doc.content)
        metas.append({"title": doc.title, "tags": ",".join(doc.tags or []), "tenant_id": tenant_id})
        ids.append(f"{tenant_id}:{doc_id}")

    # add_documents is synchronous (ChromaDB); run off the event loop to avoid blocking
    await asyncio.get_event_loop().run_in_executor(None, vector_store.add_documents, docs, metas, ids)

    return IngestResponse(
        ingested=len(docs),
        skipped=0,
        message=f"Ingested {len(docs)} document(s) into the knowledge base.",
    )
