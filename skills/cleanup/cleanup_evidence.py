"""Evidence model: ingest markers, per-candidate dependency verdicts, junk provenance, mutation readiness, and the resumable phase receipt."""

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

from cleanup_core import *  # noqa: F401,F403  shared constants and helpers
from cleanup_core import (
    log_error, log_info, log_warning, run_command, read_file_content,
    get_all_tracked_files, is_cleanup_output,
)


def scan_ingest_code_evidence(marker_path: str = ".ingest-code.json") -> Dict[str, Any]:
    """Summarize the local ingest-code marker without overstating its proof."""
    path = Path(marker_path)
    base: Dict[str, Any] = {
        "marker_path": str(path),
        "proves": "the recorded ingest-code workflow completed with the reported scope",
        "does_not_prove": "that any file is unused or safe to move/delete",
        "recommended_command": (
            f"{Path(__file__).resolve().parent.parent / 'ingest-code' / 'run.sh'} "
            f"scan {Path.cwd()} --treesitter"
        ),
    }
    if not path.exists():
        return {**base, "status": "missing"}

    try:
        marker = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "status": "invalid", "error": str(exc)}

    completed = marker.get("completed") is True and marker.get("run_status") == "complete"
    code_index = marker.get("code_index") if isinstance(marker.get("code_index"), dict) else {}
    files_scanned = marker.get("files_scanned")
    symbols_stored = code_index.get("symbols_stored", 0)
    marker_warnings: List[str] = []
    if completed and (not isinstance(files_scanned, int) or files_scanned <= 0):
        marker_warnings.append(
            "marker claims completion but files_scanned is zero or missing"
        )
    if completed and not code_index.get("enabled", False):
        marker_warnings.append("marker claims completion but code_index.enabled is false")
    if completed and code_index.get("treesitter", False) and symbols_stored == 0:
        marker_warnings.append(
            "marker claims Tree-sitter mode but stored zero structured symbols"
        )
    status = "complete" if completed and not marker_warnings else "incomplete"
    return {
        **base,
        "status": status,
        "marker_claimed_complete": completed,
        "marker_warnings": marker_warnings,
        "repository_path": marker.get("path"),
        "ingested_at": marker.get("ingested_at"),
        "scope": marker.get("scope"),
        "files_scanned": files_scanned,
        "edges_stored": marker.get("edges_stored"),
        "scan_roots": marker.get("scan_roots", []),
        "completed_scan_roots": marker.get("completed_scan_roots", []),
        "local_artifacts": marker.get("local_artifacts", {}),
        "code_index": {
            "enabled": code_index.get("enabled", False),
            "treesitter": code_index.get("treesitter", False),
            "symbols_stored": code_index.get("symbols_stored", 0),
            "content_hashes": code_index.get("content_hashes", False),
        },
    }


def validate_ingest_code_precondition(evidence: Dict[str, Any]) -> List[str]:
    """Require a current, repository-wide Tree-sitter scan before execution."""
    errors: List[str] = []
    repo_root = Path.cwd().resolve()

    if evidence.get("status") != "complete":
        return ["ingest-code marker is not complete"]

    marker_repo = evidence.get("repository_path")
    if not marker_repo:
        errors.append("ingest-code marker does not identify its repository")
    else:
        try:
            if Path(str(marker_repo)).resolve() != repo_root:
                errors.append("ingest-code marker belongs to a different repository")
        except OSError:
            errors.append("ingest-code repository path cannot be resolved")

    code_index = evidence.get("code_index", {})
    if not code_index.get("enabled") or not code_index.get("treesitter"):
        errors.append("ingest-code Tree-sitter code index is not complete")

    completed_roots = {
        Path(str(root)).resolve()
        for root in evidence.get("completed_scan_roots", [])
        if root
    }
    if repo_root not in completed_roots:
        errors.append("ingest-code did not complete a repository-root scan")

    tracked_code_files = [
        path
        for path in get_all_tracked_files()
        if Path(path).suffix.lower() in DEAD_FILE_CANDIDATE_EXTENSIONS
    ]
    files_scanned = evidence.get("files_scanned")
    if not isinstance(files_scanned, int) or files_scanned < len(tracked_code_files):
        errors.append(
            "ingest-code marker does not cover all tracked code files "
            f"({files_scanned!r} scanned, {len(tracked_code_files)} tracked)"
        )

    marker_time = evidence.get("ingested_at")
    try:
        ingested_at = datetime.fromisoformat(str(marker_time)).timestamp()
    except (TypeError, ValueError):
        errors.append("ingest-code marker has no valid ingestion timestamp")
    else:
        newer_files = []
        for filepath in tracked_code_files:
            try:
                if Path(filepath).stat().st_mtime > ingested_at:
                    newer_files.append(filepath)
            except OSError:
                continue
        if newer_files:
            errors.append(
                f"{len(newer_files)} tracked code files changed after ingest-code completed"
            )

    return errors


