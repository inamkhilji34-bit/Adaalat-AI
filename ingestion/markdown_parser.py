"""
Parses Marker-generated Markdown files into ArticleNode objects.

Why Markdown instead of raw PDF text:
  Marker's layout detection identifies headings structurally, so Article/Section
  boundaries are Markdown headings (#/##/###/####) rather than regex guesses.
  This makes parsing deterministic and robust.

Supports four source laws. Detects which law a file contains from its filename.

CRITICAL IMPLEMENTATION NOTES:

1. Heading level for articles is NOT fixed.
   Marker may output article headings at any level (#/##/###/####) depending
   on the source PDF's visual hierarchy. The parser identifies article/section
   headings by CONTENT PATTERN, not by heading level alone.

   Article/section heading patterns to detect:
   - Starts with a digit: "10-A.", "302.", "497."
   - Starts with "Article": "Article 10-A — Right to fair trial"
   - Starts with "Section": "Section 302 — Punishment for murder"

2. Hierarchy (Part → Chapter → Article) is tracked by heading level.
   Lower heading level number = higher in hierarchy.
   When a heading matches Part pattern, record it as current_part.
   When a heading matches Chapter pattern, record it as current_chapter.
   When a heading matches Article/Section pattern, build a node.

3. Cross-reference extraction must handle ALL of these patterns:
   "Article 10-A", "article 10A", "Art. 10-A", "Art.10A",
   "Section 302", "section 302", "S. 302", "S.302",
   "subsection (2) of Article 25", "clause (b) of Article 17"
   All must resolve to a canonical node ID.

4. Qualification patterns to detect as directed edges:
   "subject to Article X"          → EdgeType.SUBJECT_TO
   "subject to the provisions of Article X" → EdgeType.SUBJECT_TO
   "notwithstanding anything in Article X"  → EdgeType.NOTWITHSTANDING
   "notwithstanding anything contained in Article X" → EdgeType.NOTWITHSTANDING
   "save as provided in Article X"          → EdgeType.CROSS_REF
   "as provided in Article X"               → EdgeType.CROSS_REF

5. Amendment annotations appear as bracketed text in consolidated versions:
   "[Ins. by the Constitution (Eighteenth Amendment) Act, 2010]"
   "[Subs. by Act X of 2010]"
   "[Omitted by ...]"
   Extract the amendment name and store in node.inserted_by or node.modified_by.

6. The embedding_text for each node is ENRICHED — not just the article text.
   Prepend: source law, number, title, part, chapter, keywords, qualifications.
   This enrichment is what makes semantic search find "bail" even when the
   user asks "can I get released from custody" — because the enrichment
   includes legal keywords extracted from the article.

7. For articles longer than 1500 chars, still store the full text in full_text,
   but cap embedding_text at 1500 chars. The full_text is what the agent reads;
   the embedding_text is only used for vector similarity.
"""

import re
from pathlib import Path
from typing import Optional
from loguru import logger
from knowledge.models import ArticleNode, NodeType, SourceLaw, EdgeType
from config import ARTICLE_MIN_CHARS


# ── Regex Patterns ─────────────────────────────────────────────────────────────

# Matches Markdown headings at any level: captures (hashes, heading_text)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Article/Section number patterns in heading text
ARTICLE_NUM_RE = re.compile(
    r'^(?:Article\s+|Section\s+|Art\.\s*|S\.\s*)?'
    r'(\d{1,3}[A-Z]?(?:-[A-Z])?)'
    r'(?:[.\s—\-]+(.+))?$',
    re.IGNORECASE
)

# Part heading: "PART I", "PART IV-A", "Part Two"
PART_RE = re.compile(
    r'^PART\s+([IVXLC\d]+(?:-[A-Z])?)\b',
    re.IGNORECASE
)

# Chapter heading
CHAPTER_RE = re.compile(
    r'^CHAPTER\s+(\d+|[IVXLC]+)\b',
    re.IGNORECASE
)

# Cross-references — all variants, captures article/section number
CROSS_REF_RE = re.compile(
    r'(?:Article|Art\.?|article)\s+(\d{1,3}[A-Z]?(?:-[A-Z])?(?:\s*\([a-z0-9]+\))?)'
    r'|(?:Section|S\.?|section)\s+(\d{1,3}[A-Z]?(?:\s*\([a-z0-9]+\))?)',
    re.IGNORECASE
)

