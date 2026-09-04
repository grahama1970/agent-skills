#!/usr/bin/env python3
"""Adversarial regression gate for the relevance filtering agent.

The filtering agent (gpt-5.5 low reasoning) must decide, per detected turn,
whether it warrants an evidence card. This eval is adversarial on purpose: the
suppression cases are chosen to PASS the deterministic question-window trigger
(they carry a '?', a question lead, or a watch-term project mention) so the
only thing that can suppress them is the agent's judgment -- a naive detector
would card every one. Each case runs in its own isolated server (no
cross-turn contamination) and is posted directly over HTTP (STT-free, so the
result reflects the filter, not RealtimeSTT variance).

Contract:
- a genuine, answerable question ALWAYS surfaces a card (thin evidence is fine);
- a non-question that merely looks like one (logistics/social 'can we...',
  'can everyone...', a statement mentioning the project, a rhetorical tag) is
  suppressed by the agent, with a surface=false decision journaled.

No provider key is needed; direct provider calls are disabled.
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

# (text, distinctive tokens, should_surface, must_show_filter_decision)
# must_show_filter_decision marks the adversarial question-SHAPED cases: they
# trigger the window, so a correct suppression MUST come from a surface=false
# agent decision, not from the turn never reaching the filter.
CASES = [
    ("Remind me, what are the hard read first rules recorded in the Sparta project memory index?",
     ["hard", "rules", "sparta"], True, False),
    ("Where in the Sparta pipeline source code is QRA generation implemented, which module builds the pairs?",
     ["qra", "generation", "pipeline"], True, False),
    ("Can we push this Sparta review to Friday afternoon instead of this morning?",
     ["friday", "afternoon", "push"], False, True),
    ("Can everyone hear me okay on the Sparta call, is my audio coming through?",
     ["hear", "audio", "okay"], False, True),
    ("The Sparta Explorer framework is really coming together nicely this week, nice work team.",
     ["coming", "together", "nicely"], False, True),
    ("Okay cool, does that all sound reasonable to everyone on the call today?",
     ["sound", "reasonable", "everyone"], False, True),
]


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def run_case(text: str, tokens: list[str], should_surface: bool,
             must_show_decision: bool, index: int) -> None:
    server = campaign.Server(campaign.import_tmp(f"relfilter-{index}") / "server",
                             live_resolver=True, memory_url="http://127.0.0.1:8601",
                             repos=SPARTA)
    try:
        server.post_final(1, text)
        journal = campaign.wait_for(
            lambda: next(server.data_dir.glob("*/session.jsonl"), None), timeout_s=30)
        # Give the resolver + retrieval + filter time to decide.
        campaign.wait_for(lambda: _has_terminal(journal, tokens), timeout_s=60)
        rows = [json.loads(l) for l in journal.read_text().splitlines()] if journal else []
        carded = _card_matches(rows, tokens)
        decisions = [r["payload"] for r in rows if r.get("kind") == "surface_selection"]
        label = f"[{index}] {text[:45]}"
        if should_surface:
            check(f"SURFACE {label}", carded, "no card produced for a genuine question")
        else:
            check(f"SUPPRESS {label}", not carded, "a non-question produced a card")
            if must_show_decision:
                suppressed = any(d.get("surface") is False for d in decisions)
                check(f"  filter decided suppress {label}", suppressed,
                      f"decisions={[d.get('surface') for d in decisions]}")
    finally:
        server.close()


def _has_terminal(journal: Path | None, tokens: list[str]) -> bool:
    if journal is None:
        return False
    for line in journal.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") in ("evidence_card", "surface_selection"):
            return True
    return False


def _card_matches(rows: list[dict], tokens: list[str]) -> bool:
    for row in rows:
        if row.get("kind") != "evidence_card":
            continue
        blob = (str(row["payload"].get("query") or "") + " "
                + str(row["payload"].get("question") or "")).lower()
        if sum(1 for t in tokens if t.lower() in blob) >= 2:
            return True
    return False


def main() -> int:
    campaign.ROOT = SKILL
    if not Path(SPARTA).is_dir():
        print("relevance filter: INFRA_BLOCKED (sparta repo not present)")
        return 0
    for index, (text, tokens, surface, must_show) in enumerate(CASES):
        run_case(text, tokens, surface, must_show, index)
    print()
    if FAILURES:
        print(f"relevance filter: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("relevance filter: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
