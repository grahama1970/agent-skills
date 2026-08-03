"""
Battle Skill - Scoring System
AIxCC-style scoring and metrics calculation.
"""
from __future__ import annotations

from .state import (
    BattleState,
    Finding,
    FunctionalEvidenceStatus,
    Patch,
)
from .config import (
    VULN_DISCOVERY_SCORE,
    EXPLOIT_PROOF_SCORE,
    SUCCESSFUL_PATCH_SCORE,
    TIME_DECAY_FACTOR,
    SEVERITY_MULTIPLIERS,
)


class Scorer:
    """AIxCC-style scoring system for Red vs Blue battles."""

    @classmethod
    def score_finding(cls, finding: Finding, round_number: int) -> float:
        """
        Score a Red Team finding.

        Args:
            finding: The vulnerability finding to score
            round_number: Current round number (for time decay)

        Returns:
            Score value for this finding
        """
        base = VULN_DISCOVERY_SCORE

        # Severity multiplier
        mult = SEVERITY_MULTIPLIERS.get(finding.severity, 1.0)

        # Exploit proof bonus
        if finding.exploit_proof:
            base += EXPLOIT_PROOF_SCORE

        # Time decay (earlier findings worth more)
        decay = 1.0 / (1.0 + TIME_DECAY_FACTOR * round_number)

        return base * mult * decay

    @classmethod
    def score_patch(cls, patch: Patch, finding: Finding, round_number: int) -> float:
        """
        Score a Blue Team patch.

        Args:
            patch: The patch to score
            finding: The finding this patch addresses
            round_number: Current round number (for time decay)

        Returns:
            Score value for this patch
        """
        if not patch.verified:
            return 0.0

        base = SUCCESSFUL_PATCH_SCORE

        # Severity multiplier (fixing critical vulns worth more)
        mult = SEVERITY_MULTIPLIERS.get(finding.severity, 1.0)

        # Only explicit behavioral PASS earns the functionality bonus. Missing
        # evidence is not silently treated as either preserved or broken.
        if patch.functional_evidence_status is FunctionalEvidenceStatus.PASS:
            base *= 1.2

        # Time decay (faster patches worth more)
        decay = 1.0 / (1.0 + TIME_DECAY_FACTOR * round_number)

        return base * mult * decay

    @classmethod
    def calculate_metrics(cls, state: BattleState) -> dict[str, float | int]:
        """
        Calculate TDSR, FDSR, ASC, and unresolved functional evidence count.

        TDSR includes only verified patches with explicit functional PASS. FDSR
        includes only verified patches with explicit functional FAIL. A verified
        patch with INSUFFICIENT_EVIDENCE contributes to neither rate.
        """
        total_findings = len(state.all_findings)
        verified_patches = [p for p in state.all_patches if p.verified]
        functional_patches = [
            p
            for p in verified_patches
            if p.functional_evidence_status is FunctionalEvidenceStatus.PASS
        ]
        broken_patches = [
            p
            for p in verified_patches
            if p.functional_evidence_status is FunctionalEvidenceStatus.FAIL
        ]
        insufficient_patches = [
            p
            for p in verified_patches
            if p.functional_evidence_status
            is FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE
        ]

        # TDSR: True Defense Success Rate
        tdsr = len(functional_patches) / total_findings if total_findings > 0 else 0.0

        # FDSR: Fake Defense Success Rate (behavioral test ran and failed)
        fdsr = len(broken_patches) / total_findings if total_findings > 0 else 0.0

        # ASC: Attack Success Count
        asc = total_findings

        return {
            "tdsr": tdsr,
            "fdsr": fdsr,
            "asc": asc,
            "functional_evidence_insufficient": len(insufficient_patches),
        }


def score_round(
    findings: list[Finding],
    patches: list[Patch],
    round_number: int
) -> tuple[float, float]:
    """
    Calculate scores for a single round.

    Args:
        findings: Red team findings this round
        patches: Blue team patches this round
        round_number: Current round number

    Returns:
        Tuple of (red_score, blue_score)
    """
    red_score = sum(Scorer.score_finding(f, round_number) for f in findings)

    blue_score = 0.0
    if findings and patches:
        for patch in patches:
            # Find the corresponding finding
            matching_finding = next(
                (f for f in findings if f.id == patch.finding_id),
                findings[0] if findings else None
            )
            if matching_finding:
                blue_score += Scorer.score_patch(patch, matching_finding, round_number)

    return red_score, blue_score