# Qualification patterns: (regex, edge_type_string)
QUALIFICATION_PATTERNS = [
    (re.compile(r'subject\s+to\s+(?:the\s+provisions\s+of\s+)?'
                r'(?:Article|article|Art\.?)\s+(\d{1,3}[A-Z]?(?:-[A-Z])?)', re.IGNORECASE),
     "subject_to"),
    (re.compile(r'notwithstanding\s+anything\s+(?:contained\s+)?in\s+'
                r'(?:Article|article|Art\.?)\s+(\d{1,3}[A-Z]?(?:-[A-Z])?)', re.IGNORECASE),
     "notwithstanding"),
    (re.compile(r'(?:save\s+as|as)\s+provided\s+in\s+'
                r'(?:Article|article|Art\.?)\s+(\d{1,3}[A-Z]?(?:-[A-Z])?)', re.IGNORECASE),
     "save_as"),
]

# Amendment annotations in consolidated text
AMENDMENT_RE = re.compile(
    r'\[(?:Ins|Subs|Added|Inserted|Substituted)\.?\s+by\s+(?:the\s+)?(.+?(?:\d{4}))\]',
    re.IGNORECASE
)

# Legal keywords for enrichment and keyword extraction
LEGAL_KEYWORDS = [
    "bail", "arrest", "detention", "remand", "custody", "fundamental rights",
    "fair trial", "due process", "natural justice", "writ", "habeas corpus",
    "certiorari", "mandamus", "prohibition", "quo warranto", "injunction",
    "appeal", "revision", "review", "jurisdiction", "High Court", "Supreme Court",
    "Sessions Court", "Magistrate", "District Court", "Federal Shariat Court",
    "FIR", "first information report", "cognizable", "non-cognizable",
    "bailable", "non-bailable", "surety", "acquittal", "conviction", "sentence",
    "murder", "culpable homicide", "qatl", "theft", "robbery", "dacoity",
    "fraud", "forgery", "defamation", "blasphemy", "rape", "kidnapping",
    "property", "contract", "tort", "negligence", "damages",
    "constitutional petition", "suo motu", "locus standi", "res judicata",
    "limitation", "estoppel", "mens rea", "actus reus", "burden of proof",
    "emergency", "proclamation", "dissolution", "parliament", "legislature",
    "executive", "judiciary", "separation of powers", "federalism",
    "provincial autonomy", "concurrent list", "federal legislative list",
    "Fundamental Rights", "Directive Principles", "Islamic provisions",
]


# ── Helper Functions ───────────────────────────────────────────────────────────

def make_node_id(number: str, source_law: SourceLaw) -> str:
    """
    Canonical node ID: "art_10A", "ppc_302", "crpc_497"
    Strips hyphens, parentheses, spaces from number.
    """
    prefix_map = {
        SourceLaw.CONSTITUTION: "art",
        SourceLaw.PPC:          "ppc",
        SourceLaw.CRPC:         "crpc",
        SourceLaw.CPC:          "cpc",
        SourceLaw.QSO:          "qso",
        SourceLaw.FCA:          "fca",
        SourceLaw.OTHER:        "law",
    }
    prefix = prefix_map.get(source_law, "law")
    clean = re.sub(r'[-\s\(\)]', '', number)
    return f"{prefix}_{clean}"


def is_article_heading(heading_text: str) -> tuple[bool, str, str]:
    """
    Determine if a heading text represents an article/section.
    Returns (is_article, number, title).

    Handles:
      "10-A. Right to fair trial"
      "Article 10-A — Right to fair trial"
      "302. Punishment for qatl-i-amd"
      "Section 302 — Punishment for murder"
    """
    text = heading_text.strip()

    # Pattern: starts with digits (possibly with letter suffix and hyphen-letter)
    # e.g. "10-A. Right to fair trial" or "302. Punishment for murder"
    m = re.match(
        r'^(\d{1,3}[A-Z]?(?:-[A-Z])?)[.\s—\-]+(.*)$',
        text, re.IGNORECASE
    )
    if m:
        return True, m.group(1).strip(), m.group(2).strip()

    # Pattern: starts with "Article" or "Section" keyword
    m = re.match(
        r'^(?:Article|Section|Art\.)\s+(\d{1,3}[A-Z]?(?:-[A-Z])?)[\s.—\-]+(.*)$',
        text, re.IGNORECASE
    )
    if m:
        return True, m.group(1).strip(), m.group(2).strip()

    return False, "", ""


