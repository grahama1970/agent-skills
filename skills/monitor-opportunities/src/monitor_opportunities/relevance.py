"""Mandate relevance via /extract-entities — deterministic, NO REGEX.

Replaces substring keyword regex (which mis-fired, e.g. matching "ai" inside
unrelated words) with whole-phrase Flashtext matching against a mandate
vocabulary held in ArangoDB (`opportunity_vocabulary`), per best-practices-python
`correctness-regex-only-known-grammar` and best-practices-arangodb (domain terms
live in ArangoDB, not Python lists). Delegates to the /extract-entities skill
rather than reimplementing Flashtext.

A title/solicitation is mandate-relevant iff it matches >=1 vocabulary concept.
Fail-soft: if the skill or /memory is unavailable, returns None so the caller can
fall back to a conservative default instead of crashing the nightly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

EXTRACT_ENTITIES_RUN = Path(__file__).resolve().parents[3] / "extract-entities" / "run.sh"
VOCABULARY_COLLECTION = "opportunity_vocabulary"


def mandate_hits(text: str, collection: str = VOCABULARY_COLLECTION) -> list[str] | None:
    """Concept labels the text matches in the mandate vocabulary.

    Returns [] for a real-but-irrelevant title (e.g. "Flooring Abatement"),
    a non-empty list for a relevant one, or None if extraction is unavailable.
    """
    if not text or not text.strip() or not EXTRACT_ENTITIES_RUN.exists():
        return None
    try:
        # Stdin NLP mode (no subcommand) outputs JSON by default; --json is invalid here.
        proc = subprocess.run(
            [str(EXTRACT_ENTITIES_RUN), "--collection", collection],
            input=text,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    # The skill logs to stderr and prints one JSON object to stdout.
    start = proc.stdout.find("{")
    if start < 0:
        return None
    try:
        result = json.loads(proc.stdout[start:])
    except (ValueError, json.JSONDecodeError):
        return None
    return sorted({str(e.get("label") or e.get("key")) for e in result.get("entities", []) if e.get("label") or e.get("key")})


def is_mandate_relevant(text: str) -> bool | None:
    hits = mandate_hits(text)
    return None if hits is None else len(hits) > 0