def describe_ingest_proof_limits(evidence: Dict[str, Any]) -> List[str]:
    """State what the aggregate ingest marker can and cannot establish.

    The marker holds scalar counters only. Reporting them beside cleanup
    candidates without saying what they omit is how counts get mistaken for
    per-file safety evidence.
    """
    limits = [
        "coverage_proof=count_only: the marker compares a scanned-file count "
        "against tracked code files; it does not prove which paths were scanned",
        "freshness_proof=mtime_only: staleness is judged by filesystem mtime, "
        "which is unreliable after checkout, copy, rebase, or clock change",
        "edge_scope=python_imports_only: $ingest-code resolves dependency edges "
        "from Python static imports; other languages, dynamic imports, CLI "
        "entrypoints, and configuration references contribute no edges",
        f"aggregate_only: edges_stored={evidence.get('edges_stored', 'unknown')} "
        "is a storage count and says nothing about any individual candidate",
    ]
    for warning in evidence.get("marker_warnings", []) or []:
        limits.append(f"marker_warning={warning}")
    return limits


def _working_tree_sha256(filepath: str) -> Optional[str]:
    """Return the sha256 of a working-tree file, or None if unreadable."""
    try:
        return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()
    except OSError:
        return None


def scan_cleanup_evidence_artifact(
    artifact_path: str = CLEANUP_EVIDENCE_FILENAME,
) -> Dict[str, Any]:
    """Read the per-candidate dependency evidence artifact.

    This artifact — not the aggregate marker — is the only evidence source that
    can support tracked-file mutation, because it carries exact scanned paths,
    content hashes, parse outcomes, resolved edges, and per-candidate inbound
    references. See references/cleanup-evidence-contract.md for the schema.
    """
    path = Path(artifact_path)
    base: Dict[str, Any] = {
        "artifact_path": str(path),
        "contract": CLEANUP_EVIDENCE_CONTRACT,
        "proves": (
            "per-candidate inbound references, parse outcomes, and proof scope "
            "for exactly the paths and content hashes it lists"
        ),
        "does_not_prove": (
            "anything about paths it omits, languages outside its proof scope, "
            "or references that exist only at runtime"
        ),
        "producer_command": (
            f"{Path(__file__).resolve().parent.parent / 'ingest-code' / 'run.sh'} "
            f"scan {Path.cwd()} --treesitter --cleanup-evidence --local-artifacts-only"
        ),
    }
    if not path.exists():
        return {**base, "status": "missing"}

    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "status": "invalid", "error": str(exc)}

    if not isinstance(payload, dict):
        return {**base, "status": "invalid", "error": "artifact must be a JSON object"}
    if payload.get("contract") != CLEANUP_EVIDENCE_CONTRACT:
        return {
            **base,
            "status": "invalid",
            "error": f"unsupported contract: {payload.get('contract')!r}",
        }
    files = payload.get("files")
    if not isinstance(files, dict):
        return {**base, "status": "invalid", "error": "artifact must contain a files object"}

    return {
        **base,
        "status": "complete" if payload.get("analysis_complete") is True else "incomplete",
        "repository_path": payload.get("repository_path"),
        "generated_at": payload.get("generated_at"),
        "proof_scope": payload.get("proof_scope", {}),
        "scan_failures": payload.get("scan_failures", []),
        "files": files,
    }


