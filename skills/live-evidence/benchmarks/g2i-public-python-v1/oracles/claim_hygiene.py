"""Claim-hygiene oracle for the G2i public benchmark (#1455).

The report may state measured metrics on the pinned public challenge. It may
not claim superiority over, equivalence to, or copying of G2i's production
product. This module is imported by the benchmark eval and by any report
generator before text leaves the pack.
"""

from __future__ import annotations

FORBIDDEN_FORMULATIONS = (
    "beats g2i",
    "beat g2i",
    "better than g2i",
    "outperforms g2i",
    "copied g2i",
    "we copied g2i",
    "reproduces g2i's product",
    "same as g2i's production",
    "better than g2i's production platform",
)

ALLOWED_SHAPE = (
    "On the pinned G2i public Python challenge at commit 25ceb5ad, Live Evidence "
    "achieved the recorded question, requirement, policy, debugger, review, "
    "rubric, and rehearsal metrics."
)


def violations(report_text: str) -> list[str]:
    lowered = " ".join(report_text.lower().split())
    return [term for term in FORBIDDEN_FORMULATIONS if term in lowered]
