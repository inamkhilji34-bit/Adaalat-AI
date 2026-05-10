"""
SQLite database layer using sqlite-utils.
All tables, all queries, all CRUD in one file.
Uses sqlite-utils for clean, Pythonic database access without an ORM.
"""
import uuid
import sqlite_utils
from datetime import datetime
from loguru import logger
from config import DB_PATH


def get_db() -> sqlite_utils.Database:
    return sqlite_utils.Database(DB_PATH)


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every startup."""
    db = get_db()

    if "cases" not in db.table_names():
        db["cases"].create({
            "id":          str,
            "title":       str,
            "description": str,
            "created_at":  str,
            "updated_at":  str,
        }, pk="id")

    if "documents" not in db.table_names():
        db["documents"].create({
            "id":             str,
            "case_id":        str,
            "filename":       str,
            "extracted_text": str,
            "char_count":     int,
            "is_scanned":     int,
            "uploaded_at":    str,
        }, pk="id", foreign_keys=[("case_id", "cases", "id")])

    if "chat_messages" not in db.table_names():
        db["chat_messages"].create({
            "id":         str,
            "case_id":    str,
            "role":       str,   # "user" | "assistant"
            "content":    str,
            "created_at": str,
        }, pk="id", foreign_keys=[("case_id", "cases", "id")])

    if "drafts" not in db.table_names():
        db["drafts"].create({
            "id":            str,
            "case_id":       str,
            "document_type": str,
            "content":       str,
            "created_at":    str,
        }, pk="id", foreign_keys=[("case_id", "cases", "id")])

    logger.success("Database initialized")


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Cases ──────────────────────────────────────────────────────────────────────

def create_case(title: str, description: str = "") -> dict:
    db = get_db()
    row = {"id": str(uuid.uuid4()), "title": title, "description": description,
           "created_at": _now(), "updated_at": _now()}
    db["cases"].insert(row)
    return row


def get_case(case_id: str) -> dict | None:
    rows = list(get_db()["cases"].rows_where("id = ?", [case_id]))
    return rows[0] if rows else None


def list_cases() -> list[dict]:
    return list(get_db()["cases"].rows_where(order_by="created_at DESC"))


def case_exists(case_id: str) -> bool:
    return get_case(case_id) is not None


def ensure_case(case_id: str) -> None:
    """Create case with default title if it doesn't exist."""
    if not case_exists(case_id):
        create_case(title=f"Case {case_id[:8]}")


# ── Documents ──────────────────────────────────────────────────────────────────

def save_document(case_id: str, filename: str,
                  extracted_text: str, is_scanned: bool = False) -> dict:
    db = get_db()
    row = {
        "id":             str(uuid.uuid4()),
        "case_id":        case_id,
        "filename":       filename,
        "extracted_text": extracted_text,
        "char_count":     len(extracted_text),
        "is_scanned":     int(is_scanned),
        "uploaded_at":    _now(),
    }
    db["documents"].insert(row)
    return row


def get_documents(case_id: str) -> list[dict]:
    return list(get_db()["documents"].rows_where(
        "case_id = ?", [case_id], order_by="uploaded_at ASC"
    ))


def get_case_context(case_id: str, max_chars: int = 3000) -> str:
    """Concatenate all document texts for a case, capped at max_chars."""
    docs = get_documents(case_id)
    parts, total = [], 0
    for doc in docs:
        chunk = f"[{doc['filename']}]:\n{doc['extracted_text']}"
        if total + len(chunk) > max_chars:
            parts.append(chunk[:max_chars - total])
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts)


# ── Chat Messages ──────────────────────────────────────────────────────────────

def save_message(case_id: str, role: str, content: str) -> dict:
    db = get_db()
    row = {"id": str(uuid.uuid4()), "case_id": case_id,
           "role": role, "content": content, "created_at": _now()}
    db["chat_messages"].insert(row)
    return row


def get_conversation_history(case_id: str, last_n: int = 20) -> list[dict]:
    """
    Returns last N messages as OpenAI-format history list.
    Format: [{"role": "user"|"assistant", "content": "..."}]
    """
    rows = list(get_db()["chat_messages"].rows_where(
        "case_id = ?", [case_id], order_by="created_at ASC"
    ))
    rows = rows[-last_n:]
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ── Drafts ─────────────────────────────────────────────────────────────────────

def save_draft(case_id: str, document_type: str, content: str) -> dict:
    db = get_db()
    row = {"id": str(uuid.uuid4()), "case_id": case_id,
           "document_type": document_type, "content": content, "created_at": _now()}
    db["drafts"].insert(row)
    return row


def get_drafts(case_id: str) -> list[dict]:
    return list(get_db()["drafts"].rows_where(
        "case_id = ?", [case_id], order_by="created_at DESC"
    ))
