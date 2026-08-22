from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "autonomous_dream_cycle.py"

spec = importlib.util.spec_from_file_location("autonomous_dream_cycle", SCRIPT)
adc = importlib.util.module_from_spec(spec)
sys.modules["autonomous_dream_cycle"] = adc
assert spec.loader is not None
spec.loader.exec_module(adc)


def test_recall_instrumentation_preserves_ranked_rows_and_negative_control_block() -> None:
    dream_key = "dream_auto_cycle_test"
    instruments = {
        "probes": ["friendship", "expense report", "private television habit"],
        "negative_control": "quantum tunneling effects in silicon transistors",
    }

    def recall_post(path: str, payload: dict) -> dict:
        assert path == "/recall"
        query = payload["q"]
        if query == "friendship":
            return {"items": [{"_key": "other"}, {"_key": dream_key, "retrieval_text": "dream text"}]}
        if query == "expense report":
            return {"items": [{"_key": "source"}]}
        if query == "private television habit":
            return {"items": [{"_key": dream_key, "score": 0.4, "tags": ["synthetic_dream"]}]}
        return {
            "items": [
                {"_key": "unrelated", "retrieval_text": "silicon device note"},
                {"_key": dream_key, "kind": "synthetic_dream_memory", "persona_id": "embry"},
            ]
        }

    result = adc.evaluate_recall_instruments(instruments, dream_key, recall_post=recall_post)

    assert result["recall_probe_ranks"] == {
        "probe_1": 2,
        "probe_2": None,
        "probe_3": 1,
    }
    assert result["negative_control_absent_top10"] is False
    assert result["negative_control_dream_rank"] == 2
    assert result["negative_control_results"][1]["_key"] == dream_key
    assert result["negative_control_results"][1]["rank"] == 2
    assert "text_sha256" in result["negative_control_results"][0]


def test_recall_instrumentation_passes_negative_control_when_dream_absent() -> None:
    instruments = {"probes": ["p1", "p2", "p3"], "negative_control": "deep sea basalt"}

    def recall_post(_path: str, payload: dict) -> dict:
        return {"items": [{"_key": f"row_{payload['q']}", "retrieval_text": payload["q"]}]}

    result = adc.evaluate_recall_instruments(instruments, "dream_absent", recall_post=recall_post)

    assert result["negative_control_absent_top10"] is True
    assert result["negative_control_dream_rank"] is None
    assert result["recall_probe_ranks"] == {
        "probe_1": None,
        "probe_2": None,
        "probe_3": None,
    }
