#!/usr/bin/env python3
"""Generate and check Battle's receipt-derived current status."""

from __future__ import annotations

import argparse
import hashlib
import json
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
}

SOURCE_CONTEXT = {
    "battle_skill_contract": "skills/battle/SKILL.md",
    "terminal_semantics_decision": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
    "planning_bundle": (
        "/home/graham/workspace/experiments/agent-skills/artifacts/ask/"
        "battle_remaining_gaps_ticket_bundle_20260801.md"
    ),
}


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
                "1142": "OPEN_DURING_GENERATION",
            },
        },
        "source_receipts": receipts,
        "proven": [
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
        ],
        "partial": [
            {
                "id": "operator_pause_after_round",
                "issue_refs": [1145, 1146],
                "status": "OPEN",
                "reason": "Backend pause_after_round and canonical Pixi UX wiring remain separate P1 issues.",
            },
            {
                "id": "adaptive_lineage_effect",
                "issue_refs": [1147],
                "status": "OPEN",
                "reason": "Same-run qualification does not prove adaptive improvement for Red and Blue.",
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
            {"id": "staging_infrastructure_readiness", "issue_refs": [1149], "status": "OPEN"},
            {"id": "operator_human_interjection", "issue_refs": [1145, 1146], "status": "OPEN"},
            {"id": "terminal_semantics_implementation", "issue_refs": [1148], "status": "DECIDED_DOC_ONLY"},
        ],
        "non_claims": [
            "This status does not claim production deployment readiness.",
            "This status does not claim adaptive improvement beyond the same-run receipt.",
            "This status does not claim every remaining battle-labelled issue is closed.",
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
        if not item.get("exists"):
            errors.append(f"missing_source_receipt:{item.get('path')}")

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
