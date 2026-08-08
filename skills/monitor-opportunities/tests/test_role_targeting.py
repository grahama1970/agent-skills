"""Role-type targeting: off-mandate lane-A postings are rejected.

Uses the actual titles last night's run surfaced so the filter is proven against
real noise (sales/admin/founder/creative) while keeping real senior AI/eng roles.
"""

from __future__ import annotations

import pytest

from monitor_opportunities.ranking import _eligibility, _role_type_reject

# Real noise from the 2026-08-08 run that should be dropped.
NOISE = [
    "Navy Account Executive - Public Sector",
    "Senior Account Executive, Growth Stage",
    "Senior Solutions Engineer, Enterprise - West",
    "Manager, Analytics",
    "Accounting Manager, Technical Accounting",
    "Data Management Specialist",
    "Web Designer",
    "CMMS Administrator",
    "Founder in Residence",
    "AI Founder, AI Compute",
    "Former Founder",
    "Chief Growth Officer",
    "Classic TV Editor",
]

# Real keepers from the same run that must survive.
KEEP = [
    "AI Engineer - Public Sector",
    "Principal + Staff Software Engineers",
    "Staff AI Engineer",
    "Senior AI Engineer",
    "Senior Fullstack Software Engineer, GRC",
    "Backend Senior Software Engineer, Identity",
    "Intelligent Document Processing / OCR Engineer",
    "AI Architect Principal - AI Foundation",
    "Research Scientist / Research Engineer - Neuro",
    "Developer, Applied AI",
    "AI/ML Architect",
    "Engineering Manager, ML Platform",  # manager WITH eng signal stays
]


@pytest.mark.parametrize("title", NOISE)
def test_noise_rejected(title: str) -> None:
    assert _role_type_reject(title) is not None, f"should reject: {title}"


@pytest.mark.parametrize("title", KEEP)
def test_keepers_survive(title: str) -> None:
    assert _role_type_reject(title) is None, f"should keep: {title}"


def test_eligibility_rejects_lane_a_noise() -> None:
    c = {"candidate_id": "x", "lane": "A", "workplace_type": "REMOTE", "title": "Navy Account Executive"}
    state, reasons = _eligibility(c)
    assert state == "REJECT_ROLE_TYPE"
    assert "off-target" in reasons[0]


def test_eligibility_does_not_title_filter_lane_c_signal() -> None:
    # A commercial client signal titled like a "manager" is not title-filtered.
    c = {"candidate_id": "y", "lane": "C", "workplace_type": "NOT_APPLICABLE", "title": "Analytics Manager signal"}
    state, _ = _eligibility(c)
    assert state == "ELIGIBLE_COMMERCIAL_SIGNAL"
