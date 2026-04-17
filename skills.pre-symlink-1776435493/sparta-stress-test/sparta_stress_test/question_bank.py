"""Question bank loader and sampler for SPARTA stress tests.

Loads questions from the static fixtures JSON file and provides
filtering by difficulty, persona, and expected action.
"""

import json
import random
from pathlib import Path
from typing import Optional

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DEFAULT_BANK = FIXTURES_DIR / "sparta_stress_test.json"

# SPARTA SV-* control ID pattern for generating flawed questions
VALID_SV_PREFIXES = [
    "SV-SP", "SV-AC", "SV-MA", "SV-IT", "SV-CF", "SV-AV",
]

DIFFICULTIES = ("simple", "medium", "complex", "ambiguous", "flawed")
EXPECTED_ACTIONS = {"simple": "QUERY", "medium": "QUERY", "complex": "QUERY",
                    "ambiguous": "CLARIFY", "flawed": "NO_MATCH"}


def load_bank(path: Optional[Path] = None) -> list[dict]:
    """Load the question bank from JSON.

    Each entry has:
        id, difficulty, persona, question, expected_action,
        target_control, expected_techniques, expected_countermeasures,
        grading_notes
    """
    bank_path = path or DEFAULT_BANK
    if not bank_path.exists():
        raise FileNotFoundError(
            f"Question bank not found: {bank_path}. "
            f"Run `./run.sh generate-bank` first."
        )
    with open(bank_path) as f:
        bank = json.load(f)
    return bank


def sample(
    bank: list[dict],
    count: int = 50,
    difficulty: Optional[str] = None,
    persona: Optional[str] = None,
    seed: Optional[int] = None,
) -> list[dict]:
    """Sample questions from the bank with optional filtering.

    Args:
        bank: Full question bank.
        count: Number of questions to return.
        difficulty: Filter by difficulty level (simple/medium/complex/ambiguous/flawed).
        persona: Filter by persona name.
        seed: Random seed for reproducibility.
    """
    filtered = bank

    if difficulty:
        filtered = [q for q in filtered if q.get("difficulty") == difficulty]
    if persona:
        filtered = [q for q in filtered if q.get("persona") == persona]

    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    if count >= len(filtered):
        result = list(filtered)
        rng.shuffle(result)
        return result

    return rng.sample(filtered, count)


def validate_bank(bank: list[dict]) -> list[str]:
    """Validate question bank schema. Returns list of errors (empty = valid)."""
    errors = []
    required_fields = {"id", "difficulty", "persona", "question", "expected_action"}
    seen_ids = set()

    for i, q in enumerate(bank):
        # Check required fields
        missing = required_fields - set(q.keys())
        if missing:
            errors.append(f"Question {i}: missing fields {missing}")

        # Check difficulty enum
        diff = q.get("difficulty", "")
        if diff not in DIFFICULTIES:
            errors.append(f"Question {i} ({q.get('id', '?')}): invalid difficulty '{diff}'")

        # Check expected_action matches difficulty convention
        expected = EXPECTED_ACTIONS.get(diff, "")
        actual = q.get("expected_action", "")
        if expected and actual != expected:
            errors.append(
                f"Question {i} ({q.get('id', '?')}): "
                f"difficulty '{diff}' expects action '{expected}' but got '{actual}'"
            )

        # Check unique IDs
        qid = q.get("id", "")
        if qid in seen_ids:
            errors.append(f"Question {i}: duplicate ID '{qid}'")
        seen_ids.add(qid)

    return errors


def validate_grounding(bank: list[dict]) -> dict:
    """Validate that QUERY questions have QRAs in the ArangoDB corpus.

    Returns:
        {"total_query": N, "grounded": N, "ungrounded": N,
         "ungrounded_controls": [...], "grounding_rate": float}
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

    try:
        from graph_memory.arango_client import get_db
        db = get_db()
        # Load controls with QRAs
        result = list(db.aql.execute(
            "FOR doc IN sparta_qra COLLECT ctrl = doc.control_id RETURN ctrl"
        ))
        qra_controls = set(r for r in result if r)
    except Exception:
        return {"error": "Could not connect to ArangoDB"}

    query_questions = [q for q in bank if q.get("expected_action") == "QUERY"]
    grounded = []
    ungrounded = []
    ungrounded_controls = set()

    for q in query_questions:
        target = q.get("target_control")
        if target and target in qra_controls:
            grounded.append(q)
        elif target:
            ungrounded.append(q)
            ungrounded_controls.add(target)
        else:
            # No target_control but expected QUERY — still OK if complex
            grounded.append(q)

    total = len(query_questions)
    return {
        "total_query": total,
        "grounded": len(grounded),
        "ungrounded": len(ungrounded),
        "ungrounded_controls": sorted(ungrounded_controls),
        "grounding_rate": len(grounded) / max(1, total),
    }


def bank_stats(bank: list[dict]) -> dict:
    """Return summary statistics of the question bank."""
    by_difficulty = {}
    by_persona = {}
    by_action = {}

    for q in bank:
        d = q.get("difficulty", "unknown")
        p = q.get("persona", "unknown")
        a = q.get("expected_action", "unknown")
        by_difficulty[d] = by_difficulty.get(d, 0) + 1
        by_persona[p] = by_persona.get(p, 0) + 1
        by_action[a] = by_action.get(a, 0) + 1

    return {
        "total": len(bank),
        "by_difficulty": by_difficulty,
        "by_persona": by_persona,
        "by_action": by_action,
    }
