#!/usr/bin/env python3
"""JSON-first create-report contract and renderers."""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[3]
TRIAGE = ROOT / "skills" / "triage-error" / "run.sh"

FindingStatus = Literal[
    "Verified", "Unverified", "Stale", "Blocked", "Needs Decision", "Needs Changes"
]
OverallFinding = Literal["Ready", "Needs Changes", "Blocked", "Degraded", "Unknown", "Partially Verified"]
Priority = Literal["P0", "P1", "P2", "P3"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    path: str = Field(min_length=1)
    limitation: str = Field(min_length=1)


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed: list[str] = Field(min_length=1)
    excluded: list[str] = Field(default_factory=list)
    evidence_available: list[str] = Field(min_length=1)


class ProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goals: list[str] = Field(default_factory=list)
    current_state: str = Field(min_length=1)
    recent_decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    takeover_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class SurfaceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    owning_persona: str = Field(min_length=1)
    core_purpose: str = Field(min_length=1)
    primary_object: str = Field(min_length=1)
    source_of_truth: str = Field(min_length=1)
    valid_actions: list[str] = Field(min_length=1)
    outstanding_broken_constraints: list[str] = Field(min_length=1)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^F-[0-9]{3}$")
    title: str = Field(min_length=1)
    status: FindingStatus
    evidence: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    valid_next_actions: list[str] = Field(min_length=1)
    acceptance_check: str = Field(min_length=1)
    non_claims: list[str] = Field(min_length=1)


class StateSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finished: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    outstanding: list[str] = Field(default_factory=list)
    broken: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)
    unproven: list[str] = Field(default_factory=list)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^A-[0-9]{3}$")
    related_finding: str = Field(pattern=r"^F-[0-9]{3}$")
    action: str = Field(min_length=1)
    owner_persona: str = Field(min_length=1)
    primary_object: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    acceptance_check: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    risk_if_skipped: str = Field(min_length=1)
    suggested_priority: Priority


class PlanIterateSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommended_phase_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    candidate_phases: list[str] = Field(min_length=1)
    deterministic_evidence_gates: list[str] = Field(min_length=1)
    domain_review_loops: list[str] = Field(default_factory=list)
    interaction_evidence: str = Field(min_length=1)
    ask_persona_review: str = Field(min_length=1)
    dogpile_reference_research: str = Field(min_length=1)
    human_decisions: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(min_length=1)
    non_claims: list[str] = Field(min_length=1)


class CreateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["create_report.report.v1"] = Field(alias="schema")
    report_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    primary_object: str = Field(min_length=1)
    decision_supported: str = Field(min_length=1)
    overall_finding: OverallFinding
    core_conclusion: str = Field(min_length=1)
    evidence_basis: str = Field(min_length=1)
    highest_risk_issues: list[str] = Field(default_factory=list)
    immediate_next_steps: list[str] = Field(default_factory=list)
    scope: Scope
    project_context: ProjectContext
    source_of_truth_inventory: list[Source] = Field(min_length=1)
    findings: list[Finding] = Field(min_length=1)
    surface_contracts: list[SurfaceContract] = Field(default_factory=list)
    state_split: StateSplit
    plan_ready_next_actions: list[Action] = Field(default_factory=list)
    plan_iterate_seed: PlanIterateSeed | None = None
    non_claims: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def report_contract(self) -> "CreateReport":
        finding_ids = {item.id for item in self.findings}
        for action in self.plan_ready_next_actions:
            if action.related_finding not in finding_ids:
                raise ValueError(f"action {action.id} references missing finding {action.related_finding}")
        if self.plan_ready_next_actions and self.plan_iterate_seed is None:
            raise ValueError("actionable reports require plan_iterate_seed")
        if self.overall_finding == "Ready":
            bad = [item.id for item in self.findings if item.status != "Verified"]
            if bad:
                raise ValueError(f"Ready report has non-verified findings: {bad}")
        return self


