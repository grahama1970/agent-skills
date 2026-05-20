"""Local relevance heuristics for ask retrieval results."""


from .env import load_dotenv_once

load_dotenv_once()
import json
import os
import subprocess
from pathlib import Path

from loguru import logger as log

from .ask_routing import QUESTION_STARTERS

def _has_relevant_domain_items(domain_items: list[dict], question: str) -> bool:
    """Check if domain items are actually relevant to the question.

    BM25 matches keywords but doesn't guarantee topical relevance — "extraction"
    in a spacecraft QRA is not the same as "extraction" in a pipeline question.
    We check that at least one item contains multiple key terms from the query.
    """
    if not domain_items:
        return False

    # Extract significant terms without maintaining a Python stopword list.
    terms = [
        word.lower().rstrip("?.,!")
        for word in question.split()
        if len(word) > 3 and word.lower().rstrip("?.,!") not in QUESTION_STARTERS
    ]

    if not terms:
        return len(domain_items) > 0  # Can't filter, assume relevant

    # An item is relevant if it contains at least 2 key terms (or 1 if query has few terms)
    min_matches = min(2, len(terms))

    for item in domain_items[:10]:
        text = " ".join(
            str(item.get(field) or "")
            for field in ("solution", "text", "problem", "reasoning", "answer", "question")
        ).lower()
        matches = sum(1 for t in terms if t in text)
        if matches >= min_matches:
            return True

    return False


def _try_evidence_case(question: str, scope: str) -> dict | None:
    """Try to build a structured evidence case for a non-trivial question.

    Calls /create-evidence-case as a subprocess. Returns the evidence case
    dict on success, None on failure (skill unavailable, timeout, etc.).

    This is the global default behavior when /memory recall returns found=false
    and the question is analytical/reasoning (not a direct control lookup).
    """
    skills_dir = Path(__file__).resolve().parents[3]
    evidence_skill = skills_dir / "create-evidence-case" / "run.sh"

    if not evidence_skill.exists():
        log.debug("create-evidence-case skill not installed — skipping evidence fallback")
        return None

    log.info("Building evidence case for: %s", question[:80])
    print(f"\n  No direct knowledge found. Building evidence case...")
    print(f"  (query: {question[:60]})")

    try:
        proc = subprocess.run(
            [str(evidence_skill), "create", question, "--quiet", "--json"],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if proc.returncode != 0:
            log.warning("evidence case failed: rc=%d", proc.returncode)
            return None

        stdout = proc.stdout.strip()
        idx = stdout.find("{")
        if idx < 0:
            return None

        case = json.loads(stdout[idx:])
        verdict = case.get("verdict", {})
        log.info(
            "Evidence case %s: %s (grade=%s, score=%.3f)",
            case.get("claim", {}).get("id", "?"),
            verdict.get("state", "?"),
            verdict.get("grade", "?"),
            verdict.get("score", 0),
        )
        return case

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        log.warning("evidence case subprocess failed: %s", exc)
        return None
