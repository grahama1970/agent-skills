#!/usr/bin/env python3
"""
Cleanup Skill - Deep codebase assessment and technical debt cleanup.

Orchestration entry point. The assessment, evidence, and reporting logic lives in
focused modules so every file stays under the 800-line rule from
/best-practices-python:

    cleanup_core       shared constants, logging, git and file helpers
    cleanup_watchdog   project-watchdog registry context (read-only)
    cleanup_worktree   dirty-worktree triage buckets
    cleanup_evidence   ingest markers, dependency verdicts, mutation readiness
    cleanup_docs       documentation organization proposals
    cleanup_public     public-readiness and security-disclosure blockers
    cleanup_bp         best-practices gate and rule execution

The workflow:
1. Assessment (--dry-run): Scan and generate findings
2. Planning (--plan): Generate a Cleanup Plan markdown
3. Execution (--execute): Remove untracked junk cleared by per-path provenance
4. Finalization: Record cleanup in local/CLEANUP_LOG.md and the phase receipt

Evidence model: assessment, planning, and worktree audit never depend on an
index and always run. Each mutation class carries its own evidence requirement.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Set, Tuple, Optional

# Re-exported so `import cleanup` keeps addressing every helper by its old name.
from cleanup_core import *  # noqa: F401,F403
from cleanup_core import (
    log_error, log_info, log_warning, run_command, read_file_content,
    get_all_tracked_files, get_untracked_files, is_cleanup_output, is_junk_file,
    is_artifact_file, get_file_size, get_git_status, parse_porcelain_status,
    scan_root_strays, get_project_name, find_file_references,
    scan_repository_references, build_reference_index, scan_for_dead_files,
    get_expected_root_dirs,
)
from cleanup_watchdog import *  # noqa: F401,F403
from cleanup_watchdog import scan_project_watchdog_context
from cleanup_worktree import *  # noqa: F401,F403
from cleanup_worktree import (
    classify_worktree_entry, build_worktree_audit,
    generate_worktree_audit_markdown, _append_project_watchdog_markdown,
)
from cleanup_evidence import *  # noqa: F401,F403
from cleanup_evidence import (
    scan_ingest_code_evidence, validate_ingest_code_precondition,
    describe_ingest_proof_limits, scan_cleanup_evidence_artifact,
    evaluate_candidate_dependency_evidence, find_literal_references,
    junk_candidate_needles, evaluate_junk_candidates, evaluate_mutation_readiness,
    unusable_evidence_errors, build_phase_receipt, write_phase_receipt,
    _working_tree_sha256,
)
from cleanup_docs import *  # noqa: F401,F403
from cleanup_docs import (
    scan_for_outdated_docs, scan_doc_organization, find_markdown_inbound_links,
    get_last_commit_times, scan_script_scanability, append_cleanup_report_preamble,
    DOC_STALE_DAYS, DOC_DEPRECATION_DIR, CONVENTIONAL_ROOT_DOCS,
    GITHUB_SLUG_PATTERN, REPO_DECLARATION_PATTERN,
    _foreign_repo_reference, _current_repo_slugs, _doc_relocation_target,
)
from cleanup_public import *  # noqa: F401,F403
from cleanup_public import scan_public_readiness, append_public_readiness_markdown
from cleanup_bp import *  # noqa: F401,F403
from cleanup_bp import (
    best_practices_skill_for, evaluate_best_practices_gate,
    run_best_practices_checks, _load_skills_ci_scanners,
    _available_best_practices_skills,
)


def generate_cleanup_plan(findings: Dict) -> str:
    plan = []
    plan.append("# Cleanup Report")
    plan.append("")
    plan.append(f"Generated: {datetime.now().isoformat()}")
    plan.append("")
    append_cleanup_report_preamble(plan, findings)

    organization = findings.get("doc_organization") or []
    actionable = [
        p for p in organization
        if p["verdict"] in {"relocate_proposed", "deprecate_proposed"}
    ]
    scanability = findings.get("script_scanability") or []
    public_readiness = findings.get("public_readiness") or {}
    evidence_status = (findings.get("cleanup_evidence_artifact") or {}).get("status", "missing")

    ingest_evidence = findings.get("ingest_code_evidence", {})
    plan.append("## Ingest-Code Evidence")
    plan.append("")
    plan.append(f"- Status: `{ingest_evidence.get('status', 'missing')}`")
    plan.append(f"- Marker: `{ingest_evidence.get('marker_path', '.ingest-code.json')}`")
    plan.append(f"- Files scanned: `{ingest_evidence.get('files_scanned', 'unknown')}`")
    plan.append(f"- Dependency edges stored: `{ingest_evidence.get('edges_stored', 'unknown')}`")
    plan.append(
        f"- Structured symbols stored: "
        f"`{ingest_evidence.get('code_index', {}).get('symbols_stored', 'unknown')}`"
    )
    if ingest_evidence.get("marker_claimed_complete") is True and ingest_evidence.get("status") != "complete":
        plan.append("- Marker claim: `completed`, but aggregate proof is degraded")
    for warning in ingest_evidence.get("marker_warnings", []) or []:
        plan.append(f"- Warning: {warning}")
    plan.append(f"- Proves: {ingest_evidence.get('proves', 'ingest status only')}")
    plan.append(
        f"- Does not prove: "
        f"{ingest_evidence.get('does_not_prove', 'that files are safe to remove')}"
    )
    plan.append(
        f"- Refresh command: `{ingest_evidence.get('recommended_command', 'not available')}`"
    )
    plan.append("")

    artifact = findings.get("cleanup_evidence_artifact", {})
    readiness = findings.get("mutation_readiness", {})
    plan.append("## Per-Candidate Dependency Evidence")
    plan.append("")
    plan.append(f"- Artifact: `{artifact.get('artifact_path', CLEANUP_EVIDENCE_FILENAME)}`")
    plan.append(f"- Status: `{artifact.get('status', 'missing')}`")
    plan.append(f"- Producer: `{artifact.get('producer_command', 'not available')}`")
    if artifact.get("scan_failures"):
        plan.append(f"- Scan failures: `{len(artifact['scan_failures'])}`")
    plan.append("")
    if readiness.get("phases"):
        plan.append("| Phase | State |")
        plan.append("|---|---|")
        for phase, state in readiness["phases"].items():
            plan.append(f"| `{phase}` | `{state}` |")
        plan.append("")
    if readiness.get("proof_limits"):
        plan.append("Proof limits:")
        plan.append("")
        for limit in readiness["proof_limits"]:
            plan.append(f"- {limit}")
        plan.append("")

    _append_project_watchdog_markdown(plan, findings.get("project_watchdog", {}))

    candidate_evidence = findings.get("candidate_dependency_evidence", [])
    if candidate_evidence:
        plan.append("### Candidate Verdicts")
        plan.append("")
        plan.append("| Candidate | Verdict | Inbound refs | Mutation |")
        plan.append("|---|---|---|---|")
        for verdict in candidate_evidence:
            inbound = len(verdict.get("inbound_references", []))
            plan.append(
                f"| `{verdict['path']}` | `{verdict['verdict']}` | {inbound} | "
                f"`{'allowed' if verdict.get('mutation_allowed') else 'blocked'}` |"
            )
        plan.append("")

    # Root strays (review only)
    if findings.get("root_strays"):
        plan.append("## Root-Level Strays (Review Only)")
        plan.append("")
        plan.append(
            "These paths need owner, dependency, ingest-code, and readiness review. "
            "The cleanup CLI will not archive them automatically:"
        )
        plan.append("")
        for s in findings["root_strays"]:
            plan.append(f"- `{s['path']}` — {s['reason']} → **{s['action']}**")
        plan.append("")

    # Uncommitted changes
    if findings.get("uncommitted_changes"):
        plan.append("## Uncommitted Changes")
        plan.append("")
        for change in findings["uncommitted_changes"]:
            plan.append(f"- `{change}`")
        plan.append("")
        plan.append(
            "**Action Required**: Run `--worktree-audit` and resolve these by "
            "bucket. Commit only the coherent cleanup slice by explicit path. Do "
            "not blanket-stash or blanket-commit a dirty worktree."
        )
        plan.append("")

    # Untracked files
    if findings.get("untracked_files"):
        plan.append("## Untracked Files")
        plan.append("")

        junk_files = [f for f in findings["untracked_files"] if is_junk_file(f)]
        other_files = [f for f in findings["untracked_files"] if not is_junk_file(f)]

        if junk_files:
            plan.append("### Junk Files (Safe to Remove)")
            plan.append("")
            for f in junk_files:
                plan.append(f"- `{f}`")
            plan.append("")

        if other_files:
            plan.append("### Other Untracked Files")
            plan.append("")
            for f in other_files:
                plan.append(f"- `{f}`")
            plan.append("")

    # Dead files
    if findings.get("dead_files"):
        plan.append("## Lexically Unreferenced Candidates (Review Only)")
        plan.append("")
        for file_info in findings["dead_files"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")
        plan.append(
            "**NON-MUTATING**: Lexical absence is not unused-code proof. Confirm "
            "with language-aware references, ingest-code relationships, package "
            "entrypoints/configuration, and before/after project sanity checks."
        )
        plan.append("")

    # Outdated docs
    if findings.get("outdated_docs"):
        plan.append("## Potentially Outdated Documentation")
        plan.append("")
        for file_info in findings["outdated_docs"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")

    # Doc organization proposals
    if actionable:
        plan.append("## Documentation Organization (Proposed)")
        plan.append("")
        plan.append(
            "Each row names where the doc would go and what links to it. A move is "
            "only safe once every inbound reference is rewritten, so the reference "
            "list is part of the proposal, not a footnote. Conventional root files "
            "(README, LICENSE, CONTRIBUTING, SECURITY, ...) are never proposed."
        )
        plan.append("")
        plan.append("| Doc | Verdict | Proposed path | Inbound refs | Age (days) |")
        plan.append("| --- | --- | --- | --- | --- |")
        for p in actionable:
            refs = len(p["inbound_references"])
            age = p["age_days"] if p["age_days"] is not None else "-"
            plan.append(
                f"| `{p['path']}` | {p['verdict']} | `{p['proposed_path']}` | {refs} | {age} |"
            )
        plan.append("")
        for p in actionable:
            if p["inbound_references"]:
                plan.append(f"- `{p['path']}` is referenced by: " + ", ".join(
                    f"`{r}`" for r in p["inbound_references"][:10]
                ))
        plan.append("")

    if scanability:
        plan.append("## Script Scanability (Readability Repair)")
        plan.append("")
        plan.append(
            "These script files are hard for humans or agents to scan quickly. "
            "This finding is not unused-code evidence and does not authorize "
            "deletion, quarantine, or archival. Repairs must be a separate "
            "readability-only slice that adds useful purpose, usage, side-effect, "
            "function, or class notes without changing behavior."
        )
        plan.append("")
        plan.append("| Script | Missing scanability evidence | Repair class |")
        plan.append("| --- | --- | --- |")
        for item in scanability:
            missing = ", ".join(f"`{gap}`" for gap in item.get("missing", []))
            plan.append(
                f"| `{item['path']}` | {missing} | `{item['repair_class']}` |"
            )
        plan.append("")
        plan.append(
            "Proof for a repair slice: parse/compile the touched scripts and run "
            "each script's `--help`, entrypoint smoke, or narrow sanity command."
        )
        plan.append("")

    append_public_readiness_markdown(plan, public_readiness)

    uncommitted_count = len(findings.get("uncommitted_changes", []))
    root_strays_count = len(findings.get("root_strays", []))

    plan.append("## Outstanding / Broken / Unknown")
    plan.append("")
    if evidence_status != "complete":
        plan.append(
            f"- `Blocked`: tracked-file mutation evidence is `{evidence_status}`; "
            "tracked moves/removals remain unauthorized."
        )
    if uncommitted_count:
        plan.append("- `Needs Changes`: dirty worktree entries need owner-safe triage.")
    if root_strays_count:
        plan.append("- `Needs Decision`: root strays need human owner disposition.")
    if scanability:
        plan.append("- `Needs Changes`: script scanability repairs are unimplemented.")
    if public_readiness.get("blockers"):
        plan.append("- `Blocked`: public-readiness/security cleanup has unresolved blockers.")
    if not any([
        evidence_status != "complete",
        uncommitted_count,
        root_strays_count,
        scanability,
        public_readiness.get("blockers"),
    ]):
        plan.append("- No outstanding cleanup blocker was detected by this report scope.")
    plan.append("")

    plan.append("## Plan-Ready Next Actions")
    plan.append("")
    plan.append("| Action ID | Related Finding | Action | Owner Persona | Primary Object | Acceptance Check | Dependencies | Priority |")
    plan.append("|---|---|---|---|---|---|---|---|")
    plan.append("| A-001 | F-001 | Classify dirty entries with `--worktree-audit` | project agent | git worktree | JSON and Markdown audit exist | none | P0 |")
    plan.append("| A-002 | F-003 | Refresh per-candidate cleanup evidence | project agent | `.cleanup-evidence.json` | artifact schema loads and candidate verdicts are present | ingest-code available | P1 |")
    plan.append("| A-003 | F-004 | Add readability-only script docstrings/comments | project agent | listed script files | parse/compile plus help or narrow sanity proof passes | explicit readability slice | P2 |")
    plan.append("| A-004 | F-005 | Triage public-readiness security blockers | maintainer + project agent | gitleaks/GitHub readiness receipts | history findings triaged, noisy dir scan narrowed, GitHub settings inventoried | maintainer authority | P0 |")
    plan.append("")

    plan.append("## Non-Claims")
    plan.append("")
    plan.append("- This report does not prove that lexically unreferenced files are unused.")
    plan.append("- This report does not prove that root artifacts or root strays are safe to archive.")
    plan.append("- This report does not prove runtime, release, UI, compliance, or production readiness.")
    plan.append("- Script scanability findings do not prove behavior is wrong; they identify readability debt for humans and agents.")
    plan.append("- Public-readiness findings do not prove the repository is safe to make public until every blocker has a deterministic receipt.")
    plan.append("")

    # Best-practices gate
    gate = findings.get("best_practices_gate") or {}
    if gate:
        plan.append("## Best-Practices Gate")
        plan.append("")
        plan.append(f"Status: **{gate.get('status')}**. {gate.get('proof_limit', '')}")
        plan.append("")
        if gate.get("per_skill"):
            plan.append("| Skill | Available | Checked | Skipped (unchanged) | Failed |")
            plan.append("| --- | --- | --- | --- | --- |")
            for entry in gate["per_skill"]:
                plan.append(
                    f"| `{entry['skill']}` | {'yes' if entry['available'] else 'MISSING'} | "
                    f"{len(entry['checked'])} | {len(entry['skipped_unchanged'])} | "
                    f"{len(entry['failed'])} |"
                )
            plan.append("")
        if gate.get("unavailable_skills"):
            plan.append(
                "Unavailable skills, which must be installed before the gate can pass: "
                + ", ".join(f"`{s}`" for s in gate["unavailable_skills"])
            )
            plan.append("")

    # Summary
    plan.append("## Summary")
    plan.append("")
    plan.append(f"- Root strays requiring review: {len(findings.get('root_strays', []))}")
    plan.append(f"- Uncommitted changes: {len(findings.get('uncommitted_changes', []))}")
    plan.append(f"- Untracked files: {len(findings.get('untracked_files', []))}")
    plan.append(f"- Lexically unreferenced review candidates: {len(findings.get('dead_files', []))}")
    plan.append(f"- Potentially outdated docs: {len(findings.get('outdated_docs', []))}")
    plan.append(f"- Doc relocations proposed: {len(actionable)}")
    plan.append(f"- Script scanability repairs proposed: {len(scanability)}")
    plan.append(f"- Public-readiness blockers: {len(public_readiness.get('blockers', []))}")
    gate_counts = (gate or {}).get("counts", {})
    plan.append(
        f"- Best-practices gate: {gate_counts.get('checked', 0)} to check, "
        f"{gate_counts.get('skipped_unchanged', 0)} unchanged, "
        f"{gate_counts.get('not_applicable', 0)} not applicable"
    )
    plan.append("")

    return "\n".join(plan)


def log_cleanup(findings: Dict, actions_taken: List[str]) -> None:
    log_dir = Path("local")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "CLEANUP_LOG.md"

    entry = []
    entry.append(f"## Cleanup: {datetime.now().isoformat()}")
    entry.append("")

    if findings.get("root_strays"):
        entry.append(f"### Root Strays ({len(findings['root_strays'])})")
        for s in findings["root_strays"]:
            entry.append(f"- {s['path']} ({s['reason']})")
        entry.append("")

    if findings.get("uncommitted_changes"):
        entry.append(f"### Uncommitted Changes ({len(findings['uncommitted_changes'])})")
        for change in findings["uncommitted_changes"]:
            entry.append(f"- {change}")
        entry.append("")

    if actions_taken:
        entry.append("### Actions Taken")
        for action in actions_taken:
            entry.append(f"- {action}")
        entry.append("")

    entry.append("---")
    entry.append("")

    if not log_file.exists():
        log_file.write_text("# Cleanup Log\n\n")
    with log_file.open("a") as f:
        f.write("\n".join(entry))


def confirm_action(action: str) -> bool:
    """Ask for confirmation, declining safely when there is nobody to ask.

    Nightly and CI runs have no stdin. Prompting there used to raise EOFError,
    which surfaced as a bare "Aborted." and exit 1 — a scheduler reads that as a
    failed job rather than "declined, nothing was touched".
    """
    if not sys.stdin.isatty():
        log_warning(f"{action} — declined automatically (no interactive stdin)")
        log_warning("Pass --force to authorize this without a prompt")
        return False
    try:
        response = input(f"{action} [y/N]: ").strip().lower()
    except EOFError:
        log_warning(f"{action} — declined automatically (stdin closed)")
        return False
    return response in ("y", "yes")


def execute_cleanup(findings: Dict, force: bool = False) -> List[str]:
    actions_taken = []
    watchdog_context = findings.get("project_watchdog", {})
    if watchdog_context.get("blocks_cleanup_execution"):
        log_warning(
            "Project-watchdog coordination blocks cleanup execution; no files were removed"
        )
        log_warning(
            "Cleanup only observes watchdog state and will not tick, lease, relabel, or close issues"
        )
        return actions_taken

    # ── 1. Root strays are assessment-only ──────────────────────────────
    strays = findings.get("root_strays", [])
    if strays:
        log_warning(
            f"Found {len(strays)} root-level review candidates; automatic archival is disabled"
        )

    # ── 2. Remove junk files with per-path provenance ───────────────────
    untracked = findings.get("untracked_files", [])
    junk_verdicts = findings.get("junk_verdicts") or {}
    pattern_matches = [f for f in untracked if is_junk_file(f)]
    junk_files = [f for f in pattern_matches if junk_verdicts.get(f, {}).get("removal_allowed")]
    withheld = [f for f in pattern_matches if f not in junk_files]

    if withheld:
        log_warning(f"{len(withheld)} junk-pattern paths withheld by provenance")
        for f in withheld:
            reason = junk_verdicts.get(f, {}).get(
                "reason", "no provenance verdict was computed for this path"
            )
            log_warning(f"  {f}: {reason}")

    if junk_files:
        log_info(f"Found {len(junk_files)} junk files cleared for removal")

        for f in junk_files:
            if not force and not confirm_action(f"Remove junk file: {f}"):
                log_warning(f"Skipping: {f}")
                continue
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    actions_taken.append(f"Removed file: {f}")
                    log_info(f"Removed: {f}")
                elif os.path.isdir(f):
                    shutil.rmtree(f)
                    actions_taken.append(f"Removed directory: {f}")
                    log_info(f"Removed: {f}")
            except Exception as e:
                log_error(f"Failed to remove {f}: {e}")

    # ── 3. Lexical candidates are assessment-only ───────────────────────
    dead_files = findings.get("dead_files", [])
    if dead_files:
        log_warning(
            f"Found {len(dead_files)} lexically unreferenced candidates; "
            "tracked-file removal is disabled"
        )

    # ── 4. Remaining untracked ───────────────────────────────────────────
    other_untracked = [f for f in untracked if f not in junk_files]
    if other_untracked:
        log_info(f"Found {len(other_untracked)} other untracked files")
        log_info("Review these files - use 'git clean -i' for interactive cleanup")

    return actions_taken


app = typer.Typer(help="Cleanup Skill - Deep codebase assessment and technical debt cleanup")


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print findings without making changes (JSON output)"),
    plan: bool = typer.Option(False, "--plan", help="Generate a Cleanup Report markdown file"),
    execute: bool = typer.Option(False, "--execute", help="Perform cleanup actions (with confirmation)"),
    worktree_audit: bool = typer.Option(False, "--worktree-audit", help="Write a commit-safe dirty worktree ownership/risk audit"),
    script_scanability: bool = typer.Option(False, "--script-scanability", help="Run only the non-mutating script scanability pass"),
    public_readiness: bool = typer.Option(False, "--public-readiness", help="Run only the non-mutating public-readiness/security cleanup lane"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts for junk removal only; cannot authorize any other mutation class"),
    output: str = typer.Option("CLEANUP_PLAN.md", "--output", help="Output file for plan"),
    receipt: str = typer.Option(DEFAULT_RECEIPT_PATH, "--receipt", help="Path for the resumable phase receipt"),
) -> None:
    """Deep codebase assessment and technical debt cleanup."""
    if worktree_audit:
        audit = build_worktree_audit()
        output_path = Path(output)
        if output_path.suffix.lower() not in {".json", ".md"}:
            output_path = output_path.with_suffix(".json")
        json_path = output_path if output_path.suffix.lower() == ".json" else output_path.with_suffix(".json")
        md_path = output_path if output_path.suffix.lower() == ".md" else output_path.with_suffix(".md")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(audit, indent=2, default=str))
        md_path.write_text(generate_worktree_audit_markdown(audit))
        log_info(f"Worktree audit JSON written to: {json_path}")
        log_info(f"Worktree audit Markdown written to: {md_path}")
        if audit["summary"].get("high_risk", 0):
            log_warning(f"High-risk dirty entries: {audit['summary']['high_risk']}")
        return

    if script_scanability:
        print(json.dumps({
            "script_scanability": scan_script_scanability(),
            "mutation": "not_authorized",
            "repair_contract": (
                "readability-only edits are allowed only as an explicit cleanup "
                "slice and must be proven with parse/compile plus script help "
                "or a narrow sanity command"
            ),
        }, indent=2, default=str))
        return

    if public_readiness:
        print(json.dumps(scan_public_readiness(run_scans=True), indent=2, default=str))
        return

    log_info("Starting assessment...")

    all_untracked = get_untracked_files()
    own_outputs = [f for f in all_untracked if is_cleanup_output(f)]
    untracked_files = [f for f in all_untracked if not is_cleanup_output(f)]

    # One pass over tracked text files answers both the dead-file token index
    # and the junk-provenance literal search.
    search_dirs = [d for d in [".", "src", "lib", "packages", "docs"] if os.path.exists(d)]
    log_info("Scanning repository references...")
    reference_index, literal_hits = scan_repository_references(
        search_dirs, literal_needles=junk_candidate_needles(untracked_files)
    )

    findings = {
        "root_strays": scan_root_strays(),
        "uncommitted_changes": get_git_status(),
        "untracked_files": untracked_files,
        "own_cleanup_outputs": own_outputs,
        "dead_files": scan_for_dead_files(reference_index),
        "outdated_docs": scan_for_outdated_docs(),
        "doc_organization": scan_doc_organization(),
        "script_scanability": scan_script_scanability(),
        "public_readiness": scan_public_readiness(run_scans=False),
        "ingest_code_evidence": scan_ingest_code_evidence(),
        "cleanup_evidence_artifact": scan_cleanup_evidence_artifact(),
        "project_watchdog": scan_project_watchdog_context(),
    }

    # Join each candidate against per-file dependency evidence. Assessment
    # never depends on Memory: a blocked index degrades the verdicts, it does
    # not stop the scan.
    artifact = findings["cleanup_evidence_artifact"]
    findings["candidate_dependency_evidence"] = [
        evaluate_candidate_dependency_evidence(candidate["path"], artifact)
        for candidate in findings["dead_files"]
    ]
    findings["junk_verdicts"] = evaluate_junk_candidates(
        findings["untracked_files"], literal_hits=literal_hits
    )
    findings["ingest_proof_limits"] = describe_ingest_proof_limits(
        findings["ingest_code_evidence"]
    )
    # The best-practices gate covers what this cleanup slice would change:
    # every dirty tracked path, plus any doc the organization pass proposes to
    # move. A file nobody is touching needs no re-check.
    _changed_for_gate = [
        entry["path"]
        for entry in parse_porcelain_status(findings["uncommitted_changes"])
        if entry.get("path")
    ]
    _changed_for_gate += [
        proposal["path"]
        for proposal in findings["doc_organization"]
        if proposal["verdict"] in {"relocate_proposed", "deprecate_proposed"}
    ]
    findings["best_practices_gate"] = evaluate_best_practices_gate(_changed_for_gate)
    # Execute the rules, do not merely resolve which ones apply. A gate that
    # reports "requires_run" and never runs anything is a claim with no check
    # behind it.
    findings["best_practices_gate"]["execution"] = run_best_practices_checks(
        _changed_for_gate
    )
    _execution = findings["best_practices_gate"]["execution"]
    _ran = [
        name for name, result in _execution.get("executed", {}).items()
        if result.get("status") == "ran"
    ]
    _violations = sum(
        result.get("violation_count", 0)
        for result in _execution.get("executed", {}).values()
    )
    if _ran and _violations == 0:
        findings["best_practices_gate"]["status"] = "executed_clean"
    elif _ran:
        findings["best_practices_gate"]["status"] = "executed_with_violations"
    findings["best_practices_gate"]["violations_found"] = _violations
    findings["best_practices_gate"]["skills_executed"] = sorted(_ran)
    findings["mutation_readiness"] = evaluate_mutation_readiness(
        findings,
        findings["ingest_code_evidence"],
        artifact,
        findings["junk_verdicts"],
    )

    receipt_payload = build_phase_receipt(findings, findings["mutation_readiness"])

    # Surfaced in every mode, not just --execute. Warnings go to stderr so
    # --dry-run keeps a clean JSON stdout.
    for error in receipt_payload["unusable_evidence"]:
        log_warning(f"Unusable evidence: {error}")

    if dry_run:
        # --dry-run makes no changes. The receipt is returned inline instead of
        # written, so the mode keeps its "no writes" contract.
        findings["phase_receipt"] = receipt_payload
        print(json.dumps(findings, indent=2, default=str))
        return

    receipt_path = write_phase_receipt(receipt_payload, receipt)

    if plan:
        log_info("Generating cleanup plan...")
        cleanup_plan = generate_cleanup_plan(findings)

        with open(output, "w") as f:
            f.write(cleanup_plan)

        log_info(f"Cleanup plan written to: {output}")
        log_info(f"Phase receipt written to: {receipt_path}")
        log_info("Review the plan and run with --execute when ready")
        return

    if execute:
        readiness = findings["mutation_readiness"]
        junk_class = readiness["mutation_classes"]["junk_untracked_removal"]

        log_info("Mutation authority by class:")
        for name, detail in readiness["mutation_classes"].items():
            log_info(f"  {name}: {detail['status']}")

        # Withholding a candidate is cleanup working, not cleanup failing;
        # execute_cleanup reports each withheld path. Exit 2 is reserved for
        # evidence this run could not evaluate at all.
        unusable = unusable_evidence_errors(findings)
        if unusable:
            log_error("Cleanup cannot evaluate the evidence it was given")
            for error in unusable:
                log_error(f"  {error}")
            log_error(f"Phase receipt: {receipt_path}")
            raise typer.Exit(code=2)

        # The guard exists to protect work cleanup is not responsible for.
        # Counting the junk it is about to remove, or its own receipts, makes it
        # ask permission because of the very files it was invoked to handle.
        # `git status` collapses an untracked directory to `?? dir/`, so a
        # membership test against file paths misses it. An entry is unrelated
        # only if some path under it is something cleanup does not own.
        unowned = {
            path
            for path in findings["untracked_files"]
            if path not in set(junk_class.get("allowed_paths", []))
        }
        unrelated_changes = []
        for change in findings["uncommitted_changes"]:
            status, _, raw = change.partition(" ")
            path = raw.strip().strip('"')
            if status == "??":
                if any(p == path or p.startswith(path.rstrip("/") + "/") for p in unowned):
                    unrelated_changes.append(change)
            else:
                unrelated_changes.append(change)

        if unrelated_changes:
            log_warning(
                f"{len(unrelated_changes)} uncommitted changes are unrelated to this cleanup"
            )
            for change in unrelated_changes:
                log_warning(f"  {change}")

            if not force:
                if not confirm_action("Continue anyway?"):
                    log_info("Cleanup aborted; nothing was changed.")
                    return

        log_info("=" * 50)
        log_info("Cleanup Summary")
        log_info("=" * 50)
        log_info(f"Root strays for review:    {len(findings['root_strays'])}")
        log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
        log_info(f"Untracked files:           {len(findings['untracked_files'])}")
        log_info(f"Lexical review candidates: {len(findings['dead_files'])}")
        log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
        log_info(f"Script scanability repairs: {len(findings['script_scanability'])}")
        log_info(f"Public-readiness blockers: {len(findings['public_readiness'].get('blockers', []))}")
        log_info("=" * 50)

        log_info("Starting cleanup...")
        actions_taken = execute_cleanup(findings, force=force)

        if actions_taken:
            log_cleanup(findings, actions_taken)
            log_info("Cleanup logged to: local/CLEANUP_LOG.md")

        receipt_path = write_phase_receipt(
            build_phase_receipt(findings, readiness, actions_taken), receipt
        )
        log_info(f"Phase receipt written to: {receipt_path}")
        log_info(f"Cleanup complete. {len(actions_taken)} actions taken.")
        return

    # Default: Show summary
    log_info("=" * 50)
    log_info("Cleanup Assessment")
    log_info("=" * 50)
    log_info(f"Root strays for review:    {len(findings['root_strays'])}")
    log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
    log_info(f"Untracked files:           {len(findings['untracked_files'])}")
    log_info(f"Lexical review candidates: {len(findings['dead_files'])}")
    log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
    log_info(f"Script scanability repairs: {len(findings['script_scanability'])}")
    log_info(f"Public-readiness blockers: {len(findings['public_readiness'].get('blockers', []))}")
    log_info("=" * 50)
    for phase_name, state in findings["mutation_readiness"]["phases"].items():
        log_info(f"{phase_name}: {state}")
    log_info(f"Phase receipt: {receipt_path}")
    log_info("=" * 50)
    log_info("")
    log_info("Use --dry-run for JSON output")
    log_info("Use --plan to generate a cleanup plan")
    log_info("Use --worktree-audit to classify dirty worktree entries before commit")
    log_info("Use --script-scanability to run only the script readability pass")
    log_info("Use --public-readiness to run only the public-readiness/security lane")
    log_info("Use --execute to remove cleared untracked junk (with confirmation)")
    log_info("Use --execute --force to skip junk confirmation prompts")
    log_info("Root artifacts, root strays, and tracked candidates are review-only")


if __name__ == "__main__":
    app()
