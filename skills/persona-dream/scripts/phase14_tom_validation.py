#!/usr/bin/env python3
"""Phase 14 - Theory-of-Mind validation gate.

Takes the Phase 13 interpretation, extracts bounded ToM candidates
(belief / fear / desire / trust / distrust / stance / relationship_state /
uncertainty ...) each with subject, target, source-memory ids, Watch
observation ids, confidence, emotional intensity, and synthetic_origin=true.

The LLM MAY propose candidates. A deterministic gate DECIDES admissibility:
a candidate is rejected unless it identifies its subject and target and cites
source-memory ids and Watch observation ids that are a SUBSET of the parent
accepted interpretation it derives from. This makes it impossible for the LLM
to smuggle in ungrounded beliefs. Each candidate gets an accept/reject receipt.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("phase13_self_interpretation", _HERE / "phase13_self_interpretation.py")
assert _spec and _spec.loader
p13 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p13)

_cspec = importlib.util.spec_from_file_location(
    "persona_dream_cognition_contract", _HERE / "persona_dream_cognition_contract.py"
)
assert _cspec and _cspec.loader
cognition_contract = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(cognition_contract)

SCILLM_MODEL = p13.SCILLM_MODEL
CALLER_SKILL = p13.CALLER_SKILL
tau_adapter = p13.tau_adapter

# Distinct ToM validation statuses (Defect 3). The final status names the
# candidate provenance so a live pass, a deliberate deterministic projection
# (no-live), and a live-route fallback (live attempted then failed) are never
# collapsed into one indistinguishable PASS.
STATUS_PASS_LIVE = "PASS_TOM_VALIDATION_LIVE"
STATUS_PASS_DETERMINISTIC_PROJECTION = "PASS_TOM_VALIDATION_DETERMINISTIC_PROJECTION"
STATUS_DEGRADED_LIVE_FALLBACK = "DEGRADED_TOM_LIVE_ROUTE_FALLBACK"
STATUS_BLOCKED = "BLOCKED_TOM_VALIDATION"

# Caller-defined JSON output contract handed to (and hash-recorded by) the Tau node.
TOM_OUTPUT_CONTRACT = {
    "type": "object",
    "required": ["candidates"],
    "candidate_required": [
        "candidate_id", "parent_interpretation_id", "tom_state_type", "subject",
        "target", "statement", "source_memory_refs", "watch_observation_refs",
        "confidence", "emotional_intensity", "synthetic_origin", "literal_historical_event",
    ],
}

ALLOWED_TOM_STATES = {
    "belief", "fear", "desire", "trust", "distrust", "stance",
    "relationship_state", "uncertainty", "avoidance", "obligation",
    "preference", "emotion",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_tom_candidate(
    candidate: dict[str, Any],
    parent: dict[str, Any] | None,
) -> list[str]:
    """Return rejection reasons. Empty == admissible. Grounding must be a subset
    of the parent accepted interpretation - the LLM cannot invent citations."""
    reasons: list[str] = []

    for field in ("candidate_id", "parent_interpretation_id", "subject", "target", "statement"):
        if not str(candidate.get(field) or "").strip():
            reasons.append(f"MISSING_FIELD:{field}")

    if candidate.get("tom_state_type") not in ALLOWED_TOM_STATES:
        reasons.append(f"TOM_STATE_TYPE_NOT_BOUNDED:{candidate.get('tom_state_type')}")

    if parent is None:
        reasons.append("NO_PARENT_ACCEPTED_INTERPRETATION")
        return reasons

    parent_sources = set(parent.get("source_memory_refs", []))
    parent_obs = set(parent.get("observation_refs", []))

    src = candidate.get("source_memory_refs")
    if not isinstance(src, list) or not src:
        reasons.append("NO_SOURCE_MEMORY_CITATION")
    else:
        outside = [s for s in src if s not in parent_sources]
        if outside:
            reasons.append(f"SOURCE_REFS_NOT_IN_PARENT:{','.join(map(str, outside))}")

    obs = candidate.get("watch_observation_refs")
    if not isinstance(obs, list) or not obs:
        reasons.append("NO_WATCH_OBSERVATION_CITATION")
    else:
        outside = [o for o in obs if o not in parent_obs]
        if outside:
            reasons.append(f"OBSERVATION_REFS_NOT_IN_PARENT:{','.join(map(str, outside))}")

    conf = candidate.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        reasons.append("CONFIDENCE_OUT_OF_RANGE")

    intensity = candidate.get("emotional_intensity")
    if not isinstance(intensity, (int, float)) or not (0.0 <= float(intensity) <= 1.0):
        reasons.append("EMOTIONAL_INTENSITY_MISSING_OR_OUT_OF_RANGE")

    if candidate.get("synthetic_origin") is not True:
        reasons.append("SYNTHETIC_ORIGIN_NOT_TRUE")
    if candidate.get("literal_historical_event") is not False:
        reasons.append("LITERAL_HISTORICAL_EVENT_NOT_FALSE")

    return reasons


def validate_candidates(
    candidates: list[dict[str, Any]],
    accepted_interpretations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parents = {i.get("interpretation_id"): i for i in accepted_interpretations}
    accepted: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for cand in candidates:
        parent = parents.get(cand.get("parent_interpretation_id"))
        reasons = validate_tom_candidate(cand, parent)
        decision = "ACCEPT" if not reasons else "REJECT"
        receipts.append({
            "candidate_id": cand.get("candidate_id", "?"),
            "parent_interpretation_id": cand.get("parent_interpretation_id"),
            "decision": decision,
            "reasons": reasons,
        })
        if decision == "ACCEPT":
            stamped = dict(cand)
            stamped["schema"] = "persona_dream.tom_candidate.v1"
            accepted.append(stamped)
    return accepted, receipts


# --------------------------------------------------------------------------- #
# LLM proposal (may propose; code decides)                                    #
# --------------------------------------------------------------------------- #
def build_prompt(
    accepted_interpretations: list[dict[str, Any]],
    *,
    example_subject: str,
    example_target: str,
) -> str:
    compact = [
        {
            "interpretation_id": i.get("interpretation_id"),
            "tom_state_type": i.get("tom_state_type"),
            "subject": i.get("subject"),
            "target": i.get("target"),
            "statement": i.get("statement"),
            "observation_refs": i.get("observation_refs"),
            "source_memory_refs": i.get("source_memory_refs"),
            "confidence": i.get("confidence"),
            "emotional_intensity": i.get("emotional_intensity"),
        }
        for i in accepted_interpretations
    ]
    return f"""You extract bounded Theory-of-Mind candidates from ACCEPTED persona