def extract_cross_refs(text: str, source_law: SourceLaw) -> list[str]:
    """Extract all cross-referenced article/section IDs from text. Deduplicates."""
    refs = set()
    for match in CROSS_REF_RE.finditer(text):
        art_num = match.group(1)
        sec_num = match.group(2)
        if art_num:
            # Article references always point to Constitution
            refs.add(make_node_id(art_num.strip(), SourceLaw.CONSTITUTION))
        elif sec_num:
            # Section references point to the same statute
            refs.add(make_node_id(sec_num.strip(), source_law))
    return list(refs)


def extract_qualifications(text: str, source_law: SourceLaw) -> list[dict]:
    """Extract qualification relationships from article text."""
    qualifications = []
    seen = set()
    for pattern, qual_type in QUALIFICATION_PATTERNS:
        for match in pattern.finditer(text):
            target_num = match.group(1).strip()
            target_id = make_node_id(target_num, SourceLaw.CONSTITUTION)
            key = (qual_type, target_id)
            if key not in seen:
                qualifications.append({"type": qual_type, "target": target_id})
                seen.add(key)
    return qualifications


def extract_amendment_ref(text: str) -> Optional[str]:
    """Return the first amendment reference found, or None."""
    m = AMENDMENT_RE.search(text)
    return m.group(1).strip() if m else None


def extract_keywords(text: str) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in LEGAL_KEYWORDS if kw.lower() in text_lower]


def build_embedding_text(node: ArticleNode) -> str:
    """
    Build enriched text for embedding.
    Includes metadata so the vector captures structural context, not just content.
    Capped at 1500 chars to stay within embedding model limits.
    """
    law_label = "Constitution of Pakistan 1973" if node.source_law == SourceLaw.CONSTITUTION else node.source_law.value.upper()
    unit = "Article" if node.source_law == SourceLaw.CONSTITUTION else "Section"

    lines = [
        f"Source: {law_label}",
        f"{unit} {node.number}: {node.title}",
    ]
    if node.part:
        lines.append(f"Part: {node.part}")
    if node.chapter:
        lines.append(f"Chapter: {node.chapter}")
    if node.inserted_by:
        lines.append(f"Inserted by: {node.inserted_by}")
    if node.keywords:
        lines.append(f"Legal concepts: {', '.join(node.keywords)}")
    if node.qualifications:
        qual_strs = [
            f"{q['type'].replace('_', ' ')} {q['target']}"
            for q in node.qualifications
        ]
        lines.append(f"Qualifications: {'; '.join(qual_strs)}")
    lines.append("")
    lines.append(node.full_text)

    full = "\n".join(lines)
    return full[:1500]  # cap for embedding model


# ── Main Parser ────────────────────────────────────────────────────────────────

