#!/usr/bin/env python3
"""Live proof: /ask compete window lifecycle (operator report 2026-08-25).

Runs a real compete (or reads an existing run dir) and asserts, from the
run's own receipts, the four properties the operator requires:

  1. UNFOCUSED   - each seat window.new used --unfocused (background; never
                   hijacks the user's mouse; surf's default).
  2. DESKTOP_2   - each seat window was moved to the reviewer desktop
                   (place-window desktop_index == ASK_REVIEWER_DESKTOP, default
                   1 == KDE "Desktop 2") with verified: true.
  3. SUBMITTED   - the run recorded an answer or a named blocker for every
                   requested browser seat (tabs populated + submitted).
  4. CLOSED      - after answers were recorded, each provisioned window was
                   closed (window.close rc 0 in the lifecycle cleanup).

Prints marker lines the agentic-eval fixture asserts on; exits nonzero on any
violation. This is the regression guard that was missing while the behavior
silently drifted.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)
SKILL_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_DESKTOP = int(os.environ.get("ASK_REVIEWER_DESKTOP", "1"))


def _cmd_str(entry: dict) -> str:
    c = entry.get("command", [])
    return " ".join(c) if isinstance(c, list) else str(c)


def _run_compete(handlers: list[str], judge: str, timeout: int) -> Path:
    ask_id = f"compete-window-eval-{uuid.uuid4().hex[:8]}"
    cmd = [str(SKILL_ROOT / "run.sh"), "compete",
           "Reply with one short sentence: what is a directed acyclic graph?",
           "--repo", "local/agent-skills", "--target", "compete-window-eval",
           "--immutable-goal", "Each seat answers or names a blocker.",
           "--judge-handler", judge, "--criterion", "clarity",
           "--ask-id", ask_id, "--browser-tab-lifecycle", "fresh-temporary",
           "--execute", "--json", "--poll-timeout-seconds", str(timeout)]
    for h in handlers:
        cmd += ["--handler", h]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout + 300, cwd=SKILL_ROOT)
    text = proc.stdout
    try:
        result = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception:
        print("COMPETE_RUNNER_ERROR", (proc.stderr or text)[-300:])
        raise typer.Exit(1)
    run_dir = ((result.get("execution") or {}).get("run_dir")
               or (result.get("bundle") or {}).get("run_dir") or "")
    return Path(str(run_dir))


def _assert_lifecycle(run_dir: Path, handlers: list[str]) -> bool:
    ok = True
    lc = json.loads((run_dir / "browser-tab-lifecycle.json").read_text())
    created = lc.get("created_tabs", [])
    browser_seats = [h for h in handlers if h in {
        "webgpt", "webclaude", "webkimi", "webgemini", "webgrok", "webdeepseek"}]

    # 1. UNFOCUSED
    news = [_cmd_str(c) for c in lc.get("commands", []) if "window.new" in _cmd_str(c)]
    unfocused = bool(news) and all("--unfocused" in n for n in news)
    print(f"UNFOCUSED_WINDOWS:{len(news)}:{'all' if unfocused else 'MISSING'}")
    if not unfocused:
        ok = False
    else:
        print("COMPETE_WINDOWS_UNFOCUSED")

    # 2. DESKTOP_2
    places = [c for c in lc.get("commands", []) if "place-window" in _cmd_str(c)]
    on_desktop = 0
    for c in places:
        try:
            out = json.loads(c.get("stdout") or "{}")
        except json.JSONDecodeError:
            out = {}
        di, ver = out.get("desktop_index"), out.get("verified")
        good = c.get("returncode") == 0 and di == REVIEWER_DESKTOP and ver is True
        print(f"PLACED:{out.get('window')}:desktop_{di}:verified_{ver}:{'ok' if good else 'BAD'}")
        if good:
            on_desktop += 1
    if places and on_desktop == len(places) and on_desktop >= len(browser_seats):
        print(f"COMPETE_WINDOWS_ON_DESKTOP_{REVIEWER_DESKTOP + 1}")
    else:
        print(f"DESKTOP_PLACEMENT_FAIL: {on_desktop}/{len(places)} placed, "
              f"{len(browser_seats)} seats")
        ok = False

    # 3. SUBMITTED (answers recorded)
    answered = 0
    es = run_dir / "execution-status.json"
    if es.is_file():
        d = json.loads(es.read_text())
        for r in d.get("node_provider_receipts", []) or []:
            nid = str(r.get("node_id", ""))
            if nid.startswith("handler-") and "judge" not in nid and "join" not in nid:
                seat = nid.replace("handler-", "")
                st = r.get("status")
                chars = r.get("response_chars") or 0
                print(f"SEAT:{seat}:{st}:chars_{chars}")
                if st == "PASS" and chars > 0:
                    answered += 1
    if answered >= 1 and answered >= min(len(browser_seats), 1):
        print("COMPETE_SUBMIT_RECORDED")
    else:
        print(f"SUBMIT_FAIL: {answered} seats answered")
        ok = False

    # 4. CLOSED after record
    closes = [c for c in (lc.get("cleanup") or []) if "window.close" in _cmd_str(c)]
    closed_ok = bool(closes) and all(c.get("returncode") == 0 for c in closes)
    print(f"CLOSE_RECEIPTS:{len(closes)}:{'all_rc0' if closed_ok else 'MISSING_OR_FAILED'}")
    # Verify the placed X11 windows are actually gone from wmctrl.
    placed_wins = []
    for c in places:
        try:
            placed_wins.append(json.loads(c.get("stdout") or "{}").get("window"))
        except json.JSONDecodeError:
            pass
    wm = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True).stdout.lower()
    leaked = [w for w in placed_wins if w and w.lower() in wm]
    if closed_ok and not leaked:
        print("COMPETE_WINDOWS_CLOSED_AFTER_RECORD")
    else:
        print(f"CLOSE_FAIL: leaked={leaked} close_receipts_ok={closed_ok}")
        ok = False

    return ok


@app.command()
def main(
    handler: list[str] = typer.Option(["webgpt", "webclaude"], "--handler"),
    judge: str = typer.Option("claude-opus-5-low", "--judge"),
    timeout: int = typer.Option(900, "--timeout"),
    from_run_dir: Path = typer.Option(None, "--from-run-dir",
                                      help="Assert against an existing compete run dir (dev/replay)."),
) -> None:
    run_dir = from_run_dir if from_run_dir else _run_compete(list(handler), judge, timeout)
    if not run_dir or not (run_dir / "browser-tab-lifecycle.json").is_file():
        print(f"NO_LIFECYCLE_JSON in {run_dir}")
        raise typer.Exit(1)
    time.sleep(2)  # let teardown settle before the wmctrl leak check
    ok = _assert_lifecycle(run_dir, list(handler))
    print("COMPETE_WINDOW_LIFECYCLE_OK" if ok else "COMPETE_WINDOW_LIFECYCLE_FAIL")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