self-interpretations. A downstream deterministic gate will REJECT any candidate
whose citations are not a subset of its parent interpretation, so DO NOT invent
observation ids or source-memory ids - reuse only the ones already present.

For each accepted interpretation, emit exactly one ToM candidate:
- tom_state_type must be one of: {sorted(ALLOWED_TOM_STATES)}
- subject and target copied from the interpretation
- source_memory_refs and watch_observation_refs must be a SUBSET of the parent's
  source_memory_refs and observation_refs respectively
- confidence and emotional_intensity in [0,1]
- synthetic_origin=true, literal_historical_event=false

ACCEPTED INTERPRETATIONS:
{json.dumps(compact, indent=2)[:3000]}

Return ONLY JSON:
{{"candidates": [
  {{
    "candidate_id": "tom-001",
    "parent_interpretation_id": "<interpretation_id>",
    "tom_state_type": "trust",
    "subject": "{example_subject}",
    "target": "{example_target}",
    "statement": "<bounded ToM claim>",
    "source_memory_refs": ["<source_id from parent>"],
    "watch_observation_refs": ["<observation_id from parent>"],
    "confidence": 0.4,
    "emotional_intensity": 0.5,
    "synthetic_origin": true,
    "literal_historical_event": false
  }}
]}}
No prose outside the JSON object."""


def propose_candidates(
    accepted_interpretations: list[dict[str, Any]],
    timeout: float = 240.0,
    *,
    example_subject: str,
    example_target: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Propose ToM candidates through the sanctioned Tau text-reasoning node.

    No direct scillm call: only Tau may reach scillm. The LLM only proposes;
    the deterministic subset gate below decides admissibility. Returns the
    proposed candidates and the Tau receipt.
    """
    parsed, receipt = tau_adapter.dispatch_text_reasoning(
        build_prompt(accepted_interpretations, example_subject=example_subject, example_target=example_target),
        role="tom-candidate-proposal",
        output_contract=TOM_OUTPUT_CONTRACT,
        caller_skill=CALLER_SKILL,
        model=SCILLM_MODEL,
        timeout_s=timeout,
    )
    candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    return candidates, receipt


