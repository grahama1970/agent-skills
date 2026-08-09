#!/usr/bin/env python3
"""Verify the Proof Workshop pilot stays structural, not decorative.

This is a source-level guard for the first grahama.co design amendment. Browser
screenshots still own visual proof; this check only prevents the pilot roles from
being accidentally removed while iterating.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components" / "receipt-ticket.tsx"
CSS = ROOT / "app" / "globals.css"

tsx = COMPONENT.read_text(encoding="utf-8")
css = CSS.read_text(encoding="utf-8")

failures: list[str] = []

required_roles = ("claim", "evidence", "boundary", "judgment")
for role in required_roles:
    count = len(re.findall(rf'data-proof-role="{role}"', tsx))
    if count < 2:
        failures.append(f"data-proof-role={role}: expected at least 2 occurrences, found {count}")

if 'data-proof-pilot="receipt"' not in tsx:
    failures.append("missing data-proof-pilot receipt marker")

if "proof-workshop-pilot" not in css:
    failures.append("missing proof-workshop-pilot CSS")

if "proof-role-label" not in css:
    failures.append("missing proof-role-label CSS")

if "ticket-boundary" not in css or "ticket-judgment" not in css:
    failures.append("missing boundary/judgment CSS hooks")

ticket_rule = re.search(r"\.ticket\s*\{(?P<body>.*?)\}", css, re.S)
if ticket_rule and "font-family: var(--mono)" in ticket_rule.group("body"):
    failures.append(".ticket must not set the whole receipt to monospace")

label_rule = re.search(r"\.proof-role-label\s*\{(?P<body>.*?)\}", css, re.S)
if label_rule and "font-family: var(--mono)" in label_rule.group("body"):
    failures.append(".proof-role-label must not use monospace; it is a human-facing role label")

if failures:
    print(f"FAIL: {len(failures)} proof pilot invariant(s) failed")
    for failure in failures:
        print(f"  {failure}")
    sys.exit(1)

print("OK: Proof Workshop pilot exposes claim/evidence/boundary/judgment roles without global mono receipt skin")
