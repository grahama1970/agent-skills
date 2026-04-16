"""Build text banks from extracted datalake corpus and Wikipedia.

Scans /mnt/storage12tb/extractor_corpus/results/ for 04_sections.json,
classifies blocks into content types, and writes one JSON bank per domain.
Optionally fetches Wikipedia articles for additional prose/glossary.
"""
from __future__ import annotations

import json
import re
import os
from pathlib import Path

from loguru import logger

CORPUS_BASE = Path("/mnt/storage12tb/extractor_corpus")
RESULTS_DIR = CORPUS_BASE / "results"
BANK_DIR = Path("/mnt/storage12tb/text_banks")

# Domain detection from source PDF path
DOMAINS = [
    "arxiv", "defense", "dtic", "engineering", "faa",
    "government", "ietf", "industry", "nasa", "nist", "archive_org",
]

# --- Requirement patterns (strict: structured clauses, not policy fragments) ---
# Pattern 1: Numbered clause + shall/must  (e.g. "3.1.2 The system shall...")
_RE_REQ_NUMBERED = re.compile(
    r"^\s*(?:\d+[\.\d]+|[A-Z]{2,}-(?:REQ-?)?\d+)\s+.*\b(?:shall|must)\b",
    re.IGNORECASE | re.MULTILINE,
)
# Pattern 2: Subject + shall (binding requirement verb, not guidance)
_RE_REQ_SHALL = re.compile(
    r"\b(?:the\s+(?:system|software|equipment|contractor|developer|supplier|product|component|unit|module|operator|organization))\s+shall\b",
    re.IGNORECASE,
)
# Pattern 3: Performance/interface/environmental requirement markers
_RE_REQ_ENGINEERING = re.compile(
    r"\bshall\b.*\b(?:not exceed|no (?:more|less|greater|fewer) than|within\s+\d|at least|at most|per\s+(?:second|minute|hour)|comply with|interface with|operate in|withstand|be capable of|be designed to)\b",
    re.IGNORECASE,
)
# Pattern 4: Verification method marker
_RE_REQ_VERIFICATION = re.compile(
    r"\(V:\s*(?:Test|Analysis|Inspection|Demonstration)\)|Verification\s+(?:method|by):",
    re.IGNORECASE,
)
# Pattern 5: Conditional requirement — guard clause + shall
_RE_REQ_CONDITIONAL = re.compile(
    r"\b(?:when|if|unless|in the event|in case|whenever|where|provided that)\b.*\bshall\b",
    re.IGNORECASE,
)
# Pattern 6: Compound requirement — shall + enumerated obligations (bullets/letters after colon)
_RE_REQ_COMPOUND = re.compile(
    r"\bshall\b[^.]*:\s*\n\s*(?:[-•●◦▪a-z]\s*[.)]\s|\d+[.)]\s|[-–—]\s)",
    re.IGNORECASE | re.MULTILINE,
)
_RE_BULLET = re.compile(r"^\s*(?:[-•●◦▪▸►]|\d+[.)]\s|[a-z][.)]\s|[ivxIVX]+[.)]\s)", re.MULTILINE)
_RE_GLOSSARY = re.compile(
    r"^[A-Z][A-Za-z\s/()-]{2,50}\s*[-–—:]\s+\S",
    re.MULTILINE,
)
# LaTeX: raw source (\frac, \sum) or rendered unicode math (∑, ∫, ∈, →, ≤, ≥)
_RE_LATEX_RAW = re.compile(
    r"\\(?:frac|sum|int|prod|lim|begin|end|alpha|beta|gamma|delta|sigma|theta|lambda|partial|nabla|infty|sqrt|mathbb|mathcal|left|right|cdot|times|leq|geq|approx|neq|subset|forall|exists)\b"
)
_RE_MATH_UNICODE = re.compile(
    r"[∑∫∏∂∇∞√≤≥≈≠⊂⊃∈∉∀∃⟨⟩⊗⊕∧∨¬⇒⇔←→↔⊥∅∪∩±×÷∝∼≡≅≜△▽∆λαβγδεζηθικμνξπρστυφχψω]"
)

MIN_PROSE_SENTENCES = 3
MIN_TEXT_LEN = 30


def classify_block(text: str, block_type: str) -> str | None:
    """Classify a text block into a content type. Returns None to skip."""
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_LEN:
        return None

    if block_type == "SectionHeader":
        return "heading"
    if block_type == "Footnote":
        return "footnote"
    if block_type in ("PageHeader", "PageFooter"):
        return None  # skip navigation noise

    # Text blocks — classify further
    # LaTeX / math equations (check before prose since equations often have 3+ periods)
    math_hits = len(_RE_MATH_UNICODE.findall(stripped))
    if _RE_LATEX_RAW.search(stripped) or math_hits >= 3:
        return "latex_equation"

    # Requirement sub-types (most specific first)
    is_req = _RE_REQ_NUMBERED.search(stripped) or _RE_REQ_SHALL.search(stripped) or _RE_REQ_ENGINEERING.search(stripped) or _RE_REQ_VERIFICATION.search(stripped)
    if is_req:
        if _RE_REQ_COMPOUND.search(stripped):
            return "compound_requirement"
        if _RE_REQ_CONDITIONAL.search(stripped):
            return "conditional_requirement"
        return "requirement"
    # Conditional alone (guard + shall without the other structural patterns)
    if _RE_REQ_CONDITIONAL.search(stripped):
        return "conditional_requirement"
    if _RE_BULLET.search(stripped) and stripped.count("\n") >= 1:
        return "bullet_list"
    if _RE_GLOSSARY.match(stripped):
        return "glossary"

    # Prose: 3+ sentences
    sentence_ends = len(re.findall(r"[.!?]\s", stripped)) + (1 if stripped.endswith((".", "!", "?")) else 0)
    if sentence_ends >= MIN_PROSE_SENTENCES:
        return "prose"

    # Short text that doesn't fit other categories — could be table cell
    if len(stripped) < 200 and "\n" not in stripped:
        return "table_cell"

    return "prose" if len(stripped) > 100 else None


