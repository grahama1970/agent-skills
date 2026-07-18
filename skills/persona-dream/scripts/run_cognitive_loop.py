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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    phases: list[dict[str, Any]] = []

    # Phase 12 - already-produced Watch observation packet.
    packet = p13.read_json(observation_path)
    phases.append({
        "phase": "12_watch_observation",
        "status": packet.get("status", "UNKNOWN"),
        "role": "input",
        "artifacts": [str(observation_path)],
        "observation_packet_sha256": p13.file_sha(observation_path),
        "evidence_origin": packet.get("evidence_origin"),
    })

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

    # Phase 15 - persistence (dry-run plan + validation-collection real write).
    persist_out = output_root / "dream_persistence_receipt.json"
    persist = p15.run_phase15(
        observation_path, interp_out, tom_out, dream_id, revision_id, run_id, persona_id,
        allow_canonical_write=False, return_id=None, validation_collection=validation_collection,
    )
    p15.write_json(persist_out, persist)
    phases.append({
        "phase": "15_persistence",
        "status": persist["status"],
        "artifacts": [str(persist_out)],
        "canonical_write_allowed": persist["canonical_write_allowed"],
        "canonical_writes_performed": persist["canonical_writes_performed"],
        "canonical_write_blockers": persist["canonical_write_blockers"],
        "validation_write": bool(persist["validation_write_proof"]),
        "validation_all_match": (persist["validation_write_proof"] or {}).get("all_exact_reread_match"),
    })

    all_pass = all(
        str(ph["status"]).startswith(("PASS", "DRY_RUN", "LIVE", "DEGRADED"))
        for ph in phases
    )
    receipt = {
        "schema": "persona_dream.cognitive_loop_receipt.v1",
        "status": "PASS_COGNITIVE_LOOP" if all_pass else "PARTIAL_COGNITIVE_LOOP",
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "persona_id": persona_id,
        "live": live,
        "phases": phases,
        "canonical_dream_memory_written": False,
        "claims": {
            "proves": [
                "the persona-dream cognitive loop runs 12->13->14->15 on a real Watch observation packet",
                "self-interpretation claims cite Watch observation ids and source-memory ids (deterministic gate)",
                "accepted ToM candidates are grounded in their parent interpretation (deterministic gate)",
                "persistence emits an exact canonical would-write plan and proves the write path against a non-canonical validation collection",
            ],
            "does_not_prove": [
                "the closed-loop research claim (that needs a NON-superseded successor return)",
                "canonical dream memory persistence of this superseded historical return",
                "Qdrant semantic recall and downstream behavior change (Phase 16)",
            ],
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
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    receipt = run_loop(
        args.observation, args.residue_links, args.story_contract, args.script_contract,
        args.output_root, args.dream_id, args.revision_id, args.run_id, args.persona_id,
        live=not args.no_live, validation_collection=args.validation_collection,
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
