#!/usr/bin/env python3
"""Cognitive loop runner - chains Phase 12 -> 13 -> 14 -> 15 from a Watch
observation packet and emits a loop receipt naming each phase's status and
artifacts.

Phase 12 (Watch perception) is already proven; its output is the observation
packet passed in. This runner consumes that packet, runs self-interpretation
(13, live gpt-5.5), ToM validation (14, live gpt-5.5), and persistence (15,
dry-run plan plus an optional real write into a non-canonical validation
collection). It NEVER writes the superseded historical return into canonical
dream memory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, _HERE / f"{mod_name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p13 = _load("phase13_self_interpretation")
p14 = _load("phase14_tom_validation")
p15 = _load("phase15_dream_persistence")
guards = _load("cognitive_loop_transitions")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoopBlocked(Exception):
    """Raised when a transition guard blocks the loop before the next side effect."""

    def __init__(self, transition, receipt: dict[str, Any]):
        self.transition = transition
        self.receipt = receipt
        super().__init__(f"LOOP_BLOCKED: {transition.from_state}->{transition.to_state}")


def run_loop(
    observation_path: Path,
    residue_path: Path,
    story_contract: Path | None,
    script_contract: Path | None,
    output_root: Path,
    dream_id: str,
    revision_id: str,
    run_id: str,
    persona_id: str,
    live: bool,
    validation_collection: str | None,
    allow_canonical_write: bool = False,
    return_id: str | None = None,
    acceptance_receipt_path: Path | None = None,
    superseded_return_ids: set[str] | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    phases: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []

    def _emit_blocked(status_code: str) -> dict[str, Any]:
        """Write a fail-closed receipt and return it (nonzero at the CLI)."""
        rec = {
            "schema": "persona_dream.cognitive_loop_receipt.v1",
            "status": status_code,
            "dream_id": dream_id,
            "revision_id": revision_id,
            "run_id": run_id,
            "persona_id": persona_id,
            "live": live,
            "phases": phases,
            "transitions": transitions,
            "canonical_dream_memory_written": False,
            "generated_at": utc_now(),
        }
        p13.write_json(output_root / "cognitive_loop_receipt.json", rec)
        return rec

    # Phase 12 - already-produced Watch observation packet.
    packet = p13.read_json(observation_path)
    observation_sha = p13.canonical_sha(packet)
    acceptance_receipt = (
        p13.read_json(acceptance_receipt_path) if acceptance_receipt_path else None
    )
    acceptance_certifies, _ar = p15.acceptance_receipt_certifies(
        acceptance_receipt, packet, return_id
    )
    # Hard, non-overridable blockers (historical origin / renderer DEFECT verdict /
    # superseded id) come straight from phase15's pure decision.
    _allowed, decision_blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=return_id or "probe",
        superseded_return_ids=superseded_return_ids, acceptance_receipt=acceptance_receipt,
    )
    hard_blocks = [
        b for b in decision_blockers
        if b in {"RETURN_IS_HISTORICAL_PROVIDER_RETURN", "RETURN_ID_SUPERSEDED"}
        or b.startswith("IDENTITY_CONTINUITY_DEFECT")
    ]
    phases.append({
        "phase": "12_watch_observation",
        "status": packet.get("status", "UNKNOWN"),
        "role": "input",
        "artifacts": [str(observation_path)],
        "observation_packet_sha256": p13.file_sha(observation_path),
        "observation_packet_content_sha256": observation_sha,
        "evidence_origin": packet.get("evidence_origin"),
    })

    # GUARD 1: START -> ACCEPTED_OBSERVATION (before any interpretation side effect).
    t_obs = guards.guard_observation_accepted(
        packet, return_id=return_id, acceptance_certifies=acceptance_certifies,
        canonical_write_hard_blocks=hard_blocks, allow_canonical_write=allow_canonical_write,
    )
    transitions.append(t_obs.as_dict())
    # Structural blockers always stop; eligibility blockers stop only a requested commit.
    if t_obs.has_structural or (allow_canonical_write and not t_obs.ok):
        return _emit_blocked("BLOCKED_COGNITIVE_LOOP_OBSERVATION")

    # Phase 13 - self interpretation.
    interp_out = output_root / "dream_self_interpretation.json"
    interp = p13.run_phase13(
        observation_path, residue_path, story_contract, script_contract,
        dream_id, revision_id, run_id, persona_id, live=live,
    )
    p13.write_json(interp_out, interp)
    phases.append({
        "phase": "13_self_interpretation",
        "status": interp["status"],
        "artifacts": [str(interp_out)],
        "accepted": len(interp["accepted_interpretations"]),
        "rejected": len(interp["rejected_interpretations"]),
        "honesty_rule": interp["honesty_rule"],
    })

    # GUARD 2: ACCEPTED_OBSERVATION -> PASS_INTERPRETATION (before the phase14 LLM side effect).
    t_interp = guards.guard_interpretation(
        interp, expected_dream_id=dream_id, expected_revision_id=revision_id,
        expected_run_id=run_id, expected_observation_sha256=interp.get("observation_packet_sha256"),
        min_accepted=1,
    )
    transitions.append(t_interp.as_dict())
    if t_interp.has_structural:
        return _emit_blocked("BLOCKED_COGNITIVE_LOOP_INTERPRETATION")

    # Phase 14 - ToM validation.
    tom_out = output_root / "tom_validation_receipt.json"
    tom = p14.run_phase14(interp, dream_id, revision_id, run_id, live=live)
    p13.write_json(tom_out, tom)
    phases.append({
        "phase": "14_tom_validation",
        "status": tom["status"],
        "artifacts": [str(tom_out)],
        "accepted": tom["accepted_count"],
        "rejected": tom["rejected_count"],
        "candidate_source": tom["candidate_source"],
    })

    # GUARD 3: PASS_INTERPRETATION -> PASS_TOM_VALIDATION (before the phase15 write side effect).
    t_tom = guards.guard_tom_validation(
        tom, interp, expected_dream_id=dream_id, expected_revision_id=revision_id,
        expected_run_id=run_id, min_accepted=1,
    )
    transitions.append(t_tom.as_dict())
    if t_tom.has_structural:
        return _emit_blocked("BLOCKED_COGNITIVE_LOOP_TOM")

    # Phase 15 - persistence (dry-run plan + validation-collection real write, or
    # the guarded transactional canonical commit).
    persist_out = output_root / "dream_persistence_receipt.json"
    persist = p15.run_phase15(
        observation_path, interp_out, tom_out, dream_id, revision_id, run_id, persona_id,
        allow_canonical_write=allow_canonical_write, return_id=return_id,
        validation_collection=validation_collection,
        acceptance_receipt_path=acceptance_receipt_path,
        superseded_return_ids=superseded_return_ids,
    )
    p15.write_json(persist_out, persist)
    canonical_written = bool(persist.get("canonical_dream_memory_written"))
    canonical_proof = persist.get("canonical_write_proof") or {}
    phases.append({
        "phase": "15_persistence",
        "status": persist["status"],
        "artifacts": [str(persist_out)],
        "canonical_write_allowed": persist["canonical_write_allowed"],
        "canonical_writes_performed": persist["canonical_writes_performed"],
        "canonical_write_blockers": persist["canonical_write_blockers"],
        "canonical_dream_memory_written": canonical_written,
        "canonical_node_keys": canonical_proof.get("node_keys", []),
        "canonical_edge_keys": canonical_proof.get("edge_keys", []),
        "canonical_watch_vertex_keys": canonical_proof.get("watch_vertex_keys", []),
        "canonical_all_exact_reread_match": canonical_proof.get("all_exact_reread_match"),
        "idempotency_key": canonical_proof.get("idempotency_key"),
        "validation_write": bool(persist["validation_write_proof"]),
        "validation_all_match": (persist["validation_write_proof"] or {}).get("all_exact_reread_match"),
    })

    # GUARDS 4+5: staged persistence verified -> canonical commit. These matter
    # only when a canonical commit was requested; a dry-run plan legitimately
    # produces neither a staging proof nor a commit manifest.
    if allow_canonical_write and persist["canonical_write_allowed"]:
        t_stage = guards.guard_staged_persistence(persist)
        transitions.append(t_stage.as_dict())
        t_commit = guards.guard_canonical_commit(
            persist,
            expected_phase13_sha256=p13.canonical_sha(interp),
            expected_phase14_sha256=p13.canonical_sha(tom),
        )
        transitions.append(t_commit.as_dict())
        if t_stage.has_structural or t_commit.has_structural or not canonical_written:
            return _emit_blocked("BLOCKED_COGNITIVE_LOOP_CANONICAL_COMMIT")

    # Aggregate verdict. Fixed: only OK observations, or an enumerated
    # waiver-backed DEGRADED observation with a certifying receipt, pass at the
    # input phase; every other phase must be an explicit PASS/DRY_RUN/LIVE.
    all_pass = all(
        guards.phase_status_is_pass_like(
            ph["phase"], ph["status"],
            observation_acceptance_certifies=acceptance_certifies,
        )
        for ph in phases
    ) and all(not t["structural_blockers"] for t in transitions)
    receipt = {
        "schema": "persona_dream.cognitive_loop_receipt.v1",
        "status": "PASS_COGNITIVE_LOOP" if all_pass else "PARTIAL_COGNITIVE_LOOP",
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "persona_id": persona_id,
        "live": live,
        "phases": phases,
        "transitions": transitions,
        "canonical_dream_memory_written": canonical_written,
        "canonical_record_keys": {
            "nodes": canonical_proof.get("node_keys", []),
            "edges": canonical_proof.get("edge_keys", []),
            "watch_vertices": canonical_proof.get("watch_vertex_keys", []),
        },
        "claims": {
            "proves": [
                "the persona-dream cognitive loop runs 12->13->14->15 on a real Watch observation packet",
                "self-interpretation and ToM proposal text reasoning route through the sanctioned Tau node (no direct scillm)",
                "self-interpretation claims cite Watch observation ids and source-memory ids (deterministic gate)",
                "accepted ToM candidates are grounded in their parent interpretation (deterministic gate)",
            ] + ([
                "canonical dream memory was written through the $memory API for this ACCEPTED, non-superseded successor return, with exact reread-by-key proof",
            ] if canonical_written else [
                "persistence emits an exact canonical would-write plan and proves the write path against a non-canonical validation collection",
            ]),
            "does_not_prove": [
                "Qdrant semantic recall and downstream behavior change (Phase 16)",
                "human subjective acceptance (remains the human's)",
            ] + ([] if canonical_written else [
                "canonical dream memory persistence (deferred: needs an accepted, non-superseded return + acceptance receipt)",
            ]),
        },
        "generated_at": utc_now(),
    }
    p13.write_json(output_root / "cognitive_loop_receipt.json", receipt)
    return receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observation", type=Path, required=True)
    p.add_argument("--residue-links", type=Path, required=True)
    p.add_argument("--story-contract", type=Path, default=None)
    p.add_argument("--script-contract", type=Path, default=None)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--dream-id", required=True)
    p.add_argument("--revision-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--persona-id", default="embry")
    p.add_argument("--no-live", action="store_true")
    p.add_argument("--validation-collection", default=None)
    p.add_argument("--allow-canonical-write", action="store_true",
                   help="Permit phase 15 to write canonical dream memory (still fail-closed).")
    p.add_argument("--return-id", default=None)
    p.add_argument("--acceptance-receipt", type=Path, default=None)
    p.add_argument("--superseded-return-ids", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    superseded = (
        {s.strip() for s in args.superseded_return_ids.split(",") if s.strip()}
        if args.superseded_return_ids else None
    )
    receipt = run_loop(
        args.observation, args.residue_links, args.story_contract, args.script_contract,
        args.output_root, args.dream_id, args.revision_id, args.run_id, args.persona_id,
        live=not args.no_live, validation_collection=args.validation_collection,
        allow_canonical_write=args.allow_canonical_write, return_id=args.return_id,
        acceptance_receipt_path=args.acceptance_receipt, superseded_return_ids=superseded,
    )
    if args.json:
        print(json.dumps({
            "status": receipt["status"],
            "phases": [{"phase": ph["phase"], "status": ph["status"]} for ph in receipt["phases"]],
            "canonical_dream_memory_written": receipt["canonical_dream_memory_written"],
            "output_root": str(args.output_root),
        }, indent=2))
    return 0 if receipt["status"] == "PASS_COGNITIVE_LOOP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
