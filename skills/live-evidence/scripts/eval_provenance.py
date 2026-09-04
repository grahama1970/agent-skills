#!/usr/bin/env python3
"""Live proof for clause-level provenance navigation (#1476).

Real server (LIVE resolver + LIVE fast solver), real seeded repository, real
built UI in a surf-controlled Chrome tab:

1. >= 50 clause/source anchors across multiple questions, every source anchor
   independently recomputed (sha256 + line readback) and matched against the
   /api/provenance verification;
2. no clause borrows a citation: a clause's source_ids only ever point at
   sources whose excerpt actually overlaps that clause (recomputed here);
3. unsourced clauses are explicitly marked, never silently sourced;
4. mutating a cited file flips its clauses to invalidated in the BROWSER
   (surf DOM readback), never silently retained support;
5. the source deep view shows exact path:line and verification state; the
   anchor line matches an independent file read;
6. screenshot + receipt (mocked=false, live=true).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
        raise RuntimeError(f"surf failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def surf_js(root: Path, tab_id: int, script: str) -> Any:
    output = surf(root, ["js", script, "--tab-id", str(tab_id)])
    parsed = json.loads(output)
    return json.loads(parsed) if isinstance(parsed, str) else parsed


QUESTIONS = [
    "How does collect_all follow the pagination next links in our departures collector?",
    "Where does our departures collector apply the category and start date filter?",
    "How does fetch_page build the next link and the page results?",
    "How is the CSV written with title-case headers in our collector?",
    "What does the main function of the departures collector do end to end?",
    "Which exact string literal does the collector compare start dates against?",
    "How would you unit test fetch_page for the final short page?",
]


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root

    # Mutable copy of the seeded workspace so the mutation scenario is safe:
    # campaign.Server points LIVE_EVIDENCE_REPOS at PACK/seeded-workspace, so
    # swap PACK to a shim whose seeded-workspace is our copy.
    work = Path(tempfile.mkdtemp(prefix="provenance-eval-"))
    repo = work / "workspace"
    shutil.copytree(campaign.PACK / "seeded-workspace", repo)
    pack_shim = work / "pack"
    pack_shim.mkdir()
    (pack_shim / "seeded-workspace").symlink_to(repo)
    server_work = work / "server"
    server_work.mkdir()
    real_pack = campaign.PACK
    campaign.PACK = pack_shim
    try:
        server = campaign.Server(server_work, live_resolver=True)
    finally:
        campaign.PACK = real_pack

    tab_id = None
    try:
        journal_glob = lambda: next((work / "server" / "data").glob("*/session.jsonl"), None)
        answered = 0
        for sequence, question in enumerate(QUESTIONS, start=1):
            server.post_final(sequence, question)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                journal = journal_glob()
                if journal:
                    rows = [json.loads(line) for line in journal.read_text().splitlines()]
                    if len([r for r in rows if r.get("kind") == "fast_solver_receipt"]) > answered:
                        answered += 1
                        break
                time.sleep(0.5)

        status, provenance = campaign.http("GET", f"{server.url}/api/provenance")
        cards = provenance.get("cards") or []
        # Model phrasing varies; when no clause overlapped a retrieval excerpt
        # this round, ask one question whose answer must quote the file. This
        # tops up coverage, it never loosens a check.
        def sourced_count(payload):
            return sum(1 for card in payload for clause in card.get("clauses") or []
                       if clause.get("sourced"))
        topup = 0
        while sourced_count(cards) == 0 and topup < 2:
            topup += 1
            server.post_final(100 + topup,
                              "Quote the exact cutoff string literal from collect_departures.py and tell me which line it is on.")
            time.sleep(20)
            status, provenance = campaign.http("GET", f"{server.url}/api/provenance")
            cards = provenance.get("cards") or []
        clauses = [c for card in cards for c in card.get("clauses") or []]
        sources = [s for card in cards for s in card.get("sources") or []]
        anchors = len(clauses) + len(sources)
        check("at least 50 clause/source anchors produced live",
              status == 200 and anchors >= 50,
              f"clauses={len(clauses)} sources={len(sources)}")

        # 1. independent anchor recomputation.
        mismatches = []
        file_backed = 0
        for source in sources:
            if not source.get("path"):
                continue
            verification = source.get("verification") or {}
            path = Path(source["path"])
            if not path.is_file():
                if verification.get("state") != "missing":
                    mismatches.append(f"{source['source_id']}: missing-file not reported")
                continue
            file_backed += 1
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if verification.get("current") and verification["current"] != digest:
                mismatches.append(f"{source['source_id']}: digest drift")
            line_start = source.get("line_start")
            if line_start and verification.get("anchor_line") is not None:
                lines = path.read_text().splitlines()
                if lines[int(line_start) - 1][:200] != verification["anchor_line"]:
                    mismatches.append(f"{source['source_id']}: anchor line mismatch")
        check("independent recomputation matches every file-backed anchor",
              file_backed >= 3 and not mismatches,
              f"file_backed={file_backed} mismatches={mismatches[:3]}")

        # 2. no borrowed citations (recompute overlap independently).
        token_re = re.compile(r"[a-zA-Z0-9_]{3,}")
        borrowed = []
        source_by_id = {s["source_id"]: s for s in sources}
        for clause in clauses:
            clause_tokens = {t.lower() for t in token_re.findall(clause["clause"])}
            for source_id in clause["source_ids"]:
                excerpt = str((source_by_id.get(source_id) or {}).get("excerpt") or "")
                tokens = {t.lower() for t in token_re.findall(excerpt)}
                if clause_tokens and len(clause_tokens & tokens) / len(clause_tokens) < 0.30:
                    borrowed.append(clause["clause"][:40])
        check("no clause borrows a citation its text does not overlap", not borrowed,
              f"borrowed={borrowed[:2]}")
        check("unsourced clauses explicitly marked",
              all((c["sourced"] is bool(c["source_ids"])) for c in clauses))

        # Browser rung.
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
  const clauses = document.querySelectorAll('[data-qid^="clause-"][data-sourced]').length;
  const sourced = document.querySelectorAll('[data-sourced="true"]').length;
  const chips = document.querySelectorAll('[data-qs-action="LIVE_EVIDENCE_PROVENANCE_OPEN_SOURCE"]').length;
  return JSON.stringify({clauses, sourced, chips});
})()""")
            if dom and dom.get("chips"):
                break
            time.sleep(1.5)
        dom = dom or {}
        check("provenance clauses and source chips render in the browser",
              (dom.get("clauses") or 0) >= 1 and (dom.get("sourced") or 0) >= 1
              and (dom.get("chips") or 0) >= 1, json.dumps(dom))

        # 5. deep view: click first chip, read path:line + anchor, verify
        # against an independent file read.
        surf_js(root, tab_id, "(() => { const el = document.querySelector('[data-qs-action=LIVE_EVIDENCE_PROVENANCE_OPEN_SOURCE][data-file-backed=true]'); if (el) el.click(); return JSON.stringify({clicked: !!el}); })()")
        time.sleep(1)
        deep = surf_js(root, tab_id, """
(() => {
  const view = document.querySelector('[data-qid="source-deep-view"]');
  const state = document.querySelector('[data-qid="source-verification-state"]');
  return JSON.stringify({text: view ? view.textContent : null, state: state ? state.textContent : null});
})()""")
        deep_text = str(deep.get("text") or "")
        match = re.search(r"(/[^\s·:]+\.py):(\d+)", deep_text)
        anchor_ok = False
        if match:
            path, line_number = Path(match.group(1)), int(match.group(2))
            if path.is_file():
                line = path.read_text().splitlines()[line_number - 1].strip()
                anchor_ok = bool(line) and line[:40] in deep_text
        check("deep view shows exact path:line whose content matches the file",
              match is not None and anchor_ok and deep.get("state") == "verified",
              f"state={deep.get('state')} match={bool(match)}")

        # 4. mutate the cited file -> invalidated in the BROWSER.
        program = repo / "collect_departures.py"
        program.write_text(program.read_text().replace("2018-6-1", "2018-06-01"), encoding="utf-8")
        time.sleep(4)  # poll cycle
        after = surf_js(root, tab_id, """
(() => {
  const invalidated = document.querySelectorAll('[data-invalidated="true"]').length;
  return JSON.stringify({invalidated});
})()""")
        check("mutating a cited file flips its clauses to invalidated in the browser",
              (after.get("invalidated") or 0) >= 1, json.dumps(after))
        _, api_after = campaign.http("GET", f"{server.url}/api/provenance")
        api_states = [s.get("verification", {}).get("state")
                      for card in api_after.get("cards") or []
                      for s in card.get("sources") or []]
        check("API verification reports digest_mismatch after mutation",
              "digest_mismatch" in api_states, f"states={set(api_states)}")

        shot = work / "provenance-panel.png"
        surf(root, ["screenshot", "--tab-id", str(tab_id), "--output", str(shot)])
        check("screenshot captured", shot.is_file() and shot.stat().st_size > 10_000, str(shot))
        (work / "receipt.json").write_text(json.dumps({
            "schema": "live_evidence.provenance_receipt.v1", "mocked": False, "live": True,
            "anchors": anchors, "screenshot": str(shot), "checks_failed": FAILURES,
        }, indent=1))
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
        print(f"provenance: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
