"""Deterministic tests for the soak35 source/transition preflight."""
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


preflight = _load("validate_soak35_preflight")
reliability = _load("live_chain_reliability")


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_default_soak35(tmp_path: Path) -> Path:
    root = tmp_path / "soak35"
    preflight.write_default_artifacts(root)
    return root


def test_soak35_default_preflight_reports_required_counts(tmp_path):
    root = _copy_default_soak35(tmp_path)

    receipt = preflight.validate_preflight(
        root / "SOURCE_DIVERSITY_MANIFEST.json",
        root / "TRANSITION_POLICY.json",
        root / "PREFLIGHT_RECEIPT.json",
    )

    assert receipt["status"] == "PASS_SOAK35_PREFLIGHT"
    assert receipt["counts"]["planned_cycles"] == 35
    assert receipt["counts"]["unique_source_lineage_groups"] == 8
    assert receipt["counts"]["unique_normalized_transition_fingerprints"] >= 8
    assert receipt["counts"]["valid_no_op_count"] == 4
    assert receipt["counts"]["expected_block_count"] == 2
    assert receipt["counts"]["repeated_control_count"] == 2
    assert receipt["counts"]["canonical_write_attempts"] == 0
    assert receipt["counts"]["provider_calls"] == 0
    assert {row["status"] for row in receipt["negative_controls"]} == {"PASS_NEGATIVE_CONTROL"}


def test_soak35_recomputes_transition_fingerprints(tmp_path):
    root = _copy_default_soak35(tmp_path)
    manifest_path = root / "SOURCE_DIVERSITY_MANIFEST.json"
    manifest = preflight.load_json(manifest_path)
    manifest["planned_cycles"][0]["pre_state_hash"] = preflight.stable_hash("tampered-pre-state")
    manifest["frozen_manifest_sha256"] = preflight.manifest_freeze_sha(manifest)
    _write_json(manifest_path, manifest)

    try:
        preflight.validate_preflight(manifest_path, root / "TRANSITION_POLICY.json", root / "PREFLIGHT_RECEIPT.json")
    except preflight.PreflightError as exc:
        assert exc.reason == "DECLARED_FINGERPRINT_MISMATCH"
    else:
        raise AssertionError("tampered manifest should fail closed")


def test_soak35_repeated_control_cannot_write_state(tmp_path):
    root = _copy_default_soak35(tmp_path)
    policy = preflight.load_json(root / "TRANSITION_POLICY.json")
    manifest = preflight.load_json(root / "SOURCE_DIVERSITY_MANIFEST.json")
    control = preflight.mutated_manifest(manifest, policy, "repeated_control_writes_state")
    control_path = tmp_path / "control.json"
    _write_json(control_path, control)

    try:
        preflight.classify_rows(preflight.load_json(control_path), policy)
    except preflight.PreflightError as exc:
        assert exc.reason == "REPEATED_RENDER_CONTROL_WRITES_STATE"
    else:
        raise AssertionError("state-writing repeated control should fail closed")


def test_live_chain_aggregate_consumes_preflight_receipt(tmp_path, monkeypatch):
    root = _copy_default_soak35(tmp_path)
    receipt_path = root / "PREFLIGHT_RECEIPT.json"
    preflight_receipt = preflight.validate_preflight_receipt(receipt_path)
    monkeypatch.setattr(reliability, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(preflight, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reliability.validate_soak35_preflight, "REPO_ROOT", tmp_path)

    cycle_dir = tmp_path / "campaign" / "cycle_001"
    cycle_dir.mkdir(parents=True)
    cycle_receipt = {
        "schema": "persona_dream.live_chain_receipt.v1",
        "cycle_index": 1,
        "dream_cycle_id": "unit-cycle-001",
        "status": "PASS_PERSONA_DREAM_LIVE_CHAIN",
        "stages": [{"name": "session_mood_live_chatterbox", "status": "PASS_SESSION_MOOD_CHATTERBOX_LIVE", "turns": []}],
        "reliability_cycle": {
            "elapsed_seconds": 1.0,
            "input_manifest_sha256": "sha256:" + "1" * 64,
            "accepted_effect_counts": {"duplicate_accepted_effect_count": 0},
        },
    }
    _write_json(cycle_dir / "RECEIPT.json", cycle_receipt)
    _write_json(root / "PREFLIGHT_RECEIPT.json", preflight_receipt)

    doc = reliability.aggregate(
        [cycle_receipt],
        tmp_path / "campaign",
        campaign_id="unit",
        preflight_receipt={
            "status": preflight_receipt["status"],
            "receipt": str(receipt_path.relative_to(tmp_path)),
            "manifest": preflight_receipt["manifest"],
            "manifest_sha256": preflight_receipt["manifest_sha256"],
            "policy": preflight_receipt["policy"],
            "policy_sha256": preflight_receipt["policy_sha256"],
            "counts": preflight_receipt["counts"],
            "claims": preflight_receipt["claims"],
        },
    )

    assert doc["status"] == "PASS_LIVE_CHAIN_RELIABILITY_PILOT"
    assert doc["source_transition_preflight"]["status"] == "PASS_SOAK35_PREFLIGHT"
    assert doc["source_transition_preflight"]["counts"]["planned_cycles"] == 35
