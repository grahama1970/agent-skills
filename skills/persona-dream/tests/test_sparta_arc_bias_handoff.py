"""Checks for the Persona Dream -> SPARTA arc-bias handoff validator."""
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


arc_bias = _load("session_arc_bias")
handoff = _load("validate_sparta_arc_bias_handoff")


def _artifact() -> dict:
    doc = {
        "schema": "persona_dream.session_arc_bias.v1",
        "created_at": "2026-07-29T13:23:39Z",
        "persona_id": "embry",
        "status": "PASS_SESSION_ARC_BIAS_PUBLISHED",
        "mocked": False,
        "live": False,
        "source": {
            "ledger_path": "skills/persona-dream/reports/goal_v5/continuity/embry.continuity_state.v1.json",
            "ledger_epoch": 2,
            "ledger_sha256": "sha256:" + "a" * 64,
            "identity_core_sha256": "b" * 64,
            "source_dream_cycle_id": "live_chain_unit",
            "source_journal_id": "journal_live_chain_unit",
            "arc_delta_id": "arc_1_unit",
            "arc_delta_idempotency_key": "dream_cycle:unit",
        },
        "bias": {
            "intensity_delta": 0.18,
            "valence_delta": -0.18,
            "bounds": {
                "intensity_delta": [0.0, 0.18],
                "valence_delta": [-0.18, 0.12],
            },
            "feature_counts": {"boundary": 4, "wanting": 1, "pressure": 3, "warmth": 3},
            "derivation": "deterministic lexical arc-bias v1; deltas only, no tone category",
        },
        "consumer_contract": {
            "tone_category_owner": "per_turn_intent_classifier",
            "emits_tone": False,
            "allowed_to_modify": ["intensity", "valence"],
            "must_not_modify": ["canonical_answer_text", "identity_core", "tone_category"],
            "neutral_fallback_rule": "if missing, record neutral fallback",
        },
        "claims": {
            "proves": [
                "Persona Dream publishes bounded numeric arc deltas with ledger provenance",
                "the artifact emits no tone category and cannot replace per-turn intent classification",
            ],
            "does_not_prove": [
                "production SPARTA consumption",
                "live Chatterbox rendering",
                "perceived emotion",
                "repeated pipeline reliability",
            ],
        },
    }
    doc["artifact_sha256"] = arc_bias.sha_obj({k: v for k, v in doc.items() if k != "artifact_sha256"})
    return doc


def _write_artifact(tmp_path: Path, doc: dict | None = None) -> Path:
    path = tmp_path / "session_arc_bias.v1.json"
    path.write_text(json.dumps(doc or _artifact(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_handoff_contract_passes_for_bounded_arc_bias(tmp_path):
    path = _write_artifact(tmp_path)

    receipt = handoff.write_handoff(path, tmp_path / "handoff")

    assert receipt["status"] == "PASS_SPARTA_ARC_BIAS_HANDOFF_RECEIPT"
    assert receipt["failed_gates"] == []
    assert receipt["contract"]["exists"] is True
    assert all(row["status"] == "PASS_NEGATIVE_BLOCKED" for row in receipt["negative_controls"])
    contract = json.loads((tmp_path / "handoff" / "SPARTA_CONSUMER_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["consumer_boundary"]["owner"] == "grahama1970/sparta"
    assert contract["composition_contract"]["input_from_persona_dream"]["emits_tone"] is False
    assert "SPARTA production conversation-service consumption" in contract["claims"]["does_not_prove"]


def test_artifact_that_emits_tone_blocks(tmp_path):
    doc = _artifact()
    doc["bias"]["tone"] = "firm_boundary"
    doc["artifact_sha256"] = arc_bias.sha_obj({k: v for k, v in doc.items() if k != "artifact_sha256"})
    path = _write_artifact(tmp_path, doc)

    receipt = handoff.write_handoff(path, tmp_path / "handoff")

    assert receipt["status"] == "BLOCKED_SPARTA_ARC_BIAS_HANDOFF_RECEIPT"
    assert "arc_bias_must_not_emit_tone" in receipt["failed_gates"]


def test_handoff_rejects_sparta_consumption_claim(tmp_path):
    doc = _artifact()
    doc["claims"]["proves"].append("production SPARTA consumption")
    doc["artifact_sha256"] = arc_bias.sha_obj({k: v for k, v in doc.items() if k != "artifact_sha256"})
    path = _write_artifact(tmp_path, doc)

    receipt = handoff.write_handoff(path, tmp_path / "handoff")

    assert receipt["status"] == "BLOCKED_SPARTA_ARC_BIAS_HANDOFF_RECEIPT"
    assert "claims_must_not_prove_sparta_consumption" in receipt["failed_gates"]


def test_expected_artifact_hash_mismatch_blocks(tmp_path):
    path = _write_artifact(tmp_path)

    receipt = handoff.write_handoff(path, tmp_path / "handoff", expected_artifact_sha256="sha256:" + "0" * 64)

    assert receipt["status"] == "BLOCKED_SPARTA_ARC_BIAS_HANDOFF_RECEIPT"
    assert "arc_bias_expected_sha256_mismatch" in receipt["failed_gates"]
