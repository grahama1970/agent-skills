#!/usr/bin/env python3
"""Validate the Persona Dream session-arc-bias handoff for SPARTA.

Persona Dream does not own the SPARTA conversation service. This validator
therefore proves only the handoff contract: the published artifact is bounded,
hash-bound, provenance-linked, and safe for SPARTA to compose as numeric deltas.
It must not claim production consumption.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_ARC_BIAS = ROOT / "reports/goal_v5/continuity/session_arc_bias/session_arc_bias.v1.json"
DEFAULT_OUT_DIR = ROOT / "reports/goal_v5/continuity/sparta_arc_bias_handoff"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_arc_bias = _load("session_arc_bias")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    return session_arc_bias.sha_file(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def recompute_artifact_sha(doc: dict[str, Any]) -> str:
    return session_arc_bias.sha_obj({k: v for k, v in doc.items() if k != "artifact_sha256"})


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def validate_arc_bias(doc: dict[str, Any], *, expected_sha256: str | None = None) -> list[str]:
    errors: list[str] = []
    if doc.get("schema") != "persona_dream.session_arc_bias.v1":
        errors.append("arc_bias_schema_invalid")
    if doc.get("status") != "PASS_SESSION_ARC_BIAS_PUBLISHED":
        errors.append("arc_bias_status_not_published")
    if doc.get("mocked") is not False:
        errors.append("arc_bias_mocked_not_false")
    if doc.get("live") is not False:
        errors.append("arc_bias_live_not_false")
    if doc.get("artifact_sha256") != recompute_artifact_sha(doc):
        errors.append("arc_bias_artifact_sha256_mismatch")
    if expected_sha256 and doc.get("artifact_sha256") != expected_sha256:
        errors.append("arc_bias_expected_sha256_mismatch")

    source = doc.get("source") if isinstance(doc.get("source"), dict) else {}
    for key in (
        "ledger_path",
        "ledger_epoch",
        "ledger_sha256",
        "identity_core_sha256",
        "source_dream_cycle_id",
        "source_journal_id",
        "arc_delta_id",
        "arc_delta_idempotency_key",
    ):
        if source.get(key) in (None, ""):
            errors.append(f"arc_bias_source_missing:{key}")
    if not str(source.get("source_dream_cycle_id") or "").startswith("live_chain_"):
        errors.append("arc_bias_source_not_live_chain")

    bias = doc.get("bias") if isinstance(doc.get("bias"), dict) else {}
    if "tone" in bias or "tone_category" in bias:
        errors.append("arc_bias_must_not_emit_tone")
    bounds = bias.get("bounds") if isinstance(bias.get("bounds"), dict) else {}
    for key in ("intensity_delta", "valence_delta"):
        value = bias.get(key)
        lo_hi = bounds.get(key)
        if not _is_number(value):
            errors.append(f"arc_bias_delta_not_numeric:{key}")
            continue
        if not (isinstance(lo_hi, list) and len(lo_hi) == 2 and all(_is_number(item) for item in lo_hi)):
            errors.append(f"arc_bias_bounds_missing:{key}")
            continue
        if not (float(lo_hi[0]) <= float(value) <= float(lo_hi[1])):
            errors.append(f"arc_bias_delta_out_of_bounds:{key}")

    contract = doc.get("consumer_contract") if isinstance(doc.get("consumer_contract"), dict) else {}
    if contract.get("emits_tone") is not False:
        errors.append("consumer_contract_emits_tone_not_false")
    allowed = set(contract.get("allowed_to_modify") or [])
    if allowed != {"intensity", "valence"}:
        errors.append("consumer_contract_allowed_fields_invalid")
    forbidden = set(contract.get("must_not_modify") or [])
    for required in ("canonical_answer_text", "identity_core", "tone_category"):
        if required not in forbidden:
            errors.append(f"consumer_contract_missing_forbidden:{required}")
    proves = set(((doc.get("claims") or {}).get("proves")) or [])
    if any("production SPARTA consumption" in item for item in proves):
        errors.append("claims_must_not_prove_sparta_consumption")
    does_not_prove = set(((doc.get("claims") or {}).get("does_not_prove")) or [])
    if "production SPARTA consumption" not in does_not_prove:
        errors.append("claims_missing_sparta_consumption_boundary")
    return errors


def build_contract(arc_bias_path: Path, doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "persona_dream.sparta_arc_bias_handoff.v1",
        "created_at": utc_now(),
        "status": "PASS_SPARTA_ARC_BIAS_HANDOFF_READY",
        "mocked": False,
        "live": False,
        "source_artifact": {
            "path": rel(arc_bias_path),
            "file_sha256": sha_file(arc_bias_path),
            "artifact_sha256": doc["artifact_sha256"],
            "schema": doc["schema"],
            "status": doc["status"],
            "persona_id": doc["persona_id"],
            "source": doc["source"],
        },
        "consumer_boundary": {
            "owner": "grahama1970/sparta",
            "owned_surface": "production conversation service session/turn state and per-turn tone composition",
            "persona_dream_role": "publish bounded arc-bias deltas with provenance; do not classify per-turn tone",
            "sparta_receipt_required_before_goal_credit": True,
        },
        "composition_contract": {
            "input_from_sparta": {
                "per_turn_tone_category": "required; produced by SPARTA or Memory intent classifier",
                "per_turn_intensity": "required numeric base before slow arc bias",
                "per_turn_valence": "required numeric base before slow arc bias",
                "canonical_answer_text": "required; must be preserved byte-for-byte before voice rendering",
            },
            "input_from_persona_dream": {
                "intensity_delta": doc["bias"]["intensity_delta"],
                "valence_delta": doc["bias"]["valence_delta"],
                "emits_tone": False,
            },
            "allowed_output_change": [
                "voice_delivery.intensity",
                "voice_delivery.valence",
            ],
            "forbidden_output_change": [
                "canonical_answer_text",
                "voice_delivery.tone",
                "identity_core",
            ],
            "neutral_fallback": "If this artifact is absent, stale, blocked, or hash-mismatched, SPARTA must record no_arc_bias_applied and continue with per-turn tone only.",
        },
        "required_sparta_receipt_fields": [
            "schema",
            "status",
            "mocked",
            "live",
            "session_id",
            "turn_ids",
            "arc_bias_artifact_path",
            "arc_bias_artifact_sha256",
            "arc_bias_file_sha256",
            "arc_bias_applied_before_first_turn",
            "same_arc_bias_artifact_all_turns",
            "canonical_answer_text_sha256_before",
            "canonical_answer_text_sha256_after",
            "answer_text_unchanged",
            "tone_category_source",
            "tone_category_unchanged_by_arc_bias",
            "voice_delivery_before_arc_bias",
            "voice_delivery_after_arc_bias",
            "neutral_fallback_checked",
            "claims",
        ],
        "claims": {
            "proves": [
                "Persona Dream has published a machine-checkable SPARTA consumer contract for the current session_arc_bias artifact",
                "the handoff artifact is bounded to numeric intensity/valence deltas and cannot replace SPARTA per-turn tone classification",
            ],
            "does_not_prove": [
                "SPARTA production conversation-service consumption",
                "human-perceived emotion",
                "human listener recognition of Embry",
                "a closed immutable Persona Dream goal",
            ],
        },
    }


def negative_controls(doc: dict[str, Any], artifact_sha: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def expect(name: str, mutated: dict[str, Any], token: str, *, expected_sha256: str | None = None) -> None:
        errors = validate_arc_bias(mutated, expected_sha256=expected_sha256)
        rows.append({
            "name": name,
            "status": "PASS_NEGATIVE_BLOCKED" if token in errors else "FAIL_NEGATIVE_ALLOWED",
            "expected_token": token,
            "errors": errors,
        })

    emits_tone = deepcopy(doc)
    emits_tone["bias"]["tone"] = "firm_boundary"
    expect("arc_bias_emits_tone_blocks", emits_tone, "arc_bias_must_not_emit_tone")

    allows_answer_edit = deepcopy(doc)
    allows_answer_edit["consumer_contract"]["allowed_to_modify"].append("canonical_answer_text")
    expect("answer_text_modification_contract_blocks", allows_answer_edit, "consumer_contract_allowed_fields_invalid")

    missing_source = deepcopy(doc)
    missing_source["source"]["ledger_sha256"] = ""
    expect("missing_ledger_source_blocks", missing_source, "arc_bias_source_missing:ledger_sha256")

    out_of_bounds = deepcopy(doc)
    out_of_bounds["bias"]["intensity_delta"] = 1.0
    expect("out_of_bounds_delta_blocks", out_of_bounds, "arc_bias_delta_out_of_bounds:intensity_delta")

    claims_consumption = deepcopy(doc)
    claims_consumption["claims"]["proves"].append("production SPARTA consumption")
    expect("production_consumption_claim_blocks", claims_consumption, "claims_must_not_prove_sparta_consumption")

    stale_hash = deepcopy(doc)
    expect("stale_expected_artifact_hash_blocks", stale_hash, "arc_bias_expected_sha256_mismatch", expected_sha256="sha256:" + "0" * 64)

    tampered = deepcopy(doc)
    tampered["bias"]["valence_delta"] = 0.99
    tampered["artifact_sha256"] = artifact_sha
    expect("tampered_artifact_hash_blocks", tampered, "arc_bias_artifact_sha256_mismatch")

    return rows


def write_handoff(arc_bias_path: Path, out_dir: Path, expected_artifact_sha256: str | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    failed_gates: list[str] = []
    if not arc_bias_path.is_file():
        failed_gates.append("arc_bias_artifact_missing")
        doc: dict[str, Any] = {}
    else:
        doc = load_json(arc_bias_path)
        failed_gates.extend(validate_arc_bias(doc, expected_sha256=expected_artifact_sha256))

    negatives = negative_controls(doc, doc.get("artifact_sha256", "")) if not failed_gates else []
    if any(row["status"] != "PASS_NEGATIVE_BLOCKED" for row in negatives):
        failed_gates.append("negative_controls_failed")

    contract = build_contract(arc_bias_path, doc) if not failed_gates else {
        "schema": "persona_dream.sparta_arc_bias_handoff.v1",
        "created_at": utc_now(),
        "status": "BLOCKED_SPARTA_ARC_BIAS_HANDOFF",
        "mocked": False,
        "live": False,
        "source_artifact": artifact(arc_bias_path),
        "failed_gates": failed_gates,
    }
    contract_path = out_dir / "SPARTA_CONSUMER_CONTRACT.json"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "schema": "persona_dream.sparta_arc_bias_handoff_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_SPARTA_ARC_BIAS_HANDOFF_RECEIPT" if not failed_gates else "BLOCKED_SPARTA_ARC_BIAS_HANDOFF_RECEIPT",
        "mocked": False,
        "live": False,
        "arc_bias_artifact": artifact(arc_bias_path),
        "contract": artifact(contract_path),
        "failed_gates": failed_gates,
        "negative_controls": negatives,
        "claims": contract.get("claims", {
            "proves": [],
            "does_not_prove": ["SPARTA production conversation-service consumption"],
        }),
    }
    receipt_path = out_dir / "RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "SHA256SUMS.txt").write_text(
        f"{sha_file(contract_path).removeprefix('sha256:')}  {contract_path.name}\n"
        f"{sha_file(receipt_path).removeprefix('sha256:')}  {receipt_path.name}\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arc-bias", type=Path, default=DEFAULT_ARC_BIAS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--expected-artifact-sha256")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = write_handoff(args.arc_bias, args.out_dir, args.expected_artifact_sha256)
    summary = {
        "status": receipt["status"],
        "receipt": rel(args.out_dir / "RECEIPT.json"),
        "contract": rel(args.out_dir / "SPARTA_CONSUMER_CONTRACT.json"),
        "failed_gates": receipt["failed_gates"],
        "negative_controls": {
            "passed": sum(1 for row in receipt["negative_controls"] if row["status"] == "PASS_NEGATIVE_BLOCKED"),
            "total": len(receipt["negative_controls"]),
        },
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS_SPARTA_ARC_BIAS_HANDOFF_RECEIPT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
