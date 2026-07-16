#!/usr/bin/env python3
"""Merge backend lifecycle receipts into a pixi replay normalized UX fixture."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

BATTLE_DIR = Path(__file__).resolve().parents[1]

UX_LAB_PUBLIC = Path(__file__).resolve().parents[4] / "pi-mono/packages/ux-lab/public/battle-fixtures"


def _link_public_fixture(out_dir: Path, name: str) -> None:
    for public_root in (
        BATTLE_DIR / "spectator/public/battle-fixtures",
        UX_LAB_PUBLIC,
    ):
        public_root.mkdir(parents=True, exist_ok=True)
        public_dir = public_root / name
        if public_dir.is_symlink() or public_dir.exists():
            if public_dir.is_symlink():
                public_dir.unlink()
            elif public_dir.is_dir():
                shutil.rmtree(public_dir)
        public_dir.symlink_to(out_dir.resolve())

DEFAULT_BASE = BATTLE_DIR / "local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"
DEFAULT_OUT_DIR = BATTLE_DIR / "local/battle-004-parent-spawn-lifecycle-pixi-replay"
DEFAULT_COMBINER = Path("/tmp/battle-004-combiner")
REQUIRED_COMBINER_FILES = (
    "knowledge-packets/parent-knowledge-packet.json",
    "knowledge-packets/child-knowledge-packet.json",
    "spawn-policy-decision.json",
    "combiner-proof-receipt.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _missing_combiner_files(combiner_dir: Path) -> list[str]:
    return [name for name in REQUIRED_COMBINER_FILES if not (combiner_dir / name).is_file()]


def _lane_by_id(fixture: dict[str, Any], lane_id: str) -> dict[str, Any] | None:
    for lane in fixture.get("lanes", []):
        if lane.get("id") == lane_id:
            return lane
    return None


def _score_calibration_from_semantics(semantics: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "battle.score_calibration.v1",
        "outcome_class": semantics.get("outcome_class"),
        "score_weight": semantics.get("score_weight"),
        "formula": semantics.get("score_basis"),
        "profile_inputs": {
            "outcome_tier": semantics.get("outcome_tier"),
            "terminal_state": semantics.get("terminal_state"),
            "spawn_state": semantics.get("spawn_state"),
            "multipliers": semantics.get("multipliers"),
            "score_delta": semantics.get("score_delta"),
        },
        "ordering_invariant": [
            "sprite_choice_does_not_create_score_truth",
            "scorekeeper owns semantic totals",
        ],
    }


def _parent_knowledge_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": True,
        "status": "materialized",
        "packet_id": f"knowledge:{packet.get('parent_exploit_id', 'parent')}",
        "parent_packet_id": None,
        "research_goals": packet.get("research_goals", []),
        "parent_analysis": {
            "hypotheses": packet.get("hypotheses", []),
            "observations": packet.get("observations", []),
        },
        "child_ack": {"required": False, "received": False, "ack_source": None},
    }


def _child_knowledge_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": True,
        "status": "inherited",
        "packet_id": f"knowledge:{packet.get('child_exploit_id', 'child')}",
        "parent_packet_id": f"knowledge:{packet.get('parent_exploit_id', 'parent')}",
        "research_goals": packet.get("next_research_questions", []),
        "parent_analysis": {
            "failed_specimens": packet.get("failed_specimens", []),
            "blocked_ideas": packet.get("blocked_ideas", []),
            "inherited_methods": packet.get("inherited_methods", []),
        },
        "child_ack": {
            "required": True,
            "received": True,
            "ack_source": "combiner_proof",
        },
    }


def _spawn_request_from_policy(policy: dict[str, Any], *, child_exploit_id: str) -> dict[str, Any]:
    decision = policy.get("decision") or policy.get("status") or "NOT_REQUESTED"
    return {
        "present": True,
        "schema": policy.get("schema", "battle.spawn_policy_decision.v1"),
        "request_id": f"spawn-policy:{child_exploit_id}",
        "claim_authority": "battle",
        "requested_decision": decision,
        "child_exploit_id": child_exploit_id,
        "battle_allowed": decision == "ALLOWED",
        "policy_owner": "battle",
    }


def _tau_branch_from_spawn(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": True,
        "schema": "battle.tau_branch_decision.v1",
        "decision_authority": "battle",
        "battle_policy_authority": "battle",
        "decision": "spawn_requested" if policy.get("decision") == "ALLOWED" else "research_more",
        "observed_evidence_refs": policy.get("evidence_refs", []),
        "rationale": policy.get("reason", "combiner proof spawn policy"),
        "confidence": "high",
        "battle_policy_result": "denied" if policy.get("decision") == "NOT_REQUESTED" else "allowed",
    }


def _memory_promotion_from_combiner(receipt: dict[str, Any]) -> dict[str, Any]:
    attempts = receipt.get("attempts") or []
    candidate = attempts[0].get("specimen_id") if attempts else None
    return {
        "present": True,
        "candidate_id": candidate,
        "durable_promoted": False,
        "validator_required": True,
        "promotion_scope": "combiner_specimen_lifecycle",
        "reason": "combiner proof evaluated specimen lifecycle; durable promotion deferred",
    }


def _network_summary_placeholder() -> dict[str, Any]:
    return {
        "capture_requested": True,
        "available": False,
        "full_packet_capture_proven": False,
        "reason": "no live packet capture in combiner proof rung",
        "artifact_uri": None,
        "sha256": None,
    }


def enrich_fixture(fixture: dict[str, Any], *, combiner_dir: Path | None) -> dict[str, Any]:
    enriched = json.loads(json.dumps(fixture))
    parent_lane = _lane_by_id(enriched, "payload-857-receipt")
    child_lane = _lane_by_id(enriched, "payload-857-red-1")
    if not parent_lane or not child_lane:
        raise SystemExit("expected payload-857-receipt and payload-857-red-1 lanes")

    for lane in (parent_lane, child_lane):
        semantics = (lane.get("cockpit") or {}).get("score_semantics") or lane.get("score_semantics")
        if semantics:
            lane["score_calibration"] = _score_calibration_from_semantics(semantics)

    if combiner_dir and combiner_dir.exists():
        parent_packet = _load_json(combiner_dir / "knowledge-packets/parent-knowledge-packet.json")
        child_packet = _load_json(combiner_dir / "knowledge-packets/child-knowledge-packet.json")
        policy = _load_json(combiner_dir / "spawn-policy-decision.json")
        receipt = _load_json(combiner_dir / "combiner-proof-receipt.json")

        parent_lane["knowledge_packet"] = _parent_knowledge_packet(parent_packet)
        child_lane["knowledge_packet"] = _child_knowledge_packet(child_packet)
        parent_lane["spawn_request"] = _spawn_request_from_policy(
            policy, child_exploit_id=child_packet["child_exploit_id"]
        )
        parent_lane["tau_branch_decision"] = _tau_branch_from_spawn(policy)
        child_lane["child_plan"] = {
            "present": True,
            "schema": "battle.child_inherited_plan.v1",
            "plan_id": "child-plan:payload-857-red-1",
            "knowledge_packet_id": child_lane["knowledge_packet"]["packet_id"],
            "inherited_item_refs": child_packet.get("inherited_methods", []),
            "used_before_first_probe": True,
            "scope_inherited": True,
        }
        child_lane["inherited_probe"] = {
            "present": True,
            "schema": "battle.child_inherited_probe.v1",
            "probe_id": "probe:payload-857-red-1",
            "child_plan_id": "child-plan:payload-857-red-1",
            "knowledge_packet_id": child_lane["knowledge_packet"]["packet_id"],
            "used_inherited_state": True,
            "inherited_item_refs": child_packet.get("inherited_methods", []),
        }
        child_lane["memory_promotion"] = _memory_promotion_from_combiner(receipt)
        parent_lane["memory_promotion"] = {
            "present": True,
            "candidate_id": parent_packet.get("parent_exploit_id"),
            "durable_promoted": False,
            "validator_required": True,
            "reason": "parent lane retained useful signal; promotion evaluated by scorekeeper",
        }
        for lane in (parent_lane, child_lane):
            lane["network_summary"] = _network_summary_placeholder()

    enriched.setdefault("lifecycle_enrichment", {})
    enriched["lifecycle_enrichment"].update(
        {
            "schema": "battle.lifecycle_enrichment.v1",
            "source": str(combiner_dir) if combiner_dir else None,
            "proof_mode": "receipt_backed_fixture",
            "fields_emitted": [
                key
                for key in (
                    "knowledge_packet",
                    "spawn_request",
                    "tau_branch_decision",
                    "child_plan",
                    "inherited_probe",
                    "memory_promotion",
                    "network_summary",
                    "score_calibration",
                )
                if any(key in lane for lane in (parent_lane, child_lane))
            ],
        }
    )
    return enriched


def copy_stream_artifacts(base_dir: Path, out_dir: Path) -> None:
    for name in ("stream", "proof"):
        src = base_dir / name
        dst = out_dir / name
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--combiner-dir", type=Path, default=DEFAULT_COMBINER)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--skip-combiner", action="store_true")
    args = parser.parse_args()

    fixture = _load_json(args.base)
    combiner_dir = None if args.skip_combiner else args.combiner_dir
    if combiner_dir is not None:
        missing = _missing_combiner_files(combiner_dir)
        if missing:
            raise SystemExit(
                "combiner proof artifacts are required for lifecycle enrichment; "
                f"missing from {combiner_dir}: {', '.join(missing)}"
            )
    enriched = enrich_fixture(fixture, combiner_dir=combiner_dir)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_fixture = args.out_dir / "battle.normalized_ux_fixture.json"
    out_fixture.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
    copy_stream_artifacts(args.base.parent, args.out_dir)

    _link_public_fixture(args.out_dir, "battle-004-parent-spawn-lifecycle-pixi-replay")

    (args.out_dir / "README.md").write_text(
        "# battle-004-parent-spawn-lifecycle-pixi-replay\n\n"
        "Parent-spawn pixi replay with backend lifecycle fields merged from combiner proof artifacts.\n"
        "Route: `#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn-lifecycle`\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "out_fixture": str(out_fixture),
                "public_fixtures": [str(BATTLE_DIR / "spectator/public/battle-fixtures/battle-004-parent-spawn-lifecycle-pixi-replay"), str(UX_LAB_PUBLIC / "battle-004-parent-spawn-lifecycle-pixi-replay")],
                "combiner_dir": str(combiner_dir) if combiner_dir else None,
                "fields_emitted": enriched.get("lifecycle_enrichment", {}).get("fields_emitted", []),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
