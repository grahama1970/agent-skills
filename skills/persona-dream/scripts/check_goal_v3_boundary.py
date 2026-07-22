#!/usr/bin/env python3
"""GOAL_V3 boundary checker — the goal's single machine proof.

Exit 0 + PASS_GOAL_V3_BOUNDARY iff:
  v3_1: a dream_voice_weights receipt exists with a completed live render
        (profile sha + wav sha + nonzero duration) for the founding dream.
  v3_2: the live edge-closure negative probe receipt shows the persist layer
        blocked a dangling-edge write set pre-staging with the store
        untouched, AND the newest autonomous cycle reached strict
        claim-citation grounding fraction 1.0.
  v3_3: the newest autonomous cycle receipt is PASS_AUTONOMOUS_CYCLE with
        zero human touches and selection-time-frozen instruments, and its
        voice-weights receipt exists with a render.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
GV3 = SKILL / "reports/goal_v3"


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def newest_cycle_receipt() -> tuple[Path | None, dict | None]:
    cycles = sorted((GV3 / "cycles").glob("*/autonomous_cycle_receipt.v1.json"))
    if not cycles:
        return None, None
    return cycles[-1], load(cycles[-1])


def main() -> int:
    results: dict[str, dict] = {}

    vw_path = GV3 / "voice_weights/dream_dream_successor_943b01ecd9a3/dream_voice_weights_receipt.v1.json"
    vw = load(vw_path)
    render = (vw or {}).get("render") or {}
    v3_1 = bool(vw and vw.get("live") and vw.get("profile_sha256")
                and render.get("wav_sha256")
                and float(render.get("duration_seconds") or 0) > 0.2)
    results["v3_1_dream_voice_weights"] = {
        "state": "PASS" if v3_1 else "MISSING",
        "path": str(vw_path.relative_to(SKILL)) if vw else str(vw_path.relative_to(SKILL))}

    probe = load(GV3 / "edge_closure_gate_probe_receipt.v1.json")
    cycle_path, cycle = newest_cycle_receipt()
    v3_2 = bool(probe and probe.get("passed") and probe.get("live")
                and probe.get("blocked_status") == "BLOCKED_EDGE_ENDPOINT_UNRESOLVED"
                and cycle and cycle.get("grounding_fraction") == 1.0)
    results["v3_2_citation_closure"] = {
        "state": "PASS" if v3_2 else "MISSING",
        "path": "reports/goal_v3/edge_closure_gate_probe_receipt.v1.json"}

    cycle_vw = load(Path(cycle["voice_weights_receipt"])) if cycle and cycle.get("voice_weights_receipt") else None
    cycle_render = (cycle_vw or {}).get("render") or {}
    v3_3 = bool(cycle and cycle.get("status") == "PASS_AUTONOMOUS_CYCLE"
                and cycle.get("human_touches") == 0
                and cycle.get("instruments_frozen_before_dream") is True
                and cycle.get("anchors_unchanged") is True
                and cycle.get("negative_control_absent_top10") is True
                and (cycle.get("distinction") or {}).get("passed") is True
                and cycle_render.get("wav_sha256"))
    results["v3_3_autonomous_cycle"] = {
        "state": "PASS" if v3_3 else "MISSING",
        "path": str(cycle_path.relative_to(SKILL)) if cycle_path else "reports/goal_v3/cycles/<none>"}

    passed = v3_1 and v3_2 and v3_3
    out = {
        "schema": "persona_dream.goal_v3_boundary_check.v1",
        "status": "PASS_GOAL_V3_BOUNDARY" if passed else "BLOCKED_GOAL_V3_BOUNDARY",
        "criteria": results,
    }
    print(json.dumps(out, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
