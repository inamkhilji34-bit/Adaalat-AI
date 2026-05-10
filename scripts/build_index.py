"""
Build the legal knowledge index from Marker-converted Markdown files.
Run AFTER scripts/run_marker.sh and AFTER verifying Marker output.

Usage: python scripts/build_index.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config import GRAPH_PATH, DATA_DIR
from ingestion.indexer import run_full_ingestion
from knowledge.vector_store import legal_corpus_size
from knowledge.graph_store import graph_loaded

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Adaalat AI — Legal Knowledge Index Builder")
    logger.info("=" * 60)

    if graph_loaded():
        from knowledge.graph_store import get_graph
        g = get_graph()
        logger.info(
            f"Index already exists: {g.number_of_nodes()} nodes, "
            f"{legal_corpus_size()} vectors."
        )
        answer = input("Rebuild from scratch? [y/N]: ").strip().lower()
        if answer != "y":
            logger.info("Keeping existing index.")
            sys.exit(0)
        if GRAPH_PATH.exists():
            GRAPH_PATH.unlink()
            logger.info("Deleted existing graph.")

    stats = run_full_ingestion()

    logger.success("=" * 60)
    logger.success("Index built successfully!")
    logger.success(f"  Markdown files: {stats['markdown_files_processed']}")
    logger.success(f"  Total nodes:    {stats['total_nodes']}")
    logger.success(f"  Graph edges:    {stats['graph_edges']}")
    logger.success(f"  By source law:  {stats['nodes_by_source']}")
    logger.success("=" * 60)
    logger.success("Run: uvicorn main:app --reload --port 8000")
