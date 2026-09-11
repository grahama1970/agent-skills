"""Framework-owned domain profiles for value-bearing claims.

A domain profile enumerates the representations a format admits for data
values. Profiles are FRAMEWORK-OWNED and VERSIONED: fixture authors
reference them by id and may extend (add dimensions) but may not
silently subtract. This is the mechanical answer to the oai-trial miss:
the same person who forgot integer phones cannot declare that strings
are the complete universe.

WebGPT-reviewed 2026-09-11: the minimum acceptable design is
  required semantic classification -> independently versioned
  representation/domain profile -> automatically synthesized coverage
  cells -> representation derived from actual case data -> fail-capable
  independent oracle -> fail-before-fix retained regression.
"""

from __future__ import annotations

from typing import Any

DOMAIN_PROFILES: dict[str, dict[str, Any]] = {
    "json-scalar-v1": {
        "profile_id": "json-scalar-v1",
        "format": "JSON",
        "description": (
            "Scalar representations JSON admits for data values. "
            "A phone stored as 5551234567 is the same phone as "
            "'5551234567'; both must be guarded."
        ),
        "representations": [
            "string",
            "integer",
            "float",
            "scientific_notation",
        ],
        "metamorphic": (
            "The same semantic value in different representations "
            "must produce the same invariant outcome."
        ),
    },
    "sqlite-type-v1": {
        "profile_id": "sqlite-type-v1",
        "format": "SQLite",
        "description": (
            "SQLite storage classes for data values."
        ),
        "representations": [
            "TEXT",
            "INTEGER",
            "REAL",
        ],
        "metamorphic": (
            "The same semantic value in different storage classes "
            "must produce the same invariant outcome."
        ),
    },
    "csv-cell-v1": {
        "profile_id": "csv-cell-v1",
        "format": "CSV",
        "description": (
            "CSV cell representations for data values."
        ),
        "representations": [
            "quoted",
            "unquoted",
        ],
        "metamorphic": (
            "Quoted and unquoted cells carrying the same semantic "
            "value must produce the same invariant outcome."
        ),
    },
}

CLAIM_SEMANTICS = frozenset(
    {
        "value_bearing",
        "protocol",
        "timing",
        "control_flow",
        "human_perceptual",
        "other",
    }
)


def validate_claim_semantics(manifest: dict[str, Any]) -> list[str]:
    """Load-time gate: critical claims MUST carry a semantic classification.

    A value_bearing classification MUST reference a domain_profile; the
    runner synthesizes a value-representation seam from that profile.
    Omission is a load-time failure, not a silent default.
    """
    problems: list[str] = []
    claims = manifest.get("capability_claims") or []
    for claim in claims:
        cid = claim.get("id", "<unnamed>")
        crit = claim.get("criticality", "critical")
        semantics = claim.get("claim_semantics")
        if crit != "critical":
            continue
        if semantics is None:
            problems.append(
                f"critical claim {cid!r} missing claim_semantics; "
                f"must be one of {sorted(CLAIM_SEMANTICS)} — "
                "no default, omission is a load error"
            )
            continue
        if semantics not in CLAIM_SEMANTICS:
            problems.append(
                f"claim {cid!r} claim_semantics {semantics!r} invalid; "
                f"use {sorted(CLAIM_SEMANTICS)}"
            )
            continue
        if semantics == "value_bearing":
            profile = claim.get("domain_profile")
            if not profile:
                problems.append(
                    f"value_bearing claim {cid!r} must reference a "
                    "domain_profile (e.g. json-scalar-v1); "
                    "the framework owns the representation universe"
                )
            elif profile not in DOMAIN_PROFILES:
                problems.append(
                    f"claim {cid!r} domain_profile {profile!r} unknown; "
                    f"known profiles: {sorted(DOMAIN_PROFILES)}"
                )
    return problems


def synthesize_representation_seams(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Auto-synthesize value-representation seams for value_bearing claims.

    The seam cannot be forgotten: declaring a value_bearing critical
    claim automatically creates a required critical seam covering every
    representation in the referenced domain profile.
    """
    seams: list[dict[str, Any]] = []
    for claim in manifest.get("capability_claims") or []:
        if claim.get("claim_semantics") != "value_bearing":
            continue
        profile_id = claim.get("domain_profile")
        profile = DOMAIN_PROFILES.get(profile_id)
        if not profile:
            continue
        cid = claim.get("id", "<unnamed>")
        seam_id = f"{cid}:value-representation"
        seam: dict[str, Any] = {
            "seam_id": seam_id,
            "seam_type": "security/compliance/human-authority",
            "criticality": "critical",
            "required_evidence": ["adversarial_live_e2e"]
            if "adversarial_live_e2e"
            in (claim.get("evidence_required") or {})
            else ["deterministic"],
            "synthesized": True,
            "claim_id": cid,
            "domain_profile": profile_id,
            "representations": profile["representations"],
        }
        seams.append(seam)
    return seams