def evaluate_candidate_dependency_evidence(
    filepath: str,
    artifact: Dict[str, Any],
) -> Dict[str, Any]:
    """Join one cleanup candidate against the dependency evidence artifact.

    Static evidence never authorizes mutation on its own. Even a candidate with
    zero inbound references still requires project-native before/after readiness
    proof, so ``mutation_allowed`` is False in every branch.
    """
    verdict: Dict[str, Any] = {
        "path": filepath,
        "evidence_source": artifact.get("artifact_path", CLEANUP_EVIDENCE_FILENAME),
        "mutation_allowed": False,
    }

    if artifact.get("status") != "complete":
        return {
            **verdict,
            "verdict": "no_dependency_evidence",
            "reason": (
                "cleanup evidence artifact status is "
                f"{artifact.get('status', 'missing')!r}"
            ),
        }

    record = artifact.get("files", {}).get(filepath)
    if not isinstance(record, dict):
        return {
            **verdict,
            "verdict": "outside_proof_scope",
            "reason": "candidate is not covered by the evidence artifact",
        }

    recorded_hash = record.get("content_sha256")
    if not recorded_hash or _working_tree_sha256(filepath) != recorded_hash:
        return {
            **verdict,
            "verdict": "stale_evidence",
            "reason": "working-tree content hash does not match the analyzed content",
        }

    parse_status = record.get("parse_status")
    if parse_status == "not_analyzed":
        return {
            **verdict,
            "verdict": "outside_analysis_scope",
            "reason": (
                f"language {record.get('language', 'unknown')!r} is outside the "
                "edge-resolution scope, so an empty reference set proves nothing"
            ),
        }
    if parse_status != "ok":
        return {
            **verdict,
            "verdict": "parse_failed",
            "reason": f"parse_status={parse_status!r}; edges are incomplete",
        }

    inbound = list(record.get("inbound_references", []))
    entrypoints = list(record.get("entrypoint_references", []))
    entry_kinds = list(record.get("entry_kinds", []))
    dynamic = list(record.get("dynamic_reference_warnings", []))
    verdict.update({
        "inbound_references": inbound,
        "entrypoint_references": entrypoints,
        "entry_kinds": entry_kinds,
        "dynamic_reference_warnings": dynamic,
    })

    # A pytest module or a `__main__` script runs without anything importing
    # it, so an empty reference set says nothing about whether it is used.
    if entry_kinds:
        return {
            **verdict,
            "verdict": "entry_root",
            "reason": f"file is an entry root by convention: {', '.join(entry_kinds)}",
        }

    if inbound or entrypoints:
        return {
            **verdict,
            "verdict": "referenced",
            "reason": "candidate has resolved inbound or entrypoint references",
        }
    if dynamic:
        return {
            **verdict,
            "verdict": "unresolved_dynamic_references",
            "reason": "analysis recorded dynamic references it could not resolve",
        }
    unresolved_sites = artifact.get("proof_scope", {}).get("unresolved_dynamic_site_count", 0)
    return {
        **verdict,
        "verdict": "no_inbound_references",
        "reason": (
            "no inbound references inside the proof scope; mutation still "
            "requires project-native before/after readiness proof"
        ),
        "proof_scope_caveats": (
            [
                f"{unresolved_sites} dynamic import sites in this repository "
                "resolve no target, so any file could be reached at runtime"
            ]
            if unresolved_sites
            else []
        ),
        "readiness_required": [
            "run the project's sanity command before the move",
            "run import/entrypoint smoke checks for the owning package",
            "rerun both after the move and restore on failure",
        ],
    }


def find_literal_references(needles: Set[str]) -> Dict[str, List[str]]:
    """Return tracked text files that literally contain each needle path."""
    if not needles:
        return {}
    _, hits = scan_repository_references(["."], literal_needles=needles)
    return hits


