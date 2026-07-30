"""Documentation organization. Proposes a home or a deprecation for every tracked doc; every disposition is a move, never a delete."""

from __future__ import annotations

import fnmatch
import ast
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

SCRIPT_SCANABILITY_SUFFIXES = {".py", ".sh", ".bash", ".zsh"}
SCRIPT_SCANABILITY_DIRS = {"scripts", "tools", "bin"}
SCRIPT_SCANABILITY_ENTRYPOINTS = {"run.sh", "sanity.sh"}
MIN_USEFUL_DOCSTRING_CHARS = 20


def get_last_commit_times() -> Dict[str, int]:
    """Return the last commit timestamp for every path, in one git call.

    Asking `git log -1 <file>` per file forks once per document; on a repo with
    a few thousand tracked docs that dominates the entire run. One history walk
    answers the same question for every path at once.
    """
    success, output = run_command(
        ["git", "log", "--format=@%ct", "--name-only", "--no-renames"],
        check=False,
    )
    if not success:
        log_warning("Could not read git history for document staleness")
        return {}

    times: Dict[str, int] = {}
    current: Optional[int] = None
    for line in output.splitlines():
        if line.startswith("@"):
            try:
                current = int(line[1:])
            except ValueError:
                current = None
            continue
        path = line.strip()
        if path and current is not None and path not in times:
            # History is newest-first, so the first sighting is the newest.
            times[path] = current
    return times


def scan_for_outdated_docs() -> List[Dict[str, str]]:
    outdated = []

    tracked_docs = sorted(
        filepath
        for filepath in get_all_tracked_files()
        if filepath.endswith(".md") and Path(filepath).name != "README.md"
    )
    commit_times = get_last_commit_times()
    now = datetime.now().timestamp()

    for filepath in tracked_docs:
        content = read_file_content(filepath)

        if "TODO" in content or "FIXME" in content:
            outdated.append({
                "path": filepath,
                "status": "incomplete",
                "reason": "Contains TODO/FIXME markers"
            })

        timestamp = commit_times.get(filepath)
        if timestamp is None:
            continue
        age_days = (now - timestamp) / 86400
        if age_days > 365:
            outdated.append({
                "path": filepath,
                "status": "stale",
                "reason": f"Not modified in {int(age_days)} days"
            })

    return outdated


def _is_script_like_path(filepath: str, content: str) -> bool:
    path = Path(filepath)
    if path.name in SCRIPT_SCANABILITY_ENTRYPOINTS:
        return True
    if path.suffix not in SCRIPT_SCANABILITY_SUFFIXES:
        return False
    if SCRIPT_SCANABILITY_DIRS.intersection(path.parts):
        return True
    return content.startswith("#!")


def _docstring_is_useful(value: Optional[str]) -> bool:
    if not value:
        return False
    text = " ".join(value.split())
    return len(text) >= MIN_USEFUL_DOCSTRING_CHARS


