#!/usr/bin/env python3
"""Verify best-practices-skills requires typed validation before prose/regex."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "Typed Boundary Validation Policy (NON-NEGOTIABLE)",
    "Every skill boundary that consumes or emits structured data MUST validate",
    "Regex and prose checks are not boundary validation",
    "using regex over model/tool output to decide PASS/BLOCKED",
    "validate consumed JSON with Pydantic/typed schema",
    "validate produced JSON with Pydantic/typed schema",
    "classify every failure through triage-error as {code, cause, next_command}",
    "A prose-only step contract is not an executable contract.",
]
VIOLATIONS = [
    "regex over model/tool output to decide PASS/BLOCKED",
    "paragraph because it \"looks like\" a receipt",
    "LLM repair, classify, or summarize malformed data before the schema",
]


def missing_required(text: str) -> list[str]:
    return [s for s in REQUIRED if s not in text]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(ROOT / "SKILL.md"))
    ap.add_argument("--expect-reject", action="store_true")
    args = ap.parse_args()
    text = Path(args.path).read_text(encoding="utf-8")
    missing = missing_required(text)
    violation_terms = [s for s in VIOLATIONS if s in text]
    ok = not missing and len(violation_terms) == len(VIOLATIONS)
    if args.expect_reject:
        if ok:
            print({"status": "FAIL_NEGATIVE_ACCEPTED"})
            return 1
        print({"status": "PASS_NEGATIVE_REJECTED", "missing": missing, "violation_terms": violation_terms})
        return 0
    if not ok:
        print({"status": "FAIL", "missing": missing, "violation_terms": violation_terms})
        return 1
    print({"status": "PASS_TYPED_BOUNDARY_POLICY_RETAINED", "checked": len(REQUIRED)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
