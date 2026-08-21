#!/usr/bin/env python3
"""Surf-verified browser rung for the reviewer surfaces (#1450/#1451/#1452/#1453).

Live path: real Live Evidence server, real built UI in a real Chrome tab via
the surf extension. Proves by DOM/media readback (never by API state alone):

- review dossier renders with visually distinct dispositions; clicking a
  supported claim SEEKS the real audio element to the bound span timestamp;
  an unverified claim stays labeled unverified after clicking (#1451);
- rubric coverage chips show covered vs untested; the suggested follow-up is
  visible; dismissing it is journaled and does not change coverage (#1452);
- rehearsal turn states render from the practice partition (#1453);
- a real debugger proof (seeded-workspace defect) publishes a card visible in
  the HUD with its proof reference (#1450).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def _clean_env() -> dict:
    """Subprocesses must not inherit this eval's UV_PROJECT_ENVIRONMENT: a
    sibling skill's `uv run --project X` would REBUILD our ephemeral venv as
    project X's environment (observed live: the action eval's venv became
    surf's, complete with PIL, and the server lost pydantic mid-case)."""

    import os

    env = dict(os.environ)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    return env


def surf(root: Path, args: list[str], timeout_s: float = 60.0) -> str:
    runner = root.parent / "surf" / "run.sh"
    result = subprocess.run([str(runner), *args], cwd=root.parent.parent, text=True,
                            capture_output=True, timeout=timeout_s, env=_clean_env())
    if result.returncode != 0:
        raise RuntimeError(f"surf {' '.join(args[:2])} failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def surf_js(root: Path, tab_id: int, script: str) -> Any:
    output = surf(root, ["js", script, "--tab-id", str(tab_id)])
    parsed = json.loads(output)
    return json.loads(parsed) if isinstance(parsed, str) else parsed


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign  # reuse Server/http helpers

    campaign.ROOT = root
    from live_evidence.debugger_lane import repository_digest
    from live_evidence.review import MediaRetention, ReviewClaim, ReviewDisposition, build_review_bundle

    # Owned media: a real wav rendered by chatterbox earlier (any g2i07/embry wav).
    logs = Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"
    # The seek target is 17.0s, so the media must be longer than the span end
    # (a shorter wav clamps currentTime to its duration -- observed live).
    wavs = sorted((w for w in logs.glob("*.wav") if w.stat().st_size > 1_400_000),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not wavs:
        print("owned media wav: FAIL (no chatterbox wav >= 30s available)")
        return 1
    media = wavs[0]

    journal_fixture = root / "fixtures" / "review_interview_journal.jsonl"
    bundle = build_review_bundle(
        journal_fixture, session_id="ui-insights-session", session_policy_digest="0" * 64,
        media_id="owned-recording", media_locator=str(media),
        media_retention=MediaRetention.EXTERNAL_REFERENCE,
        question_specs=[{"question_id": "q-linkedlist", "question_revision": 0,
                         "event_ids": ["ev-q1-a"], "text": "Reverse a linked list in place"}],
        span_specs=[{"span_id": "span-ui-answer", "question_id": "q-linkedlist",
                     "question_revision": 0, "event_ids": ["ev-a1-a", "ev-a1-b"]},
                    {"span_id": "span-ui-scale", "question_id": "q-linkedlist",
                     "question_revision": 0, "event_ids": ["ev-claim-emp"]}],
        claims=[
            ReviewClaim(claim_id="ui-claim-supported",
                        text="Recursive reversal explained with base case.",
                        disposition=ReviewDisposition.SUPPORTED_BY_INTERVIEW,
                        span_ids=["span-ui-answer"]),
            ReviewClaim(claim_id="ui-claim-unverified",
                        text="Claims 200M requests/day at last employer.",
                        disposition=ReviewDisposition.CANDIDATE_ASSERTION_UNVERIFIED,
                        span_ids=["span-ui-scale"]),
        ],
    )

    work = Path(tempfile.mkdtemp(prefix="ui-insights-"))
    server = campaign.Server(work, purpose="rehearsal", live_resolver=False,
                             policy={"voice_output": True, "debugger_invocation": True})
    tab_id = None
    try:
        base = server.url
        status, _ = campaign.http("POST", f"{base}/api/insights/review",
                                  bundle.model_dump(mode="json", by_alias=True))
        check("review bundle published", status == 202, f"http={status}")
        campaign.http("POST", f"{base}/api/insights/rubric", {
            "coverage": [{"criterion_id": "api-pagination", "state": "covered"},
                          {"criterion_id": "filtering", "state": "untested"}],
            "suggestions": [{"criterion_id": "filtering",
                              "question_text": "How is the June 1st boundary handled?",
                              "why_this_is_still_open": "answer never stated the date filter"}],
        })
        campaign.http("POST", f"{base}/api/insights/rehearsal", {
            "turns": [{"turn_id": "t1", "question_text": "Describe a system you scaled.",
                        "audio_status": "accepted", "question_revision": 1},
                       {"turn_id": "t2", "question_text": "What failed in it?",
                        "audio_status": "stale", "question_revision": 1}],
        })

        # Real debugger proof -> HUD card (#1450 visible rung).
        server.post_final(1, "Why does the filtered departures CSV come out empty when the data has Adventurous trips after June 2018?")
        state = campaign.wait_for(
            lambda: next((s for s in [server.state()] if s.get("cards")), None), 60)
        cards = (state or {}).get("cards") or []
        workspace = campaign.PACK / "seeded-workspace"
        program = workspace / "collect_departures.py"
        _, debug_body = campaign.http("POST", f"{base}/api/debug/request", {
            "question_id": cards[0]["question_id"] if cards else "q" * 12,
            "question_revision": cards[0]["question_revision"] if cards else 1,
            "repository_root": str(workspace),
            "repository_commit_or_tree_digest": repository_digest(workspace),
            "technical_question": "Why is the filtered CSV empty?",
            "reproduction_command": [str(program)],
            "requested_breakpoints": [{"file": str(program), "line": 46}],
            "requested_locals": ["cutoff"],
        }, timeout=180)
        check("debugger proof published as fenced card",
              debug_body.get("result") == "supported" and debug_body.get("published") is True)

        output = surf(root, ["tab.new", f"{base}/", "--json"])
        match = re.search(r"Created tab\s+(\d+)", output)
        if not match:
            raise RuntimeError(f"no tab id in surf output: {output}")
        tab_id = int(match.group(1))
        time.sleep(2.5)

        dom = None
        for _ in range(30):
            dom = surf_js(root, tab_id, """
(() => {
  const claims = document.querySelectorAll('[data-qid^="insight-claim-"]').length;
  const chips = [...document.querySelectorAll('[data-coverage-state]')].map(e => e.getAttribute('data-coverage-state'));
  const suggestion = !!document.querySelector('[data-qid="suggestion-filtering"]');
  const turns = document.querySelectorAll('[data-qid^="turn-"]').length;
  const debuggerCard = document.body.textContent.includes('collect_departures.py') || document.body.textContent.includes('Stopped at');
  const dispositions = [...document.querySelectorAll('[data-disposition]')].map(e => e.getAttribute('data-disposition'));
  return JSON.stringify({claims, chips, suggestion, turns, debuggerCard, dispositions});
})()""")
            if dom and dom.get("claims"):
                break
            time.sleep(1.5)
        dom = dom or {}
        check("review claims render with distinct dispositions",
              dom.get("claims") == 2 and set(dom.get("dispositions") or []) ==
              {"supported_by_interview", "candidate_assertion_unverified"}, json.dumps(dom))
        check("rubric chips show covered and untested",
              set(dom.get("chips") or []) == {"covered", "untested"})
        check("suggested follow-up visible", dom.get("suggestion") is True)
        check("rehearsal turns render with audio status", dom.get("turns") == 2)
        check("debugger-backed card visible in the HUD", dom.get("debuggerCard") is True)

        surf_js(root, tab_id, "(() => { document.querySelector('[data-qid=\"insight-claim-ui-claim-supported\"]').click(); return JSON.stringify({clicked: true}); })()")
        time.sleep(1.5)
        seek = surf_js(root, tab_id, """
(() => {
  const media = document.querySelector('[data-qid="review-media"]');
  const span = document.querySelector('[data-qid="active-span"]');
  return JSON.stringify({currentTime: media ? media.currentTime : null,
                         span: span ? span.textContent : null});
})()""")
        check("clicking a supported claim seeks media to the bound span",
              seek.get("currentTime") is not None and abs(seek["currentTime"] - 17.0) < 0.5
              and "ev-a1-a" in (seek.get("span") or ""), json.dumps(seek))

        surf_js(root, tab_id, "(() => { document.querySelector('[data-qid=\"insight-claim-ui-claim-unverified\"]').click(); return JSON.stringify({clicked: true}); })()")
        time.sleep(1.0)
        unverified = surf_js(root, tab_id, """
(() => {
  const el = document.querySelector('[data-qid="insight-claim-ui-claim-unverified"]');
  return JSON.stringify({disposition: el ? el.getAttribute('data-disposition') : null});
})()""")
        check("unverified claim stays labeled unverified after clicking",
              unverified.get("disposition") == "candidate_assertion_unverified")

        surf_js(root, tab_id, "(() => { document.querySelector('[data-qid=\"dismiss-filtering\"]').click(); return JSON.stringify({clicked: true}); })()")
        time.sleep(1.5)
        _, after = campaign.http("GET", f"{base}/api/insights")
        journal_path = next(server.data_dir.glob("*/session.jsonl"))
        journal_rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        dismissed = [r for r in journal_rows if r.get("kind") == "suggestion_dismissed"]
        check(
            "dismissal journaled with actor; coverage untouched",
            not (after.get("rubric") or {}).get("suggestions")
            and dismissed and dismissed[0]["payload"]["actor"] == "reviewer:ui"
            and len((after.get("rubric") or {}).get("coverage") or []) == 2,
        )

        shot = work / "insights-panel.png"
        surf(root, ["screenshot", "--tab-id", str(tab_id), "--output", str(shot)])
        check("screenshot captured", shot.is_file() and shot.stat().st_size > 10_000, str(shot))

        receipt = {
            "schema": "live_evidence.ui_insights_receipt.v1", "mocked": False, "live": True,
            "media": str(media), "tab_id": tab_id, "screenshot": str(shot),
            "debugger_proof": debug_body.get("proof_path"),
            "checks_failed": FAILURES,
        }
        (work / "receipt.json").write_text(json.dumps(receipt, indent=1))
        print(f"receipt: {work / 'receipt.json'}")
    finally:
        if tab_id is not None:
            try:
                surf(root, ["tab.close", "--tab-id", str(tab_id)])
            except Exception:
                pass
        server.close()

    print()
    if FAILURES:
        print(f"ui insights: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("ui insights: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