def triage(error: Exception) -> dict[str, Any]:
    text = f"create-report pydantic validation failed: {error}"
    if TRIAGE.exists():
        try:
            result = subprocess.run(
                [str(TRIAGE), "classify", "--text", text, "--layer", "create-report"],
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            raw = (result.stdout or result.stderr).strip()
            if raw:
                return json.loads(raw)
        except Exception as exc:
            return {"code": "create-report_unclassified_00000000", "cause": str(exc), "next_command": "skills/triage-error/run.sh classify --text '<create-report validation error>' --layer create-report"}
    return {"code": "create-report_unclassified_00000000", "cause": text[:500], "next_command": "skills/triage-error/run.sh classify --text '<create-report validation error>' --layer create-report"}


def validate_payload(data: dict[str, Any]) -> CreateReport:
    try:
        return CreateReport.model_validate(data)
    except ValidationError as exc:
        payload = {
            "schema": "create_report.validation_failure.v1",
            "triage": triage(exc),
            "error": "create_report.report.v1 validation failed",
        }
        print(json.dumps(payload, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc


def report_from(path: str) -> CreateReport:
    return validate_payload(json.loads(Path(path).read_text()))


def sample() -> dict[str, Any]:
    return {
        "schema": "create_report.report.v1",
        "report_id": "sample-report",
        "title": "Sample Evidence Report",
        "persona": "project maintainer",
        "primary_object": "sample artifact",
        "decision_supported": "decide whether follow-on repair is needed",
        "overall_finding": "Needs Changes",
        "core_conclusion": "The sample demonstrates the JSON-first report contract.",
        "evidence_basis": "Fixture source and pydantic validation output.",
        "highest_risk_issues": ["F-001 Missing live project evidence"],
        "immediate_next_steps": ["A-001 Replace fixture evidence with live artifacts"],
        "scope": {"reviewed": ["fixture report"], "excluded": ["live UI"], "evidence_available": ["fixture JSON"]},
        "project_context": {"goals": ["report from validated JSON"], "current_state": "fixture only", "sources": ["fixtures/sample-report.json"]},
        "source_of_truth_inventory": [{"id": "S-001", "kind": "fixture", "path": "fixtures/sample-report.json", "limitation": "not live evidence"}],
        "findings": [{"id": "F-001", "title": "Missing live project evidence", "status": "Unverified", "evidence": ["fixture JSON only"], "rationale": "The fixture is enough for schema validation, not project truth.", "impact": "Report cannot support a real project decision.", "owner": "project maintainer", "valid_next_actions": ["collect live evidence"], "acceptance_check": "report cites live artifacts", "non_claims": ["does not prove live readiness"]}],
        "surface_contracts": [],
        "state_split": {"unproven": ["live evidence"]},
        "plan_ready_next_actions": [{"id": "A-001", "related_finding": "F-001", "action": "Replace fixture evidence with live artifacts.", "owner_persona": "project maintainer", "primary_object": "source_of_truth_inventory", "rationale": "A real report needs real source artifacts.", "acceptance_check": "validate-report passes and sources exist", "dependencies": [], "risk_if_skipped": "report remains a fixture", "suggested_priority": "P1"}],
        "plan_iterate_seed": {"recommended_phase_id": "replace-fixture-evidence", "objective": "Prove the report against live artifacts.", "candidate_phases": ["collect evidence", "validate JSON", "render report"], "deterministic_evidence_gates": ["skills/create-report/run.sh validate <report.json>"], "domain_review_loops": [], "interaction_evidence": "not required for this fixture", "ask_persona_review": "not required for this fixture", "dogpile_reference_research": "not required for this fixture", "human_decisions": [], "stop_conditions": ["missing source artifact"], "non_claims": ["does not prove production readiness"]},
        "non_claims": ["This sample does not prove any real project state."],
    }


def markdown(r: CreateReport) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) or "- none"

    lines = [
        f"# {r.title}", "",
        "## Report Summary", "",
        f"**Overall Finding:** {r.overall_finding}", "",
        f"**Core Conclusion:**  \n{r.core_conclusion}", "",
        f"**Evidence Basis:**  \n{r.evidence_basis}", "",
        "**Highest-Risk Issues:**", bullets(r.highest_risk_issues), "",
        "**Immediate Next Steps:**", bullets(r.immediate_next_steps), "",
        "**Non-Claims:**", bullets(r.non_claims), "",
        "## Scope", bullets(r.scope.reviewed), "",
        "## Project Context", r.project_context.current_state, "",
        "## Source-of-Truth Inventory", "", "| ID | Kind | Path | Limitation |", "|---|---|---|---|",
    ]
    for source in r.source_of_truth_inventory:
        lines.append(f"| {source.id} | {source.kind} | {source.path} | {source.limitation} |")
    lines.extend(["", "## Findings"])
    for finding in r.findings:
        lines.extend([
            "", f"### Finding: {finding.title}", "",
            f"**Finding ID:** {finding.id}", f"**Status:** {finding.status}",
            f"**Evidence:** {'; '.join(finding.evidence)}", f"**Rationale:** {finding.rationale}",
            f"**Impact:** {finding.impact}", f"**Owner:** {finding.owner}",
            f"**Valid Next Actions:** {'; '.join(finding.valid_next_actions)}",
            f"**Acceptance Check:** {finding.acceptance_check}",
            f"**Non-Claims:** {'; '.join(finding.non_claims)}",
        ])
    lines.extend(["", "## Surface / Module Contracts"])
    if not r.surface_contracts:
        lines.append("- none")
    for surface in r.surface_contracts:
        lines.extend(["", f"### Surface Contract: {surface.name}", f"- Owning Persona: {surface.owning_persona}", f"- Core Purpose: {surface.core_purpose}", f"- Primary Object: {surface.primary_object}", f"- Source of Truth: {surface.source_of_truth}"])
    lines.extend(["", "## Finished / Pending / Outstanding / Broken / Blocked / Unproven", ""])
    for name in ("finished", "pending", "outstanding", "broken", "blocked", "unproven"):
        lines.extend([f"### {name.replace('_', ' ').title()}", bullets(getattr(r.state_split, name)), ""])
    lines.extend(["## Plan-Ready Next Actions", ""])
    for action in r.plan_ready_next_actions:
        lines.extend([f"- **{action.id}** ({action.related_finding}, {action.suggested_priority}): {action.action} Acceptance: {action.acceptance_check}"])
    lines.extend(["", "## Plan-Iterate Seed", ""])
    if r.plan_iterate_seed:
        seed = r.plan_iterate_seed
        lines.extend([f"**Recommended phase id:** `{seed.recommended_phase_id}`", "", f"**Objective:** {seed.objective}", "", "**Deterministic Evidence Gates:**", bullets(seed.deterministic_evidence_gates)])
    else:
        lines.append("No follow-on phase warranted by this report.")
    lines.extend(["", "## New Plan-Iterate Instructions", "", "Use the Plan-Iterate Seed above as the initial phase contract.", "", "## Non-Claims", bullets(r.non_claims), ""])
    return "\n".join(lines)


def html_doc(r: CreateReport) -> str:
    body = html.escape(markdown(r)).replace("\n", "<br>\n")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(r.title)}</title><style>main{{max-width:960px;margin:2rem auto;font:16px/1.6 system-ui,sans-serif}}body{{background:#fafafa;color:#1f2937}}</style></head><body><main>{body}</main></body></html>\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema")
    sp = sub.add_parser("sample"); sp.add_argument("--output")
    vp = sub.add_parser("validate"); vp.add_argument("path")
    rp = sub.add_parser("render"); rp.add_argument("path"); rp.add_argument("--format", choices=["markdown", "html"], default="markdown"); rp.add_argument("--output")
    args = parser.parse_args()

    if args.cmd == "schema":
        print(json.dumps(CreateReport.model_json_schema(), indent=2))
        return 0
    if args.cmd == "sample":
        text = json.dumps(sample(), indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text)
        else:
            print(text, end="")
        return 0
    if args.cmd == "validate":
        report_from(args.path)
        print(json.dumps({"schema": "create_report.validation_result.v1", "valid": True, "validated_schema": "create_report.report.v1"}))
        return 0
    if args.cmd == "render":
        report = report_from(args.path)
        text = html_doc(report) if args.format == "html" else markdown(report)
        if args.output:
            Path(args.output).write_text(text)
        else:
            print(text, end="")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
