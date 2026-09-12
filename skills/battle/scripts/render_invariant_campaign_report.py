#!/usr/bin/env python3
"""Render Battle invariant campaign evidence through create-report.

Inputs: one or more battle.invariant_campaign_result.v1 artifacts plus a
project-state artifact. Outputs: create_report.report.v1 JSON and Markdown with
an explicit exploits table.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BATTLE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BATTLE_DIR.parents[1]
CREATE_REPORT = REPO_ROOT / "skills" / "create-report" / "run.sh"


def _load_campaign(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"campaign JSON not found: {path}")
    data = json.loads(text[start:end + 1])
    if data.get("schema") != "battle.invariant_campaign_result.v1":
        raise ValueError(f"not battle.invariant_campaign_result.v1: {path}")
    return data


def _load_project_state(path: Path) -> tuple[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return (text.splitlines()[0] if text.splitlines() else "project-state text artifact", [str(path)])
    state = data.get("readiness") or data.get("status") or data.get("state") or "project-state JSON artifact"
    goals = data.get("goals") if isinstance(data.get("goals"), list) else []
    return str(state), [str(item) for item in goals]


def _campaign_summary(path: Path, campaign: dict[str, Any]) -> str:
    return (
        f"{path}: {'PASS' if campaign.get('passed') else 'FAIL'} "
        f"({campaign.get('cases_passed')}/{campaign.get('cases_total')} versions clean; "
        f"failures={len(campaign.get('failures') or [])})"
    )


def _exploit_rows(campaigns: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path, campaign in campaigns:
        for failure in campaign.get("failures") or []:
            case = failure.get("case") or "campaign-level"
            rows.append({
                "campaign": path.name,
                "case": str(case),
                "expectation": str(failure.get("expectation") or "unknown"),
                "outcome": "RED_WIN",
                "evidence": "; ".join(str(v) for v in failure.get("violations") or []) or "failure recorded",
            })
    return rows


def _markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "## Exploits Table",
        "",
        "| Campaign | Case | Expectation | Outcome | Judge evidence |",
        "|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| all campaigns | none | n/a | NO_JUDGE_CONFIRMED_EXPLOIT | No campaign failure rows. |")
    else:
        for row in rows:
            lines.append(
                f"| {row['campaign']} | {row['case']} | {row['expectation']} | {row['outcome']} | {row['evidence'].replace('|', '/')} |"
            )
    return "\n".join(lines) + "\n"


def build_report(*, campaigns: list[Path], project_state: Path, target: str) -> tuple[dict[str, Any], str]:
    loaded = [(path, _load_campaign(path)) for path in campaigns]
    current_state, goals = _load_project_state(project_state)
    exploit_rows = _exploit_rows(loaded)
    all_passed = all(campaign.get("passed") is True for _, campaign in loaded)
    evidence = [_campaign_summary(path, campaign) for path, campaign in loaded]
    report = {
        "schema": "create_report.report.v1",
        "report_id": f"battle-invariant-{target}",
        "title": f"Battle Invariant Report: {target}",
        "persona": "Battle scorekeeper",
        "primary_object": target,
        "decision_supported": "decide whether the invariant campaign found exploitable release-boundary leaks",
        "overall_finding": "Ready" if all_passed else "Needs Changes",
        "core_conclusion": "No Judge-confirmed exploits survived the supplied campaigns." if all_passed else "One or more Judge-confirmed exploits require repair and replay.",
        "evidence_basis": "Battle campaign receipts plus project-state artifact; Markdown appends the exploits table derived from campaign failure rows.",
        "highest_risk_issues": [] if all_passed else ["F-001 Judge-confirmed Battle exploits remain"],
        "immediate_next_steps": [] if all_passed else ["A-001 Patch each Red win and rerun Battle replay"],
        "scope": {
            "reviewed": [target, "Battle invariant campaign receipts", "project-state artifact"],
            "excluded": ["unbounded exploit search", "manual human approval"],
            "evidence_available": evidence + [str(project_state)],
        },
        "project_context": {
            "goals": goals,
            "current_state": current_state,
            "sources": [str(project_state)],
        },
        "source_of_truth_inventory": [
            {"id": "S-001", "kind": "project-state", "path": str(project_state), "limitation": "project context only; Battle receipts decide exploit outcome"},
            *[
                {"id": f"S-{i + 2:03d}", "kind": "battle-campaign", "path": str(path), "limitation": "bounded campaign receipt, not unbounded exploit proof"}
                for i, (path, _) in enumerate(loaded)
            ],
        ],
        "findings": [
            {
                "id": "F-001",
                "title": "Battle invariant campaign exploit status",
                "status": "Verified" if all_passed else "Needs Changes",
                "evidence": evidence + [f"exploits_table_rows={len(exploit_rows)}"],
                "rationale": "The independent Judge, not team self-report, scored each generated version.",
                "impact": "Determines whether release-boundary PII leaks require another Blue repair cycle.",
                "owner": "Battle scorekeeper",
                "valid_next_actions": ["rerun Battle with broader generators", "patch Judge-confirmed Red wins"],
                "acceptance_check": "create-report validate passes and the Markdown contains ## Exploits Table",
                "non_claims": ["does not prove all possible exploit classes", "does not replace human acceptance review"],
            }
        ],
        "surface_contracts": [],
        "state_split": {
            "finished": evidence if all_passed else [],
            "pending": [],
            "outstanding": [] if all_passed else ["Patch and replay Judge-confirmed Red wins"],
            "broken": [] if all_passed else [row["case"] for row in exploit_rows],
            "blocked": [],
            "unproven": ["unbounded exploit search", "human approval"],
        },
        "plan_ready_next_actions": [] if all_passed else [
            {
                "id": "A-001",
                "related_finding": "F-001",
                "action": "Patch every Judge-confirmed Red win and rerun the same campaigns.",
                "owner_persona": "Blue team",
                "primary_object": target,
                "rationale": "Battle found an invariant violation in the release boundary.",
                "acceptance_check": "all replay campaign receipts pass and the exploits table is empty",
                "dependencies": [],
                "risk_if_skipped": "Known exploit remains reproducible",
                "suggested_priority": "P0",
            }
        ],
        "plan_iterate_seed": None if all_passed else {
            "recommended_phase_id": "battle-red-win-repair",
            "objective": "Remove Judge-confirmed Battle exploit rows and replay the same campaigns.",
            "candidate_phases": ["patch target", "rerun Battle", "regenerate create-report"],
            "deterministic_evidence_gates": ["Battle campaign replay PASS", "skills/create-report/run.sh validate <report.json>"],
            "domain_review_loops": [],
            "interaction_evidence": "not required",
            "ask_persona_review": "optional after deterministic replay",
            "dogpile_reference_research": "only if exploit class is unknown",
            "human_decisions": [],
            "stop_conditions": ["Judge replay still fails", "missing project-state artifact"],
            "non_claims": ["does not prove unbounded exploit absence"],
        },
        "non_claims": ["This report does not prove all possible PII representations or unbounded adversarial search."],
    }
    return report, _markdown_table(exploit_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Battle invariant report through create-report.")
    parser.add_argument("--campaign", action="append", required=True, type=Path, help="Battle invariant campaign result/log; repeatable.")
    parser.add_argument("--project-state", required=True, type=Path, help="Project-state JSON/Markdown artifact used as report context.")
    parser.add_argument("--target", default="target")
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    args = parser.parse_args()

    report, exploits_table = build_report(campaigns=args.campaign, project_state=args.project_state, target=args.target)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validate = subprocess.run([str(CREATE_REPORT), "validate", str(args.out_json)], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if validate.returncode != 0:
        sys.stderr.write(validate.stdout + validate.stderr)
        return validate.returncode
    render = subprocess.run([str(CREATE_REPORT), "render", str(args.out_json), "--format", "markdown", "--output", str(args.out_md)], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if render.returncode != 0:
        sys.stderr.write(render.stdout + render.stderr)
        return render.returncode
    with args.out_md.open("a", encoding="utf-8") as handle:
        handle.write("\n" + exploits_table)
    print(json.dumps({"schema": "battle.invariant_report_result.v1", "status": "PASS", "report_json": str(args.out_json), "report_md": str(args.out_md), "campaigns": len(args.campaign)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
