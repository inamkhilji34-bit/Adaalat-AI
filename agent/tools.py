"""
The 5 agent tools available to the OpenAI function-calling agent.

Each tool is a plain Python function:
  - Takes typed arguments matching the OpenAI function schema
  - Returns a string (the tool result fed back to the model)
  - Logs what it's doing

The OpenAI tool schemas are defined at the bottom as OPENAI_TOOLS list.
The TOOL_DISPATCH dict maps tool name → Python function.
"""
import networkx as nx
from loguru import logger
from knowledge.vector_store import search_legal
from knowledge.graph_store import get_graph, get_neighbors, get_node_data
from config import VECTOR_TOP_K


# ── Tool Implementations ────────────────────────────────────────────────────────

def tool_search_constitution(query: str) -> str:
    """
    Search the Constitution of Pakistan 1973 for relevant articles.
    Returns full text of matching articles with source annotations.
    """
    logger.info(f"[tool_search_constitution] query={query!r}")
    try:
        graph = get_graph()
    except FileNotFoundError:
        return "Legal knowledge base not loaded. Cannot search."

    results = search_legal(query, n_results=VECTOR_TOP_K)
    const_results = [r for r in results if r["id"].startswith("art_")]
    if not const_results:
        return "No relevant constitutional provisions found for this query."

    parts = []
    for r in const_results:
        data = get_node_data(graph, r["id"])
        if not data:
            continue
        number = data.get("number", "?")
        title  = data.get("title", "")
        text   = data.get("full_text", "")
        parts.append(f"[Constitution — Article {number}: {title}]\n{text}")

    return "\n\n---\n\n".join(parts) if parts else "No provisions found."


def tool_search_statutes(query: str, statute: str = "all") -> str:
    """
    Search PPC, CrPC, or CPC for relevant sections.
    statute: "ppc" | "crpc" | "cpc" | "all"
    """
    logger.info(f"[tool_search_statutes] query={query!r} statute={statute}")
    try:
        graph = get_graph()
    except FileNotFoundError:
        return "Legal knowledge base not loaded."

    results = search_legal(query, n_results=VECTOR_TOP_K)

    prefix_map = {
        "ppc":  ["ppc_"],
        "crpc": ["crpc_"],
        "cpc":  ["cpc_"],
        "all":  ["ppc_", "crpc_", "cpc_", "qso_", "fca_"],
    }
    allowed_prefixes = prefix_map.get(statute, prefix_map["all"])
    filtered = [
        r for r in results
        if any(r["id"].startswith(p) for p in allowed_prefixes)
    ]

    if not filtered:
        return f"No relevant provisions found in {statute.upper()}."

    parts = []
    for r in filtered:
        data = get_node_data(graph, r["id"])
        if not data:
            continue
        number     = data.get("number", "?")
        title      = data.get("title", "")
        text       = data.get("full_text", "")
        source_law = data.get("source_law", "statute").upper()
        parts.append(f"[{source_law} — Section {number}: {title}]\n{text}")

    return "\n\n---\n\n".join(parts) if parts else "No provisions found."


def tool_get_related_articles(article_id: str) -> str:
    """
    Given a node ID, return all directly connected provisions via graph edges.
    Use this after finding a relevant article to discover related provisions.
    """
    logger.info(f"[tool_get_related_articles] article_id={article_id!r}")
    try:
        graph = get_graph()
    except FileNotFoundError:
        return "Legal knowledge base not loaded."

    if article_id not in graph.nodes:
        return (
            f"'{article_id}' not found. "
            "Try IDs like 'art_10A', 'ppc_302', 'crpc_497'."
        )

    lines = [f"Relationships for {article_id}:"]

    for _, target, edge_data in graph.out_edges(article_id, data=True):
        data = get_node_data(graph, target)
        if not data:
            continue
        number = data.get("number", "?")
        title  = data.get("title", "")
        etype  = edge_data.get("edge_type", "cross_ref")
        lines.append(f"  [{etype}] → {target}: {number}. {title}")

    for source, _, edge_data in graph.in_edges(article_id, data=True):
        data = get_node_data(graph, source)
        if not data:
            continue
        number = data.get("number", "?")
        title  = data.get("title", "")
        etype  = edge_data.get("edge_type", "cross_ref")
        lines.append(f"  [referenced_by/{etype}] ← {source}: {number}. {title}")

    if len(lines) == 1:
        return f"No direct relationships found for {article_id}."

    return "\n".join(lines[:20])  # cap output at 20 relationships


