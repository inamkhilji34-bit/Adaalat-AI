"""
Central configuration. Every constant lives here. No magic strings anywhere else.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).parent
LEGAL_CORPUS_DIR    = BASE_DIR / "legal_corpus"          # source PDFs
LEGAL_MARKDOWN_DIR  = BASE_DIR / "legal_corpus_md"       # Marker output
UPLOADS_DIR         = BASE_DIR / "uploads"               # user-uploaded docs
DATA_DIR            = BASE_DIR / "data"
CHROMA_DIR          = DATA_DIR / "chroma_db"
DB_PATH             = DATA_DIR / "adaalat.db"
GRAPH_PATH          = DATA_DIR / "legal_graph.json"

# Create all runtime directories on import
for _d in [LEGAL_CORPUS_DIR, LEGAL_MARKDOWN_DIR, UPLOADS_DIR, DATA_DIR, CHROMA_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── OpenAI ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL   = "gpt-4o-mini"           # fast, cheap, capable
OPENAI_EMBED_MODEL  = "text-embedding-3-small" # 1536 dims, cheapest good embedder
MAX_TOKENS          = 4096
AGENT_TEMPERATURE   = 0.1                      # low temp for legal accuracy

# ── ChromaDB ───────────────────────────────────────────────────────────────────
CHROMA_COLLECTION_LEGAL = "pakistan_legal_corpus"
CHROMA_COLLECTION_DOCS  = "user_documents"

# ── Retrieval ──────────────────────────────────────────────────────────────────
VECTOR_TOP_K        = 5     # seed nodes from vector search
GRAPH_HOP_DEPTH     = 2     # graph hops from each seed
MAX_CONTEXT_CHARS   = 14000 # ~3500 tokens @ 4 chars/token

# ── Ingestion ──────────────────────────────────────────────────────────────────
ARTICLE_MIN_CHARS   = 60    # skip nodes shorter than this (noise)
EMBED_BATCH_SIZE    = 50    # articles per ChromaDB upsert batch

# ── Agent ──────────────────────────────────────────────────────────────────────
MAX_AGENT_TURNS     = 8     # max tool-call iterations per run

# ── API ────────────────────────────────────────────────────────────────────────
UPLOAD_MAX_SIZE_MB  = 20
ALLOWED_EXTENSIONS  = {".pdf"}
