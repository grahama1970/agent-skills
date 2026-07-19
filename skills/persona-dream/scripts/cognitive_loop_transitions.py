#!/usr/bin/env python3
"""Cognitive-loop transition state machine (P0 correctness guard).

The persona-dream cognitive loop chains Watch perception (12) -> self
interpretation (13) -> ToM validation (14) -> persistence (15). Before this
module existed the runner chained the phases WITHOUT gating on the predecessor's
status, accepted counts, or artifact hashes: a BLOCKED interpretation or a
zero-accepted ToM validation could still fall through to a canonical write.

This module is the typed transition guard. It implements the linear machine:

    ACCEPTED_OBSERVATION
        -> PASS_INTERPRETATION      (accepted_interpretations >= 1)
        -> PASS_TOM_VALIDATION      (accepted_tom_candidates   >= 1)
        -> STAGED_PERSISTENCE_VERIFIED
        -> CANONICAL_COMMIT

Every transition validates, fail-closed:
  * the predecessor artifact's schema id,
  * its EXACT status string (not a startswith-DEGRADED shortcut),
  * the predecessor artifact sha256 (hash binding: phase14 must bind the exact
    phase13 object it validated; the commit must bind the exact 13 + 14 objects),
  * the expected dream / revision / run / return ids,
  * minimum accepted counts,
  * any typed waiver / acceptance receipt (an enumerated DEGRADED observation is
    pass-like ONLY when a binding agent-level acceptance receipt certifies it).

Blockers are typed as STRUCTURAL (the chain itself is broken - always a hard
stop, in any mode) or ELIGIBILITY (canonical-write is not permitted for this
return - expected in a dry-run plan, fatal only when a canonical commit is
requested). The runner stops hard (nonzero + receipt) on any STRUCTURAL blocker
before the next side effect, and on any ELIGIBILITY blocker when a canonical
commit is requested.
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# States                                                                      #
# --------------------------------------------------------------------------- #
STATE_START = "START"
STATE_ACCEPTED_OBSERVATION = "ACCEPTED_OBSERVATION"
STATE_PASS_INTERPRETATION = "PASS_INTERPRETATION"
STATE_PASS_TOM_VALIDATION = "PASS_TOM_VALIDATION"
STATE_STAGED_PERSISTENCE_VERIFIED = "STAGED_PERSISTENCE_VERIFIED"
STATE_CANONICAL_COMMIT = "CANONICAL_COMMIT"

TRANSITION_ORDER = [
    STATE_START,
    STATE_ACCEPTED_OBSERVATION,
    STATE_PASS_INTERPRETATION,
    STATE_PASS_TOM_VALIDATION,
    STATE_STAGED_PERSISTENCE_VERIFIED,
    STATE_CANONICAL_COMMIT,
]

# Schemas the guards bind against.
OBSERVATION_SCHEMA = "persona_dream.watch_gauntlet_observation_packet.v1"
INTERPRETATION_SCHEMA = "persona_dream.dream_self_interpretation.v1"
TOM_SCHEMA = "persona_dream.tom_validation_receipt.v1"
PERSISTENCE_SCHEMA = "persona_dream.dream_persistence_receipt.v1"

# Enumerated observation statuses. An OK status is unconditionally acceptable;
# an enumerated DEGRADED code is acceptable ONLY with a binding acceptance
# receipt. Anything else is unknown and fails closed.
OK_OBSERVATION_STATUSES = {
    "OK_WATCH_GAUNTLET_OBSERVATION",
    "PASS_WATCH_GAUNTLET_OBSERVATION",
}
WAIVER_BACKED_DEGRADED_STATUSES = {
    "DEGRADED_WATCH_GAUNTLET_OBSERVATION",
}

PASS_INTERPRETATION_STATUSES = {
    "PASS_SELF_INTERPRETATION",
    "PASS_SELF_INTERPRETATION_WITH_REJECTIONS",
}
PASS_TOM_STATUSES = {
    "PASS_TOM_VALIDATION",
    "PASS_TOM_VALIDATION_WITH_REJECTIONS",
}

SEVERITY_STRUCTURAL = "STRUCTURAL"
SEVERITY_ELIGIBILITY = "ELIGIBILITY"


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


@dataclass
class Blocker:
    code: str
    severity: str  # STRUCTURAL | ELIGIBILITY

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity}


@dataclass
class Transition:
    from_state: str
    to_state: str
    blockers: list[Blocker] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.blockers

    @property
    def structural_blockers(self) -> list[str]:
        return [b.code for b in self.blockers if b.severity == SEVERITY_STRUCTURAL]

    @property
    def eligibility_blockers(self) -> list[str]:
        return [b.code for b in self.blockers if b.severity == SEVERITY_ELIGIBILITY]

    @property
    def has_structural(self) -> bool:
        return bool(self.structural_blockers)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "ok": self.ok,
            "blockers": [b.as_dict() for b in self.blockers],
            "structural_blockers": self.structural_blockers,
            "eligibility_blockers": self.eligibility_blockers,
            "evidence": self.evidence,
        }


class TransitionError(Exception):
    """Raised when a transition guard fails and the caller requested hard-stop."""

    def __init__(self, transition: Transition):
        self.transition = transition
        codes = ",".join(b.code for b in transition.blockers)
        super().__init__(
            f"TRANSITION_BLOCKED {transition.from_state}->{transition.to_state}: {codes}"
        )


def _s(v: Any) -> str:
    return str(v or "")


# --------------------------------------------------------------------------- #
# Guard 1: START -> ACCEPTED_OBSERVATION                                       #
# --------------------------------------------------------------------------- #
def guard_observation_accepted(
    packet: dict[str, Any],
    *,
    return_id: str | None,
    acceptance_certifies: bool,
    canonical_write_hard_blocks: list[str],
    allow_canonical_write: bool,
) -> Transition:
    """The Watch observation packet is an accepted input to the loop.

    ``canonical_write_hard_blocks`` is the (deduplicated) list of HARD,
    non-overridable blockers already decided by phase15.canonical_write_decision
    (historical origin, renderer identity-continuity DEFECT verdict, superseded
    return id). Those are surfaced here as STRUCTURAL because they mean the
    return can never legitimately become canonical dream memory.
    """
    t = Transition(STATE_START, STATE_ACCEPTED_OBSERVATION)
    schema = _s(packet.get("schema"))
    if schema != OBSERVATION_SCHEMA:
        t.blockers.append(Blocker(f"OBSERVATION_WRONG_SCHEMA:{schema or 'missing'}", SEVERITY_STRUCTURAL))

    status = _s(packet.get("status"))
    status_ok = status in OK_OBSERVATION_STATUSES
    status_degraded = status in WAIVER_BACKED_DEGRADED_STATUSES
    if not status_ok and not status_degraded:
        # Unknown status is never pass-like.
        t.blockers.append(Blocker(f"OBSERVATION_STATUS_UNKNOWN:{status or 'missing'}", SEVERITY_STRUCTURAL))
    elif status_degraded and not acceptance_certifies:
        # Enumerated DEGRADED code, but no binding acceptance receipt: eligible
        # for a dry-run plan, never for a canonical commit.
        t.blockers.append(Blocker("OBSERVATION_DEGRADED_UNWAIVED", SEVERITY_ELIGIBILITY))

    # Hard, non-overridable blocks from phase15's pure decision.
    for code in canonical_write_hard_blocks:
        t.blockers.append(Blocker(code, SEVERITY_STRUCTURAL))

    if allow_canonical_write and not return_id:
        t.blockers.append(Blocker("RETURN_ID_MISSING", SEVERITY_ELIGIBILITY))

    t.evidence = {
        "schema": schema,
        "status": status,
        "status_class": "OK" if status_ok else ("WAIVER_BACKED_DEGRADED" if status_degraded else "UNKNOWN"),
        "acceptance_certifies": acceptance_certifies,
        "return_id": return_id,
        "observation_packet_sha256": canonical_sha(packet),
    }
    return t


# --------------------------------------------------------------------------- #
# Guard 2: ACCEPTED_OBSERVATION -> PASS_INTERPRETATION                         #
# --------------------------------------------------------------------------- #
def guard_interpretation(
    interpretation: dict[str, Any],
    *,
    expected_dream_id: str,
    expected_revision_id: str,
    expected_run_id: str,
    expected_observation_sha256: str | None = None,
    min_accepted: int = 1,
) -> Transition:
    t = Transition(STATE_ACCEPTED_OBSERVATION, STATE_PASS_INTERPRETATION)
    schema = _s(interpretation.get("schema"))
    if schema != INTERPRETATION_SCHEMA:
        t.blockers.append(Blocker(f"INTERPRETATION_WRONG_SCHEMA:{schema or 'missing'}", SEVERITY_STRUCTURAL))

    status = _s(interpretation.get("status"))
    if status not in PASS_INTERPRETATION_STATUSES:
        t.blockers.append(Blocker(f"INTERPRETATION_STATUS_NOT_PASS:{status or 'missing'}", SEVERITY_STRUCTURAL))

    for field_name, expected in (
        ("dream_id", expected_dream_id),
        ("revision_id", expected_revision_id),
        ("run_id", expected_run_id),
    ):
        if _s(interpretation.get(field_name)) != _s(expected):
            t.blockers.append(Blocker(f"INTERPRETATION_ID_MISMATCH:{field_name}", SEVERITY_STRUCTURAL))

    if expected_observation_sha256 is not None:
        got = _s(interpretation.get("observation_packet_sha256"))
        if got != _s(expected_observation_sha256):
            t.blockers.append(Blocker("INTERPRETATION_OBSERVATION_SHA_MISMATCH", SEVERITY_STRUCTURAL))

    accepted = interpretation.get("accepted_interpretations") or []
    n_accepted = len(accepted) if isinstance(accepted, list) else 0
    if n_accepted < min_accepted:
        t.blockers.append(Blocker(f"INTERPRETATION_ACCEPTED_BELOW_MIN:{n_accepted}<{min_accepted}", SEVERITY_STRUCTURAL))

    t.evidence = {
        "schema": schema,
        "status": status,
        "accepted_count": n_accepted,
        "interpretation_sha256": canonical_sha(interpretation),
    }
    return t


# --------------------------------------------------------------------------- #
# Guard 3: PASS_INTERPRETATION -> PASS_TOM_VALIDATION                          #
# --------------------------------------------------------------------------- #
def guard_tom_validation(
    tom: dict[str, Any],
    interpretation: dict[str, Any],
    *,
    expected_dream_id: str,
    expected_revision_id: str,
    expected_run_id: str,
    min_accepted: int = 1,
) -> Transition:
    t = Transition(STATE_PASS_INTERPRETATION, STATE_PASS_TOM_VALIDATION)
    schema = _s(tom.get("schema"))
    if schema != TOM_SCHEMA:
        t.blockers.append(Blocker(f"TOM_WRONG_SCHEMA:{schema or 'missing'}", SEVERITY_STRUCTURAL))

    status = _s(tom.get("status"))
    if status not in PASS_TOM_STATUSES:
        t.blockers.append(Blocker(f"TOM_STATUS_NOT_PASS:{status or 'missing'}", SEVERITY_STRUCTURAL))

    for field_name, expected in (
        ("dream_id", expected_dream_id),
        ("revision_id", expected_revision_id),
        ("run_id", expected_run_id),
    ):
        if _s(tom.get(field_name)) != _s(expected):
            t.blockers.append(Blocker(f"TOM_ID_MISMATCH:{field_name}", SEVERITY_STRUCTURAL))

    # Hash binding: the ToM receipt must bind the exact interpretation object.
    expected_interp_sha = canonical_sha(interpretation)
    got_interp_sha = _s(tom.get("interpretation_sha256"))
    if got_interp_sha != expected_interp_sha:
        t.blockers.append(Blocker("TOM_INTERPRETATION_SHA_MISMATCH", SEVERITY_STRUCTURAL))

    accepted = tom.get("accepted_tom_candidates") or []
    n_accepted = tom.get("accepted_count")
    if not isinstance(n_accepted, int):
        n_accepted = len(accepted) if isinstance(accepted, list) else 0
    if n_accepted < min_accepted:
        t.blockers.append(Blocker(f"TOM_ACCEPTED_BELOW_MIN:{n_accepted}<{min_accepted}", SEVERITY_STRUCTURAL))

    t.evidence = {
        "schema": schema,
        "status": status,
        "accepted_count": n_accepted,
        "interpretation_sha256_bound": got_interp_sha,
        "interpretation_sha256_expected": expected_interp_sha,
        "tom_sha256": canonical_sha(tom),
    }
    return t


# --------------------------------------------------------------------------- #
# Guard 4: PASS_TOM_VALIDATION -> STAGED_PERSISTENCE_VERIFIED                  #
# --------------------------------------------------------------------------- #
def guard_staged_persistence(persistence: dict[str, Any]) -> Transition:
    """Every staged record must exist and reread-match before any publish."""
    t = Transition(STATE_PASS_TOM_VALIDATION, STATE_STAGED_PERSISTENCE_VERIFIED)
    proof = persistence.get("canonical_write_proof") or {}
    staging = proof.get("staging_proof") or {}
    if not staging:
        t.blockers.append(Blocker("STAGING_PROOF_MISSING", SEVERITY_STRUCTURAL))
        return t
    if not staging.get("all_exact_reread_match"):
        t.blockers.append(Blocker("STAGED_RECORD_REREAD_MISMATCH", SEVERITY_STRUCTURAL))
    if staging.get("quarantined"):
        t.blockers.append(Blocker("STAGING_QUARANTINED", SEVERITY_STRUCTURAL))
    staged = staging.get("staged_count") or 0
    expected = staging.get("expected_count") or 0
    if staged != expected or expected == 0:
        t.blockers.append(Blocker(f"STAGED_COUNT_MISMATCH:{staged}!={expected}", SEVERITY_STRUCTURAL))
    t.evidence = {
        "idempotency_key": proof.get("idempotency_key"),
        "staged_count": staged,
        "expected_count": expected,
        "all_exact_reread_match": staging.get("all_exact_reread_match"),
    }
    return t


# --------------------------------------------------------------------------- #
# Guard 5: STAGED_PERSISTENCE_VERIFIED -> CANONICAL_COMMIT                     #
# --------------------------------------------------------------------------- #
def guard_canonical_commit(
    persistence: dict[str, Any],
    *,
    expected_phase13_sha256: str,
    expected_phase14_sha256: str,
) -> Transition:
    """The commit manifest is the single source of canonical visibility. It must
    bind the exact phase13 + phase14 artifacts and every published record must
    reread-match; canonical_dream_memory_written must be strictly True."""
    t = Transition(STATE_STAGED_PERSISTENCE_VERIFIED, STATE_CANONICAL_COMMIT)
    proof = persistence.get("canonical_write_proof") or {}
    manifest = proof.get("commit_manifest") or {}
    if not manifest:
        t.blockers.append(Blocker("COMMIT_MANIFEST_MISSING", SEVERITY_STRUCTURAL))
        return t

    if not manifest.get("active"):
        t.blockers.append(Blocker("COMMIT_MANIFEST_NOT_ACTIVE", SEVERITY_STRUCTURAL))
    if not manifest.get("exact_reread_match"):
        t.blockers.append(Blocker("COMMIT_MANIFEST_REREAD_MISMATCH", SEVERITY_STRUCTURAL))

    bound13 = _s(manifest.get("phase13_sha256"))
    bound14 = _s(manifest.get("phase14_sha256"))
    if bound13 != _s(expected_phase13_sha256):
        t.blockers.append(Blocker("COMMIT_PHASE13_SHA_MISMATCH", SEVERITY_STRUCTURAL))
    if bound14 != _s(expected_phase14_sha256):
        t.blockers.append(Blocker("COMMIT_PHASE14_SHA_MISMATCH", SEVERITY_STRUCTURAL))

    if not proof.get("all_exact_reread_match"):
        t.blockers.append(Blocker("PUBLISHED_RECORD_REREAD_MISMATCH", SEVERITY_STRUCTURAL))
    if not persistence.get("canonical_dream_memory_written"):
        t.blockers.append(Blocker("CANONICAL_DREAM_MEMORY_NOT_WRITTEN", SEVERITY_STRUCTURAL))

    t.evidence = {
        "idempotency_key": proof.get("idempotency_key"),
        "commit_manifest_key": manifest.get("key"),
        "active": manifest.get("active"),
        "records_published": proof.get("records_written"),
        "all_exact_reread_match": proof.get("all_exact_reread_match"),
        "phase13_sha256_bound": bound13,
        "phase14_sha256_bound": bound14,
    }
    return t


# --------------------------------------------------------------------------- #
# Aggregate helpers used by the loop runner                                   #
# --------------------------------------------------------------------------- #
def observation_status_is_pass_like(status: str, *, acceptance_certifies: bool) -> bool:
    """Only an OK status, or an ENUMERATED waiver-backed DEGRADED code with a
    certifying acceptance receipt, is pass-like. A bare ``startswith('DEGRADED')``
    is NOT accepted - that was the defect."""
    status = _s(status)
    if status in OK_OBSERVATION_STATUSES:
        return True
    if status in WAIVER_BACKED_DEGRADED_STATUSES and acceptance_certifies:
        return True
    return False


def phase_status_is_pass_like(
    phase: str,
    status: str,
    *,
    observation_acceptance_certifies: bool = False,
) -> bool:
    """Per-phase pass predicate for the loop's aggregate verdict.

    The observation (input) phase may carry an enumerated DEGRADED code and is
    pass-like only when certified. Every other phase must be an explicit
    PASS* / DRY_RUN* / LIVE* status. No blanket DEGRADED* acceptance.
    """
    status = _s(status)
    if phase.endswith("watch_observation") or phase.startswith("12"):
        return observation_status_is_pass_like(
            status, acceptance_certifies=observation_acceptance_certifies
        )
    return status.startswith(("PASS", "DRY_RUN", "LIVE"))
