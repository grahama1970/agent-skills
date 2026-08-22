#!/usr/bin/env python3
"""Regression guard: Ashby auto-apply must FILL the form, not submit blank.

Incident (2026-08-22): commit_ashby_application captured the form and clicked
Submit but never filled name/email/linkedin or uploaded the resume -- it would
submit a blank form. The real Unstructured submission only worked because it was
filled by hand.

This guard fails (exit 1) if:
  - commit_ashby_application does not call the prefill step before submitting;
  - identity fields do not resolve from the answer bank;
  - an attested screening answer (clearance) does not resolve;
  - a genuinely unanswerable required free-text field does NOT block the submit.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.ats import ashby_apply  # noqa: E402
from monitor_opportunities.ats.ashby_apply import (  # noqa: E402
    _identity_value,
    _load_answer_bank,
    _require_no_unresolved_required,
    _screening_answer,
    commit_ashby_application,
)


def main() -> int:
    failures: list[str] = []
    ab = _load_answer_bank()

    # 1. commit_ashby_application must prefill before submitting (source contract).
    src = inspect.getsource(commit_ashby_application)
    if "_prefill_ashby" not in src or src.index("_prefill_ashby") > src.index("adapter.submit"):
        failures.append("NO_PREFILL_BEFORE_SUBMIT: commit_ashby_application must fill the form before submitting.")

    # 2. Identity fields resolve from the answer bank.
    for label in ("Name", "Email", "LinkedIn"):
        if not _identity_value(label, ab):
            failures.append(f"IDENTITY_UNRESOLVED: {label}")

    # 3. Attested screening answers resolve (never re-asked).
    if _screening_answer("Are you legally authorized to work in the US?", ab) != "Yes":
        failures.append("WORK_AUTH_NOT_ATTESTED")
    if not _screening_answer("Have you held an active security clearance?", ab):
        failures.append("CLEARANCE_NOT_ATTESTED: clearance must resolve from the attested answer bank.")

    # 4. A required free-text field with no answer still blocks.
    form = {"fields": [{"name": "Why do you want to work here?", "required": True,
                        "disposition": "human_required", "field_type": "textarea"}]}
    if not _require_no_unresolved_required(form, ab, {}):
        failures.append("BLANK_FREE_TEXT_NOT_BLOCKED: an unanswerable required free-text field did not block the submit.")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("ASHBY_PREFILL_OK: fills before submit, identity+attested screening resolve, free-text blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
