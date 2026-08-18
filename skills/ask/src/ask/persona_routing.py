"""
Persona routing for /ask queries.

Identifies relevant personas for a question using Federated Taxonomy
bridge-attribute matching and domain expertise scoring. Also provides
persona name extraction from natural language questions.
"""

import re
from typing import Optional

from loguru import logger as log

from .skills_exec import run_skill, parse_memory_output, run_memory_recall


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

def extract_bridges(question: str) -> list[str]:
    """Extract bridge attributes from the question using taxonomy keyword mode."""
    result = run_skill("taxonomy", [
        "extract",
        "--text", question,
        "--bridges-only",
        "--fast",
    ], timeout=10)

    if result["returncode"] == 0 and result["stdout"].strip():
        bridges = [b.strip() for b in result["stdout"].strip().split(",") if b.strip()]
        log.debug("Extracted bridges: {}", bridges)
        return bridges
    log.debug("No bridges extracted from question")
    return []


# ---------------------------------------------------------------------------
# Persona name extraction from questions
# ---------------------------------------------------------------------------

# Common filler tokens that should not appear in a persona name
_PERSONA_FILLER_TOKENS = frozenset({
    "the", "a", "an", "this", "that", "what", "how", "why", "when", "where",
    "on", "about", "and", "in", "for", "with", "of", "to", "from", "by", "at", "as",
})

# Phrases that look like capitalised names but are not
_COMMON_PHRASES = frozenset({
    "How Do", "What Does", "Tell Me", "Learn About", "According To",
})

# Regex patterns for person references inside questions
_PERSONA_PATTERNS = [
    # "What does <Name> say/think/believe about..."
    r"(?:what|how)\s+(?:does|did|do)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+"
    r"(?:say|think|believe|explain|describe|argue|claim)",
    # "According to <Name>..."
    r"according\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # "Tell me about <Name>" or "Learn about <Name>"
    r"(?:tell\s+me|learn|teach\s+me)\s+about\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # "<Name>'s view/theory/work on..."
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?:'s|s')\s+"
    r"(?:view|theory|work|research|ideas?|approach)",
    # "Who is <Name>" or "Who was <Name>"
    r"who\s+(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    # Direct name mention with title: "Dr. <Name>", "Professor <Name>"
    r"(?:dr\.?|prof(?:essor)?\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
    r"(?:\s+(?:on|about|and|in|for|with)|$|[,.])",
]


def extract_persona_from_question(question: str) -> Optional[str]:
    """Extract a persona name from a natural-language question.

    Examples:
        "What does Sapolsky say about stress?" -> "Sapolsky"
        "How does Lisa Feldman Barrett explain emotions?" -> "Lisa Feldman Barrett"
        "Tell me about Robert Sapolsky" -> "Robert Sapolsky"
        "What is machine learning?" -> None

    Returns:
        Persona name if detected, None otherwise.
    """
    for pattern in _PERSONA_PATTERNS:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            words = name.split()
            # Keep only capitalised words (real name components)
            words = [w for w in words if w and w[0].isupper()]
            words = [w for w in words if w.lower() not in _PERSONA_FILLER_TOKENS]
            if words:
                name = " ".join(words)
                log.debug("Extracted persona '%s' from question", name)
                return name

    # Fallback: look for "Firstname Lastname" patterns
    name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b'
    matches = re.findall(name_pattern, question)
    if matches:
        for name in matches:
            if name not in _COMMON_PHRASES:
                log.debug("Fallback persona extraction: '%s'", name)
                return name

    return None


# ---------------------------------------------------------------------------
# Persona relevance scoring
# ---------------------------------------------------------------------------

def find_relevant_personas(
    question: str,
    bridges: list[str] | None = None,
    scope: str = "personas",
    limit: int = 3,
) -> list[dict]:
    """Find personas relevant to answering a question.

    Uses Federated Taxonomy bridges and domain matching to identify
    which personas are best suited to answer a question.

    Args:
        question: The question to find experts for.
        bridges: Pre-extracted bridges (optional; extracted if not provided).
        scope: Persona scope to search.
        limit: Maximum personas to return.

    Returns:
        List of relevant personas with match scores.
    """
    if bridges is None:
        bridges = extract_bridges(question)

    if not bridges:
        log.debug("No bridges found for persona routing")
        return []

    bridge_query = f"persona expert {' '.join(bridges)}"
    log.info("Persona routing: searching for experts with bridges {}", bridges)

    result = run_memory_recall(
        bridge_query,
        scope,
        k=limit * 2,
        timeout=15,
    )

    if result["returncode"] != 0:
        log.warning("Persona search failed: {}", result["stderr"][:100])
        return []

    items = parse_memory_output(result["stdout"])

    personas: list[dict] = []
    seen_names: set[str] = set()

    for item in items:
        # Extract persona name from various fields
        name = None
        if "persona" in item:
            name = item["persona"]
        elif "name" in item:
            name = item["name"]
        elif "problem" in item and "Persona:" in item["problem"]:
            pmatch = re.search(r"Persona:\s*(\w+(?:\s+\w+)*)", item["problem"])
            if pmatch:
                name = pmatch.group(1)

        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # Score by bridge overlap
        item_bridges = (
            set(item.get("bridges", {}).keys())
            if isinstance(item.get("bridges"), dict)
            else set()
        )
        query_bridges = set(bridges)
        overlap = len(item_bridges & query_bridges)
        score = overlap / max(len(query_bridges), 1)

        # Boost for expertise / domain match
        expertise = item.get("expertise", [])
        domain = item.get("domain", "")
        question_lower = question.lower()

        if any(e.lower() in question_lower for e in expertise):
            score += 0.3
        if domain and domain.lower() in question_lower:
            score += 0.2

        if score > 0:
            personas.append({
                "name": name,
                "score": score,
                "bridges": list(item_bridges & query_bridges),
                "domain": domain,
                "expertise": expertise[:3] if expertise else [],
                "role": item.get("role", ""),
            })

    personas.sort(key=lambda p: p["score"], reverse=True)
    log.info("Persona routing: found {} relevant personas", len(personas[:limit]))
    return personas[:limit]


def suggest_persona_consultation(question: str, scope: str = "personas") -> str:
    """Suggest which personas should be consulted for a question.

    Returns a formatted string with persona recommendations.
    """
    bridges = extract_bridges(question)
    personas = find_relevant_personas(question, bridges, scope)

    if not personas:
        return ""

    lines = ["\n  Suggested personas to consult:"]
    for p in personas:
        bridge_str = ", ".join(p["bridges"]) if p["bridges"] else "domain match"
        lines.append(f"    - {p['name']} ({p.get('role', 'expert')}) [{bridge_str}]")

    return "\n".join(lines)
