"""
Orchestrates the full offline ingestion pipeline.
Called by scripts/build_index.py.

Pipeline:
  1. Find all Markdown files in legal_corpus_md/ (Marker output)
  2. Parse each → list[ArticleNode]
  3. Build NetworkX graph from all nodes
  4. Save graph to data/legal_graph.json
  5. Embed all nodes → upsert to ChromaDB
"""
from pathlib import Path
from loguru import logger
from config import LEGAL_MARKDOWN_DIR
from ingestion.markdown_parser import find_all_markdown_files, parse_markdown_file
from ingestion.graph_builder import build_graph, save_graph
from knowledge.vector_store import upsert_articles


def run_full_ingestion() -> dict:
    md_files = find_all_markdown_files(LEGAL_MARKDOWN_DIR)
    if not md_files:
        raise RuntimeError(
            f"No Markdown files found in {LEGAL_MARKDOWN_DIR}. "
            "Run scripts/run_marker.sh first to convert your PDFs."
        )

    logger.info(f"Found {len(md_files)} Markdown file(s) to ingest")
    all_nodes = []

    for md_path, source_law in md_files:
        nodes = parse_markdown_file(md_path, source_law)
        logger.info(f"  {md_path.name} → {len(nodes)} nodes")
        all_nodes.extend(nodes)

    if not all_nodes:
        raise RuntimeError(
            "No nodes extracted. Check that Marker output is correct "
            "and that PDF filenames contain the source law name."
        )

    logger.info(f"Total: {len(all_nodes)} nodes. Building graph...")
    graph = build_graph(all_nodes)
    save_graph(graph)

    logger.info("Embedding and upserting to ChromaDB...")
    upsert_articles(all_nodes)

    stats = {
        "markdown_files_processed": len(md_files),
        "total_nodes":              len(all_nodes),
        "graph_edges":              graph.number_of_edges(),
        "nodes_by_source": {},
    }
    for node in all_nodes:
        src = node.source_law.value
        stats["nodes_by_source"][src] = stats["nodes_by_source"].get(src, 0) + 1

    logger.success(f"Ingestion complete: {stats}")
    return stats
