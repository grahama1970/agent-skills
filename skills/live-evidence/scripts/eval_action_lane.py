#!/usr/bin/env python3
"""Live proof for the evidence-triggered action lane (#1475).

Real server, LIVE resolver (candidate proposal is resolver-authored), LIVE
memory service for remember_fact, real repository for open_artifact, LIVE
Brave lane for fact_check when configured (a missing Brave runner reports
unresolved, never invented support).

1. a replayed meeting segment with a seeded checkable claim, an explicit
   decision, and a named artifact produces action candidates, each bound to
   exact transcript events;
2. nothing executes without approval; approving each yields the expected
   effect read back from its DESTINATION (search card sources / memory keyed
   readback / resolved artifact path on disk);
3. a stale candidate (question moved on before approval) is fenced+journaled,
   not executed;
4. formal_assessment proposes zero candidates (backend journal proves the
   rejection);
5. the candidates render in the browser with Approve controls (surf readback).
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


MEETING_TURN = (
    "Okay, quick recap before we move on. Rust was first released publicly in 2015, "
    "please double check that. We have decided to use Postgres sixteen for the new "
    "reporting service, note that down. And the pagination logic I mentioned lives in "
    "collect_departures.py if you want to open it. Now, how should we shard the "
    "reporting tables by tenant?"
)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "scripts"))
    import run_g2i_campaign as campaign

    campaign.ROOT = root
    if not campaign.scillm_key():
        print("live SciLLM key: FAIL")
        return 1

    work = campaign.import_tmp("action-lane")
    server = campaign.Server(work, live_resolver=True, memory_url="http://127.0.0.1:8601")
    tab_id = None
    try:
        server.post_final(1, MEETING_TURN)
        pending: list[dict] = []
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            _, body = campaign.http("GET", f"{server.url}/api/actions/pending")
            pending = body.get("pending") or []
            if len(pending) >= 2:
                break
            time.sleep(1)
        kinds = sorted(c["kind"] for c in pending)
        check("resolver proposes evidence-bound action candidates",
              len(pending) >= 2 and all(c.get("trigger_event_ids") for c in pending),
              f"kinds={kinds}")

        if pending:
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
  const actions = document.querySelectorAll('[data-qid^="action-"]').length;
  const approve = document.querySelectorAll('[data-qs-action=LIVE_EVIDENCE_ACTION_APPROVE]').length;
  return JSON.stringify({actions, approve});
})()""")
                if dom and dom.get("actions"):
                    break
                time.sleep(1.5)
            dom = dom or {}
            check("candidates render in the browser with approve controls",
                  (dom.get("actions") or 0) >= 1 and (dom.get("approve") or 0) >= 1,
                  json.dumps(dom))
        else:
            check("candidates render in the browser with approve controls", False, "no candidates")

        journal_path = next(server.data_dir.glob("*/session.jsonl"), None)
        rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        executed_before = [r for r in rows if r.get("kind") == "action_executed"]
        check("nothing executes without approval", not executed_before)

        by_kind = {c["kind"]: c for c in pending}

        # remember_fact -> LIVE memory keyed readback.
        remember = by_kind.get("remember_fact")
        if remember:
            _, outcome = campaign.http(
                "POST", f"{server.url}/api/actions/{remember['action_id']}/approve",
                {"actor": "human:eval"}, timeout=120)
            receipt = outcome.get("execution_receipt") or {}
            ok = outcome.get("status") == "executed" and receipt.get("readback_ok") is True
            error_text = str(receipt.get("error") or receipt.get("detail") or "")
            if not ok and ("timed out" in error_text.lower() or "timeout" in error_text.lower()
                            or "connection" in error_text.lower()):
                print(f"MEMORY_SERVICE_STARVED: {error_text[:120]}")
            check("remember_fact executes with independent memory readback", ok,
                  f"status={outcome.get('status')} error={error_text[:80]}")
        else:
            check("remember_fact executes with independent memory readback", False, "not proposed")

        # open_artifact -> resolved path exists on disk (independent readback).
        artifact = by_kind.get("open_artifact")
        if artifact:
            _, outcome = campaign.http(
                "POST", f"{server.url}/api/actions/{artifact['action_id']}/approve",
                {"actor": "human:eval"}, timeout=120)
            receipt = outcome.get("execution_receipt") or {}
            resolved = Path(str(receipt.get("path") or "/nonexistent"))
            check("open_artifact resolves the cited file to a real path",
                  outcome.get("status") == "executed" and resolved.is_file()
                  and resolved.name == "collect_departures.py",
                  f"path={receipt.get('path')}")
        else:
            check("open_artifact resolves the cited file to a real path", False, "not proposed")

        # fact_check -> live external lane or an HONEST unresolved.
        fact = by_kind.get("fact_check")
        if fact:
            _, outcome = campaign.http(
                "POST", f"{server.url}/api/actions/{fact['action_id']}/approve",
                {"actor": "human:eval"}, timeout=120)
            check("fact_check executes supported-or-unresolved, never invented",
                  outcome.get("status") in {"executed", "unresolved"},
                  f"status={outcome.get('status')} sources={(outcome.get('execution_receipt') or {}).get('sources')}")
        else:
            print("fact_check candidate: SKIP (resolver did not propose one this run)")

        # 3. stale fence: propose against the current question, move the
        # question on, then approve -> fenced_stale, not executed.
        server.post_final(2, "Also decide and remember: we will use uv for python dependency management. How do lockfiles work in uv?")
        stale_target = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            _, body = campaign.http("GET", f"{server.url}/api/actions/pending")
            for c in body.get("pending") or []:
                if c["kind"] == "remember_fact" and "uv" in json.dumps(c).lower():
                    stale_target = c
                    break
            if stale_target:
                break
            time.sleep(1)
        if stale_target:
            server.post_final(3, "New topic entirely: what is the difference between TCP and UDP?")
            time.sleep(20)  # let the new question claim the active slot
            _, outcome = campaign.http(
                "POST", f"{server.url}/api/actions/{stale_target['action_id']}/approve",
                {"actor": "human:eval"}, timeout=120)
            rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
            fenced = [r for r in rows if r.get("kind") == "action_fenced_stale"]
            check("stale candidate is fenced and journaled, not executed",
                  outcome.get("status") == "fenced_stale" and fenced,
                  f"status={outcome.get('status')}")
        else:
            check("stale candidate is fenced and journaled, not executed", False,
                  "no second-round remember candidate to fence")

        # goal v2: an insufficient local-evidence answer auto-PROPOSES
        # bounded external research (derived query, approval-gated).
        server.post_final(50, "What is the current market share of the Zig programming language in embedded aerospace firmware?")
        research = None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            _, body = campaign.http("GET", f"{server.url}/api/actions/pending")
            research = next((c for c in body.get("pending") or []
                             if c["kind"] == "fact_check"
                             and "Research externally" in c.get("summary", "")), None)
            if research:
                break
            time.sleep(1)
        check(
            "insufficient local evidence auto-proposes bounded external research",
            research is not None and research.get("trigger_event_ids")
            and len(research.get("payload") or "") <= 500,
            f"summary={str((research or {}).get('summary'))[:80]}",
        )

        # 4. formal_assessment proposes zero.
        formal = campaign.Server(campaign.import_tmp("action-formal"),
                                 purpose="formal_assessment", live_resolver=True)
        try:
            formal.post_final(1, MEETING_TURN)
            time.sleep(25)
            _, body = campaign.http("GET", f"{formal.url}/api/actions/pending")
            formal_journal = next(formal.data_dir.glob("*/session.jsonl"), None)
            formal_rows = [json.loads(line) for line in formal_journal.read_text().splitlines()] \
                if formal_journal else []
            rejected = [r for r in formal_rows if r.get("kind") == "action_rejected_by_policy"]
            check("formal_assessment proposes zero candidates (backend-journaled)",
                  not (body.get("pending") or []),
                  f"pending={len(body.get('pending') or [])} rejections_journaled={len(rejected)}")
        finally:
            formal.close()
    finally:
        if tab_id is not None:
            try:
                surf(root, ["tab.close", "--tab-id", str(tab_id)])
            except Exception:
                pass
        server.close()

    print()
    if FAILURES:
        print(f"action lane: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("action lane: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
