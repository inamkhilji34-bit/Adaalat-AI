"""
Builds a NetworkX directed graph from ArticleNode objects.
Nodes carry their ArticleNode data as a dict (for JSON serializability).
Edges carry EdgeType as a string value.

Saved to data/legal_graph.json using NetworkX node-link format.
Reloaded at runtime without re-parsing Markdown.
"""
import json
import networkx as nx
from pathlib import Path
from loguru import logger
from knowledge.models import ArticleNode, EdgeType
from config import GRAPH_PATH


def build_graph(nodes: list[ArticleNode]) -> nx.DiGraph:
    """
    Build a directed graph.

    Edges added:
    - CROSS_REF from node.cross_refs
    - SUBJECT_TO / NOTWITHSTANDING / etc. from node.qualifications
    - Self-loops are never added.
    - Edges to non-existent nodes are silently skipped (dangling references
      are expected when only some statutes are ingested).
    """
    G = nx.DiGraph()
    node_id_set = {n.id for n in nodes}

    # Add all nodes — serialize ArticleNode to dict for JSON compatibility
    for node in nodes:
        node_dict = {
            k: (v.value if hasattr(v, "value") else v)
            for k, v in node.__dict__.items()
        }
        G.add_node(node.id, data=node_dict)

    # Add edges
    for node in nodes:
        # Cross-references
        for ref_id in node.cross_refs:
            if ref_id in node_id_set and ref_id != node.id:
                if not G.has_edge(node.id, ref_id):
                    G.add_edge(node.id, ref_id, edge_type=EdgeType.CROSS_REF.value)

        # Qualifications
        for qual in node.qualifications:
            target = qual.get("target")
            if not target or target == node.id or target not in node_id_set:
                continue
            edge_type_map = {
                "subject_to":      EdgeType.SUBJECT_TO.value,
                "notwithstanding": EdgeType.NOTWITHSTANDING.value,
                "save_as":         EdgeType.CROSS_REF.value,
                "as_provided":     EdgeType.CROSS_REF.value,
            }
            etype = edge_type_map.get(qual.get("type", ""), EdgeType.CROSS_REF.value)
            if not G.has_edge(node.id, target):
                G.add_edge(node.id, target, edge_type=etype)

    logger.success(
        f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
    )
    return G


def save_graph(G: nx.DiGraph) -> None:
    """Serialize graph to JSON. Node data must already be dicts."""
    data = nx.node_link_data(G)
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.success(f"Graph saved → {GRAPH_PATH}")


def load_graph() -> nx.DiGraph:
    """Load the persisted graph. Raises FileNotFoundError if not yet built."""
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            f"Legal graph not found at {GRAPH_PATH}. "
            "Run scripts/build_index.py first."
        )
    with open(GRAPH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    G = nx.node_link_graph(data)
    logger.info(
        f"Graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
    )
    return G


def get_neighbors(G: nx.DiGraph, node_id: str, hops: int = 2) -> list[str]:
    """
    Return all node IDs reachable within `hops` hops via any edge direction.
    Excludes the seed node itself.
    """
    if node_id not in G:
        return []
    visited = {node_id}
    frontier = {node_id}
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            nxt.update(G.predecessors(n))
            nxt.update(G.successors(n))
        frontier = nxt - visited
        visited.update(frontier)
    visited.discard(node_id)
    return list(visited)
