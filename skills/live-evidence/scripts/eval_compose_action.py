#!/usr/bin/env python3
"""Prove the compose action wiring: an analytical/visual request proposes a
multi-skill composition (a Tau DAG over brave-search -> analytics ->
create-figure), propose-only, independent of the card gate.

STT-free (posted over HTTP). 'Can you graph last quarter's metrics?' is not a
card -- it is a request to build a figure, which composes several skills. It
must PROPOSE a kind=compose action naming the planned skill chain, and it must
NEVER auto-run the DAG (fetch + compute + render is expensive and outward-
facing; execution is a separate human-approved step). A control question that
is not a visualization request proposes no compose action.

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


def _composition_executed(rows: list[dict]) -> bool:
    for r in rows:
        if r.get("kind") == "action_executed":
            rc = r["payload"].get("receipt") or {}
            if r["payload"].get("status") == "executed" and rc.get("orchestrator"):
                return True
    return False


def run_turn(text: str) -> list[dict]:
    server = campaign.Server(campaign.import_tmp("compose") / "server",
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
        print("compose action: INFRA_BLOCKED (no scillm key)")
        return 0
    if not Path(SPARTA).is_dir():
        print("compose action: INFRA_BLOCKED (sparta repo not present)")
        return 0

    rows = run_turn("Can you pull our latest Sparta coverage metrics and graph them as a bar chart for the review?")
    kinds = _proposed_kinds(rows)
    check("visualization request proposes a compose action", "compose" in kinds,
          f"proposed kinds={kinds}")
    check("compose action does NOT auto-run the skill DAG",
          not _composition_executed(rows), "an unapproved composition executed")

    control = run_turn("What are the hard read first rules in the Sparta project memory index?")
    check("a non-visualization question proposes no compose action",
          "compose" not in _proposed_kinds(control),
          f"control kinds={_proposed_kinds(control)}")

    print()
    if FAILURES:
        print(f"compose action: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("compose action: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
