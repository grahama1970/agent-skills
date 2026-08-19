"""Risk-based coverage sufficiency: does every load-bearing seam have a guard?

Counting cases is gameable -- twelve variants of one token ping protect one
seam twelve times and everything else zero. Sufficiency instead asks, per
declared seam: is there at least one case *capable of detecting a regression*
at that seam, in each evidence class the seam's risk requires? A case covers a
seam only when it lists that seam AND carries an oracle that can fail; merely
traversing the component (a bare ``exit 0`` smoke) does not count.

This module is static-presence analysis (it reads fixtures, it does not run
them): it answers "is a capable guard declared?" Pass/fail of those guards is
``run``'s job; freshness of live proof comes from the regression registry's
``last_proven``. Coverage and freshness are deliberately separate dimensions.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import evidence as evidence_mod
import regressions as regressions_mod
from evidence import LIVE_CLASSES

SEAM_TYPES = frozenset(
    {
        "pure deterministic transform",
        "filesystem/process",
        "persistent state/database/index",
        "external HTTP/API/provider",
        "browser/UI transport",
        "audio/device/media path",
        "scheduler/concurrency",
        "restart/resume/idempotency",
        "multi-agent/orchestration",
        "mutation/destructive effect",
        "security/compliance/human-authority",
    }
)


def validate_seams(manifest: dict[str, Any]) -> list[str]:
    seams = manifest.get("seams")
    if seams is None:
        return []
    if not isinstance(seams, list):
        return ["seams must be a list"]
    problems: list[str] = []
    seen: set[str] = set()
    for seam in seams:
        sid = seam.get("seam_id")
        if not isinstance(sid, str) or not sid:
            problems.append("every seam needs a non-empty seam_id")
            continue
        if sid in seen:
            problems.append(f"duplicate seam_id {sid!r}")
        seen.add(sid)
        if not seam.get("required_evidence"):
            problems.append(f"seam {sid!r} declares no required_evidence classes")
    return problems


def _case_is_weak(case: dict[str, Any]) -> bool:
    """A case is a weak/smoke guard if it cannot detect a regression.

    A positive case that only asserts ``exit_code: 0`` with no output check, no
    artifact readback, and no negative expectation would still pass if the skill
    silently produced wrong output -- it traverses the seam without guarding it.
    """
    expected = case.get("expected") or {}
    if expected.get("artifacts"):
        return False
    if expected.get("stdout_contains") or expected.get("stderr_contains") or expected.get("stdout_excludes"):
        return False
    if case.get("type") in {"negative", "adversarial"}:
        return False
    if expected.get("exit_code", 0) != 0:
        return False
    return True


def _seam_cases(seam_id: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cases if seam_id in (c.get("seams") or [])]


def _present_classes(cases: list[dict[str, Any]]) -> set[str]:
    """Evidence classes for which at least one non-weak capable case exists."""
    present: set[str] = set()
    for case in cases:
        if _case_is_weak(case):
            continue
        qual = evidence_mod.qualify(case)
        cls = qual["effective"]
        # A downgraded pseudo-live case contributes its downgraded class, never
        # the live class it merely claimed.
        present.add(cls)
    return present


def _required_classes(seam: dict[str, Any]) -> set[str]:
    req = seam.get("required_evidence") or []
    return {c for c in req if c in evidence_mod.EVIDENCE_CLASSES}


def audit_skill(skill_dir: Path, now: datetime) -> dict[str, Any]:
    """Per-skill seam sufficiency: covered seams, gaps, and prioritized next evals."""
    fixture = skill_dir / "fixtures" / "agentic_eval.json"
    if not fixture.is_file():
        return {"skill": skill_dir.name, "has_fixture": False, "seams": [], "summary": {}}
    manifest = json.loads(fixture.read_text(encoding="utf-8"))
    seams = list(manifest.get("seams") or [])
    cases = list(manifest.get("cases") or [])
    claims = list(manifest.get("capability_claims") or [])
    # Live companion fixtures carry the cases that satisfy live_e2e slots; a
    # skill's coverage is the union, or every live seam reads as a gap even
    # when a live guard exists (agent-skills, 2026-08-19).
    live_fixture = skill_dir / "fixtures" / "agentic_eval_live.json"
    if live_fixture.is_file():
        live = json.loads(live_fixture.read_text(encoding="utf-8"))
        cases.extend(live.get("cases") or [])
        seen_seams = {s.get("seam_id") for s in seams}
        seams.extend(s for s in (live.get("seams") or []) if s.get("seam_id") not in seen_seams)
        seen_claims = {c.get("id") for c in claims}
        claims.extend(c for c in (live.get("capability_claims") or []) if c.get("id") not in seen_claims)
    reg_audit = regressions_mod.audit_skill(skill_dir, now)
    reg_by_seam: dict[str, list[str]] = {}
    for row in reg_audit.get("regressions", []):
        if row["status"] != regressions_mod.STATUS_ACTIVE or not row["established_fail_before_fix"]:
            continue
        for sid in row.get("seam_ids", []):
            reg_by_seam.setdefault(sid, []).append(row["regression_id"])

    seam_rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for seam in seams:
        sid = seam["seam_id"]
        covering = _seam_cases(sid, cases)
        present = _present_classes(covering)
        required = _required_classes(seam)
        missing = sorted(required - present)
        weak_only = bool(covering) and all(_case_is_weak(c) for c in covering)
        criticality = seam.get("criticality", "critical")
        row = {
            "seam_id": sid,
            "seam_type": seam.get("seam_type"),
            "criticality": criticality,
            "claim_id": seam.get("claim_id"),
            "required_evidence": sorted(required),
            "present_evidence": sorted(present),
            "missing_evidence": missing,
            "covering_cases": [c["name"] for c in covering],
            "weak_only": weak_only,
            "has_live_coverage": bool(present & LIVE_CLASSES),
            "incident_regressions": reg_by_seam.get(sid, []),
            "covered": not missing and not weak_only and bool(covering),
        }
        seam_rows.append(row)
        if not row["covered"]:
            gaps.append(
                {
                    "seam_id": sid,
                    "criticality": criticality,
                    "missing_evidence": missing or (["<no covering case>"] if not covering else ["<weak coverage only>"]),
                    "claim_id": seam.get("claim_id"),
                }
            )

    # Prioritize gaps: critical first, then by number of missing classes.
    crit_rank = {"critical": 0, "important": 1, "optional": 2}
    gaps.sort(key=lambda g: (crit_rank.get(g["criticality"], 3), -len(g["missing_evidence"])))

    critical_seams = [s for s in seam_rows if s["criticality"] == "critical"]
    critical_covered = [s for s in critical_seams if s["covered"]]
    verdict = "READY" if critical_seams and len(critical_covered) == len(critical_seams) else "NOT_READY"
    if not critical_seams:
        verdict = "NO_CRITICAL_SEAMS_DECLARED"

    return {
        "skill": skill_dir.name,
        "has_fixture": True,
        "validation_problems": validate_seams(manifest),
        "declared_critical_claims": sum(1 for c in claims if c.get("criticality", "critical") == "critical"),
        "material_seams": len(seam_rows),
        "seams": seam_rows,
        "prioritized_gaps": gaps,
        "regression_summary": reg_audit["summary"],
        "summary": {
            "material_seams": len(seam_rows),
            "seams_covered": sum(1 for s in seam_rows if s["covered"]),
            "seams_with_no_case": sum(1 for s in seam_rows if not s["covering_cases"]),
            "seams_weak_only": sum(1 for s in seam_rows if s["weak_only"]),
            "seams_with_live_coverage": sum(1 for s in seam_rows if s["has_live_coverage"]),
            "critical_seams": len(critical_seams),
            "critical_seams_covered": len(critical_covered),
            "verdict": verdict,
            "highest_priority_gaps": [g["seam_id"] for g in gaps[:5]],
        },
    }


def audit_root(skills_root: Path, now: datetime) -> dict[str, Any]:
    """Coverage sufficiency across a skills root, for skills that declare seams."""
    reports = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if (p / "SKILL.md").exists()):
        fixture = skill_dir / "fixtures" / "agentic_eval.json"
        if not fixture.is_file():
            continue
        try:
            manifest = json.loads(fixture.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not manifest.get("seams"):
            continue
        reports.append(audit_skill(skill_dir, now))
    return {
        "schema": "agentic_evals.coverage_audit.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "static seam-coverage sufficiency audit (presence of capable guards, not their pass/fail)",
        "skills_root": str(skills_root),
        "skills_audited": len(reports),
        "skills": reports,
    }
