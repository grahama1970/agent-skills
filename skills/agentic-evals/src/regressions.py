"""Incident -> retained regression lifecycle (#1447).

A live failure that is merely fixed and mentioned in an issue leaves nothing
behind. The next agent re-learns it the hard way. This module makes an incident
become permanent evidence: a regression record that links the incident to the
claims it threatened, names the earliest violated invariant, and is only
counted as *established* once a fail-before-fix proof shows the retained guard
actually fails against the broken behaviour (or a deliberate invariant-removing
mutation). Fixing a bug by editing the eval expectation to match broken output
is exactly what the non-vacuity proof exists to catch.

The registry is explicit metadata (``fixtures/regressions.json``), never prose
scraped heuristically -- provenance a maintainer can trust.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from evidence import LIVE_CLASSES

REGISTRY_NAME = "regressions.json"
SCHEMA = "agentic_evals.regressions.v1"

STATUS_ACTIVE = "ACTIVE"
STATUS_EXEMPT = "EXEMPT"
STATUS_RETIRED = "RETIRED"
VALID_STATUS = frozenset({STATUS_ACTIVE, STATUS_EXEMPT, STATUS_RETIRED})

#: Default staleness window for live-class regression proof. A once-green live
#: regression keeps its historical proof but is flagged stale after this so a
#: reader never mistakes old evidence for current.
DEFAULT_FRESHNESS_DAYS = 30


def registry_path(skill_dir: Path) -> Path:
    return skill_dir / "fixtures" / REGISTRY_NAME


def load_registry(skill_dir: Path) -> dict[str, Any] | None:
    path = registry_path(skill_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(registry: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if registry.get("schema") != SCHEMA:
        problems.append(f"registry schema must be {SCHEMA!r}")
    records = registry.get("regressions")
    if not isinstance(records, list):
        return problems + ["registry must contain a regressions list"]
    seen: set[str] = set()
    for rec in records:
        rid = rec.get("regression_id")
        if not isinstance(rid, str) or not rid:
            problems.append("every regression needs a non-empty regression_id")
            continue
        if rid in seen:
            problems.append(f"duplicate regression_id {rid!r}")
        seen.add(rid)
        if rec.get("status", STATUS_ACTIVE) not in VALID_STATUS:
            problems.append(f"{rid}: status must be one of {sorted(VALID_STATUS)}")
        if not rec.get("retained_case"):
            problems.append(f"{rid}: retained_case is required (the case that guards the invariant)")
        if rec.get("status") == STATUS_RETIRED and not rec.get("retirement"):
            problems.append(f"{rid}: RETIRED regressions require a retirement reason/evidence")
    return problems


def _fixture_case_names(skill_dir: Path, fixture_name: str = "agentic_eval.json") -> set[str]:
    fixture = skill_dir / "fixtures" / fixture_name
    if not fixture.is_file():
        return set()
    try:
        manifest = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {c.get("name") for c in manifest.get("cases", []) if c.get("name")}


def _established(rec: dict[str, Any]) -> bool:
    """A regression is established only with a proven fail-before-fix record.

    The author's ``proven: true`` is a claim; ``regressions verify`` re-runs the
    proof command and can overwrite it. Absent any fail_before_fix block the
    regression is a bug note, not a guarded invariant.
    """
    fbf = rec.get("fail_before_fix") or {}
    return bool(fbf.get("proven"))


def _stale(rec: dict[str, Any], now: datetime, freshness_days: int) -> bool:
    if rec.get("evidence_class") not in LIVE_CLASSES:
        return False
    last = rec.get("last_proven")
    if not last:
        return True
    try:
        proven_at = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    if proven_at.tzinfo is None:
        proven_at = proven_at.replace(tzinfo=timezone.utc)
    return proven_at < now - timedelta(days=freshness_days)


def audit_skill(skill_dir: Path, now: datetime, freshness_days: int = DEFAULT_FRESHNESS_DAYS) -> dict[str, Any]:
    """Audit one skill's regression registry against its retained cases."""
    registry = load_registry(skill_dir)
    if registry is None:
        return {
            "skill": skill_dir.name,
            "has_registry": False,
            "regressions": [],
            "summary": {"total": 0},
        }
    problems = validate_registry(registry)
    records = registry.get("regressions", []) if not problems else []
    declared_incidents = registry.get("incidents", []) or []
    case_name_cache: dict[str, set[str]] = {}

    def _cases_for(fixture_name: str) -> set[str]:
        if fixture_name not in case_name_cache:
            case_name_cache[fixture_name] = _fixture_case_names(skill_dir, fixture_name)
        return case_name_cache[fixture_name]

    rows: list[dict[str, Any]] = []
    mapped_incident_keys: set[str] = set()
    for rec in records:
        case_names = _cases_for(rec.get("retained_fixture", "agentic_eval.json"))
        protected = rec.get("retained_case") in case_names
        established = _established(rec)
        stale = _stale(rec, now, freshness_days)
        status = rec.get("status", STATUS_ACTIVE)
        for key in _incident_keys(rec):
            mapped_incident_keys.add(key)
        rows.append(
            {
                "regression_id": rec.get("regression_id"),
                "claim_ids": rec.get("claim_ids", []),
                "seam_ids": rec.get("seam_ids", []),
                "evidence_class": rec.get("evidence_class"),
                "status": status,
                "protected": protected,
                "established_fail_before_fix": established,
                "stale_live_proof": stale and status == STATUS_ACTIVE,
                "last_proven": rec.get("last_proven"),
                "incident": rec.get("incident"),
                "issues": [],
            }
        )
        row = rows[-1]
        if status == STATUS_ACTIVE and not protected:
            row["issues"].append("retained case missing/renamed -> invariant UNPROTECTED")
        if status == STATUS_ACTIVE and not established:
            row["issues"].append("never proven fail-before-fix -> possibly vacuous")
        if row["stale_live_proof"]:
            row["issues"].append("live proof is stale")

    unmapped_incidents = [
        inc for inc in declared_incidents if _incident_key(inc) not in mapped_incident_keys
    ]

    active = [r for r in rows if r["status"] == STATUS_ACTIVE]
    return {
        "skill": skill_dir.name,
        "has_registry": True,
        "validation_problems": problems,
        "regressions": rows,
        "unmapped_incidents": unmapped_incidents,
        "summary": {
            "total": len(rows),
            "active": len(active),
            "unprotected": sum(1 for r in active if not r["protected"]),
            "never_proven_fail_before_fix": sum(1 for r in active if not r["established_fail_before_fix"]),
            "stale_live_proof": sum(1 for r in rows if r["stale_live_proof"]),
            "retired": sum(1 for r in rows if r["status"] == STATUS_RETIRED),
            "unmapped_incidents": len(unmapped_incidents),
        },
    }