def parse_markdown_file(md_path: Path, source_law: SourceLaw) -> list[ArticleNode]:
    """
    Parse a single Marker-generated Markdown file into ArticleNode objects.

    Algorithm:
    1. Split the file into segments on heading boundaries using HEADING_RE
    2. Walk segments in order:
       - If heading matches PART_RE → update current_part, record heading level
       - If heading matches CHAPTER_RE → update current_chapter
       - If is_article_heading() → start a new ArticleNode, collect body text
         until the next heading at same or higher level
    3. After collecting all raw nodes, run cross-ref, qualification, keyword
       extraction on each node's full_text
    4. Build embedding_text for each node
    5. Return the list of ArticleNode objects

    Implementation note on body collection:
    The heading regex splits the document into [text, heading, text, heading, ...]
    segments. After identifying an article heading, collect all subsequent text
    segments until the next heading that is at the SAME OR HIGHER heading level
    (i.e., same or fewer # characters). This correctly handles sub-headings
    within an article (e.g., subsection labels) as part of the article body.
    """
    text = md_path.read_text(encoding="utf-8")
    logger.info(f"Parsing {md_path.name} ({source_law.value}) — {len(text):,} chars")

    # Split into segments: alternating [pre-heading text, heading, body, heading, body, ...]
    # segments[0] = text before first heading (usually empty or preamble)
    # segments[1] = first heading text
    # segments[2] = body after first heading
    # segments[3] = second heading text, etc.
    segments = HEADING_RE.split(text)
    # After split with groups captured: [before, hashes, heading_text, body, hashes, heading_text, body, ...]
    # re.split with 2 groups returns: [before, group1, group2, between, group1, group2, ...]

    nodes: list[ArticleNode] = []
    current_part: Optional[str] = None
    current_chapter: Optional[str] = None

    # Walk through heading/body pairs
    i = 1  # skip the pre-heading text at index 0
    while i < len(segments) - 1:
        hashes = segments[i]       # e.g. "##"
        heading_text = segments[i + 1].strip() if i + 1 < len(segments) else ""
        body = segments[i + 2].strip() if i + 2 < len(segments) else ""
        heading_level = len(hashes)
        i += 3

        # Check if this is a Part heading
        if PART_RE.match(heading_text):
            current_part = heading_text
            current_chapter = None  # new part resets chapter
            continue

        # Check if this is a Chapter heading
        if CHAPTER_RE.match(heading_text):
            current_chapter = heading_text
            continue

        # Check if this is an Article/Section heading
        is_art, number, title = is_article_heading(heading_text)
        if not is_art:
            continue  # skip non-article headings (preamble, appendix, etc.)

        # Collect body: the body variable already contains text until the next heading
        # However, sub-headings WITHIN the article (deeper heading level) should be
        # part of the body. Re-collect by scanning forward until we hit a heading
        # at the same or higher level.
        full_body = body

        # Look ahead: if the next segments are deeper headings, absorb them
        while i < len(segments) - 1:
            next_hashes = segments[i]
            next_heading = segments[i + 1].strip() if i + 1 < len(segments) else ""
            next_body = segments[i + 2].strip() if i + 2 < len(segments) else ""
            next_level = len(next_hashes)

            if next_level > heading_level:
                # Deeper heading = sub-clause of this article, absorb it
                full_body += f"\n\n{'#' * next_level} {next_heading}\n{next_body}"
                i += 3
            else:
                break  # same or higher level = new article or chapter

        full_text = f"{heading_text}\n\n{full_body}".strip()

        if len(full_text) < ARTICLE_MIN_CHARS:
            logger.debug(f"Skipping short node: {number} ({len(full_text)} chars)")
            continue

        node = ArticleNode(
            id=make_node_id(number, source_law),
            node_type=NodeType.ARTICLE if source_law == SourceLaw.CONSTITUTION else NodeType.SECTION,
            source_law=source_law,
            number=number,
            title=title or heading_text,
            full_text=full_text,
            part=current_part,
            chapter=current_chapter,
            cross_refs=extract_cross_refs(full_text, source_law),
            qualifications=extract_qualifications(full_text, source_law),
            inserted_by=extract_amendment_ref(full_text),
            keywords=extract_keywords(full_text),
        )
        node.embedding_text = build_embedding_text(node)
        nodes.append(node)

    logger.success(f"Parsed {len(nodes)} nodes from {md_path.name}")
    return nodes


def detect_source_law(filename: str) -> SourceLaw:
    """
    Infer the source law from the filename.
    Users must name their PDF files clearly. If detection fails, returns OTHER.
    """
    name = filename.lower()
    if any(k in name for k in ["constitution", "const", "1973"]):
        return SourceLaw.CONSTITUTION
    if any(k in name for k in ["penal", "ppc", "pakistan_penal"]):
        return SourceLaw.PPC
    if any(k in name for k in ["criminal_procedure", "crpc", "cr_pc", "1898"]):
        return SourceLaw.CRPC
    if any(k in name for k in ["civil_procedure", "cpc", "c_pc", "1908"]):
        return SourceLaw.CPC
    if any(k in name for k in ["shahadat", "qso", "evidence", "1984"]):
        return SourceLaw.QSO
    if any(k in name for k in ["family", "fca", "family_court"]):
        return SourceLaw.FCA
    logger.warning(f"Could not detect source law for '{filename}'. Marking as OTHER.")
    return SourceLaw.OTHER


def find_all_markdown_files(md_dir: Path) -> list[tuple[Path, SourceLaw]]:
    """
    Walk legal_corpus_md/ and find all .md files produced by Marker.
    Marker creates: legal_corpus_md/{pdf_stem}/{pdf_stem}.md
    Returns list of (md_path, source_law) tuples.
    """
    results = []
    for md_file in sorted(md_dir.rglob("*.md")):
        source_law = detect_source_law(md_file.stem)
        results.append((md_file, source_law))
        logger.debug(f"Found: {md_file.relative_to(md_dir)} → {source_law.value}")
    return results
