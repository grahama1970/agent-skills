"""create-report bridge for acceptance-contract.

The acceptance bundle is the source of truth. This module derives a
create_report.report.v1 JSON view and optionally renders Markdown through the
real create-report skill entrypoint. If that validation/rendering fails, the
acceptance extraction fails closed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .models import AcceptanceBundle


def progress_summary(bundle: AcceptanceBundle) -> dict:
    has_questions = bool(bundle.open_questions)
    checks = [
        ("source-read", "Source bundle was read and hashed", True),
        ("requirements", "Source-backed requirements were extracted", bool(bundle.requirements)),
        ("acceptance-cases", "Executable acceptance cases were extracted", bool(bundle.acceptance_cases)),
        ("open-questions", "No unresolved source questions remain", not has_questions),
        ("human-approval", "Human approved the immutable-goal draft/amendment", False),
        ("docker-or-battle", "Docker/Battle consumed this frozen bundle and passed", False),
    ]
    passed = sum(1 for _, _, ok in checks if ok)
    outstanding = []
    if not bundle.requirements:
        outstanding.append("extract at least one source-backed requirement")
    if not bundle.acceptance_cases:
        outstanding.append("add at least one executable acceptance case")
    outstanding.extend(q.question for q in bundle.open_questions)
    outstanding.append("human approval before GOAL.md mutation")
    outstanding.append("run Docker/Battle with acceptance_bundle.json")
    next_steps = outstanding[:]
    state = "NEEDS_CHANGES" if has_questions or not bundle.requirements or not bundle.acceptance_cases else "READY_FOR_HUMAN_REVIEW"
    return {
        "schema": "acceptance_contract.progress.v1",
        "state": state,
        "percent": round(passed * 100 / len(checks)),
        "passed": passed,
        "total": len(checks),
        "counts": {
            "requirements": len(bundle.requirements),
            "acceptance_cases": len(bundle.acceptance_cases),
            "open_questions": len(bundle.open_questions),
        },
        "checks": [
            {"id": cid, "label": label, "status": "PASS" if ok else "PENDING"}
            for cid, label, ok in checks
        ],
        "outstanding": outstanding,
        "next_steps": next_steps,
    }


def build_report(bundle: AcceptanceBundle) -> dict:
    progress = progress_summary(bundle)
    has_questions = bool(bundle.open_questions)
    status = "Needs Changes" if has_questions else "Partially Verified"
    finding_status = "Needs Decision" if has_questions else "Unverified"
    evidence = [f"{req.source_path}:{req.source_line}" for req in bundle.requirements[:8]]
    if not evidence:
        evidence = [f"{q.source_path}:{q.source_line}" for q in bundle.open_questions[:8]]
    actions = []
    if bundle.immutable_goal is not None:
        actions.append(
            {
                "id": "A-001",
                "related_finding": "F-001",
                "action": f"Review {bundle.immutable_goal.mode.value} draft and approve, reject, or revise before touching GOAL.md.",
                "owner_persona": "human operator",
                "primary_object": "immutable goal",
                "rationale": "Immutable goals should come from the brief before implementation or Battle execution.",
                "acceptance_check": "A human-approved GOAL.md or amendment records the selected requirements and unresolved exclusions.",
                "dependencies": ["acceptance_bundle.json"],
                "risk_if_skipped": "Implementation-defined tests can replace client requirements.",
                "suggested_priority": "P0",
            }
        )
    return {
        "schema": "create_report.report.v1",
        "report_id": f"acceptance-contract-{bundle.project_name}",
        "title": f"{bundle.project_name} acceptance contract extraction",
        "persona": "project maintainer",
        "primary_object": "acceptance requirements bundle",
        "decision_supported": "Decide whether to create or amend an immutable goal from the supplied brief.",
        "overall_finding": status,
        "core_conclusion": f"Progress {progress['passed']}/{progress['total']} ({progress['percent']}%): extracted {len(bundle.requirements)} clear requirement(s), {len(bundle.acceptance_cases)} acceptance case(s), and {len(bundle.open_questions)} open question(s).",
        "evidence_basis": "Local source files were read and requirements were selected from explicit modal/acceptance language.",
        "highest_risk_issues": [q.question for q in bundle.open_questions[:5]],
        "immediate_next_steps": progress["next_steps"],
        "scope": {
            "reviewed": [bundle.source.path],
            "excluded": ["Unprovided client context", "Battle execution", "Implementation correctness"],
            "evidence_available": evidence,
        },
        "project_context": {
            "goals": [req.statement for req in bundle.requirements[:5]],
            "current_state": "Acceptance requirements were extracted from supplied local source only.",
            "recent_decisions": ["Do not let Battle invent requirements; Battle consumes frozen bundles."],
            "open_questions": [q.question for q in bundle.open_questions],
            "takeover_notes": ["Create/amend immutable goal only after human approval."],
            "sources": [file.path for file in bundle.source.files],
        },
        "source_of_truth_inventory": [
            {"id": f"S-{idx:03d}", "kind": "source-file", "path": file.path, "limitation": "Text extraction only; semantic approval not implied."}
            for idx, file in enumerate(bundle.source.files, start=1)
        ],
        "findings": [
            {
                "id": "F-001",
                "title": "Source-backed requirements need approval before becoming immutable goal text",
                "status": finding_status,
                "evidence": evidence,
                "rationale": "The bundle records exact source locations, but requirement completeness still depends on the supplied material and human approval.",
                "impact": "Freezing this before implementation prevents implementation-defined acceptance tests.",
                "owner": "project maintainer",
                "valid_next_actions": ["approve draft", "revise requirements", "supply missing brief material"],
                "acceptance_check": "acceptance_bundle.json and IMMUTABLE_GOAL.draft.md are reviewed before any GOAL.md mutation.",
                "non_claims": bundle.non_claims,
            }
        ],
        "surface_contracts": [
            {
                "name": "acceptance bundle",
                "owning_persona": "project maintainer",
                "core_purpose": "Freeze source-backed requirements before implementation or Battle hardening.",
                "primary_object": "acceptance_contract.bundle.v1",
                "source_of_truth": "acceptance_bundle.json",
                "valid_actions": ["review", "approve", "revise", "feed into Battle profile generation"],
                "outstanding_broken_constraints": ["Human approval is required before immutable-goal mutation."],
            }
        ],
        "state_split": {
            "finished": [check["label"] for check in progress["checks"] if check["status"] == "PASS"],
            "pending": [step for step in progress["outstanding"] if step not in [q.question for q in bundle.open_questions]],
            "outstanding": progress["outstanding"],
            "broken": [],
            "blocked": [] if bundle.requirements else ["No clear requirements found."],
            "unproven": bundle.non_claims,
        },
        "plan_ready_next_actions": actions,
        "plan_iterate_seed": {
            "recommended_phase_id": "acceptance-contract-review",
            "objective": "Approve or revise the extracted contract before implementation hardening.",
            "candidate_phases": ["source review", "human approval", "Battle bundle/profile generation"],
            "deterministic_evidence_gates": ["create-report validate acceptance_report.json", "acceptance-contract validate acceptance_bundle.json"],
            "domain_review_loops": ["create-report"],
            "interaction_evidence": "Not applicable unless the source bundle includes UI requirements.",
            "ask_persona_review": "Optional WebGPT review for high-stakes client briefs.",
            "dogpile_reference_research": "Only needed if the brief relies on external standards or competitor behavior.",
            "human_decisions": ["create new immutable goal or amend existing immutable goal"],
            "stop_conditions": ["No clear requirements", "Unresolved source ambiguity", "Human rejects goal draft"],
            "non_claims": bundle.non_claims,
        },
        "non_claims": bundle.non_claims,
    }


def run_create_report(skill_dir: Path, report_json: Path, report_md: Path) -> None:
    run_sh = skill_dir.parent / "create-report" / "run.sh"
    clean_env = ["env", "-u", "UV_PROJECT_ENVIRONMENT", "-u", "VIRTUAL_ENV"]
    subprocess.run(clean_env + [str(run_sh), "validate", str(report_json)], check=True, capture_output=True, text=True, timeout=60)
    subprocess.run(
        clean_env + [str(run_sh), "render", str(report_json), "--format", "markdown", "--output", str(report_md)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
