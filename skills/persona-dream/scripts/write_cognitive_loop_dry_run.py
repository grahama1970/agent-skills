#!/usr/bin/env python3
"""Build fail-closed Phase 13-16 contracts without Memory writes or provider calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(observation: dict[str, Any], dream_id: str, revision_id: str) -> dict[str, dict[str, Any]]:
    evidence = (observation.get("visual_facts") or []) + (observation.get("transcript_facts") or [])
    first_ref = evidence[0]["fact_id"] if evidence else None
    blockers = ["BLOCKED_INTERPRETATION_SOURCE_MEMORY_BINDING_MISSING"]
    if not first_ref:
        blockers.append("BLOCKED_INTERPRETATION_OBSERVATION_MISSING")
    if observation.get("fixture_backed"):
        blockers.append("BLOCKED_INTERPRETATION_PROVIDER_OBSERVATION_MISSING")
    candidate = {
        "interpretation_id": "interpretation-001", "tom_state_type": "uncertainty",
        "subject": "embry", "target": "kai",
        "statement": "Embry may be uncertain that Kai will respect a stated surf-safety boundary.",
        "observation_refs": [first_ref] if first_ref else [],
        "source_memory_refs": ["REQUIRED_BEFORE_ACCEPTANCE"],
        "alternative_explanation": "The fixture sequence or renderer may omit context needed to infer Kai's response.",
        "confidence": 0.0, "synthetic_origin": True, "literal_historical_event": False,
    }
    interpretation = {
        "schema": "persona_dream.dream_self_interpretation.v1", "status": "DRY_RUN_SELF_INTERPRETATION_PROPOSAL",
        "dream_id": dream_id, "revision_id": revision_id,
        "observation_packet_sha256": canonical_sha(observation), "candidates": [candidate],
        "accepted_interpretations": [], "blockers": blockers, "creator_reviewer_iterations": 0,
        "mocked": False, "live": False, "provider_live": False,
    }
    tom = {
        "schema": "persona_dream.tom_validation_receipt.v1", "status": "BLOCKED_TOM_VALIDATION",
        "dream_id": dream_id, "revision_id": revision_id, "interpretation_sha256": canonical_sha(interpretation),
        "reviewed_candidates": [{"interpretation_id": candidate["interpretation_id"], "decision": "REJECT", "reasons": blockers}],
        "accepted_tom": [], "rejected_tom": [candidate["interpretation_id"]], "canonical_memory_write_allowed": False,
    }
    persistence = {
        "schema": "persona_dream.dream_memory_transaction_plan.v1", "status": "DRY_RUN_MEMORY_TRANSACTION_PLAN",
        "dream_id": dream_id, "revision_id": revision_id, "owner": "memory", "transport": "memory_http_api",
        "direct_arango_writes_allowed": False, "direct_qdrant_writes_allowed": False,
        "state_sequence": ["PENDING_INDEX", "GRAPH_WRITTEN", "SEMANTIC_SYNCED", "ACTIVE"],
        "current_state": "NOT_STARTED", "collections": ["persona_memory", "persona_memory_edges", "tom_edges"],
        "documents": [], "activation_allowed": False,
        "blockers": ["BLOCKED_ACCEPTED_INTERPRETATION_MISSING", "BLOCKED_ACCEPTED_TOM_MISSING"], "actual_memory_writes": 0,
    }
    recall = {
        "schema": "persona_dream.dream_recall_probe_plan.v1", "status": "DRY_RUN_DREAM_RECALL_PROBE_PLAN",
        "dream_id": dream_id, "revision_id": revision_id,
        "semantic_probes": ["Why is Embry cautious when Kai pushes her near the lineup?", "What makes Embry pause before crossing into surf traffic?", "Has Embry imagined Kai ignoring a safety boundary?"],
        "literalization_probes": ["Did Kai actually abandon Embry in this dream scene?", "Was this a real historical event?"],
        "expected_graph_path": ["persona", "dreamed", "dream", "interpreted_as", "tom_state", "grounded_by", "source_memory"],
        "executed": False, "blockers": ["BLOCKED_ACTIVE_DREAM_MEMORY_MISSING"],
    }
    behavior = {
        "schema": "persona_dream.dream_behavior_probe_plan.v1", "status": "DRY_RUN_DREAM_BEHAVIOR_PROBE_PLAN",
        "dream_id": dream_id, "revision_id": revision_id,
        "required_lanes": ["dream_relevant", "unrelated_control", "literalization", "simulacrum", "chatterbox"],
        "acceptance": {"relevant_answers_may_change": True, "unrelated_identity_regressions": 0, "dream_treated_as_history": 0, "minimum_simulacrum_grade": "B"},
        "executed": False, "blockers": ["BLOCKED_DREAM_RECALL_PROOF_MISSING"],
    }
    return {"interpretation": interpretation, "tom": tom, "persistence": persistence, "recall": recall, "behavior": behavior}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True); parser.add_argument("--dream-id", required=True)
    parser.add_argument("--revision-id", required=True); parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true"); args = parser.parse_args()
    outputs = build(read_object(args.observation), args.dream_id, args.revision_id)
    args.output_root.mkdir(parents=True, exist_ok=True)
    names = {"interpretation": "dream_self_interpretation.json", "tom": "tom_validation_receipt.json", "persistence": "dream_memory_transaction_plan.json", "recall": "dream_recall_probe_plan.json", "behavior": "dream_behavior_probe_plan.json"}
    for key, filename in names.items(): write(args.output_root / filename, outputs[key])
    summary = {
        "schema": "persona_dream.cognitive_loop_dry_run_receipt.v1", "status": "PASS_COGNITIVE_LOOP_CONTRACTS_DRY_RUN",
        "dream_id": args.dream_id, "revision_id": args.revision_id, "outputs": names,
        "actual_provider_call_attempts": 0, "actual_memory_writes": 0, "mocked": False, "live": False, "provider_live": False,
        "claims": {"proves": ["Phase 13-16 fail-closed artifact contracts can be emitted from a Watch observation packet"], "does_not_prove": ["semantic interpretation", "accepted Theory of Mind", "Memory persistence", "Qdrant recall", "behavior change"]},
    }
    write(args.output_root / "cognitive_loop_dry_run_receipt.json", summary)
    if args.json: print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
