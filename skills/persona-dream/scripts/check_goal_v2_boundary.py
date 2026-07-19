#!/usr/bin/env python3
"""Deterministic primary proof for GOAL_V2.md (P0 boundary).

Exits 0 with PASS_GOAL_V2_P0_BOUNDARY only when every P0 criterion has its
hash-bound receipt on disk. Missing/failed criteria are listed individually;
this checker never fabricates or authors receipts (P0.1 and M5 are
human-authored artifacts it merely verifies).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
RR = SKILL / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
VIDEO_SHA = "59b9ff3155d6ba9d0b90d795bafe7b84cc4e10849db08299217b65d61e211fff"

CRITERIA = {
    "p0_1_human_acceptance": {
        "path": RR / "human_acceptance_receipt.v1.json",
        "check": lambda d: d.get("author") == "human"
        and d.get("video_sha256", "").endswith(VIDEO_SHA)
        and d.get("verdict") in ("ACCEPTED", "REJECTED"),
    },
    "p0_2_v2_lineage": {
        "path": RR / "watch_gauntlet/59b9ff3155d6/cognitive_loop_v2/lineage_receipt.v1.json",
        "check": lambda d: d.get("status") == "PASS_V2_LINEAGE"
        and d.get("dream_node_untouched") is True,
    },
    "p0_3_routing_semantics": {
        "path": RR / "routing_semantics_calibration_receipt.v1.json",
        "check": lambda d: d.get("status") == "PASS_ROUTING_SEMANTICS"
        and d.get("montage_equivalence") == "PASS"
        and d.get("arcface_enforced") is True,
    },
    "p0_4_gmo_pin": {
        "path": RR / "gmo_deployment_pin.v1.json",
        "check": lambda d: bool(d.get("gmo_commit")) and bool(d.get("pinned_at")),
    },
    "p0_5_phase16_v2": {
        "path": RR / "phase_16_behavior_evaluation/phase16_v2_lineage_receipt.v1.json",
        "check": lambda d: d.get("overall_status") == "PASS",
    },
    "p0_6_voice_expression": {
        "path": RR / "voice_expression/voice_expression_evaluation_receipt.v1.json",
        "check": lambda d: d.get("text_route") == "PASS" and d.get("audio_route") == "PASS"
        and bool(d.get("lipsync_canary_receipt")),
    },
    "p0_7_pilot_result": {
        "path": SKILL / "contracts/pilot_c_vs_f_result_receipt.v1.json",
        "check": lambda d: d.get("published_under") == "pilot_c_vs_f_frozen_protocol.v2"
        and d.get("result") in ("POSITIVE", "NULL", "INVALID")
        and d.get("m5_read_author") == "human",
    },
}


def main() -> int:
    as_json = "--json" in sys.argv
    results, passed = {}, True
    for name, spec in CRITERIA.items():
        path = spec["path"]
        if not path.exists():
            results[name] = {"state": "MISSING", "path": str(path.relative_to(SKILL))}
            passed = False
            continue
        try:
            doc = json.loads(path.read_text())
            ok = bool(spec["check"](doc))
        except Exception as exc:  # malformed receipt = fail closed
            results[name] = {"state": f"MALFORMED: {exc}", "path": str(path.relative_to(SKILL))}
            passed = False
            continue
        results[name] = {
            "state": "PASS" if ok else "FAIL",
            "path": str(path.relative_to(SKILL)),
        }
        passed = passed and ok
    out = {
        "schema": "persona_dream.goal_v2_boundary_check.v1",
        "status": "PASS_GOAL_V2_P0_BOUNDARY" if passed else "BLOCKED_GOAL_V2_P0_BOUNDARY",
        "criteria": results,
    }
    print(json.dumps(out, indent=2) if as_json else out["status"])
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
