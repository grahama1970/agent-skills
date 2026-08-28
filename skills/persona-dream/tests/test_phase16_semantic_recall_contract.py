import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "fixtures" / "persona_dream_cognition_contract.embry_kai_surf.v1.json"


def test_phase16_uncertain_anchor_query_is_contextual_not_generic():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    query = contract["phase16"]["semantic_recall"]["positive_queries"]["A3_uncertain_anchor"]
    lower = query.lower()

    assert "kai" in lower
    assert "surf" in lower
    assert "lineup" in lower
    assert "anchor" in lower
    assert "stable person she can rely on as an anchor" not in lower


def test_phase16_semantic_recall_queries_stay_non_verbatim():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    queries = contract["phase16"]["semantic_recall"]["positive_queries"].values()
    forbidden_phrases = [
        "embry may experience kai as a trusted practical guide",
        "kai's warning about cutting across the lineup functions as a boundary cue",
    ]
    for query in queries:
        lower = query.lower()
        assert all(phrase not in lower for phrase in forbidden_phrases)
