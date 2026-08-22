#!/usr/bin/env python3
"""Regression guard: ATS eligibility-field classification.

Incident (2026-08-22): the Ashby field classifier lumped citizenship-derived
eligibility questions ("authorized to work", "sponsorship") into
``human_required`` alongside clearance/EEO, so the skill re-asked the human for
answers already attested in the answer bank (US citizen -> authorized=Yes,
sponsorship=No). Separately, the "clearance" question was captured as OPTIONAL
when Ashby actually requires it, so a submit failed on a blank required field.

This guard exercises the REAL production classifier (`_field_kind`,
`_eligibility_answer_key`, `_load_answer_bank`) on the exact incident labels and
fails (exit 1) if:
  - a citizenship-derived eligibility field is classified human_required
    (the re-ask flaw), or
  - its answer does not resolve from the answer bank, or
  - clearance is NOT human_required (clearance is genuinely the human's).
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.ats.ashby import (  # noqa: E402
    _eligibility_answer_key,
    _field_kind,
    _load_answer_bank,
)

WORK_AUTH = "Are you legally authorized to work in the United States?"
SPONSORSHIP = "Will you now or in future require sponsorship for employment visa status?"
CLEARANCE = "Have you held or currently hold an active security clearance?"


def main() -> int:
    failures: list[str] = []
    bank = _load_answer_bank()

    # 1. Citizenship-derived eligibility must be answerable, never human_required.
    for label, (section, key) in ((WORK_AUTH, ("work_authorization", "authorized_us")),
                                  (SPONSORSHIP, ("work_authorization", "require_sponsorship"))):
        kind = _field_kind(label, "radio")
        if kind == "human_required":
            failures.append(
                f"RE_ASK_REGRESSION: '{label[:40]}' classified human_required; "
                "it is a citizenship-derived answer bank fact, must be answerable."
            )
        elif kind != "answer_bank_choice":
            failures.append(f"UNEXPECTED_KIND: '{label[:40]}' -> {kind}")
        resolved = _eligibility_answer_key(label)
        answer = (bank.get(section) or {}).get(key) if resolved else None
        if not answer:
            failures.append(f"NO_ANSWER_BANK_VALUE: '{label[:40]}' did not resolve from answer bank")

    # 2. Clearance is genuinely variable -> must stay the human's.
    if _field_kind(CLEARANCE, "radio") != "human_required":
        failures.append("CLEARANCE_MISCLASSIFIED: clearance must be human_required, not auto-answered.")

    # 3. Required-capture tripwire: Ashby marks required fields with a CSS class
    #    on the label (e.g. _required_f7cvd_91), not always an asterisk. Clearance
    #    was captured as optional and a submit failed on the blank required field.
    #    Guard the class-based detection against silent removal.
    from monitor_opportunities.ats.ashby import _ASHBY_FIELD_JS  # noqa: E402
    if "reqClass" not in _ASHBY_FIELD_JS or "_required" not in _ASHBY_FIELD_JS:
        failures.append(
            "REQUIRED_CAPTURE_REGRESSION: Ashby field capture no longer detects the "
            "'_required' label class; required fields (e.g. clearance) will be miscaptured as optional."
        )

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print("FIELD_CLASSIFIER_OK: work_auth=answerable(Yes), sponsorship=answerable(No), "
          "clearance=human_required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