def _python_scanability_gaps(filepath: str, content: str) -> List[str]:
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as exc:
        return [f"python_parse_error:{exc.lineno or 'unknown'}"]

    gaps: List[str] = []
    if not _docstring_is_useful(ast.get_docstring(tree)):
        gaps.append("missing_file_purpose_docstring")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if not _docstring_is_useful(ast.get_docstring(node)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                gaps.append(f"missing_public_{kind}_docstring:{node.name}")

    if "argparse.ArgumentParser" in content and "description=" not in content:
        gaps.append("argparse_missing_description")

    return gaps


def _shell_scanability_gaps(content: str) -> List[str]:
    gaps: List[str] = []
    header_lines = []
    for line in content.splitlines()[:12]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#!"):
            continue
        header_lines.append(stripped)
    has_header_comment = any(
        line.startswith("#") and len(line.lstrip("#").strip()) >= MIN_USEFUL_DOCSTRING_CHARS
        for line in header_lines
    )
    if not has_header_comment:
        gaps.append("missing_file_purpose_comment")

    lines = content.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:function\s+)?([A-Za-z_][\w.-]*)\s*(?:\(\))?\s*\{", line)
        if not match:
            continue
        name = match.group(1)
        if name.startswith("_"):
            continue
        previous = lines[max(0, index - 3):index]
        if not any(
            prev.strip().startswith("#") and not prev.strip().startswith("#!")
            for prev in previous
        ):
            gaps.append(f"missing_function_comment:{name}")

    return gaps


def scan_script_scanability(tracked: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Flag script files that are hard for humans or agents to scan quickly.

    This is readability debt, not unused-code or deletion evidence. The repair
    path is a separate documentation-only cleanup slice that adds useful
    purpose, usage, and side-effect notes without changing behavior.
    """
    tracked = get_all_tracked_files() if tracked is None else tracked
    findings: List[Dict[str, Any]] = []

    for filepath in sorted(tracked):
        content = read_file_content(filepath)
        if not content or not _is_script_like_path(filepath, content):
            continue

        suffix = Path(filepath).suffix
        if suffix == ".py":
            gaps = _python_scanability_gaps(filepath, content)
        elif suffix in {".sh", ".bash", ".zsh"}:
            gaps = _shell_scanability_gaps(content)
        else:
            gaps = ["unsupported_script_language_scanability"]

        if not gaps:
            continue

        findings.append({
            "path": filepath,
            "verdict": "script_scanability_repair",
            "reason": "Script is missing purpose, usage, or public API scanability notes",
            "missing": gaps,
            "repair_class": "readability_only",
            "automatic_cleanup_mutation_allowed": False,
            "proof_required": "parse/compile plus the script's --help or narrow sanity command",
        })

    return findings


def append_cleanup_report_preamble(plan: List[str], findings: Dict[str, Any]) -> None:
    """Append the evidence-first report sections required before details."""
    root_strays_count = len(findings.get("root_strays", []))
    uncommitted_count = len(findings.get("uncommitted_changes", []))
    untracked_count = len(findings.get("untracked_files", []))
    dead_count = len(findings.get("dead_files", []))
    outdated_count = len(findings.get("outdated_docs", []))
    organization = findings.get("doc_organization") or []
    actionable = [
        p for p in organization
        if p["verdict"] in {"relocate_proposed", "deprecate_proposed"}
    ]
    scanability = findings.get("script_scanability") or []
    artifact = findings.get("cleanup_evidence_artifact") or {}
    evidence_status = artifact.get("status", "missing")

    risk_items = []
    if uncommitted_count:
        risk_items.append("`[F-001]` Dirty worktree requires ownership triage before mutation")
    if root_strays_count:
        risk_items.append("`[F-002]` Root-level strays require owner review")
    if dead_count and evidence_status != "complete":
        risk_items.append("`[F-003]` Tracked-file candidates lack complete dependency evidence")
    if scanability:
        risk_items.append("`[F-004]` Script scanability gaps make maintenance harder")
    if not risk_items:
        risk_items.append("No high-risk cleanup finding was produced by this assessment.")

    has_findings = any([
        root_strays_count, uncommitted_count, untracked_count, dead_count,
        outdated_count, actionable, scanability,
    ])
    overall = "Needs Changes" if has_findings else "Partially Verified"

    plan.extend([
        "## Report Summary",
        "",
        f"**Overall Finding:** {overall}",
        "",
        (
            "**Core Conclusion:** This report identifies cleanup candidates and "
            "mutation boundaries from local repository evidence. Automatic "
            "execution is limited to untracked junk paths that clear provenance; "
            "tracked files, root strays, artifacts, documentation moves, and "
            "script scanability repairs require explicit review or a separate "
            "repair slice."
        ),
        "",
        (
            "**Evidence Basis:** The report uses git status, tracked/untracked "
            "file inventory, lexical reference scans, cleanup evidence artifacts, "
            "ingest markers, project-watchdog state, documentation scans, and "
            "best-practices gate mapping where available."
        ),
        "",
        "**Highest-Risk Issues:**",
        "",
    ])
    for item in risk_items:
        plan.append(f"1. {item}")
    plan.extend([
        "",
        "**Immediate Next Steps:**",
        "",
        "1. `[A-001]` Run or review `--worktree-audit` before mutating a dirty repository.",
        "2. `[A-002]` Refresh `.cleanup-evidence.json` before proposing tracked-file moves.",
        "3. `[A-003]` Handle script scanability as readability-only documentation repair.",
        "",
        (
            "**Non-Claims:** This report does not prove unused code, runtime "
            "safety, release readiness, semantic correctness, or that any tracked "
            "file is safe to delete."
        ),
        "",
        "## Scope",
        "",
        "- Reviewed: repository file inventory, cleanup candidates, evidence states, documentation organization, script scanability, and mutation authority.",
        "- Not reviewed: product correctness, full runtime behavior, external service health, semantic code ownership, and human acceptance of moves or repairs.",
        "- Mutation policy: only untracked junk with per-path provenance may be removed by `--execute`; all other classes require explicit review or a separate repair slice.",
        "",
        "## Source-of-Truth Inventory",
        "",
        "| Source ID | Source Name | Type | Recency | Used For | Limitations |",
        "|---|---|---|---|---|---|",
        "| S-001 | `git status --porcelain=v1` | git inventory | fresh for this run | F-001, worktree risk | Does not identify semantic ownership |",
        "| S-002 | tracked/untracked file lists | git inventory | fresh for this run | cleanup candidate discovery | Does not prove runtime usage |",
        "| S-003 | lexical reference scan | local static scan | fresh for this run | dead-file nomination, junk provenance | Lexical absence is not dependency proof |",
        "| S-004 | `.cleanup-evidence.json` | dependency evidence artifact | status shown below | tracked candidate verdicts | Missing or stale evidence blocks tracked mutation |",
        "| S-005 | `.ingest-code.json` | aggregate ingest marker | status shown below | context only | Aggregate counters are not per-file safety evidence |",
        "| S-006 | documentation and script scans | local static scan | fresh for this run | doc/readability findings | Findings require review before repair |",
        "| S-007 | best-practices gate mapping | local rule mapping | fresh for this run | changed-file proof planning | Mapping is not proof unless checks execute |",
        "",
        "## Finding Index",
        "",
        "| Finding ID | Status | Evidence | Valid Next Action | Non-Claim |",
        "|---|---|---|---|---|",
        f"| F-001 | {'Needs Changes' if uncommitted_count else 'Partially Verified'} | `{uncommitted_count}` dirty entries | Run `--worktree-audit` and isolate owner-approved changes | Does not prove entries are disposable |",
        f"| F-002 | {'Needs Decision' if root_strays_count else 'Partially Verified'} | `{root_strays_count}` root strays | Ask owner before moving or archiving | Does not authorize mutation |",
        f"| F-003 | {'Blocked' if dead_count and evidence_status != 'complete' else 'Partially Verified'} | `{dead_count}` lexical candidates; evidence `{evidence_status}` | Refresh per-candidate evidence and run readiness checks | Does not prove unused code |",
        f"| F-004 | {'Needs Changes' if scanability else 'Partially Verified'} | `{len(scanability)}` script scanability candidates | Apply readability-only repair slice | Does not prove behavior is wrong |",
        "",
    ])


def _current_repo_slugs() -> Set[str]:
    """Repository identifiers that legitimately name this project."""
    slugs = {Path.cwd().resolve().name.lower()}
    success, output = run_command(["git", "remote", "get-url", "origin"], check=False)
    if success and output.strip():
        match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", output.strip())
        if match:
            slug = match.group(1).lower()
            slugs.add(slug)
            slugs.add(slug.split("/")[-1])
    return slugs


def _foreign_repo_reference(content: str, filepath: str) -> Optional[str]:
    """Return another repo slug this doc is about, if it is about one.

    A document describing a different repository is not documentation of this
    project; it travelled here. It is never deleted -- it is proposed for
    docs/deprecated so the history survives and the reader is not misled.
    """
    if not content:
        return None
    ours = _current_repo_slugs()
    head = "\n".join(content.splitlines()[:40])
    counts: Dict[str, int] = {}
    # correctness-regex-only-known-grammar: both patterns are scoped to grammars
    # that are specified rather than learned. GITHUB_SLUG_PATTERN matches the
    # documented github.com/<owner>/<repo> URL shape; REPO_DECLARATION_PATTERN
    # matches an explicit "Repo:"-style declaration line. Neither is used to
    # classify prose, the failure mode is an explicit None, and
    # test_foreign_repo_doc_is_detected / test_foreign_repo_ignores_this_repository
    # cover an accepted and a rejected input.
    for match in re.finditer(GITHUB_SLUG_PATTERN, head + " "):
        slug = match.group(1).lower()
        if slug in ours or slug.split("/")[-1] in ours:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    for match in re.finditer(REPO_DECLARATION_PATTERN, head):
        slug = match.group(1).lower()
        if slug in ours or slug.split("/")[-1] in ours:
            continue
        counts[slug] = counts.get(slug, 0) + 2
    if not counts:
        return None
    return max(counts, key=counts.get)


def _doc_relocation_target(filepath: str) -> str:
    """Propose a docs/ home for a root-level doc, from its filename stem."""
    stem = Path(filepath).stem.lower()
    tokens = set(re.split(r"[^a-z0-9]+", stem)) - {""}
    for keywords, target_dir in DOC_RELOCATION_HINTS:
        if tokens & keywords:
            return f"{target_dir}/{Path(filepath).name}"
    return f"docs/{Path(filepath).name}"


def find_markdown_inbound_links(target: str, tracked: Set[str]) -> List[str]:
    """Return tracked files that reference `target` by path or filename.

    A relocation that silently breaks these links trades one kind of mess for a
    worse one, so every proposal carries the list it would have to rewrite.
    """
    name = Path(target).name
    inbound = []
    for candidate in tracked:
        if candidate == target:
            continue
        if Path(candidate).suffix not in {".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".toml", ".sh"}:
            continue
        content = read_file_content(candidate)
        if not content:
            continue
        if target in content or f"({name})" in content or f"]({name}" in content:
            inbound.append(candidate)
    return sorted(inbound)


def scan_doc_organization(
    tracked: Optional[Set[str]] = None,
    commit_times: Optional[Dict[str, int]] = None,
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Propose a home or a deprecation for every tracked markdown doc.

    Detection alone leaves the reader with a list and no decision. This emits a
    verdict per doc with the evidence behind it: where it would go, what links
    to it, how stale it is. Proposals are never executed without an explicit
    opt-in flag, and conventional root files are never proposed at all.
    """
    tracked = get_all_tracked_files() if tracked is None else tracked
    commit_times = get_last_commit_times() if commit_times is None else commit_times
    now = datetime.now().timestamp() if now is None else now

    docs = sorted(f for f in tracked if f.endswith(".md"))
    proposals: List[Dict[str, Any]] = []

    for filepath in docs:
        name = Path(filepath).name
        is_root = "/" not in filepath
        timestamp = commit_times.get(filepath)
        age_days = int((now - timestamp) / 86400) if timestamp else None
        content = read_file_content(filepath)
        has_markers = bool(content) and ("TODO" in content or "FIXME" in content)

        if is_root and name in CONVENTIONAL_ROOT_DOCS:
            proposals.append({
                "path": filepath,
                "verdict": "keep_root_conventional",
                "reason": f"{name} is resolved by name by GitHub or package tooling",
                "proposed_path": None,
                "inbound_references": [],
                "age_days": age_days,
                "has_todo_markers": has_markers,
            })
            continue

        inbound = find_markdown_inbound_links(filepath, tracked)
        stale = age_days is not None and age_days > DOC_STALE_DAYS

        # Content-shape defects. These do not depend on age: an empty doc or a
        # stray copy is wrong the day it lands, and waiting a year to say so
        # leaves a reader trusting a file with nothing in it.
        stem = Path(filepath).stem
        is_duplicate = any(pattern in stem for pattern in DOC_DUPLICATE_PATTERNS)
        # Content verdicts require the file to be present in the working tree.
        # A tracked path that is absent is a deletion under review, not an
        # empty document, and must not be reported as one.
        present = Path(filepath).is_file()
        body = (content or "").strip()
        is_empty = present and len(body) == 0
        heading_only = present and bool(body) and all(
            not line.strip() or line.lstrip().startswith("#")
            for line in body.splitlines()
        )
        foreign_repo = _foreign_repo_reference(content, filepath) if present else None

        if is_duplicate:
            proposals.append({
                "path": filepath,
                "verdict": "duplicate_copy",
                "reason": "Filename matches a copy artifact, not a deliberate name",
                "proposed_path": f"{DOC_DEPRECATION_DIR}/{name}",
                "inbound_references": inbound,
                "age_days": age_days,
                "has_todo_markers": has_markers,
            })
            continue

        if is_empty:
            proposals.append({
                "path": filepath,
                "verdict": "empty_doc",
                "reason": "Tracked document has no content",
                "proposed_path": f"{DOC_DEPRECATION_DIR}/{name}",
                "inbound_references": inbound,
                "age_days": age_days,
                "has_todo_markers": has_markers,
            })
            continue

        if foreign_repo:
            proposals.append({
                "path": filepath,
                "verdict": "foreign_repo_doc",
                "reason": f"Documents another repository ({foreign_repo}), not this one",
                "proposed_path": f"{DOC_DEPRECATION_DIR}/{name}",
                "inbound_references": inbound,
                "age_days": age_days,
                "has_todo_markers": has_markers,
            })
            continue

        if heading_only:
            proposals.append({
                "path": filepath,
                "verdict": "stub_doc",
                "reason": "Headings only, no prose — a placeholder that reads as documentation",
                "proposed_path": f"{DOC_DEPRECATION_DIR}/{name}",
                "inbound_references": inbound,
                "age_days": age_days,
                "has_todo_markers": has_markers,
            })
            continue

        if stale and not inbound:
            verdict = "deprecate_proposed"
            proposed = f"{DOC_DEPRECATION_DIR}/{name}"
            reason = f"Unreferenced and unmodified for {age_days} days"
        elif is_root:
            verdict = "relocate_proposed"
            proposed = _doc_relocation_target(filepath)
            reason = "Root-level doc outside the conventional root set"
        else:
            verdict = "keep"
            proposed = None
            reason = "Already filed under a docs path"

        proposals.append({
            "path": filepath,
            "verdict": verdict,
            "reason": reason,
            "proposed_path": proposed,
            "inbound_references": inbound,
            "age_days": age_days,
            "has_todo_markers": has_markers,
        })

    return proposals
