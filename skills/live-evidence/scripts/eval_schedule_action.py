#!/usr/bin/env python3
"""Prove the schedule action wiring: a heard scheduling request proposes an
ops-google-calendar action, propose-only, independent of the card gate.

STT-free (posted over HTTP). A scheduling utterance ('can we push this to
Friday?') is a logistics turn whose evidence CARD is suppressed by the
filtering agent -- but it must still PROPOSE a schedule action routed to
ops-google-calendar, and that action must NEVER auto-write a calendar (it
stays proposed/unresolved, awaiting human approval and the calendar skill's
own --confirm). A control question that is not a scheduling request proposes
no schedule action.

No scillm key -> INFRA_BLOCKED, never a fake pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
sys.path.insert(0, str(SKILL / "scripts"))

import run_g2i_campaign as campaign

FAILURES: list[str] = []
SPARTA = str(Path.home() / "workspace" / "experiments" / "sparta")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def _proposed_kinds(rows: list[dict]) -> list[str]:
    kinds: list[str] = []
    for r in rows:
        if r.get("kind") == "action_candidates_proposed":
            for c in r["payload"].get("candidates") or []:
                kinds.append(c.get("kind"))
    return kinds


def _executed_calendar_write(rows: list[dict]) -> bool:
    for r in rows:
        if r.get("kind") == "action_executed":
            rc = r["payload"].get("receipt") or {}
            if r["payload"].get("status") == "executed" and rc.get("destination") == "ops-google-calendar":
                return True
    return False


def run_turn(text: str) -> list[dict]:
    server = campaign.Server(campaign.import_tmp("sched") / "server",
                             live_resolver=True, memory_url="http://127.0.0.1:8601",
                             repos=SPARTA)
    try:
        server.post_final(1, text)
        journal = campaign.wait_for(
            lambda: next(server.data_dir.glob("*/session.jsonl"), None), timeout_s=30)
        campaign.wait_for(
            lambda: journal and any(
                json.loads(l).get("kind") in ("action_candidates_proposed", "evidence_card",
                                              "surface_selection")
                for l in journal.read_text().splitlines()), timeout_s=60)
        return [json.loads(l) for l in journal.read_text().splitlines()] if journal else []
    finally:
        server.close()


def main() -> int:
    campaign.ROOT = SKILL
    if not campaign.scillm_key():
        print("schedule action: INFRA_BLOCKED (no scillm key)")
        return 0
    if not Path(SPARTA).is_dir():
        print("schedule action: INFRA_BLOCKED (sparta repo not present)")
        return 0

    rows = run_turn("Can we push the Sparta Explorer review to Friday afternoon at 3pm instead of this morning?")
    kinds = _proposed_kinds(rows)
    check("scheduling request proposes a schedule action", "schedule" in kinds,
          f"proposed kinds={kinds}")
    check("schedule action does NOT auto-write a calendar",
          not _executed_calendar_write(rows), "an unapproved calendar write executed")

    control = run_turn("What are the hard read first rules in the Sparta project memory index?")
    check("a non-scheduling question proposes no schedule action",
          "schedule" not in _proposed_kinds(control),
          f"control kinds={_proposed_kinds(control)}")

    print()
    if FAILURES:
        print(f"schedule action: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("schedule action: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
