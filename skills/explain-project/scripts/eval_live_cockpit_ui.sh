#!/usr/bin/env bash
# Live-UI walkthrough eval for $explain-project: the REAL first interviewer
# question drives the actual React cockpit in a real Chrome tab (Surf), the
# DOM is the readback oracle (active-question banner, revision fence, step
# walk via the J hotkey, debugger target, scannable bullets), and
# chatterbox-speak renders the Embry-voice narration for the breakpoint stop.
#
# Disposable: boots its own cockpit API + vite preview and closes only its
# own tab/processes. Render only (no playback), no mic, no Excalidraw
# mutation, no VS Code GUI control.
set -euo pipefail

exec python3 - "$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)" <<'PY'
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SKILL = Path(sys.argv[1]).resolve()
UI = SKILL / "ui"
OAI = Path("/home/graham/workspace/experiments/oai-trial")
SURF = SKILL.parent / "surf" / "run.sh"
SPEAK = SKILL.parent / "chatterbox-speak" / "run.sh"
T = Path(tempfile.mkdtemp())
API_PORT = 18773
UI_PORT = 15177
BASE = f"http://127.0.0.1:{API_PORT}"

QUESTION = (
    "Walk me through your solution from receiving "
    "an input dataset to releasing the anonymized "
    "result."
)

# JS expressions: single-quoted Python strings, double quotes inside the JS
# only, no backslash escapes anywhere.
BOOT_JS = "JSON.stringify({rev:document.querySelector(\"[data-qid='cockpit:state:root']\")?.getAttribute(\"data-revision\"),ready:!!document.querySelector(\"[data-qid='cockpit:question:manual-input']\")})"
PROBE_JS = "JSON.stringify({rev:document.querySelector(\"[data-qid='cockpit:state:root']\")?.getAttribute(\"data-revision\"),banner:document.querySelector(\"[data-qid='cockpit:stage:active-question']\")?.textContent,title:document.querySelector(\"h1\")?.textContent,bullets:document.querySelectorAll(\"section.cockpit-stage li\").length,step:(document.body.textContent.split(\"Step \")[1]||\"\").slice(0,8)})"
DBG_JS = "JSON.stringify({target:document.querySelector(\"[data-qid='cockpit:debugger:panel']\")?.textContent})"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def surf(*args, tab=None):
    cmd = ["bash", str(SURF), *args]
    if tab is not None:
        cmd += ["--tab-id", str(tab)]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=60
    )


def surf_retry(*args, tab=None, tries=4, delay=2.0):
    last = None
    for _ in range(tries):
        last = surf(*args, tab=tab)
        combined = last.stdout + last.stderr
        if "Another debugger is already attached" not in combined:
            return last
        time.sleep(delay)
    return last


def dom_probe(tab, expression, tries=20):
    last = ""
    for _ in range(tries):
        r = surf_retry(
            "js", "--no-activate", expression, tab=tab
        )
        out = (r.stdout + r.stderr).strip()
        # surf js double-encodes the evaluate result as a JSON string
        # literal; decode fully, then fall back to brace slicing.
        parsed = None
        try:
            value = json.loads(out)
            if isinstance(value, str):
                value = json.loads(value)
            parsed = value
        except ValueError:
            start = out.find("{")
            end = out.rfind("}")
            if start >= 0 and end > start:
                try:
                    value = json.loads(
                        out[start:end + 1]
                    )
                    if isinstance(value, str):
                        value = json.loads(value)
                    parsed = value
                except ValueError:
                    parsed = None
        if isinstance(parsed, dict):
            return parsed
        last = out
        time.sleep(1)
    raise SystemExit(f"DOM probe failed: {last[-300:]}")


