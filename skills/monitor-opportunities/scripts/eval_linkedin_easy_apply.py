#!/usr/bin/env python3
"""Regression guard: LinkedIn Easy Apply safety contract.

LinkedIn Easy Apply auto-submit is authorized but must never fabricate an answer
or submit a blank required field. This guard exercises the real gate,
classification, and block logic and fails (exit 1) if any safety invariant
regresses:
  - the scoped promotion gate rejects a wrong-scope / non-human promotion;
  - work-authorization and sponsorship are answerable from the answer bank;
  - salary, clearance, years-of-experience, and free-text are human_required;
  - a required field left empty after filling BLOCKS the submit (NEEDS_HUMAN).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.ats.linkedin_easy_apply import (  # noqa: E402
    LinkedInEasyApplyAdapter,
    LinkedInEasyApplyError,
    classify_screening_field,
    _require_promotion,
)


def main() -> int:
    failures: list[str] = []

    # 1. Promotion gate.
    for bad in ({"capability": "ats_form_submit:ashby:x", "actor": "human", "decision": "PROMOTE"},
                {"capability": "ats_form_submit:linkedin:linkedin.com", "actor": "agent", "decision": "PROMOTE"},
                None):
        try:
            _require_promotion(bad)
            failures.append(f"GATE_ACCEPTED_BAD_PROMOTION: {bad}")
        except LinkedInEasyApplyError:
            pass

    # 2. Answerable vs human_required classification.
    answerable = ["Are you legally authorized to work in the US?", "Will you require sponsorship?"]
    human = ["What are your salary expectations?", "Do you hold an active security clearance?",
             "How many years of Python experience?", "Why do you want to work here?"]
    for lab in answerable:
        if classify_screening_field(lab)[0] != "answerable":
            failures.append(f"SHOULD_BE_ANSWERABLE: {lab}")
    for lab in human:
        if classify_screening_field(lab)[0] != "human_required":
            failures.append(f"SHOULD_BE_HUMAN_REQUIRED: {lab}")

    # 3. A required field empty after filling must block.
    a = LinkedInEasyApplyAdapter.__new__(LinkedInEasyApplyAdapter)
    a.answer_bank = json.loads((SKILL_DIR / "config" / "answer_bank.json").read_text())
    fields = [{"label": "What are your salary expectations?", "required": True, "value": ""}]
    if not a._blocking_required(fields):
        failures.append("BLANK_REQUIRED_NOT_BLOCKED: an unanswered required field did not block the submit.")
    # A filled answerable field must NOT block.
    if a._blocking_required([{"label": "Authorized to work?", "required": True, "value": "Yes"}]):
        failures.append("FILLED_FIELD_WRONGLY_BLOCKED")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("LINKEDIN_EASY_APPLY_SAFE: gate holds, classification correct, blank-required blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
