#!/usr/bin/env python3
"""Regression guard: LinkedIn Easy Apply safety contract.

LinkedIn Easy Apply submission is never automatic. It requires post-report
human authorization for one exact candidate/posting/apply URL/idempotency key,
and must never fabricate an answer or submit a blank required field. This guard
exercises the real gate, classification, and block logic and fails (exit 1) if
any safety invariant regresses:
  - the scoped promotion gate rejects a wrong-scope / non-human promotion;
  - the exact per-application authorization gate rejects missing or mismatched
    authorization;
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
    commit_linkedin_easy_apply,
    _require_application_authorization,
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

    idempotency_key = "apply:linkedin:4448643688"
    good_authorization = {
        "schema": "monitor_opportunities.application_authorization.v1",
        "actor": "human",
        "state": "HUMAN_AUTHORIZED",
        "candidate_id": "candidate:a:linkedin:canvas",
        "posting_id": "4448643688",
        "apply_url": "https://www.linkedin.com/jobs/view/4448643688/",
        "idempotency_key": idempotency_key,
        "authorization_digest": "a" * 64,
    }
    for bad in (
        None,
        {**good_authorization, "actor": "agent"},
        {**good_authorization, "posting_id": "different"},
        {**good_authorization, "apply_url": "https://www.linkedin.com/jobs/view/other/"},
        {**good_authorization, "candidate_id": "candidate:a:other"},
        {**good_authorization, "idempotency_key": "apply:linkedin:other"},
    ):
        try:
            _require_application_authorization(
                bad,
                candidate_id="candidate:a:linkedin:canvas",
                posting_id="4448643688",
                apply_url="https://www.linkedin.com/jobs/view/4448643688/",
                idempotency_key=idempotency_key,
            )
            failures.append(f"AUTHORIZATION_ACCEPTED_BAD_PAYLOAD: {bad}")
        except LinkedInEasyApplyError:
            pass
    try:
        _require_application_authorization(
            good_authorization,
            candidate_id="candidate:a:linkedin:canvas",
            posting_id="4448643688",
            apply_url="https://www.linkedin.com/jobs/view/4448643688/",
            idempotency_key=idempotency_key,
        )
    except LinkedInEasyApplyError as exc:
        failures.append(f"AUTHORIZATION_REJECTED_GOOD_PAYLOAD: {exc}")

    try:
        commit_linkedin_easy_apply(
            tab_id="0",
            candidate_id="candidate:a:linkedin:canvas",
            posting_id="4448643688",
            apply_url="https://www.linkedin.com/jobs/view/4448643688/",
            promotion={"capability": "ats_form_submit:linkedin:linkedin.com", "actor": "human", "decision": "PROMOTE"},
            authorization=None,  # type: ignore[arg-type]
        )
        failures.append("COMMIT_ACCEPTED_MISSING_AUTHORIZATION")
    except LinkedInEasyApplyError as exc:
        if "AUTHORIZATION_MISSING" not in str(exc):
            failures.append(f"COMMIT_WRONG_MISSING_AUTHORIZATION_ERROR: {exc}")

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
    print("LINKEDIN_EASY_APPLY_SAFE: exact authorization gate holds, classification correct, blank-required blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
