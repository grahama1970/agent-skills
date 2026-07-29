"""Unit checks for the live-chain reliability campaign wrapper."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reliability = _load("live_chain_reliability")


def _write_cycle(root: Path, index: int, status: str = "PASS_PERSONA_DREAM_LIVE_CHAIN") -> dict:
    cycle_dir = root / f"cycle_{index:03d}"
    cycle_dir.mkdir(parents=True)
    receipt = {
        "schema": "persona_dream.live_chain_receipt.v1",
        "cycle_index": index,
        "dream_cycle_id": f"live_chain_reliability_unit_cycle_{index:03d}",
        "status": status,
        "stages": [
            {"name": "accepted_synthetic_dream_memory", "status": "PASS"},
            {"name": "session_mood_live_chatterbox", "status": "PASS_SESSION_MOOD_CHATTERBOX_LIVE"},
        ],
        "reliability_cycle": {
            "elapsed_seconds": 1.25,
            "input_manifest_sha256": f"sha256:{index:064x}",
            "accepted_effect_counts": {
                "known_accepted_effect_count": 3,
                "duplicate_accepted_effect_count": 0,
            },
            "first_divergent_gate": None,
            "services_before": {"memory": {"available": True}},
            "services_after": {"memory": {"available": True}},
        },
    }
    (cycle_dir / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def test_aggregate_binds_cycle_receipts_and_reports_wilson_interval(tmp_path):
    receipts = [_write_cycle(tmp_path, idx) for idx in range(1, 6)]

    doc = reliability.aggregate(receipts, tmp_path, campaign_id="unit")

    assert doc["status"] == "PASS_LIVE_CHAIN_RELIABILITY_PILOT"
    assert doc["counts"]["attempted"] == 5
    assert doc["counts"]["passed"] == 5
    assert len(doc["cycles"]) == 5
    assert doc["success_interval"]["method"].startswith("Wilson")
    for row in doc["cycles"]:
        assert (reliability.REPO_ROOT / row["receipt"]).is_file()
        assert row["receipt_sha256"].startswith("sha256:")


def test_validate_aggregate_fails_closed_on_hash_mismatch(tmp_path):
    receipts = [_write_cycle(tmp_path, idx) for idx in range(1, 3)]
    doc = reliability.aggregate(receipts, tmp_path, campaign_id="unit")
    doc["cycles"][0]["receipt_sha256"] = "sha256:" + "0" * 64
    aggregate_path = tmp_path / "AGGREGATE_RECEIPT.json"
    aggregate_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    checked = reliability.validate_aggregate(aggregate_path)

    assert checked["status"] == "BLOCKED_LIVE_CHAIN_RELIABILITY_PILOT"
    assert "cycle_receipt_hash_mismatch:" + doc["cycles"][0]["receipt"] in checked["validation_failures"]


def test_terminal_cycle_receipt_preserves_classified_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        reliability,
        "accepted_effect_counts",
        lambda cycle_id: {
            "exact_key_counts": {},
            "known_accepted_effect_count": 0,
            "duplicate_accepted_effect_count": 0,
        },
    )

    receipt = reliability.terminal_cycle_receipt(
        cycle_index=1,
        cycle_id="live_chain_reliability_unit_cycle_001",
        cycle_dir=tmp_path / "cycle_001",
        status="BLOCKED_LIVE_CHAIN_CYCLE",
        started_at="2026-07-29T00:00:00Z",
        ended_at="2026-07-29T00:00:01Z",
        elapsed_seconds=1.0,
        input_manifest={"manifest_sha256": "sha256:" + "1" * 64},
        services_before={"memory": {"available": True}},
        blocked_reason="BLOCKED_RECOGNITION_RECEIPT_FAILED",
        failure_signature="BLOCKED_RECOGNITION",
    )

    assert receipt["status"] == "BLOCKED_LIVE_CHAIN_CYCLE"
    assert receipt["first_divergent_gate"]["stage"] == "BLOCKED_RECOGNITION"
    assert (tmp_path / "cycle_001" / "RECEIPT.json").is_file()
