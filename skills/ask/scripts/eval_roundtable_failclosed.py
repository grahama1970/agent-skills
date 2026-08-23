#!/usr/bin/env python3
"""Regression guard: a browser roundtable that captured no panel must fail closed.

Incident (2026-08-23): five browser seats were dispatched for a resume-review
roundtable; the models answered (ChatGPT tabs auto-titled "Resume Review Verdict"
carried complete reviews with valid <<<WEBGPT_DONE...>>> sentinels), but surf's
capture failed (stale persistent tab bindings + 6KB inline prompt), so every
seat's response file was 0 bytes and no node-receipt.json was written. The
load-bearing invariant is: a roundtable with fewer than ROUNDTABLE_MIN_ANSWERING
seats actually answering must NOT be presentable as a panel result — it must
report the shortfall (BLOCKED / NEEDS_ATTENTION), and a join must never claim
consensus over a silent seat.

This exercises the real panel_compliance audit against synthetic run dirs shaped
exactly like the failed run (empty response files) and fails (exit 1) if the
fail-closed contract is not enforced.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from ask.panel_compliance import (  # noqa: E402
    ROUNDTABLE_MIN_ANSWERING,
    check_no_silent_consensus,
    check_roundtable_quorum,
)

SEATS = ["webgpt", "webclaude", "webkimi", "webgrok", "webgemini"]
PACKET = "You are one seat on a collaborative review panel. Review the attached bundle."


_RUN_SEQ = [0]


def _make_run(tmp: Path, *, answered: int, join_status: str, join_text: str = "") -> Path:
    """Build a tau-dag-shaped run dir: N seats with a non-empty response, the
    rest with a 0-byte response (the exact capture-failure shape)."""
    _RUN_SEQ[0] += 1
    run = tmp / f"run_{_RUN_SEQ[0]}_{answered}_{join_status or 'none'}"
    for i, seat in enumerate(SEATS):
        d = run / "node-artifacts" / f"handler-{seat}"
        d.mkdir(parents=True)
        (d / "prompt.md").write_text(PACKET, encoding="utf-8")
        if i < answered:
            (d / "node-receipt.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            (d / "response.md").write_text(
                f"## Position\nSEND_WITH_REVISIONS\nHandler: {seat}\n<<<DONE:{seat}>>>\n", encoding="utf-8")
        else:
            # capture failure: response file exists but is empty, no receipt
            (d / "response.raw.md").write_text("", encoding="utf-8")
    jd = run / "node-artifacts" / "join"
    jd.mkdir(parents=True)
    if join_status:
        (jd / "node-receipt.json").write_text(json.dumps({"status": join_status}), encoding="utf-8")
    if join_text:
        (jd / "join.md").write_text(join_text, encoding="utf-8")
    return run


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. Zero seats captured, join reports success -> MUST be non-compliant.
        q = check_roundtable_quorum(_make_run(tmp, answered=0, join_status="PASS"))
        if q["compliant"]:
            failures.append("EMPTY_PANEL_PASSED: 0 answered seats with a PASS join was accepted as a panel")

        # 2. Sub-quorum captured, join reports success -> MUST be non-compliant.
        q = check_roundtable_quorum(_make_run(tmp, answered=ROUNDTABLE_MIN_ANSWERING - 1, join_status="PASS"))
        if q["compliant"]:
            failures.append(
                f"SUBQUORUM_PASSED: {ROUNDTABLE_MIN_ANSWERING-1} answered with a PASS join was accepted")

        # 3. Sub-quorum but honestly BLOCKED -> compliant (shortfall disclosed).
        q = check_roundtable_quorum(_make_run(tmp, answered=0, join_status="BLOCKED"))
        if not q["compliant"]:
            failures.append("HONEST_BLOCK_REJECTED: a run honestly reporting BLOCKED was flagged non-compliant")

        # 4. Full quorum answered -> compliant (non-vacuity: audit is not always-fail).
        q = check_roundtable_quorum(_make_run(tmp, answered=ROUNDTABLE_MIN_ANSWERING, join_status="PASS"))
        if not q["compliant"]:
            failures.append("QUORUM_MET_REJECTED: a full-quorum panel was wrongly flagged non-compliant")

        # 5. Silent consensus: join claims agreement while a seat never answered -> non-compliant.
        c = check_no_silent_consensus(
            _make_run(tmp, answered=ROUNDTABLE_MIN_ANSWERING, join_status="PASS",
                      join_text="The panel agrees the resume is ready to send."))
        if c["compliant"]:
            failures.append("SILENT_CONSENSUS_PASSED: join claimed agreement over a non-answering seat")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print(f"ROUNDTABLE_FAILCLOSED_OK: sub-quorum panels fail closed unless BLOCKED/NEEDS_ATTENTION is "
          f"disclosed; consensus over a silent seat is rejected (quorum={ROUNDTABLE_MIN_ANSWERING})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