def junk_candidate_needles(untracked_files: List[str]) -> Set[str]:
    """Return the literal paths whose provenance must be checked."""
    return {f.rstrip("/") for f in untracked_files if is_junk_file(f)}


def evaluate_junk_candidates(
    untracked_files: List[str],
    literal_hits: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Decide, per path, whether an untracked junk-pattern file may be removed.

    Dependency edges are irrelevant to this class: the mutation only ever
    touches paths git does not track. The relevant evidence is untracked status,
    the junk pattern that nominated the path, and the absence of a literal
    reference from tracked code or configuration.
    """
    candidates = [f for f in untracked_files if is_junk_file(f)]
    if not candidates:
        return {}

    tracked_files = get_all_tracked_files()
    references = (
        literal_hits
        if literal_hits is not None
        else find_literal_references(junk_candidate_needles(untracked_files))
    )

    verdicts: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        needle = candidate.rstrip("/")
        referenced_by = references.get(needle, [])
        if candidate in tracked_files or needle in tracked_files:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": False,
                "reason": "path is tracked by git; junk removal only covers untracked paths",
                "referenced_by": referenced_by,
            }
        elif referenced_by:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": False,
                "reason": "tracked files reference this path literally; review before removal",
                "referenced_by": referenced_by,
            }
        else:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": True,
                "reason": "untracked, matches a junk pattern, and no tracked file names it",
                "referenced_by": [],
            }
    return verdicts


def evaluate_mutation_readiness(
    findings: Dict[str, Any],
    ingest_evidence: Dict[str, Any],
    evidence_artifact: Dict[str, Any],
    junk_verdicts: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Report phase states and per-class mutation authority.

    Assessment never depends on indexing. Local dependency analysis, Memory
    indexing, assessment, and mutation are tracked as separate states so a
    Memory outage blocks only what it actually invalidates.
    """
    artifact_status = evidence_artifact.get("status", "missing")
    marker_complete = ingest_evidence.get("status") == "complete"
    marker_claimed_complete = ingest_evidence.get("marker_claimed_complete") is True

    if artifact_status == "complete":
        local_analysis = "complete"
    elif artifact_status in {"incomplete", "invalid"}:
        local_analysis = "incomplete"
    elif marker_complete or marker_claimed_complete:
        local_analysis = "unavailable_legacy_marker"
    else:
        local_analysis = "unavailable"

    if marker_complete:
        memory_indexing = "complete"
    elif local_analysis == "complete":
        memory_indexing = "blocked"
    else:
        memory_indexing = "unknown"

    junk_allowed = [v["path"] for v in junk_verdicts.values() if v["removal_allowed"]]
    junk_blocked = [v["path"] for v in junk_verdicts.values() if not v["removal_allowed"]]

    if junk_allowed:
        junk_status = "allowed"
    elif junk_verdicts:
        # Candidates existed and every one failed provenance. That is a blocked
        # class, not an empty one; collapsing the two hides withheld paths.
        junk_status = "blocked"
    else:
        junk_status = "no_candidates"

    classes: Dict[str, Any] = {
        "junk_untracked_removal": {
            "status": junk_status,
            "evidence_required": "untracked status + junk pattern + no literal tracked reference",
            "allowed_paths": sorted(junk_allowed),
            "blocked_paths": sorted(junk_blocked),
            "note": (
                "this class never touches tracked files, so it does not require "
                "dependency edges or a repository-wide index"
            ),
        },
        "tracked_file_mutation": {
            "status": "blocked",
            "evidence_required": (
                "per-candidate dependency evidence from the cleanup evidence "
                "artifact plus project-native before/after readiness proof"
            ),
            "reasons": [],
            "candidate_count": len(findings.get("dead_files", [])),
        },
        "root_stray_mutation": {
            "status": "review_only",
            "evidence_required": "human owner decision; root paths may be runtime inputs",
        },
        "artifact_archive": {
            "status": "review_only",
            "evidence_required": "human owner decision; artifacts may be runtime inputs",
        },
        "project_watchdog_coordination": {
            "status": "read_only",
            "evidence_required": (
                "read-only project-watchdog registry/state observation; cleanup "
                "must not tick, lease, relabel, close, or dispatch GitHub issues"
            ),
        },
    }

    watchdog_context = findings.get("project_watchdog", {})
    if watchdog_context:
        classes["project_watchdog_coordination"].update({
            "watchdog_status": watchdog_context.get("status", "unknown"),
            "global_state": watchdog_context.get("global_state", "unknown"),
            "project_states": watchdog_context.get("project_states", {}),
            "coordination_risk": watchdog_context.get("coordination_risk", "unknown"),
            "blocks_cleanup_execution": watchdog_context.get("blocks_cleanup_execution", False),
        })
    if watchdog_context.get("blocks_cleanup_execution"):
        classes["project_watchdog_coordination"]["status"] = "blocked"
        classes["project_watchdog_coordination"]["reason"] = (
            "project-watchdog may dispatch active issue work in this repo; "
            "coordinate or pause watchdog state before cleanup mutates files"
        )
        if junk_allowed:
            classes["junk_untracked_removal"]["status"] = "blocked"
            classes["junk_untracked_removal"]["blocked_paths"] = sorted(
                set(classes["junk_untracked_removal"]["blocked_paths"]) | set(junk_allowed)
            )
            classes["junk_untracked_removal"]["allowed_paths"] = []
            classes["junk_untracked_removal"]["note"] += (
                "; active project-watchdog coordination currently blocks execution"
            )
            junk_allowed = []

    tracked_reasons = classes["tracked_file_mutation"]["reasons"]
    if artifact_status != "complete":
        tracked_reasons.append(
            f"cleanup evidence artifact is {artifact_status}; run "
            f"{evidence_artifact.get('producer_command', 'ingest-code with --cleanup-evidence --local-artifacts-only')}"
        )
    candidate_verdicts = findings.get("candidate_dependency_evidence", [])
    verdict_counts = Counter(
        str(verdict.get("verdict", "unknown")) for verdict in candidate_verdicts
    )
    no_reference_candidates = verdict_counts.get("no_inbound_references", 0)
    unusable_evidence_count = sum(
        verdict_counts.get(verdict, 0)
        for verdict in (
            "no_dependency_evidence",
            "outside_proof_scope",
            "stale_evidence",
            "parse_failed",
            "outside_analysis_scope",
        )
    )
    dependency_blocked_count = max(
        len(candidate_verdicts) - no_reference_candidates - unusable_evidence_count,
        0,
    )
    if candidate_verdicts:
        classes["tracked_file_mutation"]["verdict_counts"] = dict(sorted(verdict_counts.items()))
    if unusable_evidence_count:
        tracked_reasons.append(
            f"{unusable_evidence_count} candidates have missing, stale, failed, "
            "or out-of-scope dependency evidence"
        )
    if dependency_blocked_count:
        tracked_reasons.append(
            f"{dependency_blocked_count} candidates have dependency evidence that "
            "blocks mutation"
        )
    if no_reference_candidates:
        tracked_reasons.append(
            f"{no_reference_candidates} candidates have no inbound references "
            "inside the current proof scope but still require readiness proof"
        )
    tracked_reasons.append(
        "readiness proof is a separate project-native check and is never inferred "
        "from static analysis"
    )

    mutation = "allowed_limited" if junk_allowed else "no_authorized_mutations"

    return {
        "phases": {
            "local_dependency_analysis": local_analysis,
            "memory_indexing": memory_indexing,
            "assessment": "complete",
            "mutation": mutation,
        },
        "mutation_classes": classes,
        "proof_limits": describe_ingest_proof_limits(ingest_evidence)
        + [
            f"evidence_artifact_status={artifact_status}",
            "unresolved_dynamic_sites="
            + str(evidence_artifact.get("proof_scope", {}).get("unresolved_dynamic_site_count", 0))
            + ": each one is a runtime path static analysis cannot follow",
            "artifact_proof_scope="
            + json.dumps(evidence_artifact.get("proof_scope", {}), sort_keys=True),
        ],
    }


def unusable_evidence_errors(findings: Dict[str, Any]) -> List[str]:
    """Return conditions under which cleanup cannot judge its own evidence.

    Absent evidence is a known state that blocks mutation and exits 0. Corrupt
    or foreign evidence is different: cleanup was handed something it cannot
    trust, and continuing would mean guessing. That is the only exit-2 case.
    """
    errors: List[str] = []

    artifact = findings.get("cleanup_evidence_artifact", {})
    if artifact.get("status") == "invalid":
        errors.append(
            f"cleanup evidence artifact is unreadable: {artifact.get('error', 'unknown error')}"
        )
    else:
        artifact_repo = artifact.get("repository_path")
        if artifact_repo and Path(str(artifact_repo)).resolve() != Path.cwd().resolve():
            errors.append(
                f"cleanup evidence artifact belongs to {artifact_repo}, not this repository"
            )

    marker = findings.get("ingest_code_evidence", {})
    if marker.get("status") == "invalid":
        errors.append(f"ingest-code marker is unreadable: {marker.get('error', 'unknown error')}")

    if not get_all_tracked_files() and findings.get("untracked_files"):
        errors.append("git reported no tracked files; cleanup cannot establish provenance")

    return errors


def build_phase_receipt(
    findings: Dict[str, Any],
    readiness: Dict[str, Any],
    actions_taken: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the resumable phase receipt for this cleanup invocation."""
    ingest_evidence = findings.get("ingest_code_evidence", {})
    evidence_artifact = findings.get("cleanup_evidence_artifact", {})
    return {
        "contract": CLEANUP_RECEIPT_CONTRACT,
        "generated_at": datetime.now().isoformat(),
        "repository_path": str(Path.cwd().resolve()),
        "phases": readiness["phases"],
        "mutation_classes": readiness["mutation_classes"],
        "proof_limits": readiness["proof_limits"],
        "inputs": {
            "ingest_marker": {
                "path": ingest_evidence.get("marker_path"),
                "status": ingest_evidence.get("status"),
                "marker_claimed_complete": ingest_evidence.get("marker_claimed_complete"),
                "marker_warnings": ingest_evidence.get("marker_warnings", []),
                "files_scanned": ingest_evidence.get("files_scanned"),
                "code_index": ingest_evidence.get("code_index", {}),
            },
            "cleanup_evidence_artifact": {
                "path": evidence_artifact.get("artifact_path"),
                "status": evidence_artifact.get("status"),
                "scan_failures": evidence_artifact.get("scan_failures", []),
            },
            "project_watchdog": findings.get("project_watchdog", {}),
        },
        "counts": {
            "root_strays": len(findings.get("root_strays", [])),
            "untracked_files": len(findings.get("untracked_files", [])),
            "lexical_review_candidates": len(findings.get("dead_files", [])),
            "outdated_docs": len(findings.get("outdated_docs", [])),
            "doc_relocations_proposed": sum(
                1 for p in findings.get("doc_organization", [])
                if p.get("verdict") == "relocate_proposed"
            ),
            "doc_deprecations_proposed": sum(
                1 for p in findings.get("doc_organization", [])
                if p.get("verdict") == "deprecate_proposed"
            ),
            "script_scanability_candidates": len(findings.get("script_scanability", [])),
            "public_readiness_blockers": len(
                (findings.get("public_readiness") or {}).get("blockers", [])
            ),
            "quality_gate_blockers": len(
                (findings.get("quality_gate") or {}).get("blockers", [])
            ),
        },
        "best_practices_gate": findings.get("best_practices_gate", {}),
        "actions_taken": actions_taken or [],
        "unusable_evidence": unusable_evidence_errors(findings),
        "resume_commands": [
            evidence_artifact.get("producer_command", ""),
            ingest_evidence.get("recommended_command", ""),
        ],
    }


def write_phase_receipt(receipt: Dict[str, Any], receipt_path: str) -> Path:
    """Persist the phase receipt so a blocked run stays resumable."""
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, default=str))
    return path