def detect_domain(source_pdf: str) -> str:
    """Extract domain from source PDF path."""
    for domain in DOMAINS:
        if domain in source_pdf:
            return domain
    return "other"


def build_from_corpus() -> dict[str, list[dict]]:
    """Scan extracted sections and build per-domain chunk lists."""
    banks: dict[str, list[dict]] = {}

    for result_dir in sorted(RESULTS_DIR.iterdir()):
        sections_file = result_dir / "04_section_builder" / "json_output" / "04_sections.json"
        if not sections_file.exists():
            continue

        try:
            data = json.loads(sections_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(f"Skip corrupt: {sections_file}")
            continue

        source_pdf = data.get("source_pdf", str(result_dir))
        domain = detect_domain(source_pdf)
        doc_name = result_dir.name

        for section in data.get("sections", []):
            for block in section.get("blocks", []):
                text = block.get("text", "").strip()
                block_type = block.get("block_type", "Text")
                content_type = classify_block(text, block_type)
                if content_type is None:
                    continue

                banks.setdefault(domain, []).append({
                    "text": text,
                    "content_type": content_type,
                    "domain": domain,
                    "source_doc": doc_name,
                    "block_id": block.get("id", ""),
                })

    return banks


def build_from_wikipedia(categories: list[str] | None = None) -> list[dict]:
    """Fetch Wikipedia articles and chunk into prose/glossary."""
    try:
        import wikipediaapi  # noqa: E402
    except ImportError:
        logger.warning("wikipediaapi not installed. Run: uv pip install wikipedia-api")
        return []

    wiki = wikipediaapi.Wikipedia("create-text/1.0 (embry-os)", "en")
    chunks: list[dict] = []

    default_categories = [
        "Cybersecurity", "Avionics", "Systems_engineering",
        "Software_engineering", "Aeronautics", "Cryptography",
        "Computer_networks", "Artificial_intelligence",
    ]
    cats = categories or default_categories

    for cat_name in cats:
        cat = wiki.page(f"Category:{cat_name}")
        if not cat.exists():
            logger.warning(f"Wikipedia category not found: {cat_name}")
            continue

        # Get articles from category (limit to 50 per category)
        members = list(cat.categorymembers.values())[:50]
        for page in members:
            if page.ns != wikipediaapi.Namespace.MAIN:
                continue
            if not page.exists():
                continue

            # Split into sections
            for section in _wiki_sections(page):
                text = section["text"].strip()
                content_type = classify_block(text, "Text")
                if content_type is None:
                    continue

                chunks.append({
                    "text": text,
                    "content_type": content_type,
                    "domain": "wikipedia",
                    "source_doc": page.title,
                    "block_id": section["title"],
                })

        logger.info(f"Wikipedia/{cat_name}: {len(members)} articles")

    return chunks


def _wiki_sections(page) -> list[dict]:
    """Recursively extract sections from a Wikipedia page."""
    results = []
    if page.text:
        results.append({"title": page.title, "text": page.text})
    for section in page.sections:
        results.extend(_wiki_section_recurse(section))
    return results


def _wiki_section_recurse(section) -> list[dict]:
    """Recurse into Wikipedia section tree."""
    results = []
    if section.text:
        results.append({"title": section.title, "text": section.text})
    for sub in section.sections:
        results.extend(_wiki_section_recurse(sub))
    return results


def write_banks(banks: dict[str, list[dict]]) -> None:
    """Write per-domain JSON bank files."""
    BANK_DIR.mkdir(parents=True, exist_ok=True)

    for domain, chunks in banks.items():
        out = BANK_DIR / f"{domain}.json"
        out.write_text(json.dumps(chunks, indent=2))
        logger.info(f"Wrote {out}: {len(chunks)} chunks")


def build(source: str = "corpus", categories: list[str] | None = None) -> None:
    """Main build entrypoint."""
    banks: dict[str, list[dict]] = {}

    if source in ("corpus", "all"):
        logger.info(f"Scanning corpus at {RESULTS_DIR}")
        banks = build_from_corpus()
        total = sum(len(v) for v in banks.values())
        logger.info(f"Corpus: {total} chunks across {len(banks)} domains")

    if source in ("wikipedia", "all"):
        wiki_chunks = build_from_wikipedia(categories)
        if wiki_chunks:
            banks.setdefault("wikipedia", []).extend(wiki_chunks)
            logger.info(f"Wikipedia: {len(wiki_chunks)} chunks")

    write_banks(banks)

    # Summary
    for domain, chunks in sorted(banks.items()):
        from collections import Counter
        types = Counter(c["content_type"] for c in chunks)
        logger.info(f"  {domain}: {len(chunks)} total — {dict(types)}")
