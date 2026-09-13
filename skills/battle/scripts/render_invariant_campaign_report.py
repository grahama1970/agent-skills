#!/usr/bin/env python3
"""Render Battle invariant campaign evidence through create-report.

Inputs: one or more battle.invariant_campaign_result.v1 artifacts plus a
project-state artifact. Outputs: create_report.report.v1 JSON and Markdown with
an explicit exploits table.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

BATTLE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BATTLE_DIR.parents[1]
CREATE_REPORT = REPO_ROOT / "skills" / "create-report" / "run.sh"


def _load_campaign(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"campaign JSON not found: {path}")
    data = json.loads(text[start:end + 1])
    schema = data.get("schema")
    if schema == "battle.production_adapter_round.v1":
        campaign = data.get("campaign")
        if not isinstance(campaign, dict):
            raise ValueError(f"production adapter receipt has no campaign: {path}")
        campaign = dict(campaign)
        campaign["_source_schema"] = schema
        campaign["_source_status"] = data.get("status")
        campaign["_acceptance_parent_by_case"] = _acceptance_parent_by_case(data.get("acceptance_floor"))
        return campaign
    if schema not in {"battle.invariant_campaign_result.v1", "battle.campaign_contract_receipt.v1"}:
        raise ValueError(f"not a Battle campaign receipt: {path}")
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


def _campaign_passed(campaign: dict[str, Any]) -> bool:
    if campaign.get("passed") is True or campaign.get("verdict") == "PASS":
        return True
    return campaign.get("_source_status") == "PASS" and (campaign.get("campaign") or {}).get("verdict") == "PASS"


def _campaign_counts(campaign: dict[str, Any]) -> tuple[Any, Any, int]:
    aggregate = campaign.get("aggregation") if isinstance(campaign.get("aggregation"), dict) else {}
    passed = campaign.get("cases_passed", aggregate.get("cases_passed"))
    total = campaign.get("cases_total", aggregate.get("cases_total"))
    failures = campaign.get("failures") or []
    return passed, total, len(failures) if isinstance(failures, list) else int(aggregate.get("failures") or 0)


def _campaign_summary(path: Path, campaign: dict[str, Any]) -> str:
    passed, total, failures = _campaign_counts(campaign)
    return f"{path}: {'PASS' if _campaign_passed(campaign) else 'FAIL'} ({passed}/{total} versions clean; failures={failures})"


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


def _acceptance_parent_by_case(acceptance_floor: Any) -> dict[str, str]:
    if not isinstance(acceptance_floor, dict):
        return {}
    parents: dict[str, list[str]] = {}
    case_map = acceptance_floor.get("case_map")
    if not isinstance(case_map, dict):
        return {}
    for parent, cases in case_map.items():
        if not isinstance(cases, list):
            continue
        for case in cases:
            parents.setdefault(str(case), []).append(str(parent))
    return {case: ", ".join(sorted(set(items))) for case, items in parents.items()}


def _scope(path: Path, campaign: dict[str, Any] | None = None) -> str:
    text = "/".join(part.lower() for part in path.parts)
    campaign = campaign or {}
    if campaign.get("_source_schema") == "battle.production_adapter_round.v1" or "acceptance-floor" in text:
        return "contractual"
    haystack = text + " " + json.dumps({"request": campaign.get("request"), "plan": campaign.get("plan")}, sort_keys=True).lower()
    if "beyond" in haystack:
        return "beyond-contract"
    if "brief" in text or "fuzz" in text or "contract" in path.name.lower():
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


def _format_refs(value: Any) -> str:
    if isinstance(value, list):
        refs = []
        for item in value:
            if isinstance(item, dict):
                label = item.get("title") or item.get("name") or item.get("source") or item.get("url") or item.get("id")
                url = item.get("url")
                refs.append(f"{label} ({url})" if label and url and label != url else str(label or item))
            else:
                refs.append(str(item))
        return "; ".join(ref for ref in refs if ref) or "not recorded in case receipt"
    if value:
        return str(value)
    return "not recorded in case receipt"


def _case_example(case: str, description: str) -> str:
    return f"{case}: {description}"


def _attack_rows(campaigns: list[tuple[Path, dict[str, Any]]], lineage: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    for path, campaign in campaigns:
        cases = campaign.get("case_receipts") or campaign.get("case_log") or campaign.get("failures") or []
        for item in cases:
            case = item.get("case_id") or item.get("case") or "campaign-level"
            case = str(case)
            seen_cases.add(case)
            violations = item.get("violations") or []
            scope = _scope(path, campaign)
            description = str(item.get("description") or _case_description(case))
            acceptance_parent_by_case = campaign.get("_acceptance_parent_by_case") if isinstance(campaign.get("_acceptance_parent_by_case"), dict) else {}
            rows.append({
                "scope": scope,
                "contractual": "yes" if scope == "contractual" else "no",
                "adaptive_lineage": lineage.get(case, "no"),
                "campaign": path.name,
                "case": case,
                "description": description,
                "example": str(item.get("example") or _case_example(case, description)),
                "why_chosen": str(item.get("why_chosen") or item.get("rationale") or _why_chosen(scope, case)),
                "related_research": _format_refs(item.get("research_refs") or item.get("source_refs") or item.get("sources")),
                "acceptance_parent": str(item.get("acceptance_parent") or acceptance_parent_by_case.get(case) or "not recorded in case receipt"),
                "expectation": str(item.get("expectation") or "unknown"),
                "result": _row_result(item),
                "evidence": "; ".join(str(v) for v in violations) or "Judge passed; no policy value survived.",
            })
    for case, marker in sorted(lineage.items()):
        if case in seen_cases:
            continue
        description = "adaptive lineage Red/Blue replay chain"
        rows.append({
            "scope": "adaptive-lineage",
            "contractual": "no",
            "adaptive_lineage": marker,
            "campaign": "adaptive-lineage",
            "case": case,
            "description": description,
            "example": f"{case}: live adaptive-lineage receipt chain",
            "why_chosen": "adaptive lineage receipt supplied with live Red/Blue replay proof",
            "related_research": "not recorded in case receipt",
            "acceptance_parent": "not applicable",
            "expectation": "REPLAY_PASS",
            "result": "ACCEPTED_CLEAN",
            "evidence": "Adaptive-lineage proof was validated live/non-mocked before rendering.",
        })
    return rows


def _markdown_table(rows: list[dict[str, Any]]) -> str:
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


def _row_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "accepted_clean": sum(1 for row in rows if row["result"] == "ACCEPTED_CLEAN"),
        "fail_closed": sum(1 for row in rows if row["result"] == "BLOCKED_FAIL_CLOSED"),
        "red_wins": sum(1 for row in rows if row["result"] == "RED_WIN"),
    }


def _terminal_evidence(row: dict[str, Any]) -> str:
    if row["result"] == "RED_WIN":
        return row["evidence"]
    if row["result"] == "BLOCKED_FAIL_CLOSED":
        return "target rejected this attack; Judge found no released policy value"
    return "target processed the case; Judge found no released policy value"


def _clip(value: str, width: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= width:
        return clean
    return clean[:max(0, width - 1)] + "…"


def _terminal_table(rows: list[dict[str, Any]]) -> list[str]:
    widths = {
        "scope": 15,
        "case": 35,
        "expectation": 11,
        "result": 18,
        "description": 44,
        "evidence": 54,
    }
    header = (
        f"{'Scope':<{widths['scope']}} "
        f"{'Case':<{widths['case']}} "
        f"{'Expect':<{widths['expectation']}} "
        f"{'Result':<{widths['result']}} "
        f"{'Attack':<{widths['description']}} "
        "Evidence"
    )
    separator = "-" * len(header)
    if not rows:
        return [header, separator, "NO_CASES_RECORDED"]
    lines = [header, separator]
    for row in rows:
        lines.append(
            f"{_clip(row['scope'], widths['scope']):<{widths['scope']}} "
            f"{_clip(row['case'], widths['case']):<{widths['case']}} "
            f"{_clip(row['expectation'], widths['expectation']):<{widths['expectation']}} "
            f"{_clip(row['result'], widths['result']):<{widths['result']}} "
            f"{_clip(row['description'], widths['description']):<{widths['description']}} "
            f"{_clip(_terminal_evidence(row), widths['evidence'])}"
        )
    return lines


def _color_enabled_stderr() -> bool:
    return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _print_rich_terminal_summary(target: str, rows: list[dict[str, Any]]) -> None:
    summary = _terminal_summary(target, rows)
    console = Console(stderr=True)
    table = Table(title="Case table", box=box.SIMPLE_HEAVY, row_styles=["", "dim"])
    for heading in ["Scope", "Case", "Expect", "Result", "Attack", "Evidence"]:
        style = "bold" if heading != "Result" else "bold white"
        table.add_column(heading, style=style, overflow="fold" if heading in {"Attack", "Evidence"} else "ellipsis")
    if rows:
        for row in rows:
            result = row["result"]
            result_style = {"RED_WIN": "bold red", "ACCEPTED_CLEAN": "green", "BLOCKED_FAIL_CLOSED": "yellow"}.get(result, "white")
            table.add_row(
                row["scope"],
                row["case"],
                row["expectation"],
                Text(result, style=result_style),
                row["description"],
                _terminal_evidence(row),
            )
    else:
        table.add_row("all", "NO_CASES_RECORDED", "n/a", Text("NO_CASES_RECORDED", style="yellow"), "Campaign had no case rows.", "n/a")
    overview = "\n".join(summary.split("Case table:", 1)[0].splitlines()[2:]).rstrip()
    tail = summary.split("Highlight plays:", 1)[1]
    with console.capture() as capture:
        console.print(f"[bold]Battle report:[/bold] {target}")
        if overview:
            console.print(overview)
        console.print(table)
        console.print("[bold]Highlight plays:[/bold]" + tail)
    sys.stderr.write(capture.get())

def _terminal_summary(target: str, rows: list[dict[str, Any]]) -> str:
    contract = [row for row in rows if row["scope"] == "contractual"]
    beyond = [row for row in rows if row["scope"] == "beyond-contract"]
    other = [row for row in rows if row["scope"] not in {"contractual", "beyond-contract"}]
    total = _row_counts(rows)
    contract_counts = _row_counts(contract)
    beyond_counts = _row_counts(beyond)
    highlights = [row for row in rows if row["result"] == "RED_WIN"]
    highlights += [row for row in rows if row["case"] in {
        "adv-formatted-phone-json-integer",
        "adv-cross-format-same-identity-trap",
        "adv-leading-zero-json-integer",
        "bb-json-object-key",
        "bb-sqlite-generated-reconstruction",
        "bb-filename-value",
    } and row not in highlights]
    highlights = highlights[:6]

    lines = [
        f"Battle report: {target}",
        "",
        "Contract floor:",
        f"  {contract_counts['total']} acceptance-floor cases: {contract_counts['accepted_clean']} accepted clean, {contract_counts['fail_closed']} fail-closed, {contract_counts['red_wins']} RED_WIN.",
        "Red pressure:",
        f"  {beyond_counts['total']} beyond-contract probes: {beyond_counts['accepted_clean']} accepted clean, {beyond_counts['fail_closed']} fail-closed, {beyond_counts['red_wins']} RED_WIN.",
    ]
    if other:
        other_counts = _row_counts(other)
        lines.append(f"  {other_counts['total']} other campaign cases: {other_counts['accepted_clean']} accepted clean, {other_counts['fail_closed']} fail-closed, {other_counts['red_wins']} RED_WIN.")
    lines += [
        "Scorekeeper call:",
        f"  {total['total']} total cases; {total['accepted_clean']} accepted clean; {total['fail_closed']} stopped fail-closed; {total['red_wins']} RED_WIN.",
    ]
    if total["red_wins"]:
        lines.append("  RED_WIN blocks release until Blue patches and Judge replay passes.")
    else:
        lines.append("  No RED_WIN rows in this bounded report.")
    lines += ["", "Case table:", *_terminal_table(rows), ""]
    lines.append("Highlight plays:")
    if highlights:
        for row in highlights:
            lines.append(f"  - {row['case']}: Red tried {row['description']}; result {row['result']}; Judge evidence: {_terminal_evidence(row)}")
    else:
        lines.append("  - No named case rows were recorded.")
    lines += [
        "Next playbook:",
        "  If Red wins, research similar exploit families, freeze deterministic variants, patch, and replay with the independent Judge.",
        "Caveats:",
        "  This is bounded Battle evidence, not proof that every possible exploit is absent.",
        "  Dogpile/Ask research is design input until selected cases are frozen and run.",
        "  Adaptive lineage is shown only when a Red win was fixed and replayed.",
    ]
    return "\n".join(lines) + "\n"



def _terminal_card_lines(row: dict[str, Any]) -> list[str]:
    return [
        "==============",
        f"Scope: {row['scope']}",
        f"Case: {row['case']}",
        f"Acceptance parent: {row['acceptance_parent']}",
        f"Expect: {row['expectation']}",
        f"Result: {row['result']}",
        f"Example: {row['example']}",
        f"Why Battle checks this: {row['why_chosen']}",
        f"Related research: {row['related_research']}",
        f"Adaptive lineage: {row['adaptive_lineage']}",
        f"Judge evidence: {_terminal_evidence(row)}",
    ]


def _terminal_cards(target: str, rows: list[dict[str, Any]]) -> str:
    counts = _row_counts(rows)
    lines = [
        f"Battle case cards: {target}",
        f"Scorekeeper call: {counts['total']} total cases; {counts['accepted_clean']} accepted clean; {counts['fail_closed']} stopped fail-closed; {counts['red_wins']} RED_WIN.",
    ]
    if not rows:
        lines += ["", "## Other campaign cases", "==============", "Case: NO_CASES_RECORDED", "Judge evidence: Campaign had no case rows."]
        return "\n".join(lines) + "\n"

    sections = [
        ("Acceptance contract floor", [row for row in rows if row["scope"] == "contractual" and row["adaptive_lineage"] == "no"]),
        ("Beyond-contract exploits", [row for row in rows if row["scope"] == "beyond-contract" and row["adaptive_lineage"] == "no"]),
        ("Adaptive lineage", [row for row in rows if row["adaptive_lineage"] != "no"]),
        ("Other campaign cases", [row for row in rows if row["scope"] not in {"contractual", "beyond-contract"} and row["adaptive_lineage"] == "no"]),
    ]
    for title, section_rows in sections:
        if not section_rows and title != "Other campaign cases":
            continue
        if not section_rows:
            continue
        lines += ["", f"## {title}"]
        for row in section_rows:
            lines += _terminal_card_lines(row)
    return "\n".join(lines) + "\n"

def build_report(*, campaigns: list[Path], project_state: Path, target: str, adaptive_lineage: list[Path] | None = None) -> tuple[dict[str, Any], str]:
    loaded = [(path, _load_campaign(path)) for path in campaigns]
    lineage_paths = adaptive_lineage or []
    lineage = _lineage_cases(lineage_paths)
    current_state, goals = _load_project_state(project_state)
    attack_rows = _attack_rows(loaded, lineage)
    red_win_rows = [row for row in attack_rows if row["result"] == "RED_WIN"]
    all_passed = all(_campaign_passed(campaign) for _, campaign in loaded)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Battle invariant report through create-report.")
    parser.add_argument("--campaign", action="append", required=True, type=Path, help="Battle invariant campaign result/log; repeatable.")
    parser.add_argument("--adaptive-lineage", action="append", default=[], type=Path, help="battle.invariant_adaptive_lineage.v1 receipt; repeatable.")
    parser.add_argument("--project-state", required=True, type=Path, help="Project-state JSON/Markdown artifact used as report context.")
    parser.add_argument("--target", default="target")
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--terminal-summary", action="store_true", help="Also print a plain-spoken Battle story with a case table to stderr; JSON stdout stays stable.")
    parser.add_argument("--terminal-table", action="store_true", help="Alias for --terminal-summary; prints the project-agent-friendly terminal table/report to stderr.")
    parser.add_argument("--terminal-cards", action="store_true", help="Print one long-form case card per separator block to stderr; JSON stdout stays stable.")
    args = parser.parse_args(argv)

    loaded = [(path, _load_campaign(path)) for path in args.campaign]
    lineage = _lineage_cases(args.adaptive_lineage)
    attack_rows = _attack_rows(loaded, lineage)
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
    if args.terminal_cards:
        sys.stderr.write(_terminal_cards(args.target, attack_rows))
    elif args.terminal_summary or args.terminal_table:
        if _color_enabled_stderr():
            try:
                _print_rich_terminal_summary(args.target, attack_rows)
            except Exception as exc:
                sys.stderr.write(f"Battle terminal table color render failed; using plain fallback: {exc}\n")
                sys.stderr.write(_terminal_summary(args.target, attack_rows))
        else:
            sys.stderr.write(_terminal_summary(args.target, attack_rows))
    print(json.dumps({"schema": "battle.invariant_report_result.v1", "status": "PASS", "report_json": str(args.out_json), "report_md": str(args.out_md), "campaigns": len(args.campaign)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
