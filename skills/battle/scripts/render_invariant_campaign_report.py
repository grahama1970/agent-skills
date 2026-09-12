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


def _load_lineage(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "battle.invariant_adaptive_lineage.v1":
        raise ValueError(f"not battle.invariant_adaptive_lineage.v1: {path}")
    return data


def _lineage_cases(paths: list[Path]) -> dict[str, str]:
    marked: dict[str, set[str]] = {}
    for path in paths:
        lineage = _load_lineage(path)
        target = str(lineage.get("target") or path.name)
        for item in lineage.get("red_wins") or []:
            case = item.get("case")
            if case:
                marked.setdefault(str(case), set()).add(target)
        for case in lineage.get("fixed_cases") or []:
            marked.setdefault(str(case), set()).add(target)
    return {case: "yes: adaptive Red win fixed/replayed for " + ", ".join(sorted(targets)) for case, targets in marked.items()}


def _scope(path: Path) -> str:
    name = path.name.lower()
    if "beyond" in name:
        return "beyond-contract"
    if "brief" in name or "fuzz" in name or "contract" in name:
        return "contractual"
    return "campaign"


def _case_description(case: str) -> str:
    words = case.replace("bb-", "").replace("adv-", "").replace("fuzz-", "random ").replace("-", " ")
    specifics = {
        "json-string": "policy value in a JSON string field",
        "csv-cell": "policy value in a CSV cell",
        "utf8-text": "policy value in UTF-8 text",
        "sqlite-text": "policy value in a SQLite TEXT cell",
        "json-integer": "policy phone value encoded as a JSON integer",
        "json-float": "policy phone value encoded as a JSON float",
        "json-scientific": "policy numeric value encoded in JSON scientific notation",
        "adv-formatted-phone-json-integer": "formatted phone policy value represented as an unformatted JSON integer",
        "adv-formatted-phone-csv-bare": "formatted phone policy value represented as bare CSV digits",
        "adv-formatted-phone-text-bare": "formatted phone policy value represented as bare text digits",
        "adv-leading-zero-json-integer": "leading-zero policy number coerced into a lossy JSON integer",
        "adv-lossy-big-json-float": "large numeric policy value coerced into a lossy JSON float",
        "adv-formatted-phone-sqlite-integer": "formatted phone policy value represented as a SQLite integer",
        "adv-cross-format-same-identity-trap": "same identity planted across JSON, CSV, text, and SQLite representations",
        "bb-json-object-key": "policy value hidden in a JSON object key",
        "bb-json-object-key-uescape": "policy value hidden in a Unicode-escaped JSON key",
        "bb-json-object-key-numeric-alias": "numeric alias hidden in a JSON object key",
        "bb-json-duplicate-key-sensitive-first": "policy value hidden in the first copy of a duplicate JSON key",
        "bb-json-duplicate-key-sensitive-second": "policy value hidden in the second copy of a duplicate JSON key",
        "bb-csv-header-cell": "policy value hidden in a CSV header",
        "bb-csv-header-numeric-alias": "numeric alias hidden in a CSV header",
        "bb-csv-late-column": "policy value hidden in a later CSV column",
        "bb-csv-multiline-quoted-cell": "policy value hidden inside a multiline quoted CSV cell",
        "bb-json-deep-array": "policy value hidden in a deeply nested JSON array",
        "bb-json-root-string": "JSON file whose root value is the policy string",
        "bb-json-root-int": "JSON file whose root value is the policy integer",
        "bb-jsonl-lines": "JSONL-style records sent through the JSON boundary",
        "bb-sqlite-table-identifier": "policy value hidden in a SQLite table name",
        "bb-sqlite-column-identifier-numeric-alias": "numeric alias hidden in a SQLite column name",
        "bb-sqlite-default-numeric-alias": "numeric alias hidden in a SQLite DEFAULT literal",
        "bb-sqlite-generated-reconstruction": "SQLite generated column reconstructs the policy value",
        "bb-sqlite-partial-index": "policy value hidden in a SQLite partial-index predicate",
        "bb-sqlite-trigger-literal": "policy value hidden in a SQLite trigger body",
        "bb-utf16le-text": "policy value hidden in UTF-16LE text",
        "bb-utf16le-bomless-text": "policy value hidden in BOM-less UTF-16LE text",
        "bb-filename-value": "policy value hidden in the released filename",
        "bb-filename-numeric-alias": "numeric alias hidden in the released filename",
    }
    return specifics.get(case, f"attack case: {words}")


def _why_chosen(scope: str, case: str) -> str:
    if scope == "contractual":
        return "required by frozen acceptance contract"
    if "schema" in case or "identifier" in case or "key" in case or "header" in case:
        return "schema and names are release surfaces, not just row values"
    if "utf16" in case or "filename" in case:
        return "release artifacts can leak through encoding or path surfaces"
    if "numeric" in case or "root-int" in case or "default" in case or "generated" in case or "partial-index" in case:
        return "typed/canonical aliases previously caused the disqualification class"
    return "chosen to search beyond the written contract for realistic release-boundary leaks"


def _row_result(item: dict[str, Any]) -> str:
    if item.get("verdict") == "FAIL" or item.get("passed") is False:
        return "RED_WIN"
    execution = item.get("execution") if isinstance(item.get("execution"), dict) else {}
    if execution.get("kind") == "ACCEPT" or execution.get("exit_code") == 0:
        return "ACCEPTED_CLEAN"
    return "BLOCKED_FAIL_CLOSED"


def _md(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")


def _attack_rows(campaigns: list[tuple[Path, dict[str, Any]]], lineage: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path, campaign in campaigns:
        cases = campaign.get("case_receipts") or campaign.get("case_log") or campaign.get("failures") or []
        for item in cases:
            case = item.get("case_id") or item.get("case") or "campaign-level"
            violations = item.get("violations") or []
            scope = _scope(path)
            rows.append({
                "scope": scope,
                "contractual": "yes" if scope == "contractual" else "no",
                "adaptive_lineage": lineage.get(str(case), "no"),
                "campaign": path.name,
                "case": str(case),
                "description": str(item.get("description") or _case_description(str(case))),
                "why_chosen": str(item.get("why_chosen") or _why_chosen(scope, str(case))),
                "expectation": str(item.get("expectation") or "unknown"),
                "result": _row_result(item),
                "evidence": "; ".join(str(v) for v in violations) or "Judge passed; no policy value survived.",
            })
    return rows


def _markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "## Exploits Table",
        "",
        "Plain-English scan: contractual rows are the frozen acceptance-contract floor; beyond-contract rows say why Battle chose the probe. `RED_WIN` blocks release. Adaptive lineage marks cases Red discovered, Blue fixed, and Judge replayed.",
        "",
        "| Scope | Contractual? | Adaptive lineage? | Case | Exploit / attack | Why chosen | Expectation | Result | Judge evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| all | all campaigns | none | n/a | NO_CASES_RECORDED | Campaign had no case_log rows. |")
    else:
        for row in rows:
            lines.append(
                f"| {_md(row['scope'])} | {_md(row['contractual'])} | {_md(row['adaptive_lineage'])} | {_md(row['case'])} | {_md(row['description'])} | {_md(row['why_chosen'])} | {_md(row['expectation'])} | {_md(row['result'])} | {_md(row['evidence'])} |"
            )
    return "\n".join(lines) + "\n"


def build_report(*, campaigns: list[Path], project_state: Path, target: str, adaptive_lineage: list[Path] | None = None) -> tuple[dict[str, Any], str]:
    loaded = [(path, _load_campaign(path)) for path in campaigns]
    lineage_paths = adaptive_lineage or []
    lineage = _lineage_cases(lineage_paths)
    current_state, goals = _load_project_state(project_state)
    attack_rows = _attack_rows(loaded, lineage)
    red_win_rows = [row for row in attack_rows if row["result"] == "RED_WIN"]
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
        "core_conclusion": f"No Judge-confirmed exploits survived {len(attack_rows)} attempted attack cases." if all_passed else f"{len(red_win_rows)} Judge-confirmed exploit rows require repair and replay.",
        "evidence_basis": "Battle campaign receipts plus project-state artifact; Markdown appends the exploits table derived from every campaign case_log row, including contractual and beyond-contract cases, descriptions, selection rationale, and adaptive-lineage marks.",
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
            *[
                {"id": f"L-{i + 1:03d}", "kind": "battle-adaptive-lineage", "path": str(path), "limitation": "marks which rows came from adaptive Red wins fixed and replayed"}
                for i, path in enumerate(lineage_paths)
            ],
        ],
        "findings": [
            {
                "id": "F-001",
                "title": "Battle invariant campaign exploit status",
                "status": "Verified" if all_passed else "Needs Changes",
                "evidence": evidence + [f"exploits_table_rows={len(attack_rows)}", f"red_win_rows={len(red_win_rows)}", f"adaptive_lineage_rows={sum(1 for row in attack_rows if row['adaptive_lineage'] != 'no')}"],
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
            "broken": [] if all_passed else [row["case"] for row in red_win_rows],
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
    return report, _markdown_table(attack_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Battle invariant report through create-report.")
    parser.add_argument("--campaign", action="append", required=True, type=Path, help="Battle invariant campaign result/log; repeatable.")
    parser.add_argument("--adaptive-lineage", action="append", default=[], type=Path, help="battle.invariant_adaptive_lineage.v1 receipt; repeatable.")
    parser.add_argument("--project-state", required=True, type=Path, help="Project-state JSON/Markdown artifact used as report context.")
    parser.add_argument("--target", default="target")
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    args = parser.parse_args()

    report, exploits_table = build_report(campaigns=args.campaign, project_state=args.project_state, target=args.target, adaptive_lineage=args.adaptive_lineage)
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
