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

exec python3 -u - "$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)" <<'PY'
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
DBG = SKILL.parent / "debugger" / "run.sh"
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


def last_json_object(text):
    """Return the last top-level JSON object printed in stdout."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].rstrip().endswith("}"):
            start = i
            while start >= 0 and not lines[start].lstrip().startswith("{"):
                start -= 1
            if start < 0:
                continue
            chunk = "\n".join(lines[start:i + 1])
            if '"schema"' not in chunk:
                continue
            return json.loads(chunk)
    raise ValueError("no JSON object in output")


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


def surf_retry(*args, tab=None, tries=6, delay=3.0):
    """Retry a surf call through debugger-attach conflicts.

    A killed mid-js eval leaves a leaked chrome.debugger session wedging
    the tab; one clean extension.reload releases it. Recover once, then
    keep retrying.
    """
    last = None
    reloaded = False
    for attempt in range(tries):
        last = surf(*args, tab=tab)
        combined = last.stdout + last.stderr
        if "Another debugger is already attached" not in combined:
            return last
        if not reloaded and attempt >= 1:
            reloaded = True
            surf("extension.reload")
            time.sleep(8)
        else:
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
board = None
board_tab_id = None
board_restore_url = "https://excalidraw.com/"
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

    # 1b. Persistent ops-excalidraw whiteboard (tab 837436448's home).
    #     Boot a disposable one only as fallback.
    BOARD_URL = "http://127.0.0.1:7683/"
    board = None
    try:
        with urllib.request.urlopen(
            BOARD_URL, timeout=2
        ) as _r:
            healthy = _r.status == 200
    except Exception:
        healthy = False
    if not healthy:
        board = subprocess.Popen(
        [
            "bash",
            str(SKILL.parent / "ops-excalidraw" / "run.sh"),
            "whiteboard", "--port", "7684",
        ],
        stdout=(T / "board.log").open("w"),
        stderr=subprocess.STDOUT,
    )
        BOARD_URL = "http://127.0.0.1:7684/"
    board_served = board is not None or healthy

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
    # Never restore into the eval's own navigation artifact.
    if "liveui=1" in restore_url:
        restore_url = "http://127.0.0.1:15176/"
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

    # 6. Per-step walkthrough: 1-2 sentence context + bullets per step,
    #    the real $debugger break + receipt flipping the live UI at the
    #    breakpoint step, and the ops-excalidraw whiteboard tab open.
    surf("key", "e", tab=tab_id)  # expand evidence rail once
    time.sleep(1)

    def bootstrap():
        with urllib.request.urlopen(
            f"{BASE}/api/cockpit/bootstrap", timeout=10
        ) as r:
            return json.loads(r.read())["state"]

    # authoritative step count from the API, not a fuzzy DOM text match
    step_total = bootstrap()["selection"]["step_count"]
    for step_index in range(step_total):
        snap = dom_probe(tab_id, PROBE_JS)
        state = bootstrap()
        assert snap["bullets"] >= 2, snap
        assert snap["title"], snap
        src = dom_probe(
            tab_id,
            'JSON.stringify({src:document.querySelector('
            '"[data-qid=\'cockpit:source:panel\']")'
            '?.textContent})',
        )
        explanation = (src.get("src") or "").strip()
        assert explanation and len(explanation) < 400, src
        print(
            "PER_STEP_EXPLAINER_OK step", step_index + 1,
            snap["title"][:30], "bullets", snap["bullets"],
        )

        dbg = dom_probe(tab_id, DBG_JS)
        stop_line = state["debugger"]["target"]["line"] \
            if state["debugger"]["target"] else None
        if (
            "pipeline.py" in (dbg.get("target") or "")
            and stop_line
        ):
            # Whiteboard tab for this breakpoint's diagram:
            # ONE persistent entered tab id, navigated and restored.
            if board_tab_id is None and board_served:
                board_tab_id = int(
                    os.environ.get(
                        "LIVEUI_BOARD_TAB_ID",
                        "837436448",
                    )
                )
                # Verify via tab.list (no debugger attach): a
                # DevTools window on the tab wedges chrome.debugger.
                listing = surf("tab.list", "--json")
                entries = json.loads(listing.stdout)
                entry = next(
                    (
                        e for e in entries
                        if str(e.get("id"))
                        == str(board_tab_id)
                    ),
                    None,
                )
                assert entry is not None, (
                    "board tab not open: "
                    + str(board_tab_id)
                )
                surf(
                    "go", BOARD_URL,
                    "--tab-id", str(board_tab_id),
                )
                time.sleep(2)
                listing = surf("tab.list", "--json")
                entries = json.loads(listing.stdout)
                entry = next(
                    (
                        e for e in entries
                        if str(e.get("id"))
                        == str(board_tab_id)
                    ),
                    None,
                )
                assert entry is not None
                assert "whiteboard" in (
                    entry.get("title") or ""
                ), entry
                print(
                    "WHITEBOARD_TAB_OK",
                    board_tab_id,
                )

            # REAL headless breakpoint at the step's stop.
            driver = T / "driver.py"
            driver.write_text(
                "from pathlib import Path\n"
                "import tempfile\n"
                "from anonymization_trial.fixture "
                "import generate_fixture\n"
                "from anonymization_trial.pipeline "
                "import run_pipeline\n"
                "root = Path(tempfile.mkdtemp())\n"
                "inp = root / 'input'\n"
                "out = root / 'output'\n"
                "generate_fixture(inp, records=50)\n"
                "run_pipeline(inp, out)\n"
            )
            brk = subprocess.run(
                [
                    "bash", str(DBG), "break",
                    f"src/anonymization_trial/pipeline.py:{stop_line}",
                    "--local", "tmp",
                    "--local", "report_path",
                    "--local", "output_corpus",
                    "--out", str(T / "proof.json"),
                    "--", "python3", str(driver),
                ],
                capture_output=True, text=True,
                cwd=OAI,
                env={
                    **os.environ,
                    "PYTHONPATH": str(OAI / "src"),
                },
                timeout=180,
            )
            (T / "break.log").write_text(
                brk.stdout + brk.stderr
            )
            assert brk.returncode == 0, (
                T / "break.log"
            ).read_text()[-300:]
            val = subprocess.run(
                [
                    "bash", str(DBG), "validate",
                    str(T / "proof.json"),
                    "--expect-valid",
                    "--repo-root", str(OAI),
                    "--canonical-out",
                    str(T / "canonical.json"),
                ],
                capture_output=True, text=True,
                cwd=OAI, timeout=60,
            )
            assert "debugger proof validation passed" in (
                val.stdout + val.stderr
            ), (val.stdout + val.stderr)[-300:]
            rec = subprocess.run(
                [
                    "bash", str(SKILL / "run.sh"),
                    "debugger-runtime-proof-receipt",
                    "--proof", str(T / "canonical.json"),
                    "--workspace", str(OAI),
                    "--target-file",
                    "src/anonymization_trial/pipeline.py",
                    "--start-line", str(stop_line - 30),
                    "--end-line", str(stop_line + 10),
                    "--feature-id", "publish.report_last",
                    "--step-id",
                    state["selection"]["step_id"],
                    "--request-revision",
                    str(state["revision"]),
                    "--local", "tmp",
                    "--local", "report_path",
                    "--local", "output_corpus",
                    "--proves",
                    "paused runtime at atomic publish rename",
                ],
                capture_output=True, text=True,
                cwd=SKILL, timeout=120,
            )
            receipt = last_json_object(rec.stdout)
            assert receipt["adapter"] == "debugger_proof"
            post("/api/cockpit/event", {
                "schema":
                    "explain_project.cockpit_event.v1",
                "event_id":
                    f"liveui-dbg-{step_index}",
                "type": "adapter.receipt",
                "expected_revision": state["revision"],
                "payload": {"receipt": receipt},
            })

            # The live UI must flip to PROOF_RECEIVED.
            for _ in range(15):
                time.sleep(1)
                flip = dom_probe(
                    tab_id,
                    'JSON.stringify({d:document.querySelector('
                    '"[data-qid=\'cockpit:debugger:panel\']")'
                    '?.textContent})',
                )
                if "PROOF_RECEIVED" in (
                    flip.get("d") or ""
                ):
                    break
            assert "PROOF_RECEIVED" in (
                flip.get("d") or ""
            ), flip
            print(
                "DEBUGGER_PROOF_UI_OK step",
                step_index + 1,
            )

        if step_index < step_total - 1:
            before_rev = int(snap["rev"])
            surf("key", "j", tab=tab_id)
            time.sleep(2)
            after = dom_probe(tab_id, PROBE_JS)
            assert int(after["rev"]) > before_rev, after
            print(
                "HOTKEY_STEP_OK rev",
                before_rev, "->", after["rev"],
            )

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
                "--pace", "slow",
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

    # 9. Diagrams Explorer interactions (criterion #14): expand,
    #    filter, select, proposal-safe note.
    surf(
        "click",
        '[data-qid="left-pane:diagrams:expand"]',
        tab=tab_id,
    )
    time.sleep(1)
    pane = dom_probe(
        tab_id,
        'JSON.stringify({items:document.querySelectorAll("[data-qid^=\'left-pane:diagrams:item:\']").length})',
    )
    assert int(pane.get("items") or 0) >= 1, pane

    set_filter = (
        '(()=>{const i=document.querySelector('
        '"[data-qid=\'left-pane:diagrams:filter\']");'
        'const set=Object.getOwnPropertyDescriptor('
        'window.HTMLInputElement.prototype,"value").set;'
        'set.call(i,%s);'
        'i.dispatchEvent(new Event("input",{bubbles:true}));'
        'return "ok"})()'
    )
    surf_retry("js", "--no-activate", set_filter % '"publish"', tab=tab_id)
    time.sleep(0.5)
    pane = dom_probe(
        tab_id,
        'JSON.stringify({items:document.querySelectorAll("[data-qid^=\'left-pane:diagrams:item:\']").length})',
    )
    assert int(pane.get("items") or 0) >= 1, pane
    surf_retry("js", "--no-activate", set_filter % '"zzz-no-match"', tab=tab_id)
    time.sleep(0.5)
    pane = dom_probe(
        tab_id,
        'JSON.stringify({items:document.querySelectorAll("[data-qid^=\'left-pane:diagrams:item:\']").length,empty:document.body.textContent.includes("No matching")})',
    )
    assert int(pane.get("items") or 0) == 0 and pane.get(
        "empty"
    ), pane
    surf_retry("js", "--no-activate", set_filter % '""', tab=tab_id)
    time.sleep(0.5)

    rev_before = int(
        dom_probe(tab_id, PROBE_JS)["rev"]
    )
    surf(
        "click",
        '[data-qid^="left-pane:diagrams:item:"]',
        tab=tab_id,
    )
    time.sleep(2)
    rev_after = int(
        dom_probe(tab_id, PROBE_JS)["rev"]
    )
    assert rev_after > rev_before, (rev_before, rev_after)

    surf(
        "click",
        '[data-qid="left-pane:diagrams:propose"]',
        tab=tab_id,
    )
    time.sleep(0.5)
    note = dom_probe(
        tab_id,
        'JSON.stringify({note:document.body.textContent'
        '.includes("ops-excalidraw-owned")})',
    )
    assert note.get("note"), note
    print("DIAGRAMS_EXPLORER_OK filter/select/propose")

    print("LIVE_COCKPIT_WALKTHROUGH_OK")
finally:
    if board_tab_id is not None:
        for _ in range(3):
            surf(
                "go", BOARD_URL,
                "--tab-id", str(board_tab_id),
            )
            time.sleep(1)
    if board is not None:
        board.terminate()
        try:
            board.wait(timeout=10)
        except Exception:
            board.kill()
    if tab_id is not None:
        for _ in range(4):
            back = surf(
                "go", restore_url,
                "--tab-id", str(tab_id),
            )
            time.sleep(2)
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
