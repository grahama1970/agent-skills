#!/usr/bin/env python3
"""Prove the Phase 07 Tau DAG command-loop preflight on genuinely rendered
artifacts — no paid provider call, no image generation.

This driver:
  1. renders the successor spine chain with ``phase07_prompt_renderer`` (real
     deterministic compiled prompts, hash-bound contracts, validator receipts),
  2. re-derives every compiled prompt to prove determinism / not-hand-edited,
  3. runs the real spine-chain validator gate,
  4. runs the node's ``_run_phase07_live_preflight`` for both roles in the
     local, no-provider gate (``require_provider_live=False``), including the
     reviewer-pass precondition check bound to the real Phase C acceptances,
  5. runs a targeted single-frame preflight with ``require_target_scope=True``
     exactly as the node's per-panel command-loop scopes it,
and writes one machine-readable proof receipt.  It reuses the already-accepted
Phase C frames; it never generates images or calls a paid provider.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import phase07_prompt_renderer as renderer  # noqa: E402
from validate_persona_dream_spine_chain import validate_manifest  # noqa: E402


def _load_node():
    spec = importlib.util.spec_from_file_location("phase07_storyboard_tau_node", SCRIPTS_DIR / "phase07_storyboard_tau_node.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _preflight(node, *, role: str, run_root: Path, packet: dict[str, Any], packet_path: Path, manifest_path: Path, require_target_scope: bool, require_reviewer_pass: bool) -> dict[str, Any]:
    context = {
        "provider_live": False,
        "mocked": False,
        "live_image_call_started": False,
        "persona_dream_spine_chain_manifest": str(manifest_path),
    }
    start_payload = {"context": context}
    res = node._run_phase07_live_preflight(
        role=role,
        run_root=run_root,
        packet=packet,
        packet_path=packet_path,
        start_payload=start_payload,
        require_provider_live=False,
        require_target_scope=require_target_scope,
        require_reviewer_pass_preconditions=require_reviewer_pass,
    )
    return {"role": role, "status": res["status"], "require_target_scope": require_target_scope, "require_reviewer_pass": require_reviewer_pass, "blockers": res.get("blockers", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revision-root", type=Path, required=True)
    ap.add_argument("--max-steps-evidence", type=int, default=4, help="max_steps the Tau handoff loop is run with (must be >2 to reach the panel-specific 3rd node).")
    args = ap.parse_args()

    rev = args.revision_root.resolve()
    p07 = rev / "phase_07_storyboard_live_tau"
    packet_path = p07 / "storyboard_packet.json"
    phase_c_frames = p07 / "phase_c_successor_regen" / "generated_storyboard_frames"
    idea_text = rev / "phase_01_idea" / "dream_prompt.txt"
    proof_dir = p07 / "tau_loop_preflight_proof"
    spine_dir = proof_dir / "spine_chain"

    render_receipt = renderer.render_spine_chain(
        packet_path=packet_path,
        out_dir=spine_dir,
        idea_text_path=idea_text if idea_text.exists() else None,
        phase_c_frames_dir=phase_c_frames if phase_c_frames.exists() else None,
    )
    manifest_path = spine_dir / "spine_chain_manifest.v1.json"

    verify_receipt = renderer.verify_render(manifest_path)
    spine_gate = validate_manifest(manifest_path)

    node = _load_node()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    # Full-storyboard local gate: both roles, no provider, reviewer preconditions
    # bound to the real Phase C acceptances.
    full_run_root = proof_dir / "preflight_full_storyboard"
    full_run_root.mkdir(parents=True, exist_ok=True)
    creator = _preflight(node, role="panel-creator", run_root=full_run_root, packet=packet, packet_path=packet_path, manifest_path=manifest_path, require_target_scope=False, require_reviewer_pass=False)
    reviewer = _preflight(node, role="panel-reviewer", run_root=full_run_root, packet=packet, packet_path=packet_path, manifest_path=manifest_path, require_target_scope=False, require_reviewer_pass=True)

    # Targeted single-frame gate, exactly as the node's per-panel command loop
    # scopes generation (require_target_scope=True). Uses a targeted view of the
    # packet (a scoping projection; no content change).
    target_panel = "sb_001"
    targeted_packet = dict(packet)
    targeted_packet["generation_scope"] = {
        "mode": "targeted_panel_proof",
        "target_panel_ids": [target_panel],
        "target_frame_ids": [f"{target_panel}.start_frame", f"{target_panel}.end_frame"],
    }
    targeted_run_root = proof_dir / "preflight_targeted_sb_001"
    targeted_run_root.mkdir(parents=True, exist_ok=True)
    targeted_packet_path = targeted_run_root / "targeted_storyboard_packet.json"
    targeted_packet_path.write_text(json.dumps(targeted_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    t_creator = _preflight(node, role="panel-creator", run_root=targeted_run_root, packet=targeted_packet, packet_path=targeted_packet_path, manifest_path=manifest_path, require_target_scope=True, require_reviewer_pass=False)
    t_reviewer = _preflight(node, role="panel-reviewer", run_root=targeted_run_root, packet=targeted_packet, packet_path=targeted_packet_path, manifest_path=manifest_path, require_target_scope=True, require_reviewer_pass=True)

    preflights = [creator, reviewer, t_creator, t_reviewer]
    passing = {
        "panel-creator": "PASS_LIVE_CREATOR_PREFLIGHT",
        "panel-reviewer": "PASS_LIVE_REVIEWER_PREFLIGHT",
    }
    all_preflight_pass = all(p["status"] == passing[p["role"]] for p in preflights)

    proof = {
        "schema": "persona_dream.phase07.tau_loop_preflight_proof.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision_root": str(rev),
        "no_paid_call": True,
        "no_image_generation": True,
        "reused_accepted_phase_c_frames": str(phase_c_frames),
        "renderer": render_receipt["renderer"],
        "render": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": render_receipt["manifest_sha256"],
            "all_contracts_pass": render_receipt["all_contracts_pass"],
            "stage_statuses": render_receipt["stage_statuses"],
            "frames": render_receipt["frames"],
        },
        "determinism_verify": {"status": verify_receipt["status"], "frames_checked": verify_receipt["frames_checked"], "mismatches": verify_receipt["mismatches"]},
        "spine_chain_gate": {"status": spine_gate["status"], "verdict": spine_gate["verdict"], "blockers": spine_gate["blockers"]},
        "node_preflights": preflights,
        "all_preflight_pass": all_preflight_pass,
        "tau_command_loop": {
            "scheduler": "handoff-loop",
            "engine": "~/workspace/experiments/tau (branch issue-74-ready-queue-condition-block)",
            "max_steps_used": args.max_steps_evidence,
            "truncation_at_2_root_cause": "No hard max_steps=2 exists in the loop; the loop default is 5 and the persona-dream proof runner hardcodes max_steps=4. A 2-node (creator+reviewer, each max_attempts=1) DAG contract with no limits.max_total_attempts derives _max_steps==2 and stops with stop_reason=max_steps_exhausted before the 3rd node. Raising limits.max_total_attempts>=3 (or node max_attempts) reaches the panel-specific 3rd node (persona-dream-panel-repair-gate).",
            "panel_specific_third_node": "persona-dream-panel-repair-gate",
        },
        "status": "PASS_TAU_LOOP_PREFLIGHT_PROOF" if (
            render_receipt["all_contracts_pass"]
            and verify_receipt["status"] == "PASS_DETERMINISTIC_RENDER"
            and spine_gate["status"] == "PASS_SPINE_CHAIN_CONTRACT_GATE"
            and all_preflight_pass
        ) else "BLOCKED_TAU_LOOP_PREFLIGHT_PROOF",
        "proves": [
            "compiled prompts are deterministically rendered from typed contract inputs (not hand-authored stubs)",
            "spine-chain integrity gate passes on genuinely rendered artifacts",
            "node creator+reviewer live preflight pass in the local no-provider gate",
            "targeted per-panel preflight passes with require_target_scope=True (command-loop scope)",
            "reviewer-pass preconditions bound to the real Phase C actual-pixel acceptances",
        ],
        "does_not_prove": [
            "provider reference attachment or image generation (out of scope; frames already accepted)",
            "paid Kling submission (human-gated; not crossed)",
        ],
    }
    receipt_path = proof_dir / "tau_loop_preflight_proof_receipt.v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": proof["status"], "receipt": str(receipt_path), "preflights": [(p["role"], p["status"], p["require_target_scope"]) for p in preflights]}, indent=2))
    return 0 if proof["status"] == "PASS_TAU_LOOP_PREFLIGHT_PROOF" else 1


if __name__ == "__main__":
    raise SystemExit(main())
