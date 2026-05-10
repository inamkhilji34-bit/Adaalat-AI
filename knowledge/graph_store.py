"""
Singleton wrapper for the loaded NetworkX graph.
Loaded once on first access. Subsequent calls return the cached instance.
"""
import networkx as nx
from loguru import logger
from ingestion.graph_builder import load_graph, get_neighbors as _get_neighbors

_graph: nx.DiGraph | None = None


def get_graph() -> nx.DiGraph:
    global _graph
    if _graph is None:
        _graph = load_graph()
    return _graph


def get_neighbors(graph: nx.DiGraph, node_id: str, hops: int = 2) -> list[str]:
    return _get_neighbors(graph, node_id, hops=hops)


def graph_loaded() -> bool:
    """Returns True if the graph file exists and has nodes."""
    try:
        g = get_graph()
        return g.number_of_nodes() > 0
    except FileNotFoundError:
        return False


def get_node_data(graph: nx.DiGraph, node_id: str) -> dict | None:
    """
    Safely retrieve node data dict.
    Always returns a plain dict (node data is stored as dict, not ArticleNode).
    Returns None if node_id not in graph.
    """
    if node_id not in graph.nodes:
        return None
    return graph.nodes[node_id].get("data")