def tool_draft_document(
    document_type: str,
    case_facts: str,
    court_name: str = "[COURT NAME]",
    petitioner: str = "[PETITIONER NAME]",
    respondent: str = "[RESPONDENT NAME]",
) -> str:
    """
    Retrieve legal basis for a document type so the agent can draft it correctly.
    Returns the relevant statutory provisions the agent must cite in the draft.
    """
    logger.info(f"[tool_draft_document] type={document_type!r}")

    type_queries = {
        "bail_application":  "bail application Section 496 497 498 CrPC grounds surety",
        "writ_petition":     "writ petition Article 199 Constitution High Court fundamental rights",
        "legal_notice":      "legal notice Section 80 CPC format service",
        "civil_suit":        "civil suit plaint Order 7 CPC requirements filing",
        "appeal":            "appeal Section 408 CrPC Sessions Court conviction",
        "habeas_corpus":     "habeas corpus Article 199 illegal detention unlawful arrest",
        "revision_petition": "revision petition Section 435 CrPC High Court",
    }
    query = type_queries.get(document_type, document_type.replace("_", " "))

    results = search_legal(query, n_results=5)
    if not results:
        return f"No legal basis found for '{document_type}' in knowledge base."

    try:
        graph = get_graph()
    except FileNotFoundError:
        return "Legal knowledge base not loaded."

    parts = []
    for r in results:
        data = get_node_data(graph, r["id"])
        if not data:
            continue
        number     = data.get("number", "?")
        title      = data.get("title", "")
        text       = data.get("full_text", "")[:600]
        source_law = data.get("source_law", "").upper()
        parts.append(f"[{source_law} — {number}: {title}]\n{text}")

    return (
        f"Legal basis for {document_type}:\n\n"
        + "\n\n---\n\n".join(parts)
        + f"\n\nCase facts to incorporate:\n{case_facts}"
    )


def tool_explain_procedure(procedure: str) -> str:
    """
    Explain a legal procedure step-by-step by retrieving the relevant provisions.
    procedure: "bail_process" | "writ_filing" | "fir_process" |
               "appeal_process" | "civil_suit_filing"
    """
    logger.info(f"[tool_explain_procedure] procedure={procedure!r}")
    # Convert procedure name to a natural language query for retrieval
    queries = {
        "bail_process":        "bail process steps CrPC application surety conditions",
        "writ_filing":         "writ petition filing steps Article 199 High Court",
        "fir_process":         "FIR first information report process police station",
        "appeal_process":      "appeal filing process conviction Sessions Court High Court",
        "civil_suit_filing":   "civil suit filing steps plaint CPC court fee",
    }
    query = queries.get(procedure, procedure.replace("_", " "))
    return tool_search_statutes(query, statute="all")


# ── OpenAI Tool Schemas ────────────────────────────────────────────────────────

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_constitution",
            "description": (
                "Search the Constitution of Pakistan 1973 for relevant articles. "
                "Use for: fundamental rights, constitutional petitions, emergency powers, "
                "writ jurisdiction, any question about constitutional provisions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The legal topic or question to search for",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_statutes",
            "description": (
                "Search PPC, CrPC, or CPC for relevant sections. "
                "Use for: criminal offences (PPC), criminal procedure/bail/arrest (CrPC), "
                "civil procedure (CPC)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The legal topic to search for",
                    },
                    "statute": {
                        "type": "string",
                        "enum": ["ppc", "crpc", "cpc", "all"],
                        "description": "Which statute to search. Use 'all' if unsure.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_articles",
            "description": (
                "Get all provisions directly related to a specific article/section "
                "via the knowledge graph. Use after finding a key provision to discover "
                "what it cross-references, qualifies, or is qualified by."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "string",
                        "description": (
                            "Canonical node ID. Examples: 'art_10A' (Constitution Art. 10-A), "
                            "'ppc_302' (PPC S.302), 'crpc_497' (CrPC S.497)"
                        ),
                    }
                },
                "required": ["article_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_document",
            "description": (
                "Retrieve the legal basis and format requirements for a specific court "
                "document before drafting it. Always call this tool before drafting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_type": {
                        "type": "string",
                        "enum": [
                            "bail_application", "writ_petition", "legal_notice",
                            "civil_suit", "appeal", "habeas_corpus", "revision_petition"
                        ],
                    },
                    "case_facts": {
                        "type": "string",
                        "description": "Summary of the case facts to incorporate",
                    },
                    "court_name":  {"type": "string"},
                    "petitioner":  {"type": "string"},
                    "respondent":  {"type": "string"},
                },
                "required": ["document_type", "case_facts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_procedure",
            "description": (
                "Explain a legal procedure step-by-step. Use when the user asks "
                "'how do I file X' or 'what is the process for Y'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "procedure": {
                        "type": "string",
                        "enum": [
                            "bail_process", "writ_filing", "fir_process",
                            "appeal_process", "civil_suit_filing"
                        ],
                    }
                },
                "required": ["procedure"],
            },
        },
    },
]

# Dispatch map: tool name string → Python function
TOOL_DISPATCH: dict = {
    "search_constitution":  tool_search_constitution,
    "search_statutes":      tool_search_statutes,
    "get_related_articles": tool_get_related_articles,
    "draft_document":       tool_draft_document,
    "explain_procedure":    tool_explain_procedure,
}