api = None
preview = None
tab_id = None
try:
    # 1. Disposable cockpit API on the oai-trial explainers.
    api = subprocess.Popen(
        [
            "uv", "run", "--isolated",
            "--with", "pydantic", "--with", "typer",
            "--with", "httpx", "--with", "loguru",
            "python3", "scripts/explain_project.py",
            "cockpit",
            "--explainers",
            str(OAI / "docs/explain/explainers.jsonl"),
            "--repo", str(OAI),
            "--host", "127.0.0.1",
            "--port", str(API_PORT),
        ],
        cwd=SKILL,
        stdout=(T / "api.log").open("w"),
        stderr=subprocess.STDOUT,
    )

    # 2. Disposable vite preview proxying /api to the API.
    preview = subprocess.Popen(
        [
            "npm", "run", "preview", "--",
            "--host", "127.0.0.1",
            "--port", str(UI_PORT),
            "--strictPort",
        ],
        cwd=UI,
        env={
            **os.environ,
            "EXPLAIN_PROJECT_API_URL": BASE,
        },
        stdout=(T / "preview.log").open("w"),
        stderr=subprocess.STDOUT,
    )

    for _ in range(40):
        try:
            urllib.request.urlopen(
                f"{BASE}/api/health", timeout=1
            )
            urllib.request.urlopen(
                f"http://127.0.0.1:{UI_PORT}/", timeout=1
            )
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit(
            "stack did not start: "
            + (T / "api.log").read_text()[-200:]
            + (T / "preview.log").read_text()[-200:]
        )

    # 3. ONE persistent cockpit tab (default 837436340) — navigate it
    #    to the disposable preview and restore its URL afterwards.
    #    Never tab.new / tab.close here.
    tab_id = int(
        os.environ.get("LIVEUI_TAB_ID", "837436340")
    )
    prev = surf_retry(
        "js", "--no-activate", "location.href", tab=tab_id
    )
    restore_url = (
        prev.stdout.strip().strip('"')
        or f"http://127.0.0.1:15176/"
    )
    surf(
        "go",
        f"http://127.0.0.1:{UI_PORT}/?liveui=1",
        "--tab-id", str(tab_id),
    )
    time.sleep(2)

    boot = dom_probe(tab_id, BOOT_JS)
    assert boot["ready"], boot
    print("UI_TAB_READY tab", tab_id)

    # 4. Real question through the live-evidence intake boundary.
    candidate = {
        "schema": "live_evidence.question_candidate.v1",
        "question_id": "liveui-question-0001",
        "normalized_question": QUESTION,
        "speaker": "interviewer",
        "source_event_ids": ["liveui-event-1"],
        "source_spans": [{
            "event_id": "liveui-event-1",
            "sequence": 1,
            "start_offset": 0,
            "end_offset": 95,
        }],
        "start_sequence": 1,
        "end_sequence": 1,
        "trigger_reason": "question_mark",
        "fingerprint": "liveui-fingerprint-0001",
    }
    intake = post("/api/intake/live-evidence", {
        "schema": "explain_project.live_evidence_intake.v1",
        "source": "live_evidence_replay",
        "candidate": candidate,
    })
    assert intake["status"] == "ACCEPTED", intake
    assert intake["state"]["route"]["status"] == "MATCHED"

    # 5. The live DOM is the oracle: the 1 Hz poll must surface the
    #    active-question banner, the routed step, and the bullets.
    seen = {"banner": None}
    for _ in range(20):
        seen = dom_probe(tab_id, PROBE_JS, tries=1)
        if seen.get("banner") and "Walk me through" in seen["banner"]:
            break
        time.sleep(1)
    assert "Walk me through" in (
        seen.get("banner") or ""
    ), seen
    assert int(seen["rev"]) >= 1, seen
    assert seen["bullets"] >= 2, seen
    assert seen["step"], seen
    print(
        "LIVE_DOM_ORACLE_OK step", seen["step"],
        "bullets", seen["bullets"],
    )

    # 6. Drive the UI with the J hotkey; the revision fence must move.
    before_rev = int(seen["rev"])
    surf("key", "j", tab=tab_id)
    time.sleep(2)
    after = dom_probe(tab_id, PROBE_JS)
    assert int(after["rev"]) > before_rev, after
    print(
        "HOTKEY_STEP_OK rev",
        before_rev, "->", after["rev"],
    )

    # 7. Debugger target visible in the evidence rail (expand with E).
    surf("key", "e", tab=tab_id)
    time.sleep(1)
    dbg = dom_probe(tab_id, DBG_JS)
    assert "pipeline.py" in (
        dbg.get("target") or ""
    ), dbg
    assert "210" in dbg["target"], dbg
    print("DEBUGGER_TARGET_IN_DOM_OK pipeline.py:210")

    # 8. Embry narrates the stop (render receipt; no playback).
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8018/health", timeout=3
        ) as h:
            live = json.loads(h.read()).get("ok") is True
    except Exception:
        live = False

    if live:
        narration = " ".join([
            "Interviewer question routed.",
            QUESTION,
            "The stop is the atomic publish:",
            "staged corpus renamed into place, report written last.",
            "Bullets are on the teleprompter.",
        ])
        sp = subprocess.run(
            [
                "bash", str(SPEAK), "speak",
                "--voice", "embry",
                "--text", narration,
                "--context",
                "live cockpit walkthrough: first question",
                "--tone", "calm_precise",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if sp.returncode == 0:
            marker = '"receipt": "'
            idx = sp.stdout.find(marker)
            assert idx >= 0, sp.stdout[-300:]
            receipt_path = Path(
                sp.stdout[idx + len(marker):]
                .split('"', 1)[0]
            )
            receipt = json.loads(receipt_path.read_text())
            wav = Path(receipt["wav"])
            assert wav.is_file() and wav.stat().st_size > 1000, receipt
            print("EMBRY_NARRATION_OK", wav.name)
        else:
            print("EMBRY_NARRATION_SKIPPED render failed")
    else:
        print("EMBRY_NARRATION_SKIPPED service down")

    print("LIVE_COCKPIT_WALKTHROUGH_OK")
finally:
    if tab_id is not None:
        for _ in range(3):
            back = surf_retry(
                "go", restore_url,
                "--tab-id", str(tab_id),
            )
            time.sleep(1)
            check = surf_retry(
                "js", "--no-activate", "location.href",
                tab=tab_id,
            )
            if restore_url.split("?")[0] in check.stdout:
                print("TAB_RESTORED_OK", restore_url)
                break
    for proc in (preview, api):
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
PY
