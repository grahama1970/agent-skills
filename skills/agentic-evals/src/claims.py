"""Claim-based readiness: compute what each declared capability actually proved.

Readiness is scored per capability claim, then aggregated -- never from a raw
case count. This is the mechanism that stops twenty passing deterministic cases
around one narrow path from looking like readiness for a skill whose live
capability was never exercised (#1445).

A claim declares the evidence classes it *requires*. A required `live_e2e` slot
is satisfied only by a case whose effective class (after the real-E2E
qualification in ``evidence.py``) is that live class and that passed every
trial. Ten deterministic passes cannot fill a live slot; a `BLOCKED_EXTERNAL`
live case leaves the slot unmet; an exemption is surfaced but never launders a
missing live proof into PROVEN.
"""

from __future__ import annotations

from typing import Any

from evidence import (
    DETERMINISTIC,
    EVIDENCE_CLASSES,
    LIVE_CLASSES,
)

# Per-claim verdicts (issue #1445).
PROVEN = "PROVEN"
PARTIALLY_PROVEN = "PARTIALLY_PROVEN"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
FAILED = "FAILED"
NOT_ESTABLISHED = "NOT_ESTABLISHED"

# Per-required-class status (internal to a claim).
_PROVEN = "PROVEN"
_FAILED = "FAILED"
_BLOCKED = "BLOCKED"
_EXEMPT = "EXEMPT"
_MISSING = "MISSING"

CRITICALITIES = frozenset({"critical", "important", "optional"})


def normalize_required(evidence_required: Any) -> set[str]:
    """Accept either the object form ``{live_e2e: true}`` or a list of names."""
    required: set[str] = set()
    if isinstance(evidence_required, dict):
        for name, wanted in evidence_required.items():
            if wanted and name in EVIDENCE_CLASSES:
                required.add(name)
    elif isinstance(evidence_required, list):
        for name in evidence_required:
            if name in EVIDENCE_CLASSES:
                required.add(name)
    return required


def validate_claims(manifest: dict[str, Any]) -> list[str]:
    """Structural validation of the capability-claim block at load time."""
    claims = manifest.get("capability_claims")
    if claims is None:
        return []
    problems: list[str] = []
    if not isinstance(claims, list):
        return ["capability_claims must be a list"]
    seen: set[str] = set()
    for claim in claims:
        cid = claim.get("id")
        if not isinstance(cid, str) or not cid:
            problems.append("every capability claim needs a non-empty string id")
            continue
        if cid in seen:
            problems.append(f"duplicate capability claim id {cid!r}")
        seen.add(cid)
        crit = claim.get("criticality", "critical")
        if crit not in CRITICALITIES:
            problems.append(f"claim {cid!r} criticality {crit!r} invalid; use {sorted(CRITICALITIES)}")
        if not normalize_required(claim.get("evidence_required")):
            problems.append(
                f"claim {cid!r} declares no required evidence classes; a claim that "
                "requires nothing cannot gate anything"
            )
    return problems


def _valid_exemption(exemption: dict[str, Any], now_iso: str) -> bool:
    """An exemption counts only if it is complete and not past its expiry.

    An exemption is a promise to prove something out of band, with an owner and
    a review date. A blanket, ownerless, or expired exemption is not evidence --
    it is the absence of a decision, so it does not even reach EXEMPT status.
    """
    required_fields = ("reason_code", "justification", "owner", "expires")
    if any(not exemption.get(field) for field in required_fields):
        return False
    expires = str(exemption.get("expires", ""))
    # ISO date/datetime strings compare lexicographically for expiry.
    return expires >= now_iso


