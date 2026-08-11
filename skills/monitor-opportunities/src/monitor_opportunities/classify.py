"""Classify each opportunity as EMPLOYMENT vs CONSULTING — and never confuse them.

The two demand different actions, and crossing them is a defect:

- EMPLOYMENT = a job posting. Action: **apply on their site** AND send an **InMail
  to the right person** (hiring manager / a warm connection on the team). Materials:
  tailored resume. There is a role to apply to.
- CONSULTING = a company/solicitation with a need or budget but **no job to apply
  to** (federal Sources Sought/RFI, a commercial signal, a firm that just won work).
  Action: **InMail to the decision-maker** (the buyer of services) + a capability
  statement / proposal. Materials: capability statement, NOT a resume-into-an-ATS.
  There is NO "apply on site" — doing so is the confusion this module prevents.

Deterministic: classifies from lane / signal_type / apply-URL shape, and emits the
exact action plan so downstream never sends a job application to a consulting
prospect or an InMail-only flow to a real job posting.
"""

from __future__ import annotations

from typing import Any

EMPLOYMENT = "employment"
CONSULTING = "consulting"

_CONSULTING_SIGNALS = frozenset({
    "federal", "commercial", "federal_buyer", "commercial_signal",
    "client_decision_maker", "partner", "prospect",
})
_CONSULTING_TITLE_HINTS = ("solicitation", "sources sought", "rfi", "rfp",
                           "request for information", "request for proposal",
                           "broad agency announcement", "signal", "sbir", "sttr")
_JOB_URL_HINTS = ("ashbyhq.com", "greenhouse.io", "lever.co", "/jobs/",
                  "linkedin.com/jobs", "/careers", "workday", "job-boards")


def classify_opportunity(opp: dict[str, Any]) -> dict[str, Any]:
    """Return {opportunity_type, confidence, action_plan}. Never both actions."""
    lane = str(opp.get("lane") or "")
    signal = str(opp.get("signal_type") or opp.get("prospect_class") or "").lower()
    apply_url = opp.get("apply_url") or opp.get("posting_url") or ""
    title = str(opp.get("title") or "").lower()

    otype = None
    confidence = "high"
    if lane in ("B", "C") or signal in _CONSULTING_SIGNALS:
        otype = CONSULTING
    elif any(h in title for h in _CONSULTING_TITLE_HINTS):
        otype = CONSULTING
    elif lane == "A" or any(h in str(apply_url).lower() for h in _JOB_URL_HINTS):
        otype = EMPLOYMENT
    else:
        # No clear signal: an apply surface implies a job; otherwise treat as a
        # consulting/company signal and require human confirmation.
        otype = EMPLOYMENT if apply_url else CONSULTING
        confidence = "low"

    if otype == EMPLOYMENT:
        action_plan = {
            "apply_on_site": apply_url or None,
            "inmail": {
                "target": "hiring manager or a warm/mutual connection on the team",
                "goal": "referral or a heads-up so your application is READ, not buried",
            },
            "materials": ["tailored_resume"],
            "do_not": ["send a services/consulting pitch — this is a job application"],
        }
    else:
        action_plan = {
            "apply_on_site": None,  # NEVER — there is no job to apply to
            "inmail": {
                "target": "decision-maker who owns the problem/budget (not a recruiter)",
                "goal": "start a services conversation, offer a capability statement",
            },
            "materials": ["capability_statement", "proposal_outline"],
            "do_not": ["apply on a careers page", "attach a resume as if applying to a role"],
        }

    return {
        "opportunity_id": opp.get("candidate_id") or opp.get("id"),
        "organization": opp.get("organization"),
        "title": opp.get("title"),
        "opportunity_type": otype,
        "confidence": confidence,
        "action_plan": action_plan,
    }
