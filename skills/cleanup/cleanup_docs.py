"""Documentation organization. Proposes a home or a deprecation for every tracked doc; every disposition is a move, never a delete."""

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

