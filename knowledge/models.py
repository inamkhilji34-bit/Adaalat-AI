"""
Core data models. Every node type in the knowledge graph is defined here.
Uses plain Python dataclasses — no ORM, no magic.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SourceLaw(str, Enum):
    CONSTITUTION = "constitution"   # Constitution of Pakistan 1973
    PPC          = "ppc"            # Pakistan Penal Code 1860
    CRPC         = "crpc"           # Code of Criminal Procedure 1898
    CPC          = "cpc"            # Code of Civil Procedure 1908
    QSO          = "qso"            # Qanun-e-Shahadat Order 1984
    FCA          = "fca"            # Family Courts Act 1964
    OTHER        = "other"


class NodeType(str, Enum):
    ARTICLE   = "article"           # Constitution articles
    SECTION   = "section"           # PPC/CrPC/CPC sections
    AMENDMENT = "amendment"
    PRECEDENT = "precedent"
    PART      = "part"
    CHAPTER   = "chapter"


class EdgeType(str, Enum):
    CONTAINS        = "contains"        # Part → Chapter → Article hierarchy
    CROSS_REF       = "cross_ref"       # generic "see Article X"
    SUBJECT_TO      = "subject_to"      # "subject to Article X"
    NOTWITHSTANDING = "notwithstanding" # "notwithstanding Article X"
    MODIFIED_BY     = "modified_by"     # Article ← Amendment
    INTERPRETED_BY  = "interpreted_by"  # Article ← Precedent
    STATUTE_LINK    = "statute_link"    # Constitution ↔ PPC/CrPC cross-statute


@dataclass
class ArticleNode:
    id: str                   # canonical: "art_10A", "ppc_302", "crpc_497"
    node_type: NodeType
    source_law: SourceLaw
    number: str               # "10-A", "302", "497"
    title: str                # "Right to fair trial"
    full_text: str            # complete text including sub-clauses
    part: Optional[str]       = None   # "Part II — Fundamental Rights"
    chapter: Optional[str]    = None   # "Chapter 1"
    status: str               = "active"
    inserted_by: Optional[str]= None   # "18th Amendment 2010"
    modified_by: list         = field(default_factory=list)
    cross_refs: list          = field(default_factory=list)   # list of node IDs
    qualifications: list      = field(default_factory=list)   # [{"type":..., "target":...}]
    precedents: list          = field(default_factory=list)   # PLD citation strings
    keywords: list            = field(default_factory=list)
    embedding_text: str       = ""    # enriched text used for the vector (set by parser)


@dataclass
class AmendmentNode:
    id: str               # "amend_18"
    name: str             # "18th Constitutional Amendment"
    year: int             # 2010
    affected_articles: list
    summary: str


@dataclass
class PrecedentNode:
    id: str               # "pld_2018_sc_311"
    citation: str         # "PLD 2018 SC 311"
    court: str            # "Supreme Court of Pakistan"
    year: int
    ratio: str            # the legal principle established
    articles_interpreted: list
    keywords: list
