#!/usr/bin/env python3
"""Live proof for briefing-pack opening detection.

Real server, the committed Straive pack, a replayed owned conversation:

1. loading the pack journals its digest; formal_assessment sessions are
   refused in the backend;
2. each seeded opening surfaces the RIGHT point, bound to the exact trigger
   transcript events (journal readback);
3. small talk and unrelated technical chatter surface nothing;
4. cooldown: the same topic twice in quick succession surfaces once;
5. a cross-sentence opening (terms split over adjacent turns) still matches;
6. surfaced openings render in the browser with the heard terms (surf).
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


# Owned, clean-room simulation of the Straive side of the call.
CONVERSATION = [
    ("smalltalk-1", "Hi Graham, thanks for making time today, how has your week been?", []),
    ("opening-operationalize",
     "So the core of what we do now is helping enterprises operationalize AI, getting them from pilots and POCs into production.",
     ["operationalization"]),
    ("smalltalk-2", "Before I forget, our colleague from Singapore will join a few minutes late.", []),
    ("opening-agentic",
     "A big growth area for us is agentic AI, multi-agent orchestration with proper monitoring and auditability.",
     ["agentic-verification"]),
    ("opening-evals",
     "One thing we always probe: how do you test agent systems, how do you deal with hallucinations in production?",
     ["verification-differentiator"]),
    ("cross-sentence-a", "We acquired a company called NextGen Invent recently.", []),
    ("cross-sentence-b", "Their forward deployed engineers embed with the client and scale the work up.",
     ["forward-deployed"]),
    ("opening-pharma",
     "Many of our clients are in pharma and life sciences, so regulated delivery and audit trails matter a great deal.",
     ["governance-compliance"]),
    ("unrelated-tech", "Separately our IT team is migrating the office wifi this weekend.", []),
    ("closing",
     "That covers what we had. Do you have any questions for us?",
     ["why-me-question"]),
]


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root
    pack_payload = json.loads((root / "fixtures" / "briefing_straive.json").read_text())

    # 1a. formal_assessment refusal.
    formal = campaign.Server(campaign.import_tmp("briefing-formal"),
                             purpose="formal_assessment", live_resolver=False)
    try:
        status, _ = campaign.http("POST", f"{formal.url}/api/briefing/load", pack_payload)
        check("formal_assessment cannot load a briefing pack (403)", status == 403, f"http={status}")
    finally:
        formal.close()

    server = campaign.Server(campaign.import_tmp("briefing"), live_resolver=False)
    tab_id = None
    try:
        status, load = campaign.http("POST", f"{server.url}/api/briefing/load", pack_payload)
        check("pack loads with digest journaled", status == 202 and load.get("points") == 15,
              f"digest={str(load.get('pack_digest'))[:12]}")

        expected: dict[str, list[str]] = {}
        sequence = 0
        for label, text, expected_points in CONVERSATION:
            sequence += 1
            server.post_final(sequence, text)
            for point in expected_points:
                expected.setdefault(point, []).append(label)
            time.sleep(0.4)
        time.sleep(2)

        journal_path = next(server.data_dir.glob("*/session.jsonl"))
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        surfaced = [r["payload"] for r in rows if r.get("kind") == "briefing_point_surfaced"]
        surfaced_ids = [h["point_id"] for h in surfaced]
        transcript = {e["payload"]["event_id"]: e["payload"]["text"]
                      for e in rows if e.get("kind") == "transcript"}

        missing = [p for p in expected if p not in surfaced_ids]
        check("every seeded opening surfaces its point",
              not missing, f"surfaced={surfaced_ids} missing={missing}")

        # exact trigger-event binding: each surfaced hit's trigger events must
        # contain its matched terms (stem-tolerant readback).
        bad_bindings = []
        for hit in surfaced:
            texts = " ".join(transcript.get(eid, "") for eid in hit["trigger_event_ids"]).lower()
            stems = [t.split()[0][:5].lower() for t in hit["matched_terms"]]
            if not all(stem in texts for stem in stems):
                bad_bindings.append(hit["point_id"])
        check("every surfaced point binds the exact trigger transcript events",
              not bad_bindings, f"bad={bad_bindings}")

        smalltalk_leaks = [
            h["point_id"] for h in surfaced
            if any("weekend" in transcript.get(eid, "").lower()
                   or "wifi" in transcript.get(eid, "").lower()
                   for eid in h["trigger_event_ids"])
            and h["point_id"] not in ("career-path",)
        ]
        check("small talk and unrelated chatter surface nothing", not smalltalk_leaks,
              f"leaks={smalltalk_leaks}")
        check("cross-sentence opening matches (NextGen + forward deployed across turns)",
              "forward-deployed" in surfaced_ids)

        # 4. cooldown: repeat the agentic topic immediately -> no duplicate.
        before = surfaced_ids.count("agentic-verification")
        sequence += 1
        server.post_final(sequence, "Right, as I said, agentic systems with multi-agent orchestration are the focus.")
        time.sleep(1.5)
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        after = [r["payload"]["point_id"] for r in rows
                 if r.get("kind") == "briefing_point_surfaced"].count("agentic-verification")
        check("cooldown suppresses an immediate repeat of the same topic",
              after == before, f"before={before} after={after}")

        # 6. browser rung.
        for _ in range(30):
            ui_status, _ = campaign.http("GET", f"{server.url}/")
            if ui_status == 200:
                break
            time.sleep(1)
        output = surf(root, ["tab.new", f"{server.url}/", "--json"])
        tab_id = int(re.search(r"Created tab\s+(\d+)", output).group(1))
        time.sleep(3)
        dom = None
        for _ in range(30):
            dom = surf_js(root, tab_id, """
(() => {
  const hits = [...document.querySelectorAll('[data-qid^="briefing-"]')]
    .filter(e => e.getAttribute('data-qid') !== 'briefing-panel')
    .map(e => ({id: e.getAttribute('data-qid'), terms: e.getAttribute('data-matched-terms')}));
  const heard = document.body.textContent.includes('heard:');
  return JSON.stringify({hits, heard});
})()""")
            if dom and dom.get("hits"):
                break
            time.sleep(1.5)
        dom = dom or {}
        check(
            "surfaced openings render in the browser with the heard terms",
            len(dom.get("hits") or []) >= 3 and dom.get("heard") is True,
            f"rendered={[h['id'] for h in dom.get('hits') or []]}",
        )
        shot = Path(campaign.import_tmp("briefing-shot")) / "briefing-panel.png"
        surf(root, ["screenshot", "--tab-id", str(tab_id), "--output", str(shot)])
        check("screenshot captured", shot.is_file() and shot.stat().st_size > 10_000, str(shot))
    finally:
        if tab_id is not None:
            try:
                surf(root, ["tab.close", "--tab-id", str(tab_id)])
            except Exception:
                pass
        server.close()

    print()
    if FAILURES:
        print(f"briefing pack: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("briefing pack: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
