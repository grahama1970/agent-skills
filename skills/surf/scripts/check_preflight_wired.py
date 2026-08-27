#!/usr/bin/env python3
"""Regression guard: assert the pre-submit DOM doctor stays wired into the
ChatGPT submit flow. Fails (exit 1) if a future edit removes the doctor, its
call before typePrompt, the fail-fast throw, or the cross-run baseline field.

This is what prevents the reliability feature from silently regressing.
"""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "vendor" / "surf-cli" / "native" / "chatgpt-client.cjs"


def main() -> int:
    src = CLIENT.read_text(encoding="utf-8")
    problems: list[str] = []

    if "async function preflightDoctor" not in src:
        problems.append("preflightDoctor function removed")

    call = src.find("await preflightDoctor(")
    type_prompt = src.find("await typePrompt(")
    if call < 0:
        problems.append("preflightDoctor is never called")
    elif type_prompt < 0:
        problems.append("typePrompt call not found")
    elif call > type_prompt:
        problems.append("preflightDoctor no longer runs BEFORE typePrompt (submit not gated)")

    if 'doctor.verdict !== "PROCEED"' not in src or "throw" not in src[src.find('doctor.verdict !== "PROCEED"'):]:
        problems.append("fail-fast throw on non-PROCEED verdict missing")

    for token in ("driftSinceBaseline", "surf.preflight_doctor.v1", "STOP_HANDOFF", "RETRY_AFTER_RELOAD"):
        if token not in src:
            problems.append(f"expected token missing: {token}")

    # Boundary guard: the doctor must never claim to solve/bypass a captcha.
    lowered = src.lower()
    for banned in ("solvecaptcha", "bypasscaptcha", "captcha_solver", "solve_captcha"):
        if banned in lowered:
            problems.append(f"forbidden captcha-solving token present: {banned}")

    if problems:
        print("PREFLIGHT_WIRING_FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("PREFLIGHT_WIRED_OK: doctor gates submit before typePrompt, fails fast, "
          "carries cross-run baseline, and solves no captcha")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
