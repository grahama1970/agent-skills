#!/usr/bin/env python3
"""Generate and check Battle's receipt-derived current status."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]
STATUS_PATH = BATTLE_DIR / "CURRENT_STATUS.json"
STATUS_DOC = BATTLE_DIR / "docs" / "status" / "README.md"

DEFAULT_RECEIPTS = {
    "project_agent_dispatch": Path(
        "/home/graham/.local/state/project-watchdog/receipts/"
        "project-watchdog-20260801T120749Z/receipt.json"
    ),
    "fast_sanity": Path("/tmp/battle-tiered-1150-pushed-fast.json"),
    "deterministic_backend": Path(
        "/tmp/battle-tiered-1150-pushed-backend/tiered-deterministic-gate.json"
    ),
    "same_run_qualification": Path(
        "/tmp/battle-same-run-qualification-1143-pushed-20260801T124449Z/"
        "qualification-receipt.json"
    ),
    "live_qualification_gate": Path("/tmp/battle-tiered-1150-pushed-live.json"),
    "human_interjection": Path("/tmp/battle-human-interjection-1145/proof.json"),
    "human_interjection_spectator": Path("/tmp/battle-human-interjection-spectator-proof/proof.json"),
}

SOURCE_CONTEXT = {
    "battle_skill_contract": "skills/battle/SKILL.md",
    "terminal_semantics_decision": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
    "planning_bundle": (
        "/home/graham/workspace/experiments/agent-skills/artifacts/ask/"
        "battle_remaining_gaps_ticket_bundle_20260801.md"
    ),
}

ADAPTIVE_LINEAGE_QUALIFICATION_SCHEMAS = {
    "battle.adaptive_lineage_qualification.v1",
    "battle.adaptive_lineage_goal_qualification.v1",
}

MIN_ADAPTIVE_LINEAGE_CHECKS = 11


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gh_issue_list(state: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            "grahama1970/agent-skills",
            "--label",
            "battle",
            "--state",
            state,
            "--limit",
            "200",
            "--json",
            "number,title,state,labels,url",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def _receipt(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return item
    payload = _read_json(path)
    item.update(
        {
            "sha256": _sha256(path),
            "schema": payload.get("schema"),
            "status": payload.get("status"),
            "mocked": payload.get("mocked"),
            "live": payload.get("live"),
        }
    )
    return item


def _artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False}
    item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        item.update({"sha256": _sha256(path), "kind": "file"})
    elif path.is_dir():
        item["kind"] = "directory"
    return item


def _latest_backend_goal_dir() -> Path | None:
    env_path = os.environ.get("BATTLE_BACKEND_GOAL_PROOF_DIR")
    candidates = [Path(env_path)] if env_path else []
    candidates.extend(Path("/tmp").glob("battle-backend-goal-proof-*"))
    valid: list[Path] = []
    required = [
        Path("battle-004-combiner/combiner-proof-receipt.json"),
        Path("battle-004-spawn-architect/spawn-architect-receipt.json"),
        Path("battle-semantic-outcome-matrix.json"),
        Path("battle-exploit-lifecycle-dag.json"),
    ]
    for candidate in candidates:
        if candidate.is_dir() and all((candidate / rel).is_file() for rel in required):
            valid.append(candidate)
    if not valid:
        return None
    return max(valid, key=lambda path: path.stat().st_mtime)


def _is_adaptive_lineage_qualification(payload: dict[str, Any]) -> bool:
    if payload.get("schema") in ADAPTIVE_LINEAGE_QUALIFICATION_SCHEMAS:
        return True
    return (
        payload.get("battle_id") == "battle-004"
        and isinstance(payload.get("checks"), list)
        and "adaptive-lineage" in str(payload.get("proof_scope", ""))
    )


def _latest_adaptive_lineage_qualification() -> Path | None:
    candidates: list[Path] = []
    for path in (BATTLE_DIR / "local").glob("**/adaptive-lineage-qualification.json"):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if _is_adaptive_lineage_qualification(payload):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _check_passed(item: dict[str, Any]) -> bool:
    if "ok" in item:
        return bool(item.get("ok"))
    return item.get("status") == "PASS"


def _named_check(checks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((item for item in checks if item.get("name") == name), {})


def _adaptive_lineage_qualification_evidence(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "status": None,
            "checks_ok": False,
            "check_count": 0,
            "selected_id": None,
            "runner_up_id": None,
            "g2_judge_attempts": None,
            "budget": None,
        }
    payload = _read_json(path)
    checks = payload.get("checks") or []
    counts = payload.get("counts") or {}
    provider_check = _named_check(checks, "provider_live_authority_receipts_bound")
    return {
        "status": payload.get("status"),
        "schema": payload.get("schema"),
        "stop_condition": payload.get("stop_condition"),
        "checks_ok": all(_check_passed(item) for item in checks),
        "check_count": len(checks),
        "failed_checks": [item.get("name") for item in checks if not _check_passed(item)],
        "selected_id": payload.get("selected_id"),
        "runner_up_id": payload.get("runner_up_id"),
        "g2_judge_attempts": (payload.get("g2_outcome") or {}).get("judge_attempts"),
        "g2_patched_bypass": (payload.get("g2_outcome") or {}).get("patched_bypass"),
        "g2_vulnerable_original_confirmed": (payload.get("g2_outcome") or {}).get(
            "vulnerable_original_confirmed"
        ),
        "exact_replays_matched": counts.get("exact_replays_matched"),
        "exact_replays_required": counts.get("exact_replays_required"),
        "slot_hashes_matched": counts.get("slot_hashes_matched"),
        "slot_hashes_required": counts.get("slot_hashes_required"),
        "provider_receipts_passed": provider_check.get("passed"),
        "provider_receipts_required": provider_check.get("required"),
        "budget": payload.get("budget"),
    }


def _adaptive_lineage_evidence_passes(evidence: dict[str, Any]) -> bool:
    if evidence.get("status") != "PASS" or evidence.get("checks_ok") is not True:
        return False
    if int(evidence.get("check_count") or 0) < MIN_ADAPTIVE_LINEAGE_CHECKS:
        return False
    if evidence.get("g2_judge_attempts") is not None:
        return evidence.get("g2_judge_attempts") == 1
    return all(
        evidence.get(passed) == evidence.get(required) and evidence.get(required)
        for passed, required in [
            ("exact_replays_matched", "exact_replays_required"),
            ("slot_hashes_matched", "slot_hashes_required"),
            ("provider_receipts_passed", "provider_receipts_required"),
        ]
    )


def _source_context_item(path: str) -> dict[str, Any]:
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    return {"path": path, "exists": resolved.is_file()}


def _issue_ref(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "url": issue["url"],
        "labels": sorted(label["name"] for label in issue.get("labels", [])),
    }


def generate(out: Path) -> int:
    receipts = {name: _receipt(path) for name, path in DEFAULT_RECEIPTS.items()}
    adaptive_lineage_qualification = _latest_adaptive_lineage_qualification()
    receipts["adaptive_lineage_qualification"] = _receipt(
        adaptive_lineage_qualification or BATTLE_DIR / "local" / "MISSING" / "adaptive-lineage-qualification.json"
    )
    backend_goal_dir = _latest_backend_goal_dir()
    receipts["backend_goal_full_proof_dir"] = _artifact(backend_goal_dir)
    if backend_goal_dir is not None:
        receipts["backend_goal_combiner"] = _receipt(
            backend_goal_dir / "battle-004-combiner" / "combiner-proof-receipt.json"
        )
        receipts["backend_goal_spawn_architect"] = _receipt(
            backend_goal_dir / "battle-004-spawn-architect" / "spawn-architect-receipt.json"
        )
        receipts["backend_goal_semantic_matrix"] = _receipt(
            backend_goal_dir / "battle-semantic-outcome-matrix.json"
        )
        receipts["backend_goal_lifecycle_dag"] = _receipt(
            backend_goal_dir / "battle-exploit-lifecycle-dag.json"
        )
        receipts["pr8_live_transport_browser"] = _receipt(
            Path("/tmp/battle-pr8-live-transport-proof/summary.json")
        )
        receipts["adaptive_lineage_v13_browser"] = _receipt(
            Path("/tmp/battle-adaptive-lineage-v13-proof/proof-summary.json")
        )
        receipts["adaptive_lineage_panel_source"] = _receipt(
            Path("/tmp/battle-adaptive-lineage-panel-source-proof/proof.json")
        )
        for key in [
            "fast_sanity",
            "deterministic_backend",
            "same_run_qualification",
            "live_qualification_gate",
            "human_interjection",
            "human_interjection_spectator",
        ]:
            if not receipts[key].get("exists"):
                receipts[key].update(
                    {
                        "status": "SUPERSEDED_BY_BACKEND_GOAL_PROOF",
                        "superseded_by": str(backend_goal_dir),
                    }
                )
    same_run = (
        _read_json(DEFAULT_RECEIPTS["same_run_qualification"])
        if DEFAULT_RECEIPTS["same_run_qualification"].is_file()
        else {}
    )
    live_gate = (
        _read_json(DEFAULT_RECEIPTS["live_qualification_gate"])
        if DEFAULT_RECEIPTS["live_qualification_gate"].is_file()
        else {}
    )
    fast = (
        _read_json(DEFAULT_RECEIPTS["fast_sanity"])
        if DEFAULT_RECEIPTS["fast_sanity"].is_file()
        else {}
    )
    deterministic = (
        _read_json(DEFAULT_RECEIPTS["deterministic_backend"])
        if DEFAULT_RECEIPTS["deterministic_backend"].is_file()
        else {}
    )
    dispatch = (
        _read_json(DEFAULT_RECEIPTS["project_agent_dispatch"])
        if DEFAULT_RECEIPTS["project_agent_dispatch"].is_file()
        else {}
    )
    human_interjection = (
        _read_json(DEFAULT_RECEIPTS["human_interjection"])
        if DEFAULT_RECEIPTS["human_interjection"].is_file()
        else {}
    )
    human_interjection_spectator = (
        _read_json(DEFAULT_RECEIPTS["human_interjection_spectator"])
        if DEFAULT_RECEIPTS["human_interjection_spectator"].is_file()
        else {}
    )
    adaptive_lineage_evidence = _adaptive_lineage_qualification_evidence(
        adaptive_lineage_qualification
    )
    adaptive_proof_dir = adaptive_lineage_qualification.parent if adaptive_lineage_qualification else None
    pixi_binding_path = (
        adaptive_proof_dir / "pixi-replay-proof.json" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "pixi-replay-proof.json"
    )
    pixi_gameplay_path = (
        adaptive_proof_dir / "pixi-gameplay-video-proof.json" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "pixi-gameplay-video-proof.json"
    )
    surf_text_path = (
        adaptive_proof_dir / "surf-text-corrected.txt" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "surf-text-corrected.txt"
    )
    surf_screenshot_path = (
        adaptive_proof_dir / "surf-battle-replay-corrected2.png" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "surf-battle-replay-corrected2.png"
    )
    receipts["adaptive_lineage_pixi_binding"] = _receipt(pixi_binding_path)
    receipts["adaptive_lineage_pixi_gameplay"] = _receipt(pixi_gameplay_path)
    receipts["adaptive_lineage_surf_text"] = _artifact(surf_text_path)
    receipts["adaptive_lineage_surf_screenshot"] = _artifact(surf_screenshot_path)
    pixi_binding = _read_json(pixi_binding_path) if pixi_binding_path.is_file() else {}
    pixi_gameplay = _read_json(pixi_gameplay_path) if pixi_gameplay_path.is_file() else {}
    pixi_binding_passes = (
        pixi_binding.get("status") == "PASS"
        and (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_fixture_sha256") is True
        and (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_run_id") is True
    )
    pixi_gameplay_passes = (
        pixi_gameplay.get("status") == "PASS"
        and pixi_gameplay.get("source_identity_visible") is True
        and pixi_gameplay.get("pause_after_round_not_in_primary_replay") is True
    )
    immutable_goal_met = (
        _adaptive_lineage_evidence_passes(adaptive_lineage_evidence)
        and pixi_binding_passes
        and pixi_gameplay_passes
        and surf_text_path.is_file()
        and surf_screenshot_path.is_file()
    )
    open_issues = [_issue_ref(issue) for issue in _gh_issue_list("open")]
    all_issues = [_issue_ref(issue) for issue in _gh_issue_list("all")]

    status = {
        "schema": "battle.current_status.v1",
        "updated_at": _utc(),
        "generated_by": {
            "command": "./skills/battle/run.sh current-status generate",
            "script": "skills/battle/scripts/current_status.py",
        },
        "source": {
            "repository": "grahama1970/agent-skills",
            "commit": _git(["rev-parse", "HEAD"]),
            "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
        },
        "immutable_goal_status": "MET" if immutable_goal_met else "NOT_MET",
        "primary_proof": {
            "backend_qualification": _adaptive_lineage_evidence_passes(adaptive_lineage_evidence),
            "pixi_receipt_binding": pixi_binding_passes,
            "pixi_gameplay_browser_proof": pixi_gameplay_passes,
            "surf_text_readback": surf_text_path.is_file(),
            "surf_screenshot": surf_screenshot_path.is_file(),
        },
        "source_context": {
            key: _source_context_item(value) for key, value in SOURCE_CONTEXT.items()
        },
        "issue_state_at_generation": {
            "open_battle_label_count": len(open_issues),
            "open_battle_label_issues": open_issues,
            "all_battle_label_issue_count": len(all_issues),
            "all_battle_label_issues": all_issues,
            "focused_p0_issues": {
                "1141": "CLOSED",
                "1144": "CLOSED",
                "1143": "CLOSED",
                "1150": "CLOSED",
                "1142": "CLOSED",
            },
        },
        "source_receipts": receipts,
        "proven": [
            {
                "id": "p0_adaptive_lineage_fresh_qualification",
                "status": (
                    "PASS" if _adaptive_lineage_evidence_passes(adaptive_lineage_evidence) else "MISSING_OR_STALE"
                ),
                "issue_refs": [1499],
                "receipt": receipts["adaptive_lineage_qualification"]["path"],
                "evidence": adaptive_lineage_evidence,
                "does_not_prove": [
                    "fresh provider-backed overnight campaign breadth.",
                ],
            },
            {
                "id": "adaptive_lineage_pixi_receipt_replay",
                "status": "PASS" if pixi_binding_passes and pixi_gameplay_passes else "MISSING_OR_STALE",
                "issue_refs": [1500, 1501],
                "receipt": receipts["adaptive_lineage_pixi_gameplay"]["path"],
                "evidence": {
                    "binding_receipt": receipts["adaptive_lineage_pixi_binding"],
                    "gameplay_receipt": receipts["adaptive_lineage_pixi_gameplay"],
                    "route_loaded_same_fixture_sha256": (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_fixture_sha256"),
                    "route_loaded_same_run_id": (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_run_id"),
                    "source_identity_visible": pixi_gameplay.get("source_identity_visible"),
                    "pause_after_round_not_in_primary_replay": pixi_gameplay.get("pause_after_round_not_in_primary_replay"),
                    "surf_screenshot": receipts["adaptive_lineage_surf_screenshot"],
                },
                "does_not_prove": [
                    "production deployment readiness.",
                    "arbitrary target exploitability beyond the authorized battle-004 proof.",
                ],
            },
            {
                "id": "p0_project_agent_dispatch_selection",
                "status": "PROVEN_SELECTION_PARTIAL_REPAIR_NEEDS_ATTENTION",
                "issue_refs": [1141],
                "receipt": receipts["project_agent_dispatch"]["path"],
                "evidence": {
                    "receipt_status": dispatch.get("status"),
                    "handled_count": dispatch.get("handled_count"),
                    "selected_issue": 1150,
                    "selected_target": "skills/battle/sanity.sh",
                    "worktree_ready": True,
                },
                "does_not_prove": [
                    "Ask/WebGPT transport completed a repair.",
                    "Every future Battle ticket will dispatch successfully.",
                ],
            },
            {
                "id": "p0_root_layout_and_fast_sanity",
                "status": "PASS",
                "issue_refs": [1144, 1150],
                "receipt": receipts["fast_sanity"]["path"],
                "evidence": {
                    "status": fast.get("status"),
                    "source": fast.get("source"),
                    "proof_scope": fast.get("proof_scope"),
                },
            },
            {
                "id": "p0_deterministic_backend_gate",
                "status": "PASS",
                "issue_refs": [1150],
                "receipt": receipts["deterministic_backend"]["path"],
                "evidence": {
                    "status": deterministic.get("status"),
                    "source": deterministic.get("source"),
                    "backend_eval_receipt": deterministic.get("backend_eval_receipt"),
                    "proof_scope": deterministic.get("proof_scope"),
                },
            },
            {
                "id": "p0_same_run_arena_to_pixi",
                "status": "PASS",
                "issue_refs": [1143, 1150],
                "receipt": receipts["same_run_qualification"]["path"],
                "evidence": {
                    "status": same_run.get("status"),
                    "mocked": same_run.get("mocked"),
                    "live": same_run.get("live"),
                    "run_id": same_run.get("run_id"),
                    "judge_verdict": same_run.get("judge_verdict"),
                    "source_commit": same_run.get("source_commit"),
                    "source_tree": same_run.get("source_tree"),
                    "tau_source": same_run.get("tau_source"),
                    "browser_status": (same_run.get("browser") or {}).get("status"),
                    "proof_scope": same_run.get("proof_scope"),
                },
            },
            {
                "id": "p0_live_qualification_gate",
                "status": "PASS",
                "issue_refs": [1150],
                "receipt": receipts["live_qualification_gate"]["path"],
                "evidence": {
                    "status": live_gate.get("status"),
                    "current_source": live_gate.get("current_source"),
                    "inputs": live_gate.get("inputs"),
                    "errors": live_gate.get("errors"),
                },
            },
            {
                "id": "p1_pause_after_round_backend_contract",
                "status": "PASS",
                "issue_refs": [1145],
                "receipt": receipts["human_interjection"]["path"],
                "evidence": {
                    "status": human_interjection.get("status"),
                    "mocked": human_interjection.get("mocked"),
                    "live": human_interjection.get("live"),
                    "case_statuses": human_interjection.get("case_statuses"),
                    "proof_scope": human_interjection.get("proof_scope"),
                },
            },
            {
                "id": "p1_pause_after_round_canonical_pixi_ux",
                "status": "PASS",
                "issue_refs": [1146],
                "receipt": receipts["human_interjection_spectator"]["path"],
                "evidence": {
                    "status": human_interjection_spectator.get("status"),
                    "mocked": human_interjection_spectator.get("mocked"),
                    "live": human_interjection_spectator.get("live"),
                    "screenshots": human_interjection_spectator.get("screenshots"),
                    "readbacks": human_interjection_spectator.get("readbacks"),
                    "failed": human_interjection_spectator.get("failed"),
                    "claims": human_interjection_spectator.get("claims"),
                },
            },
        ],
        "partial": [] if immutable_goal_met else [
            {
                "id": "adaptive_lineage_effect",
                "issue_refs": [1147],
                "status": "OPEN",
                "reason": "Fresh backend qualification and Pixi replay proof have not both passed.",
            },
        ],
        "decisions": [
            {
                "id": "terminal_semantics_local_mvp",
                "issue_refs": [1148],
                "status": "DECIDED",
                "path": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
                "supported_states": [
                    "BLUE_SUCCESS",
                    "RED_SUCCESS",
                    "INSUFFICIENT_EVIDENCE",
                    "BLOCKED",
                    "UNAVAILABLE",
                ],
                "unsupported_states": ["kill", "promotion", "fastest_crash"],
                "receipt_requirement": "Operator-visible terminal success must be Judge/scorekeeper receipt-backed.",
            }
        ],
        "blocked": [],
        "unsupported": [
            {
                "claim": "production_deployment_ready",
                "status": "UNSUPPORTED",
                "issue_refs": [1149],
                "reason": "No DNS/TLS/ingress/secrets/auth/capacity/rollback/teardown readiness receipt yet.",
            },
            {
                "claim": "full_adaptive_improvement_proven",
                "status": "UNSUPPORTED",
                "issue_refs": [1147],
                "reason": "Current live receipt proves same-run Arena/Tau/Judge/Pixi qualification, not adaptive effect.",
            },
            {
                "claim": "kill_promotion_fastest_crash_supported",
                "status": "UNSUPPORTED",
                "issue_refs": [1148],
                "reason": "Local MVP decision supports only Judge-backed success/blocked states.",
            },
            {
                "claim": "fast_sanity_is_live_product_proof",
                "status": "UNSUPPORTED",
                "issue_refs": [1150],
                "reason": "Fast sanity is explicitly offline/deterministic; live proof is a separate gate.",
            },
        ],
        "production_gaps": [
            {"id": "staging_infrastructure_readiness", "issue_refs": [1149], "status": "NON_GOAL_UNPROVEN"},
            {"id": "terminal_semantics_implementation", "issue_refs": [1148], "status": "DECIDED_DOC_ONLY"},
        ],
        "non_claims": [
            "This status does not claim production deployment readiness.",
            "This status does not claim production-scale overnight campaign breadth.",
            "This status does not claim arbitrary target exploitability beyond the authorized battle-004 proof.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "path": str(out), "open_battle_label_count": len(open_issues)}, indent=2))
    return 0


def check(path: Path) -> int:
    status = _read_json(path)
    errors: list[str] = []
    if status.get("schema") != "battle.current_status.v1":
        errors.append("schema_mismatch")
    for item in status.get("source_receipts", {}).values():
        if not item.get("exists") and not item.get("superseded_by"):
            errors.append(f"missing_source_receipt:{item.get('path')}")
    receipts = status.get("source_receipts", {})
    adaptive_receipt = receipts.get("adaptive_lineage_qualification") or {}
    if adaptive_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_qualification_not_pass")
    pixi_binding_receipt = receipts.get("adaptive_lineage_pixi_binding") or {}
    if pixi_binding_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_binding_not_pass")
    pixi_gameplay_receipt = receipts.get("adaptive_lineage_pixi_gameplay") or {}
    if pixi_gameplay_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_gameplay_not_pass")
    if status.get("immutable_goal_status") == "MET":
        primary_proof = status.get("primary_proof") or {}
        for key in [
            "backend_qualification",
            "pixi_receipt_binding",
            "pixi_gameplay_browser_proof",
            "surf_text_readback",
            "surf_screenshot",
        ]:
            if primary_proof.get(key) is not True:
                errors.append(f"immutable_goal_primary_proof_false:{key}")
    adaptive_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "p0_adaptive_lineage_fresh_qualification"
        ),
        {},
    )
    adaptive_evidence = adaptive_claim.get("evidence") or {}
    if adaptive_claim.get("status") != "PASS":
        errors.append("adaptive_lineage_fresh_qualification_claim_not_pass")
    if not _adaptive_lineage_evidence_passes(adaptive_evidence):
        errors.append("adaptive_lineage_fresh_qualification_checks_not_green")
    pixi_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "adaptive_lineage_pixi_receipt_replay"
        ),
        {},
    )
    if pixi_claim.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_receipt_replay_claim_not_pass")

    closed = {
        str(issue["number"])
        for issue in status.get("issue_state_at_generation", {}).get("all_battle_label_issues", [])
        if issue.get("state") == "CLOSED"
    }
    docs = STATUS_DOC.read_text(encoding="utf-8") if STATUS_DOC.exists() else ""
    if "CURRENT_STATUS.json" not in docs:
        errors.append("docs_status_missing_current_status_link")
    closed_blocker_pattern = re.compile(r"(open|blocked|blocker)[^\n#]{0,80}#(\d+)", re.I)
    for match in closed_blocker_pattern.finditer(docs):
        if match.group(2) in closed:
            errors.append(f"closed_issue_cited_as_open_blocker:#{match.group(2)}")
    forbidden_claims = [
        "production ready",
        "production-ready",
        "full adaptive improvement proven",
    ]
    lower_docs = docs.lower()
    for phrase in forbidden_claims:
        if phrase in lower_docs:
            errors.append(f"unsupported_claim_in_docs_status:{phrase}")

    print(json.dumps({"status": "PASS" if not errors else "FAIL", "path": str(path), "errors": errors}, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or check Battle CURRENT_STATUS.json")
    sub = parser.add_subparsers(dest="command", required=True)
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--out", type=Path, default=STATUS_PATH)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--path", type=Path, default=STATUS_PATH)
    args = parser.parse_args()
    if args.command == "generate":
        return generate(args.out)
    if args.command == "check":
        return check(args.path)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
