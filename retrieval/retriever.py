"""
Two-phase graph-aware retriever.

Phase 1 — Vector search: semantic similarity to find seed nodes.
Phase 2 — Graph traversal: expand context via edges in the knowledge graph.

Result: assembled context string with source annotations, ready to inject
into the LLM prompt. Ordered: direct matches first, then related nodes.
Capped at MAX_CONTEXT_CHARS to avoid exceeding the model context window.
"""
import networkx as nx
from loguru import logger
from knowledge.vector_store import search_legal
from knowledge.graph_store import get_neighbors, get_node_data
from config import VECTOR_TOP_K, GRAPH_HOP_DEPTH, MAX_CONTEXT_CHARS


def retrieve(query: str, graph: nx.DiGraph) -> str:
    """
    Main entry point. Takes a query string and loaded graph.
    Returns assembled context string or a fallback message.
    """
    # Phase 1: vector search
    vector_results = search_legal(query, n_results=VECTOR_TOP_K)
    if not vector_results:
        return "No relevant legal provisions found in the knowledge base."

    seed_ids = [r["id"] for r in vector_results]
    logger.debug(f"Vector seeds ({len(seed_ids)}): {seed_ids}")

    # Phase 2: graph traversal
    expanded_ids = set(seed_ids)
    for seed_id in seed_ids:
        neighbors = get_neighbors(graph, seed_id, hops=GRAPH_HOP_DEPTH)
        expanded_ids.update(neighbors)

    logger.debug(f"After graph expansion: {len(expanded_ids)} nodes")

    # Build ordered list: seeds first (most relevant), then expansion
    ordered_ids = list(seed_ids) + [
        nid for nid in expanded_ids if nid not in set(seed_ids)
    ]

    # Assemble context blocks
    context_blocks = []
    char_count = 0

    for node_id in ordered_ids:
        data = get_node_data(graph, node_id)
        if not data:
            continue

        number     = data.get("number", "?")
        title      = data.get("title", "")
        full_text  = data.get("full_text", "")
        source_law = data.get("source_law", "")
        part       = data.get("part") or ""

        unit = "Article" if source_law == "constitution" else "Section"
        header = f"[{source_law.upper()} — {unit} {number}: {title}"
        if part:
            header += f" | {part}"
        header += "]"

        block = f"{header}\n{full_text}"

        if char_count + len(block) > MAX_CONTEXT_CHARS:
            logger.debug(f"Context cap reached at {char_count} chars")
            break

        context_blocks.append(block)
        char_count += len(block)

    if not context_blocks:
        return "No relevant legal provisions could be assembled."

    logger.info(
        f"Retrieved {len(context_blocks)} blocks, "
        f"~{char_count // 4} tokens of legal context"
    )
    return "\n\n---\n\n".join(context_blocks)
