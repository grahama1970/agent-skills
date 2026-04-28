"""Routing helpers for natural ask/persona queries."""

import re
from typing import Optional

QUESTION_STARTERS = frozenset({
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "is",
    "are",
    "do",
    "does",
    "did",
    "should",
    "can",
    "could",
    "would",
    "will",
    "tell",
    "explain",
    "compare",
    "analyze",
    "assess",
    "check",
    "critique",
    "describe",
    "diagnose",
    "evaluate",
    "grade",
    "investigate",
    "recommend",
    "review",
    "summarize",
    "state",
    "validate",
})

def _is_operational_question(question: str) -> bool:
    """Detect questions about pipeline/datalake operations (not domain content).

    Nico asks about extraction quality, convergence, scoring dimensions, pipeline
    health — these should route to evidence cases, not BM25 datalake search.
    """
    q = question.lower()
    # Operational signals: pipeline/system health vocabulary
    ops_terms = {
        "extraction", "pipeline", "convergence", "scoring", "quality",
        "table_fidelity", "figure_fidelity", "section_alignment",
        "content_coverage", "equation_fidelity", "data_quality",
        "ordering_yx", "degrading", "improving", "score", "accuracy",
        "fail_pct", "pass rate", "persona", "assessment", "datalake health",
        "learn-datalake", "extracted", "ingest", "remediat",
    }
    # Must also contain a system-referencing term (not just generic words)
    system_refs = {"pipeline", "extraction", "datalake", "extractor", "scoring",
                   "learn-datalake", "convergence", "assessment", "persona",
                   "dimension", "fidelity", "coverage"}
    has_ops = any(t in q for t in ops_terms)
    has_sys = any(t in q for t in system_refs)
    return has_ops and has_sys


def _normalize_question_parts(question_parts: list[str]) -> str:
    """Join Typer varargs into a single question string."""
    return " ".join(part.strip() for part in question_parts if part.strip()).strip()


def _parse_natural_persona_query(
    question_parts: list[str],
    explicit_persona: Optional[str],
) -> tuple[str, Optional[str], Optional[str], bool]:
    """Parse natural syntax like `ask Brandon what should we do?`.

    Returns: question, inferred_persona, inferred_peer, inferred_oracle.
    """
    question = _normalize_question_parts(question_parts)
    if explicit_persona or len(question_parts) < 2:
        return question, None, None, False

    cleaned_parts = [part.strip(" ,:;") for part in question_parts if part.strip(" ,:;")]
    if len(cleaned_parts) < 2:
        return question, None, None, False

    if (
        len(cleaned_parts) >= 3
        and cleaned_parts[1].lower().rstrip("?,.!") in {"persona", "as"}
        and _looks_like_persona_prefix(cleaned_parts[0])
    ):
        prompt_parts = cleaned_parts[2:]
        if prompt_parts and prompt_parts[0].lower().rstrip("?,.!") == "about":
            prompt_parts = prompt_parts[1:]
        prompt = " ".join(prompt_parts)
        if prompt:
            return prompt, cleaned_parts[0], None, True

    if cleaned_parts[0].lower() == "as" and len(cleaned_parts) >= 3:
        for index in range(2, min(len(cleaned_parts), 6)):
            if cleaned_parts[index].lower().rstrip("?,.!") in QUESTION_STARTERS:
                persona = " ".join(cleaned_parts[1:index])
                return " ".join(cleaned_parts[index:]), persona, None, True

    max_persona_words = min(4, len(cleaned_parts) - 1)
    for index in range(1, max_persona_words + 1):
        next_word = cleaned_parts[index].lower().rstrip("?,.!")
        if next_word == "ask" and _looks_like_persona_prefix(" ".join(cleaned_parts[:index])):
            peer_parse = _parse_persona_peer_query(cleaned_parts, index)
            if peer_parse:
                prompt, persona, peer = peer_parse
                return prompt, persona, peer, True
        if next_word not in QUESTION_STARTERS:
            continue
        persona = " ".join(cleaned_parts[:index])
        if _looks_like_persona_prefix(persona):
            return " ".join(cleaned_parts[index:]), persona, None, True

    return question, None, None, False


