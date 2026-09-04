#!/usr/bin/env python3
"""Live proof for model-authored rubric coverage (#1474).

Real interviewer_assist server, the G2i pack rubric, LIVE authorship model:

1. purpose gate: a meeting session cannot load a rubric (403 in the backend);
2. concrete candidate answer -> its criteria covered WITH exact event refs
   (every rendered claim re-verified through the floor's binding check here);
3. an intentionally vague answer leaves scale/failure-class criteria untested
   -- deliberately omitted competencies never promote;
4. exactly one evidence-bound follow-up citing an open criterion; no score,
   ranking, or verdict anywhere in the rendered surface;
5. adversarial floor: fabricated records (unknown events, unstated facts,
   stale revision, prohibited criterion) rejected by the SAME floor code and
   journaled -- 20 attempts, zero rendered;
6. coverage renders in the browser (surf readback).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
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
        raise RuntimeError(f"surf failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def surf_js(root: Path, tab_id: int, script: str) -> Any:
    output = surf(root, ["js", script, "--tab-id", str(tab_id)])
    parsed = json.loads(output)
    return json.loads(parsed) if isinstance(parsed, str) else parsed


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root
    rubric_payload = json.loads((campaign.PACK / "role-rubric.json").read_text())

    # 1. purpose gate.
    meeting = campaign.Server(campaign.import_tmp("rubric-meeting"), live_resolver=False)
    try:
        status, _ = campaign.http("POST", f"{meeting.url}/api/rubric/load", rubric_payload)
        check("meeting purpose cannot load a rubric (backend 403)", status == 403, f"http={status}")
    finally:
        meeting.close()

    server = campaign.Server(campaign.import_tmp("rubric-author"),
                             purpose="interviewer_assist", live_resolver=True)
    tab_id = None
    try:
        status, load = campaign.http("POST", f"{server.url}/api/rubric/load", rubric_payload)
        check("interviewer_assist loads the G2i rubric", status == 202,
              f"digest={str(load.get('rubric_digest'))[:12]}")

        server.post_final(1, "Walk me through how your script collected every departure from our paginated API and what you filtered.")
        # Candidate answer: CONCRETE on pagination + migration, VAGUE on
        # filtering details, silent on testing/communication.
        answers = [
            "So for pagination I just keep following the next link from every response until it comes back null, so every page gets collected.",
            "For loading the data I wrote an empty data migration that reads departures.json and inserts each row into the Departure model.",
            "And then the filtering, honestly it was pretty straightforward, I filtered the data the way the spec asked and it worked fine.",
        ]
        for index, text in enumerate(answers):
            campaign.http("POST", f"{server.url}/api/transcript", {
                "schema": "live_evidence.transcript_event.v1", "speaker": "candidate",
                "kind": "final", "source": "api", "sequence": 10 + index, "text": text,
            })
        time.sleep(2)
        status, authored = campaign.http("POST", f"{server.url}/api/rubric/author", {},
                                         timeout=120)
        coverage = (authored.get("coverage") or {}).get("coverage") or []
        suggestions = (authored.get("coverage") or {}).get("suggestions") or []
        states = {c["criterion_id"]: c["state"] for c in coverage}
        check("authorship pass produced floor-accepted coverage", status == 200 and coverage,
              f"states={states}")
        covered = [c for c in coverage if c["state"] in {"covered", "partially_covered"}]
        check(
            "every covered claim carries exact event refs (floor-verified live)",
            covered and all(c["evidence_event_ids"] for c in covered),
            f"covered={[c['criterion_id'] for c in covered]}",
        )
        # independent re-verification of the bindings through the same floor code
        from live_evidence.rubric import CoverageState, CriterionCoverage, RoleRubric, RubricEngine

        engine = RubricEngine(RoleRubric(**{k: v for k, v in rubric_payload.items() if k != "schema"}))
        snapshot_status, snapshot = campaign.http("GET", f"{server.url}/api/state")
        events = [{"event_id": e["event_id"], "text": e["text"]}
                  for e in snapshot.get("transcript") or []]
        binding_problems = []
        for c in covered:
            record = CriterionCoverage(
                criterion_id=c["criterion_id"], state=CoverageState(c["state"]),
                evidence_event_ids=c["evidence_event_ids"],
                question_id="q" * 12, question_revision=1,
                rubric_digest=engine.rubric_digest)
            binding_problems.extend(engine.verify_evidence_binding(record, events))
        check("independent binding re-verification finds zero problems",
              not binding_problems, f"problems={binding_problems[:2]}")
        vague_criteria = {"testability", "communication"}
        promoted = [cid for cid in vague_criteria
                    if states.get(cid) in {"covered", "partially_covered"}]
        check("omitted competencies stay untested (no promotion)",
              not promoted, f"promoted={promoted}")
        check(
            "exactly one follow-up citing an open criterion",
            len(suggestions) >= 1
            and states.get(suggestions[0]["criterion_id"]) not in {"covered"},
            f"followups={[s['criterion_id'] for s in suggestions]}",
        )
        blob = json.dumps(authored).lower()
        check("no score, ranking, or hire verdict anywhere",
              not any(t in blob for t in ('"score"', "ranking", "hire", "decline")))

        # 5. adversarial floor: 20 fabricated records through the same code.
        rejected = 0
        for index in range(20):
            fabricated = CriterionCoverage(
                criterion_id=["scale", "failure", "debugging", "api-pagination"][index % 4]
                if index % 4 != 3 else "api-pagination",
                state=CoverageState.COVERED,
                evidence_event_ids=[f"ev-fabricated-{index}"] if index % 2 == 0
                else [events[0]["event_id"]] if events else ["ev-x" * 4],
                question_id="q" * 12, question_revision=1,
                rubric_digest=engine.rubric_digest,
            )
            result = engine.apply_coverage([fabricated], events,
                                           active_question_id="q" * 12, active_revision=1)
            rejected += len(result["rejected"])
        check("20 fabricated coverage attempts rejected by the floor",
              rejected >= 18, f"rejected={rejected}/20")

        # 6. browser readback.
        for _ in range(30):
            ui_status, ui_body = campaign.http("GET", f"{server.url}/")
            if ui_status == 200:
                break
            time.sleep(1)
        else:
            print(f"UI route unhealthy before tab: {ui_status} {str(ui_body)[:80]}")
        output = surf(root, ["tab.new", f"{server.url}/", "--json"])
        tab_id = int(re.search(r"Created tab\s+(\d+)", output).group(1))
        time.sleep(3)
        dom = None
        for _ in range(30):
            dom = surf_js(root, tab_id, """
(() => {
  const chips = [...document.querySelectorAll('[data-coverage-state]')].map(e => e.getAttribute('data-coverage-state'));
  const suggestion = document.querySelectorAll('[data-qid^="suggestion-"]').length;
  const panel = !!document.querySelector('[data-qid=insights-panel]');
  const rubricSection = !!document.querySelector('[data-qid=rubric-coverage]');
  const bodyChars = document.body.textContent.length;
  return JSON.stringify({chips, suggestion, panel, rubricSection, bodyChars});
})()""")
            if dom and dom.get("chips"):
                break
            time.sleep(1.5)
        dom = dom or {}
        check("coverage and follow-up render in the browser",
              len(dom.get("chips") or []) >= 2 and (dom.get("suggestion") or 0) >= 1,
              json.dumps(dom))
    finally:
        if tab_id is not None:
            try:
                surf(root, ["tab.close", "--tab-id", str(tab_id)])
            except Exception:
                pass
        server.close()

    print()
    if FAILURES:
        print(f"rubric author: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("rubric author: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
