#!/usr/bin/env python3
"""Prove research-lane selection: a deep/comparative question routes external
research to /dogpile (the deep aggregator over web/code/papers/videos); a quick
current-fact question routes to /brave-search.

STT-free (posted over HTTP). Both are propose-only external research (the human
approves the egress); this checks which skill the proposal targets, read from
the proposed fact_check candidate's summary.

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


def _research_lanes(rows: list[dict]) -> list[str]:
    """Lanes of every proposed fact_check (external-research) candidate."""

    out: list[str] = []
    for r in rows:
        if r.get("kind") == "action_candidates_proposed":
            for c in r["payload"].get("candidates") or []:
                if c.get("kind") == "fact_check" and c.get("research_lane"):
                    out.append(str(c["research_lane"]))
    return out


def run_turn(text: str) -> list[dict]:
    server = campaign.Server(campaign.import_tmp("reslane") / "server",
                             live_resolver=True, memory_url="http://127.0.0.1:8601",
                             repos=SPARTA)
    try:
        server.post_final(1, text)
        journal = campaign.wait_for(
            lambda: next(server.data_dir.glob("*/session.jsonl"), None), timeout_s=30)
        campaign.wait_for(
            lambda: journal and any(
                json.loads(l).get("kind") == "action_candidates_proposed"
                for l in journal.read_text().splitlines()), timeout_s=70)
        return [json.loads(l) for l in journal.read_text().splitlines()] if journal else []
    finally:
        server.close()


def main() -> int:
    campaign.ROOT = SKILL
    if not campaign.scillm_key():
        print("research lane: INFRA_BLOCKED (no scillm key)")
        return 0
    if not Path(SPARTA).is_dir():
        print("research lane: INFRA_BLOCKED (sparta repo not present)")
        return 0

    deep = _research_lanes(run_turn(
        "Can you do a deep dive comparing the different approaches to retrieval augmented generation in the literature?"))
    check("deep/comparative research routes to dogpile",
          any("dogpile" in s for s in deep), f"lanes={deep}")

    quick = _research_lanes(run_turn(
        "What is the latest released version of the MITRE SPARTA framework right now?"))
    check("quick current-fact research routes to brave",
          any("brave" in s for s in quick), f"lanes={quick}")

    print()
    if FAILURES:
        print(f"research lane: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("research lane: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