def _parse_natural_roundtable_query(question_parts: list[str]) -> tuple[str, str | None, bool]:
    """Parse `Brandon, Margaret, and Jennifer to debate X` syntax.

    Returns: topic/question, comma-separated persona list, inferred_roundtable.
    """
    question = _normalize_question_parts(question_parts)
    if not question:
        return question, None, False
    lowered = question.lower()

    leading_roundtable = re.match(
        r"^roundtable\s+with\s+(?P<names>.+?)\s+on\s+(?P<topic>.+)$",
        question,
        flags=re.IGNORECASE,
    )
    if leading_roundtable:
        personas = _parse_persona_list(leading_roundtable.group("names"))
        topic = _clean_roundtable_topic(leading_roundtable.group("topic"))
        if len(personas) >= 2 and topic:
            return topic, ",".join(personas), True

    verbs = (
        " to roundtable about ",
        " to roundtable ",
        " to debate ",
        " debate ",
        " to discuss ",
        " discuss ",
        " roundtable about ",
        " roundtable ",
    )
    split_at = -1
    verb_used = ""
    for verb in verbs:
        idx = lowered.find(verb)
        if idx > 0:
            split_at = idx
            verb_used = verb
            break
    if split_at <= 0:
        return question, None, False

    names_text = question[:split_at].strip(" ,:;")
    topic = _clean_roundtable_topic(question[split_at + len(verb_used):])
    if names_text.lower().startswith(("ask ", "$ask ")):
        names_text = names_text.split(" ", 1)[1].strip()
    personas = _parse_persona_list(names_text)
    if len(personas) < 2 or not topic:
        return question, None, False
    if not all(_looks_like_persona_prefix(persona.split(":", 1)[0].strip()) for persona in personas):
        return question, None, False
    return topic, ",".join(personas), True


def _parse_natural_argue_query(question_parts: list[str]) -> tuple[str, str | None, bool]:
    """Parse two-sided argue syntax into topic, FOR/AGAINST personas, inferred flag."""
    question = _normalize_question_parts(question_parts)
    if not question:
        return question, None, False

    explicit_roles = re.match(
        r"^(?P<for_persona>.+?)\s+argue\s+for\s+and\s+(?P<against_persona>.+?)\s+argue\s+against\s+(?P<topic>.+)$",
        question,
        flags=re.IGNORECASE,
    )
    if explicit_roles:
        for_persona = explicit_roles.group("for_persona").strip(" ,:;")
        against_persona = explicit_roles.group("against_persona").strip(" ,:;")
        topic = _clean_roundtable_topic(explicit_roles.group("topic"))
        if (
            topic
            and _looks_like_persona_prefix(for_persona)
            and _looks_like_persona_prefix(against_persona)
        ):
            return topic, f"{for_persona}:for,{against_persona}:against", True

    paired_argue = re.match(
        r"^(?P<names>.+?)\s+(?:argue|argues)\s+(?:about|over|on)\s+(?P<topic>.+)$",
        question,
        flags=re.IGNORECASE,
    )
    if paired_argue:
        personas = _parse_persona_list(paired_argue.group("names"))
        topic = _clean_roundtable_topic(paired_argue.group("topic"))
        if (
            len(personas) == 2
            and topic
            and all(_looks_like_persona_prefix(persona.split(":", 1)[0].strip()) for persona in personas)
        ):
            return topic, f"{personas[0]}:for,{personas[1]}:against", True

    no_persona_patterns = [
        r"^(?:argue\s+)?for\s+and\s+against\s+(?P<topic>.+)$",
        r"^(?:show\s+)?both\s+sides\s+(?:of|on)\s+(?P<topic>.+)$",
        r"^devil'?s\s+advocate:?\s+(?P<topic>.+)$",
        r"^devil’s\s+advocate:?\s+(?P<topic>.+)$",
    ]
    for pattern in no_persona_patterns:
        match = re.match(pattern, question, flags=re.IGNORECASE)
        if match:
            topic = _clean_roundtable_topic(match.group("topic"))
            if topic:
                return topic, None, True

    lowered = question.lower()
    if "for and against" in lowered or "both sides" in lowered or "devil's advocate" in lowered:
        return question, None, True
    return question, None, False


