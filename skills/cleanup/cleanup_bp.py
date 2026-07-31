"""Best-practices gate. Resolves which best-practices-* skill governs each changed file and executes the matching rule scanners from skills-ci."""

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
from cleanup_evidence import _working_tree_sha256


def best_practices_skill_for(filepath: str) -> Optional[str]:
    """Return the best-practices skill governing a file, or None."""
    for marker, skill in BEST_PRACTICES_BY_PATH:
        if filepath.endswith(marker) or marker in filepath:
            return skill
    return BEST_PRACTICES_BY_SUFFIX.get(Path(filepath).suffix)


def _available_best_practices_skills(skills_root: Optional[Path] = None) -> Set[str]:
    """Names of best-practices-* skills installed alongside this one."""
    root = skills_root if skills_root is not None else Path(__file__).resolve().parent.parent
    if not root.is_dir():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("best-practices-")}


def _load_skills_ci_scanners(skills_root: Optional[Path] = None):
    """Import the executable best-practices rule scanners from skills-ci.

    best-practices-* skills are guidance documents; their sanity.sh validates
    the skill's own files, not a target project. skills-ci holds the executable
    form of the same rules, so the gate runs those rather than claiming a pass
    no checker produced.
    """
    root = skills_root if skills_root is not None else Path(__file__).resolve().parent.parent
    ci_dir = root / "skills-ci"
    if not (ci_dir / "scanners.py").is_file():
        return None
    if str(ci_dir) not in sys.path:
        sys.path.insert(0, str(ci_dir))
    try:
        import scanners  # type: ignore
        # The rule scanners are spread across four modules. Attach the ones this
        # gate uses onto a single namespace so callers ask for a rule by name
        # rather than knowing which file it happens to live in.
        for module_name in ("quality_scanners", "style_scanners", "runtime_scanners"):
            try:
                extra = __import__(module_name)
            except Exception as exc:
                log_warning(f"best-practices scanner module {module_name} unavailable: {exc}")
                continue
            for attr in dir(extra):
                if attr.startswith("scan_") and not hasattr(scanners, attr):
                    setattr(scanners, attr, getattr(extra, attr))
        return scanners
    except Exception as exc:
        # correctness-no-silent-fallback: a gate that cannot load its scanners
        # must say so. Swallowing this would let the run report "no violations"
        # when in fact no rule was ever evaluated.
        log_error(f"best-practices scanners failed to import from {ci_dir}: {exc}")
        return None


