#!/usr/bin/env python3
"""Regression gate for agentic card surfacing (which card the model displays).

This isolates the selector from the STT flake: questions are posted directly
over HTTP (`/api/transcript`), so there is no audio, no RealtimeSTT
segmentation variance, and the run deterministically exercises
retrieval -> project-affinity rank -> gpt-5.5 surface selector -> card ->
agentic judge. It fails if a future change lets deterministic ripgrep noise
outrank the answering memory document again, or re-pins recall to one project.

Two rungs:
1. Direct selector discrimination: given a fixed candidate list (one answering
   memory doc buried under ripgrep file-name noise), the gpt-5.5 low-reasoning
   selector must order the memory doc first. No live server needed.
2. End-to-end live surfacing: post a memory-answerable question to a real
   server scoped to the sparta repo; the surfaced card must cite the sparta
   memory document (not a cross-project chunk) AND its answer must be judged
   SEMANTICALLY SIMILAR to the expected read-first rules by the agentic judge.

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
import eval_transcript_meeting as judge_mod
from live_evidence.config import AppSettings, InterviewProfile
from live_evidence.models import EvidenceSource, Freshness, RetrievalLane
from live_evidence.query_bounds import bounded_query
from live_evidence.surface_policy import should_force_surface_source_backed_code
from live_evidence.surface_selector import SurfaceSelector

FAILURES: list[str] = []
SPARTA = str(Path.home() / "workspace" / "experiments" / "sparta")
EXPECTED = ("The read-first hard rules from the SPARTA memory index: never skim "
            "a SKILL.md -- read the entire SKILL.md before running any command.")
QUESTION = "What are the hard read-first rules recorded in the Sparta project memory index?"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def _src(lane: RetrievalLane, label: str, excerpt: str, key: str = "", path: str = "") -> EvidenceSource:
    return EvidenceSource(
        lane=lane, label=label, excerpt=excerpt, score=0.9,
        freshness=Freshness.CURRENT if lane is RetrievalLane.RIPGREP else Freshness.UNKNOWN,
        path=path or None, metadata={"_key": key} if key else {},
    )


def rung_selector_discrimination(key: str) -> None:
    """The model must float the answering memory doc above ripgrep noise."""

    candidates = [
        _src(RetrievalLane.RIPGREP, "sparta/THIRD_PARTY_NOTICES.md",
             "This inventory is part of the public-publication boundary.", path="/x/THIRD_PARTY_NOTICES.md"),
        _src(RetrievalLane.RIPGREP, "sparta/README.md",
             "Sparta Explorer is a local-first investigation tool.", path="/x/README.md"),
        _src(RetrievalLane.RIPGREP, "sparta/LICENSES/mitre-attack.txt",
             "MITRE ATT&CK license text.", path="/x/LICENSES/mitre-attack.txt"),
        _src(RetrievalLane.MEMORY, "SPARTA Project Memory Index",
             "READ FIRST HARD RULES: never skim a SKILL.md; read the entire "
             "SKILL.md cover to cover before running any command.",
             key="local_memory__experiments-sparta__memory"),
        _src(RetrievalLane.RIPGREP, "sparta/SECURITY.md",
             "Report vulnerabilities to security@.", path="/x/SECURITY.md"),
    ]
    ordered, receipt = SurfaceSelector().order(QUESTION, "sparta", candidates)
    applied = receipt.get("applied")
    top_is_memory = ordered and ordered[0].lane is RetrievalLane.MEMORY
    check("selector floats the answering memory doc above ripgrep noise",
          bool(applied and top_is_memory),
          f"applied={applied} top={ordered[0].lane.value if ordered else None}")


def rung_source_backed_code_override() -> None:
    """A declarative coding-problem fragment must still surface source-backed evidence."""

    raw = (
        "Correct. So to make it clear, let me paste in the sample in terms of "
        "looking for the minimum number of parentheses. We remove the last "
        "closing parenthesis because there is no corresponding opening. "
        "An opening parenthesis always has to come before a closing one, right?"
    )
    query = bounded_query(raw, None)
    sources = [
        _src(
            RetrievalLane.RIPGREP,
            "live-evidence-proof/remove_invalid_parentheses.py",
            "Remove the minimum number of parentheses so the string is valid.",
            path="/tmp/live-evidence-proof/remove_invalid_parentheses.py",
        )
    ]
    check(
        "source-backed declarative code prompt forces surface",
        should_force_surface_source_backed_code(query, sources),
        f"query={query}",
    )
    partial_query = (
        "if we see an opening parentheses we know we have seen one and then "
        "we see another closing parentheses"
    )
    check(
        "source-backed partial parentheses walkthrough forces surface",
        should_force_surface_source_backed_code(partial_query, sources),
        f"query={partial_query}",
    )


def rung_live_surfacing(key: str) -> None:
    """Post the question to a real sparta-scoped server; judge the card."""

    server = campaign.Server(campaign.import_tmp("surface-sel") / "server",
                             live_resolver=True, memory_url="http://127.0.0.1:8601",
                             repos=SPARTA)
    try:
        server.post_final(1, QUESTION)
        journal = campaign.wait_for(
            lambda: next(server.data_dir.glob("*/session.jsonl"), None), timeout_s=30)
        if journal is None:
            check("live card produced", False, "no journal")
            return
        card = campaign.wait_for(lambda: _latest_card(journal), timeout_s=90)
        check("live card produced for the memory question", card is not None)
        if card is None:
            return
        selection = any(
            json.loads(l).get("kind") == "surface_selection"
            for l in journal.read_text().splitlines())
        check("surface selector ran on the live question", selection)
        mem_keys = [str((s.get("metadata") or {}).get("_key") or "")
                    for s in card.get("sources") or [] if s.get("lane") == "memory"]
        cites_sparta = any("experiments-sparta" in k for k in mem_keys)
        check("surfaced card cites the sparta project memory (not cross-project)",
              cites_sparta, f"memory_keys={mem_keys}")
        verdict = judge_mod.judge_similarity(
            QUESTION, EXPECTED, str(card.get("answer") or ""),
            str(card.get("evidence") or ""), key)
        check("surfaced answer is judged similar to the expected read-first rules",
              bool(verdict.get("similar")), str(verdict.get("reason"))[:120])
    finally:
        server.close()


def _latest_card(journal: Path) -> dict | None:
    card = None
    for line in journal.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "evidence_card" and row["payload"].get("answer"):
            card = row["payload"]
    return card


def main() -> int:
    import os

    campaign.ROOT = SKILL
    key = campaign.scillm_key()
    if not key:
        print("surface selection: INFRA_BLOCKED (no scillm key; selector/judge unavailable)")
        return 0
    # The selector reads its key from the env (resolver_key); export it so the
    # in-process discrimination rung can call SciLLM the same way the server does.
    os.environ["LIVE_EVIDENCE_SCILLM_KEY"] = key
    if not Path(SPARTA).is_dir():
        print("surface selection: INFRA_BLOCKED (sparta repo not present)")
        return 0
    rung_source_backed_code_override()
    rung_selector_discrimination(key)
    rung_live_surfacing(key)
    print()
    if FAILURES:
        print(f"surface selection: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("surface selection: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