def derive_candidates_deterministic(accepted_interpretations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback: derive one grounded ToM candidate per accepted interpretation."""
    out: list[dict[str, Any]] = []
    for n, i in enumerate(accepted_interpretations, start=1):
        state = i.get("tom_state_type")
        if state not in ALLOWED_TOM_STATES:
            state = "uncertainty"
        out.append({
            "candidate_id": f"tom-{n:03d}",
            "parent_interpretation_id": i.get("interpretation_id"),
            "tom_state_type": state,
            "subject": i.get("subject"),
            "target": i.get("target"),
            "statement": i.get("statement"),
            "source_memory_refs": list(i.get("source_memory_refs", [])),
            "watch_observation_refs": list(i.get("observation_refs", [])),
            "confidence": float(i.get("confidence", 0.0)),
            "emotional_intensity": float(i.get("emotional_intensity", 0.3) or 0.3),
            "synthetic_origin": True,
            "literal_historical_event": False,
        })
    return out


def run_phase14(
    interpretation: dict[str, Any],
    dream_id: str,
    revision_id: str,
    run_id: str,
    live: bool = True,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if contract is None:
        contract = cognition_contract.load_contract()
    example_subject = contract["default_subject"]
    example_target = contract["default_target"]

    accepted_interps = interpretation.get("accepted_interpretations", [])
    candidate_source = "none"
    live_route_attempted = False
    live_route_failed = False
    candidates: list[dict[str, Any]] = []
    tau_routing: dict[str, Any] | None = None
    if accepted_interps:
        if live:
            live_route_attempted = True
            try:
                candidates, tau_receipt = propose_candidates(
                    accepted_interps, example_subject=example_subject, example_target=example_target,
                )
                tau_routing = tau_adapter.receipt_provenance(tau_receipt)
                candidate_source = "llm_via_tau"
            except Exception:  # noqa: BLE001
                candidates = []
                live_route_failed = True
        if not candidates:
            candidates = derive_candidates_deterministic(accepted_interps)
            candidate_source = "deterministic_fallback" if live else "deterministic"

    accepted, receipts = validate_candidates(candidates, accepted_interps)
    had_rejections = any(r["decision"] == "REJECT" for r in receipts)

    # Distinct statuses (Defect 3): the live pass, the deliberate deterministic
    # projection (no-live), and the degraded live-route fallback (live attempted
    # then failed -> deterministic) are separately named. The fallback status is
    # DEGRADED and the downstream transition guard requires an explicit waiver to
    # proceed on it.
    if not accepted_interps or not accepted:
        status = STATUS_BLOCKED
    elif candidate_source == "llm_via_tau":
        status = STATUS_PASS_LIVE
    elif candidate_source == "deterministic":
        status = STATUS_PASS_DETERMINISTIC_PROJECTION
    elif candidate_source == "deterministic_fallback":
        status = STATUS_DEGRADED_LIVE_FALLBACK
    else:  # pragma: no cover - defensive; accepted implies a known source
        status = STATUS_BLOCKED

    return {
        "schema": "persona_dream.tom_validation_receipt.v1",
        "status": status,
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "interpretation_sha256": p13.canonical_sha(interpretation),
        "candidate_source": candidate_source,
        "live_route_attempted": live_route_attempted,
        "live_route_failed": live_route_failed,
        "had_rejections": had_rejections,
        "tau_routing": tau_routing,
        "proposed_candidate_count": len(candidates),
        "accepted_tom_candidates": accepted,
        "candidate_receipts": receipts,
        "accepted_count": len(accepted),
        "rejected_count": sum(1 for r in receipts if r["decision"] == "REJECT"),
        "canonical_memory_write_allowed": False,
        "mocked": False,
        "live": bool(live),
        "generated_at": utc_now(),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interpretation", type=Path, required=True)
    p.add_argument("--dream-id", required=True)
    p.add_argument("--revision-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--no-live", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    interpretation = p13.read_json(args.interpretation)
    result = run_phase14(interpretation, args.dream_id, args.revision_id, args.run_id, live=not args.no_live)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p13.write_json(args.output, result)
    if args.json:
        print(json.dumps({"status": result["status"], "accepted": result["accepted_count"],
                          "rejected": result["rejected_count"], "output": str(args.output)}, indent=2))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