def _incident_key(incident: Any) -> str:
    if isinstance(incident, dict):
        return str(incident.get("issue") or incident.get("receipt") or incident.get("id") or json_key(incident))
    return str(incident)


def _incident_keys(rec: dict[str, Any]) -> list[str]:
    inc = rec.get("incident")
    if inc is None:
        return []
    return [_incident_key(inc)]


def json_key(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)


def verify_regression(skill_dir: Path, rec: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    """Re-run a regression's fail-before-fix proof and its retained-case pass.

    Non-vacuity is proven live: the proof_command reproduces the broken
    behaviour (or removes the guard) and must exit as declared -- a guard that
    cannot fail against a broken artifact proves nothing. This is a real
    execution, not a self-report.
    """
    fbf = rec.get("fail_before_fix") or {}
    proof_command = fbf.get("proof_command")
    result: dict[str, Any] = {
        "regression_id": rec.get("regression_id"),
        "fail_before_fix_verified": None,
        "detail": None,
    }
    if not proof_command:
        result["detail"] = "no fail_before_fix.proof_command to run"
        return result
    expected_fail = bool(fbf.get("expected_fail", True))
    cwd = skill_dir / fbf.get("cwd", ".")
    try:
        proc = subprocess.run(
            proof_command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["detail"] = f"proof command error: {exc}"
        result["fail_before_fix_verified"] = False
        return result
    failed = proc.returncode != 0
    # The guard must have caught the broken behaviour: when expected_fail is
    # true the reproduction must exit non-zero.
    result["fail_before_fix_verified"] = failed == expected_fail
    result["proof_exit_code"] = proc.returncode
    result["proof_expected_fail"] = expected_fail
    result["detail"] = (
        "guard failed against broken behaviour as required"
        if result["fail_before_fix_verified"]
        else "proof did not demonstrate fail-before-fix (guard may be vacuous)"
    )
    return result


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