def _parse_natural_parallel_review_query(question_parts: list[str]) -> tuple[str, bool, int | None, str | None]:
    """Parse human syntax like `run 3 parallel reviewers on this design`.

    Returns: question, inferred_parallel_review, reviewer_count, focus.
    """
    question = _normalize_question_parts(question_parts)
    if not question:
        return question, False, None, None

    patterns = [
        r"^(?:run|launch)\s+(?P<count>\d+|n)\s+parallel(?:\s+adversarial)?\s+reviewers?\s+on\s+(?P<topic>.+)$",
        r"^(?:run|launch)\s+(?P<count>\d+|n)\s+parallel\s+reviews?\s+on\s+(?P<topic>.+)$",
        r"^parallel\s+review\s+(?P<topic>.+?)(?:\s+with\s+(?P<focus>.+))?$",
        r"^parallel\s+reviewers?\s+on\s+(?P<topic>.+?)(?:\s+with\s+(?P<focus>.+))?$",
        r"^adversarially\s+review\s+(?P<topic>.+?)(?:\s+with\s+(?P<count>\d+)\s+independent\s+personas?)?$",
        r"^(?:run|launch)\s+(?P<count>\d+|n)\s+parallel\s+reviewers?\s+for\s+(?P<focus>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, question, flags=re.IGNORECASE)
        if not match:
            continue
        topic = (match.groupdict().get("topic") or question).strip(" ,:;")
        focus = _clean_parallel_focus(match.groupdict().get("focus"))
        count = _parse_reviewer_count(match.groupdict().get("count"))
        return topic, True, count, focus

    lowered = question.lower()
    if "parallel" in lowered and "review" in lowered:
        return question, True, None, None
    if "adversarial reviewers" in lowered or "adversarial review" in lowered:
        return question, True, None, None
    return question, False, None, None


def _parse_persona_peer_query(cleaned_parts: list[str], ask_index: int) -> tuple[str, str, str] | None:
    """Parse `Brandon ask Margaret ...` into primary persona, peer, and prompt."""
    persona = " ".join(cleaned_parts[:ask_index])
    max_peer_end = min(ask_index + 5, len(cleaned_parts))
    for peer_end in range(ask_index + 2, max_peer_end + 1):
        if peer_end >= len(cleaned_parts):
            continue
        peer = " ".join(cleaned_parts[ask_index + 1:peer_end])
        if not _looks_like_persona_prefix(peer):
            continue
        prompt = " ".join(cleaned_parts[peer_end:])
        if prompt:
            return prompt, persona, peer
    return None


def _parse_persona_list(value: str) -> list[str]:
    names_text = value.strip(" ,:;")
    for suffix in (" personas", " persona"):
        if names_text.lower().endswith(suffix):
            names_text = names_text[: -len(suffix)].strip(" ,:;")
            break
    names_text = names_text.replace(", and ", ",").replace(" and ", ",")
    return [part.strip() for part in names_text.split(",") if part.strip()]


def _clean_roundtable_topic(value: str) -> str:
    topic = value.strip(" ,:;")
    for prefix in ("about the topic:", "about topic:", "about:", "the topic:"):
        if topic.lower().startswith(prefix):
            return topic[len(prefix):].strip(" ,:;")
    return topic


def _parse_reviewer_count(value: str | None) -> int | None:
    if not value or value.lower() == "n":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _clean_parallel_focus(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip(" ,:;")
    cleaned = cleaned.replace(", and ", ",").replace(" and ", ",")
    cleaned = re.sub(r"\s*,\s*", ",", cleaned)
    return cleaned or None


def _looks_like_persona_prefix(value: str) -> bool:
    """Conservative natural persona detector."""
    words = value.split()
    if not words:
        return False
    first = words[0].lower()
    if first in QUESTION_STARTERS:
        return False
    known_aliases = {
        "brandon", "brandon bailey", "margaret", "margaret bailey",
        "jennifer", "jennifer cheung", "embry", "horus", "sapolsky", "barrett",
    }
    if value.lower() in known_aliases:
        return True
    return all(word[:1].isupper() for word in words)


def _should_auto_oracle_persona(question: str) -> bool:
    """Return True for broad analytical questions that benefit from a persona oracle."""
    q = question.lower().strip()
    broad_patterns = (
        "what is the state of ",
        "what's the state of ",
        "state of ",
        "where are we weak",
        "what are we missing",
        "how should we think about",
    )
    if any(pattern in q for pattern in broad_patterns):
        return True
    domain_terms = {"cybersecurity", "space-based", "space based", "satellite", "sparta", "qra"}
    analytical_terms = {"state", "strategy", "weak", "risk", "threat", "architecture", "roadmap"}
    return any(term in q for term in domain_terms) and any(term in q for term in analytical_terms)
