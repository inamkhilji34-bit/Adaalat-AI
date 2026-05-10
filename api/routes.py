"""
All FastAPI route handlers.
Routes are thin — validate input, call business logic, return response.
No business logic in this file.
"""
import pdfplumber
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from config import UPLOADS_DIR, ALLOWED_EXTENSIONS, UPLOAD_MAX_SIZE_MB
from database.db import (
    create_case, get_case, list_cases, case_exists, ensure_case,
    save_document, get_documents, get_case_context,
    save_message, get_conversation_history,
    save_draft, get_drafts,
)
from knowledge.vector_store import upsert_user_document, legal_corpus_size
from knowledge.graph_store import graph_loaded, get_graph
from retrieval.retriever import retrieve
from agent.agent_runner import run_agent

router = APIRouter()


# ── Pydantic models ────────────────────────────────────────────────────────────

class CreateCaseRequest(BaseModel):
    title: str
    description: str = ""

class ChatRequest(BaseModel):
    case_id: str
    message: str

class DraftRequest(BaseModel):
    case_id: str
    document_type: str
    additional_instructions: Optional[str] = None


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "legal_graph_loaded": graph_loaded(),
        "legal_corpus_vectors": legal_corpus_size(),
    }


# ── Cases ──────────────────────────────────────────────────────────────────────

@router.post("/cases", status_code=201)
async def create_case_route(req: CreateCaseRequest):
    return create_case(req.title, req.description)

@router.get("/cases")
async def list_cases_route():
    return list_cases()

@router.get("/cases/{case_id}")
async def get_case_route(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case

@router.get("/cases/{case_id}/history")
async def case_history(case_id: str):
    if not case_exists(case_id):
        raise HTTPException(404, "Case not found")
    return {
        "case_id":   case_id,
        "documents": get_documents(case_id),
        "drafts":    get_drafts(case_id),
    }


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    case_id: str = Query(...),
    file: UploadFile = File(...),
):
    """
    Upload a user's legal PDF document (FIR, court order, deed, contract).
    Extracts text with pdfplumber, saves to DB, embeds chunks into ChromaDB.
    NOTE: This is for USER documents only. Legal corpus PDFs are handled
    offline by Marker + build_index.py.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Only PDF files are accepted. Got: {suffix}")

    content = await file.read()
    if len(content) > UPLOAD_MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large. Maximum: {UPLOAD_MAX_SIZE_MB}MB")

    ensure_case(case_id)

    # Save to disk
    save_path = UPLOADS_DIR / f"{case_id}_{file.filename}"
    save_path.write_bytes(content)

    # Extract text with pdfplumber
    extracted_text = ""
    is_scanned = False
    try:
        with pdfplumber.open(save_path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
            extracted_text = "\n\n".join(t for t in pages_text if t.strip())
        avg_chars = len(extracted_text) / max(len(pages_text), 1)
        is_scanned = avg_chars < 100
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not read PDF: {str(e)}")

    if not extracted_text.strip():
        raise HTTPException(
            422,
            "Could not extract text from this PDF. It appears to be a scanned image. "
            "Please type out the key facts from this document in the chat instead."
        )

    # Save to DB
    doc = save_document(case_id, file.filename, extracted_text, is_scanned)

    # Chunk and embed for semantic search during analysis
    chunk_size = 800
    chunks = [
        extracted_text[i:i + chunk_size]
        for i in range(0, len(extracted_text), chunk_size)
        if extracted_text[i:i + chunk_size].strip()
    ]
    upsert_user_document(doc["id"], chunks, case_id)

    return {
        "doc_id":     doc["id"],
        "filename":   file.filename,
        "char_count": len(extracted_text),
        "is_scanned": is_scanned,
        "preview":    extracted_text[:400] + "..." if len(extracted_text) > 400 else extracted_text,
    }


# ── Analysis ───────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_document(
    case_id: str = Query(...),
    doc_id:  str = Query(...),
):
    """Run the agent analysis on a specific uploaded document."""
    if not case_exists(case_id):
        raise HTTPException(404, "Case not found")
    if not graph_loaded():
        raise HTTPException(503, "Legal knowledge base not loaded. Run build_index.py first.")

    docs = get_documents(case_id)
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Document not found in this case")

    doc_text = doc["extracted_text"]
    graph = get_graph()
    legal_context = retrieve(doc_text[:1500], graph)

    analysis = run_agent(
        user_message=(
            f"Please analyze this legal document and provide your full assessment.\n\n"
            f"DOCUMENT:\n{doc_text[:3000]}\n\n"
            f"LEGAL CONTEXT:\n{legal_context}"
        ),
        conversation_history=[],
        case_context=doc_text[:1500],
    )

    save_message(case_id, "user", f"[Analyzed: {doc['filename']}]")
    save_message(case_id, "assistant", analysis)

    return {"case_id": case_id, "doc_id": doc_id, "analysis": analysis}


# ── Chat ───────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(req: ChatRequest):
    """Multi-turn legal consultation. Maintains history per case."""
    ensure_case(req.case_id)
    if not graph_loaded():
        raise HTTPException(503, "Legal knowledge base not loaded.")

    case_context = get_case_context(req.case_id, max_chars=2000)
    history      = get_conversation_history(req.case_id, last_n=16)

    response = run_agent(
        user_message=req.message,
        conversation_history=history,
        case_context=case_context,
    )

    save_message(req.case_id, "user",      req.message)
    save_message(req.case_id, "assistant", response)

    return {"case_id": req.case_id, "response": response}


# ── Draft ──────────────────────────────────────────────────────────────────────

@router.post("/draft")
async def draft_document(req: DraftRequest):
    """Generate a court-ready legal document."""
    if not case_exists(req.case_id):
        raise HTTPException(404, "Case not found")
    if not graph_loaded():
        raise HTTPException(503, "Legal knowledge base not loaded.")

    case_context = get_case_context(req.case_id, max_chars=2000)
    history      = get_conversation_history(req.case_id, last_n=8)

    doc_type_display = req.document_type.replace("_", " ")
    prompt = (
        f"Please draft a complete {doc_type_display} for my case. "
        f"Use the facts from my uploaded documents. "
        + (f"Additional instructions: {req.additional_instructions}" if req.additional_instructions else "")
    )

    response = run_agent(
        user_message=prompt,
        conversation_history=history,
        case_context=case_context,
    )

    draft = save_draft(req.case_id, req.document_type, response)
    save_message(req.case_id, "user",      prompt)
    save_message(req.case_id, "assistant", response)

    return {
        "draft_id":      draft["id"],
        "case_id":       req.case_id,
        "document_type": req.document_type,
        "content":       response,
    }
