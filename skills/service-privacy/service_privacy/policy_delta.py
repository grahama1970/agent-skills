"""Deterministic safety gate for agent-proposed policy deltas (#1743).

The agent may PROPOSE; this validator decides. It never trusts the proposal's
own `protected_overlap` claim and re-derives every verdict independently.
ACCEPTED_FOR_HUMAN_REVIEW only marks eligibility for human review — it never
applies anything. All rejections are typed; there is no generic ACCEPT.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import Strict, contained, overlaps_protected

DeltaVerdict = Literal[
    'ACCEPTED_FOR_HUMAN_REVIEW',
    'REJECTED_PROTECTED_OVERLAP',
    'REJECTED_WRITABLE_EXEC',
    'REJECTED_CAP_RESTORE',
    'REJECTED_NNP_WEAKEN',
    'REJECTED_NETWORK_BROADEN',
    'REJECTED_DENY_REMOVAL',
    'INCONCLUSIVE_NO_EVIDENCE',
]

# Baseline service-writable roots from Policy; anything executable landing in
# one of these is a self-modification channel.
WRITABLE_ROOTS = ('/var/kolide-k2', '/var/lib/ubuntu-service-privacy-data')


class PolicyDeltaProposal(Strict):
    """An agent's proposed widening; every field is untrusted input."""
    schema_version: Literal['ubuntu_service_privacy.policy_delta_proposal.v1'] = 'ubuntu_service_privacy.policy_delta_proposal.v1'
    add_read_roots: list[str] = Field(min_length=1, max_length=24)
    resource_class: str
    reason: str
    required_for_observed_check: bool
    # Agent's own claim about protected overlap — recorded for audit but NEVER
    # trusted; the validator re-derives the truth.
    protected_overlap: bool
    add_write_roots: list[str] = Field(default_factory=list, max_length=8)
    add_executables: list[str] = Field(default_factory=list, max_length=8)
    add_capabilities: list[str] = Field(default_factory=list, max_length=16)
    no_new_privileges: bool = True
    requested_network_mode: str | None = None
    approved_network_mode: str = 'OFFLINE'
    remove_deny_paths: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode='after')
    def shape(self) -> 'PolicyDeltaProposal':
        if len(set(self.add_read_roots)) != len(self.add_read_roots):
            raise ValueError('duplicate read roots are rejected')
        for mode in (self.requested_network_mode, self.approved_network_mode):
            if mode is not None and mode not in ('OFFLINE', 'PUBLIC_EGRESS_LOCAL_DENY'):
                raise ValueError('unknown network mode')
        return self


def _writable_exec(proposal: PolicyDeltaProposal) -> bool:
    writable = list(WRITABLE_ROOTS) + list(proposal.add_write_roots)
    return any(contained(path, root) for path in proposal.add_executables for root in writable)


def validate_delta(proposal: PolicyDeltaProposal) -> DeltaVerdict:
    """Deterministic, independently re-derived verdict. Rejection reasons are
    checked in a fixed priority order; evidence is checked LAST so a dangerous
    proposal without evidence still gets a typed REJECTED_* verdict, not a
    soft INCONCLUSIVE."""
    if any(overlaps_protected(path) for path in proposal.add_read_roots + proposal.add_write_roots
           + proposal.add_executables + proposal.remove_deny_paths):
        return 'REJECTED_PROTECTED_OVERLAP'
    if _writable_exec(proposal):
        return 'REJECTED_WRITABLE_EXEC'
    if proposal.add_capabilities:
        return 'REJECTED_CAP_RESTORE'
    if not proposal.no_new_privileges:
        return 'REJECTED_NNP_WEAKEN'
    if proposal.requested_network_mode is not None and proposal.requested_network_mode != proposal.approved_network_mode:
        return 'REJECTED_NETWORK_BROADEN'
    if proposal.remove_deny_paths:
        return 'REJECTED_DENY_REMOVAL'
    if not proposal.required_for_observed_check or not proposal.reason.strip():
        return 'INCONCLUSIVE_NO_EVIDENCE'
    return 'ACCEPTED_FOR_HUMAN_REVIEW'