def _exempt_classes(claim: dict[str, Any], now_iso: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for exemption in claim.get("exemptions", []) or []:
        ec = exemption.get("evidence_class")
        if ec in EVIDENCE_CLASSES and _valid_exemption(exemption, now_iso):
            out[ec] = exemption
    return out


def _class_status(
    required_class: str,
    supporting: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Status of one required evidence class from its matching supporting cases.

    A case matches only when its *effective* class equals the required class, so
    a case that declared live but was downgraded by the real-E2E contract never
    satisfies a live slot.
    """
    matching = [c for c in supporting if c["effective_class"] == required_class]
    case_names = [c["name"] for c in matching]
    if any(c["outcome"] == "PASS" for c in matching):
        return _PROVEN, [c["name"] for c in matching if c["outcome"] == "PASS"]
    if any(c["outcome"] == "FAIL" for c in matching):
        return _FAILED, case_names
    if any(c["outcome"] == "BLOCKED" for c in matching):
        return _BLOCKED, case_names
    return _MISSING, case_names


def compute_claim(
    claim: dict[str, Any],
    supporting_cases: list[dict[str, Any]],
    now_iso: str,
) -> dict[str, Any]:
    """Compute one claim's verdict, per-class status, and the missing evidence."""
    required = sorted(normalize_required(claim.get("evidence_required")))
    exempt = _exempt_classes(claim, now_iso)

    per_class: dict[str, dict[str, Any]] = {}
    for rclass in required:
        status, names = _class_status(rclass, supporting_cases)
        if status == _MISSING and rclass in exempt:
            status = _EXEMPT
        per_class[rclass] = {"status": status, "cases": names}

    statuses = [meta["status"] for meta in per_class.values()]
    missing = [c for c, m in per_class.items() if m["status"] == _MISSING]
    blocked = [c for c, m in per_class.items() if m["status"] == _BLOCKED]
    exempted = [c for c, m in per_class.items() if m["status"] == _EXEMPT]
    proven = [c for c, m in per_class.items() if m["status"] == _PROVEN]

    if any(s == _FAILED for s in statuses):
        verdict = FAILED
    elif statuses and all(s == _PROVEN for s in statuses):
        verdict = PROVEN
    elif not supporting_cases and not exempted:
        verdict = NOT_ESTABLISHED
    elif not proven and blocked and not missing:
        verdict = BLOCKED_EXTERNAL
    elif proven and blocked and not missing:
        # Some proven, the rest only blocked by external unavailability.
        verdict = BLOCKED_EXTERNAL
    elif proven:
        verdict = PARTIALLY_PROVEN
    elif blocked:
        verdict = BLOCKED_EXTERNAL
    else:
        verdict = NOT_ESTABLISHED

    # Cases that declared live but were downgraded are surfaced so a reader can
    # see why an apparently-live case did not count.
    unqualified = [
        {"name": c["name"], "declared": c["declared_class"], "reasons": c["qualify_reasons"]}
        for c in supporting_cases
        if c["declared_class"] in LIVE_CLASSES and not c["live_qualified"]
    ]

    return {
        "id": claim.get("id"),
        "description": claim.get("description", ""),
        "criticality": claim.get("criticality", "critical"),
        "required_evidence": required,
        "verdict": verdict,
        "per_class": per_class,
        "missing_evidence": missing,
        "blocked_evidence": blocked,
        "exempt_evidence": exempted,
        "exemptions": [exempt[c] for c in exempted],
        "unqualified_live_cases": unqualified,
        "supporting_cases": [c["name"] for c in supporting_cases],
    }


def enrich_case(case_report: dict[str, Any], case_spec: dict[str, Any], qual: dict[str, Any]) -> dict[str, Any]:
    """Attach evidence metadata to a case report for claim/coverage scoring."""
    supports = case_spec.get("supports_claims") or []
    if not isinstance(supports, list):
        supports = []
    # Multi-claim guard (#1445 rule 4): a live case that supports more than one
    # claim must carry independent per-claim artifacts, else it does not count
    # as live for any of them.
    live_multi_ok = len(supports) <= 1 or bool((case_spec.get("expected") or {}).get("artifacts"))
    effective = qual["effective"]
    live_qualified = qual["live_qualified"] and live_multi_ok
    if qual["live_qualified"] and not live_multi_ok:
        effective = DETERMINISTIC
    return {
        "name": case_report["name"],
        "outcome": case_report["outcome"],
        "declared_class": qual["declared"],
        "effective_class": effective if live_qualified or qual["declared"] not in LIVE_CLASSES else qual["effective"],
        "live_qualified": live_qualified,
        "qualify_reasons": qual["reasons"] + ([] if live_multi_ok else ["supports multiple claims without independent per-claim artifacts"]),
        "supports_claims": supports,
        "seams": case_spec.get("seams") or [],
    }


def compute_readiness(
    manifest: dict[str, Any],
    enriched_cases: list[dict[str, Any]],
    now_iso: str,
) -> dict[str, Any] | None:
    """Per-claim readiness plus the aggregate. Returns None when no claims declared."""
    claims = manifest.get("capability_claims")
    if not claims:
        return None
    claim_reports = []
    for claim in claims:
        supporting = [c for c in enriched_cases if claim["id"] in c["supports_claims"]]
        claim_reports.append(compute_claim(claim, supporting, now_iso))

    critical = [c for c in claim_reports if c["criticality"] == "critical"]
    critical_proven = [c for c in critical if c["verdict"] == PROVEN]
    # Skill READY requires every required critical claim PROVEN under its own
    # declared evidence requirements. Nothing else -- not a blocked live slot,
    # not an exemption -- makes a critical claim count as proven.
    if not critical:
        aggregate = "READY" if all(c["verdict"] == PROVEN for c in claim_reports) else "NOT_READY"
    elif len(critical_proven) == len(critical):
        aggregate = "READY"
    elif any(c["verdict"] == FAILED for c in critical):
        aggregate = "NOT_READY"
    else:
        aggregate = "USABLE_WITH_GAPS"

    return {
        "aggregate_readiness": aggregate,
        "critical_claim_count": len(critical),
        "critical_claims_proven": len(critical_proven),
        "claims": claim_reports,
    }
