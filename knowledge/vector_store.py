"""
ChromaDB vector store using OpenAI embeddings (text-embedding-3-small).

Two collections:
  legal_corpus  — Constitution/PPC/CrPC/CPC nodes (built once offline)
  user_documents — uploaded case documents per session (built at upload time)

Embedding calls use the OpenAI client directly (not ChromaDB's built-in
embedding function) so we have full control over batching and error handling.
"""
import chromadb
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
from config import (
    CHROMA_DIR, OPENAI_API_KEY, OPENAI_EMBED_MODEL,
    CHROMA_COLLECTION_LEGAL, CHROMA_COLLECTION_DOCS, EMBED_BATCH_SIZE
)
from knowledge.models import ArticleNode

_client: chromadb.PersistentClient | None = None
_openai_client: OpenAI | None = None
_legal_col = None
_docs_col = None


def _chroma() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _legal_collection():
    global _legal_col
    if _legal_col is None:
        _legal_col = _chroma().get_or_create_collection(
            name=CHROMA_COLLECTION_LEGAL,
            metadata={"hnsw:space": "cosine"},
        )
    return _legal_col


def _docs_collection():
    global _docs_col
    if _docs_col is None:
        _docs_col = _chroma().get_or_create_collection(
            name=CHROMA_COLLECTION_DOCS,
            metadata={"hnsw:space": "cosine"},
        )
    return _docs_col


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
def _embed(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts using OpenAI text-embedding-3-small.
    Returns list of float vectors.
    Retries on rate limit with exponential backoff.
    """
    response = _openai().embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def upsert_articles(nodes: list[ArticleNode]) -> None:
    """
    Embed and store all ArticleNodes into the legal collection.
    Uses node.embedding_text (enriched) for the vector.
    Stores node.id as the ChromaDB document ID.
    Stores key metadata for filtering.
    """
    if not nodes:
        return
        
    unique_nodes = {}
    for n in nodes:
        if n.id not in unique_nodes:
            unique_nodes[n.id] = n
    nodes = list(unique_nodes.values())

    collection = _legal_collection()
    total = len(nodes)
    logger.info(f"Upserting {total} nodes into ChromaDB...")

    for start in range(0, total, EMBED_BATCH_SIZE):
        batch = nodes[start:start + EMBED_BATCH_SIZE]
        texts = [n.embedding_text for n in batch]
        ids = [n.id for n in batch]
        metadatas = [
            {
                "number":     n.number,
                "title":      n.title,
                "source_law": n.source_law.value,
                "node_type":  n.node_type.value,
                "part":       n.part or "",
                "chapter":    n.chapter or "",
                "keywords":   ", ".join(n.keywords),
            }
            for n in batch
        ]

        embeddings = _embed(texts)
        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)
        logger.debug(f"  Upserted {min(start + EMBED_BATCH_SIZE, total)}/{total} nodes")

    logger.success(f"Legal collection size: {collection.count()}")


def search_legal(query: str, n_results: int = 5) -> list[dict]:
    """
    Semantic search over the legal corpus.
    Returns list of {id, metadata, distance} sorted by relevance (ascending distance).
    Returns [] if collection is empty.
    """
    collection = _legal_collection()
    if collection.count() == 0:
        logger.warning("Legal collection empty. Run build_index.py first.")
        return []

    q_embedding = _embed([query])[0]
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(n_results, collection.count()),
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    return [
        {"id": doc_id, "metadata": meta, "distance": dist}
        for doc_id, meta, dist in zip(
            results["ids"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


def upsert_user_document(doc_id: str, chunks: list[str], case_id: str) -> None:
    """Embed and store user document chunks for a case."""
    if not chunks:
        return
    collection = _docs_collection()
    ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    embeddings = _embed(chunks)
    metadatas = [{"doc_id": doc_id, "case_id": case_id, "chunk_index": i}
                 for i in range(len(chunks))]
    collection.upsert(ids=ids, embeddings=embeddings,
                      metadatas=metadatas, documents=chunks)
    logger.info(f"Stored {len(chunks)} chunks for doc {doc_id}")


def search_user_docs(query: str, case_id: str, n_results: int = 3) -> list[str]:
    """Search user documents for a specific case. Returns text chunks."""
    collection = _docs_collection()
    if collection.count() == 0:
        return []
    q_embedding = _embed([query])[0]
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=n_results,
        where={"case_id": case_id},
        include=["documents"],
    )
    if not results["documents"] or not results["documents"][0]:
        return []
    return results["documents"][0]


def legal_corpus_size() -> int:
    return _legal_collection().count()