def run_best_practices_checks(
    changed_files: List[str],
    skills_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute the rule scanners that exist, over the changed files.

    Returns per-skill violations plus an explicit record of which skills have no
    executable checker. A skill with no checker is reported as such -- never as
    a pass.
    """
    scanners = _load_skills_ci_scanners(skills_root)
    results: Dict[str, Any] = {
        "executed": {},
        "no_executable_checker": [],
        "scanner_source": None if scanners is None else "skills-ci",
    }
    if scanners is None:
        results["error"] = "skills-ci scanners unavailable; no rules were executed"
        return results

    changed = {f for f in changed_files}
    by_skill: Dict[str, List[str]] = {}
    for filepath in changed:
        skill = best_practices_skill_for(filepath)
        if skill:
            by_skill.setdefault(skill, []).append(filepath)

    for skill, files in sorted(by_skill.items()):
        if skill == "best-practices-python" and hasattr(scanners, "scan_best_practices_python"):
            try:
                violations, _ = scanners.scan_best_practices_python(Path.cwd())
            except Exception as exc:  # scanner failure is reported, never swallowed
                results["executed"][skill] = {"status": "scanner_error", "error": str(exc)}
                continue
            # The rest of the Python rule set. Running only the file-length and
            # import checks would under-report a skill whose rules also cover
            # regex misuse, __init__ bloat, mock-only tests, and blocking
            # subprocess calls in async code.
            for extra_scanner in (
                "scan_regex_classifier",
                "scan_style_thin_init_py",
                "scan_mock_only_tests",
                "scan_subprocess_hygiene",
            ):
                fn = getattr(scanners, extra_scanner, None)
                if fn is None:
                    log_warning(f"python rule scanner missing: {extra_scanner}")
                    continue
                try:
                    violations.extend(fn(Path.cwd()))
                except Exception as exc:
                    log_error(f"python rule scanner {extra_scanner} failed: {exc}")
            relevant = [
                {"rule": v.rule, "severity": v.severity, "path": v.path, "message": v.message}
                for v in violations
                if any(str(v.path).endswith(f) or f in str(v.path) for f in files)
            ]
            results["executed"][skill] = {
                "status": "ran",
                "files_considered": sorted(files),
                "violations": relevant,
                "violation_count": len(relevant),
            }
        elif skill == "best-practices-skills" and hasattr(scanners, "scan_best_practices_skills"):
            try:
                violations = scanners.scan_best_practices_skills(Path.cwd())
            except Exception as exc:
                results["executed"][skill] = {"status": "scanner_error", "error": str(exc)}
                continue
            results["executed"][skill] = {
                "status": "ran",
                "files_considered": sorted(files),
                "violations": [
                    {"rule": v.rule, "severity": v.severity, "path": v.path, "message": v.message}
                    for v in violations
                ],
                "violation_count": len(violations),
            }
        else:
            results["no_executable_checker"].append({
                "skill": skill,
                "files": sorted(files),
                "reason": "guidance-only skill; no executable rule scanner exists",
            })

    return results


def evaluate_best_practices_gate(
    changed_files: List[str],
    previous_receipt: Optional[Dict[str, Any]] = None,
    skills_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Resolve which best-practices skills a cleanup slice must run.

    SKILL.md has required this gate and required the receipt to report it since
    before any code existed for it. This computes the mapping and the per-skill
    counts; it reports what must run rather than claiming a run happened.
    """
    available = _available_best_practices_skills(skills_root)
    baseline = {}
    if previous_receipt:
        baseline = (previous_receipt.get("best_practices_gate") or {}).get("file_digests") or {}

    per_skill: Dict[str, Dict[str, Any]] = {}
    not_applicable: List[str] = []
    file_digests: Dict[str, str] = {}

    for filepath in sorted(set(changed_files)):
        skill = best_practices_skill_for(filepath)
        if skill is None:
            not_applicable.append(filepath)
            continue

        digest = _working_tree_sha256(filepath)
        if digest:
            file_digests[filepath] = digest

        entry = per_skill.setdefault(skill, {
            "skill": skill,
            "available": skill in available,
            "checked": [],
            "skipped_unchanged": [],
            "failed": [],
        })

        if digest and baseline.get(filepath) == digest:
            entry["skipped_unchanged"].append(filepath)
        else:
            entry["checked"].append(filepath)

    unavailable = sorted(s for s, e in per_skill.items() if not e["available"])
    required = sorted(s for s, e in per_skill.items() if e["checked"])

    return {
        "contract": "cleanup.best_practices_gate.v1",
        "status": "requires_run" if required else "satisfied",
        "required_skills": required,
        "unavailable_skills": unavailable,
        "per_skill": [per_skill[s] for s in sorted(per_skill)],
        "not_applicable": not_applicable,
        "counts": {
            "checked": sum(len(e["checked"]) for e in per_skill.values()),
            "skipped_unchanged": sum(len(e["skipped_unchanged"]) for e in per_skill.values()),
            "failed": sum(len(e["failed"]) for e in per_skill.values()),
            "not_applicable": len(not_applicable),
        },
        "file_digests": file_digests,
        "proof_limit": (
            "mapping_only: this resolves which skills govern the changed files and "
            "which files changed since the last receipt. It does not execute the "
            "skills, and never reports a pass the skill did not produce."
        ),
    }


