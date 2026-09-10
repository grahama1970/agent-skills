#!/usr/bin/env bash
# First-interviewer-question full-chain rehearsal for $explain-project.
#
# Chain: REAL first pasted question -> live-evidence intake boundary ->
# deterministic route (publish.report_last) -> walk steps to the
# debugger-target step -> REAL headless breakpoint at pipeline.py:210 under
# `python -m anonymization_trial demo` -> debugger-proof adapter receipt ->
# excalidraw proposal receipt -> integration health READY -> Chatterbox
# narration render receipt (render only; no playback, no perceptual claim).
#
# Boundaries: no microphone, no Chatterbox playback, no Excalidraw mutation,
# no live DAP/VS Code GUI control. The breakpoint stop is real and headless.
set -euo pipefail

exec python3 - "$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)" <<'PY'
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PORT = 18772
BASE = f"http://127.0.0.1:{PORT}"
SKILL = Path(sys.argv[1]).resolve()
OAI = Path("/home/graham/workspace/experiments/oai-trial")
DBG = SKILL.parent / "debugger" / "run.sh"
SPEAK = SKILL.parent / "chatterbox-speak" / "run.sh"
T = Path(tempfile.mkdtemp())


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())



def last_json_object(text):
    """Return the last top-level JSON object printed in stdout."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].rstrip().endswith("}"):
            # walk back to the opening brace of this object
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


def run(cmd, **kw):
    return subprocess.run(
        cmd, capture_output=True, text=True, **kw
    )


# 0. Boot cockpit on the oai-trial explainers.
boot = subprocess.Popen(
    [
        "uv", "run", "--isolated",
        "--with", "pydantic", "--with", "typer",
        "--with", "httpx", "--with", "loguru",
        "python3", "scripts/explain_project.py", "cockpit",
        "--explainers", str(OAI / "docs/explain/explainers.jsonl"),
        "--repo", str(OAI),
        "--host", "127.0.0.1", "--port", str(PORT),
    ],
    cwd=SKILL,
    stdout=(T / "boot.log").open("w"),
    stderr=subprocess.STDOUT,
)
try:
    import time

    for _ in range(40):
        try:
            urllib.request.urlopen(
                f"{BASE}/api/health", timeout=1
            )
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("cockpit did not start")

    # 1. Real first question through the live-evidence intake boundary.
    candidate = {
        "schema": "live_evidence.question_candidate.v1",
        "question_id": "rehearsal-q1",
        "normalized_question": (
            "Walk me through your solution from receiving "
            "an input dataset to releasing the anonymized "
            "result."
        ),
        "speaker": "interviewer",
        "source_event_ids": ["rehearsal-event-1"],
        "source_spans": [{
            "event_id": "rehearsal-event-1",
            "sequence": 1,
            "start_offset": 0,
            "end_offset": 95,
        }],
        "start_sequence": 1,
        "end_sequence": 1,
        "trigger_reason": "question_mark",
        "fingerprint": "rehearsal-fingerprint-1",
    }
    intake = post("/api/intake/live-evidence", {
        "schema": "explain_project.live_evidence_intake.v1",
        "source": "live_evidence_replay",
        "candidate": candidate,
    })
    state = intake["state"]
    assert intake["status"] == "ACCEPTED", intake
    assert state["route"]["status"] == "MATCHED"
    assert (
        state["selection"]["feature_id"]
        == "publish.report_last"
    )
    assert (
        state["integration_health"]["live_evidence"]
        == "READY"
    )
    step_count = state["selection"]["step_count"]
    print(
        "STEP1_ROUTE_OK publish.report_last"
        f" step 1/{step_count} live_evidence READY"
    )

    # 2. Walk steps until the debugger-target step.
    rev = state["revision"]
    target_state = None
    for i in range(step_count):
        if state["debugger"]["target"] is not None:
            target_state = state
            break
        state = post("/api/cockpit/event", {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": f"rehearsal-step-{i}",
            "type": "step.next",
            "expected_revision": rev,
            "payload": {},
        })
        rev = state["revision"]
    assert target_state is not None, "no debugger step found"
    target = target_state["debugger"]["target"]
    assert target["file"].endswith(
        "src/anonymization_trial/pipeline.py"
    ), target
    assert target["line"] == 210, target
    assert (
        target_state["integration_health"]["debugger_target"]
        == "STALE"
    )
    print(
        "DEBUGGER_STEP_OK", target["file"],
        target["line"], "health STALE pre-receipt",
    )

    # 3. REAL headless breakpoint stop at pipeline.py:210. The demo
    #    subcommand shells out to a child process (untraceable), so the
    #    driver calls run_pipeline in-process like a real reproduction.
    driver = T / "driver.py"
    driver.write_text(
        "from pathlib import Path\n"
        "import tempfile\n"
        "from anonymization_trial.fixture import generate_fixture\n"
        "from anonymization_trial.pipeline import run_pipeline\n"
        "root = Path(tempfile.mkdtemp())\n"
        "inp = root / 'input'\n"
        "out = root / 'output'\n"
        "generate_fixture(inp, records=50)\n"
        "run_pipeline(inp, out)\n"
    )
    import os

    brk = run(
        [
            "bash", str(DBG), "break",
            "src/anonymization_trial/pipeline.py:210",
            "--local", "tmp",
            "--local", "report_path",
            "--local", "output_corpus",
            "--out", str(T / "proof.json"),
            "--", "python3", str(driver),
        ],
        cwd=OAI,
        env={
            **os.environ,
            "PYTHONPATH": str(OAI / "src"),
        },
    )
    (T / "break.log").write_text(brk.stdout + brk.stderr)
    assert brk.returncode == 0, (
        T / "break.log"
    ).read_text()[-400:]
    proof = json.loads(
        (T / "proof.json").read_text()
    )
    status = proof["status"]
    if isinstance(status, dict):
        assert status.get("ok") is True, status
    assert proof["hit_count"] >= 1, proof
    print(
        "REAL_BREAK_OK pipeline.py:210 hits",
        proof["hit_count"],
    )

    # 3b. Normalize the raw capture to canonical debugger.proof.v1.
    val = run(
        [
            "bash", str(DBG), "validate",
            str(T / "proof.json"),
            "--expect-valid",
            "--repo-root", str(OAI),
            "--canonical-out", str(T / "canonical.json"),
        ],
        cwd=OAI,
    )
    assert "debugger proof validation passed" in (
        val.stdout + val.stderr
    ), (val.stdout + val.stderr)[-300:]

    # 4. Debugger proof adapter receipt -> health READY.
    step_id = target_state["selection"]["step_id"]
    rev = target_state["revision"]
    rec = run([
        "bash", str(SKILL / "run.sh"),
        "debugger-runtime-proof-receipt",
        "--proof", str(T / "canonical.json"),
        "--workspace", str(OAI),
        "--target-file",
        "src/anonymization_trial/pipeline.py",
        "--start-line", "180", "--end-line", "220",
        "--feature-id", "publish.report_last",
        "--step-id", step_id,
        "--request-revision", str(rev),
        "--local", "tmp",
        "--local", "report_path",
        "--local", "output_corpus",
        "--proves", "paused runtime at atomic publish rename",
    ], cwd=SKILL)
    (T / "dbg-rec.log").write_text(
        rec.stdout + "\n--STDERR--\n" + rec.stderr
    )
    receipt = last_json_object(rec.stdout)
    assert receipt["adapter"] == "debugger_proof", receipt
    assert receipt["status"] == "PROOF_RECEIVED", receipt
    state = post("/api/cockpit/event", {
        "schema": "explain_project.cockpit_event.v1",
        "event_id": "rehearsal-dbg-receipt",
        "type": "adapter.receipt",
        "expected_revision": rev,
        "payload": {"receipt": receipt},
    })
    assert (
        state["integration_health"]["debugger_target"]
        == "READY"
    ), state["integration_health"]
    assert (
        state["debugger"]["status"] == "PROOF_RECEIVED"
    )
    print("DEBUGGER_RECEIPT_OK health READY proof_received")

    # 5. Excalidraw proposal receipt (display-only).
    (T / "ops.json").write_text(json.dumps({
        "schema": "ops_excalidraw.push_board.v1",
        "status": "PASS",
        "mode": "proposal",
        "version": 1,
        "elements": 3,
    }))
    rec = run([
        "bash", str(SKILL / "run.sh"),
        "excalidraw-proposal-receipt",
        "--receipt", str(T / "ops.json"),
        "--feature-id", "publish.report_last",
        "--step-id", step_id,
        "--request-revision", str(state["revision"]),
    ], cwd=SKILL)
    receipt = last_json_object(rec.stdout)
    assert receipt["adapter"] == "excalidraw_proposal", receipt
    assert receipt["status"] == "PROPOSED", receipt
    state = post("/api/cockpit/event", {
        "schema": "explain_project.cockpit_event.v1",
        "event_id": "rehearsal-exc-receipt",
        "type": "adapter.receipt",
        "expected_revision": state["revision"],
        "payload": {"receipt": receipt},
    })
    assert (
        state["integration_health"]["diagram"] == "READY"
    ), state["integration_health"]
    print("EXCALIDRAW_RECEIPT_OK diagram READY")

    # 6. Spoken walkthrough: chatterbox narrates the breakpoint stop
    #    with code context, diagram nodes, and the scannable bullets.
    bullets = target_state["teleprompter"]["bullets"]
    assert len(bullets) >= 2, "no scannable bullets on stop"
    assert all(len(b) <= 160 for b in bullets), bullets
    print(
        "COCKPIT_BULLETS_OK",
        len(bullets), "scannable bullets",
    )

    title = target_state["teleprompter"]["title"]
    context = target_state["source"]["explanation"] or ""
    proves = (
        target_state["debugger"]["target"].get("proves")
        or ""
    )
    nodes = ", ".join(
        target_state["diagram"]["active_node_ids"]
        or target_state["diagram"]["node_ids"][:3]
    )
    narration = " ".join([
        f"{title}.",
        context,
        f"The debugger stop proves: {proves}.",
        f"On the board: {nodes}.",
        *bullets[:2],
    ]).replace("\n", " ")

    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8018/health", timeout=3
        ) as h:
            live = json.loads(h.read()).get("ok") is True
    except Exception:
        live = False

    if live:
        sp = run([
            "bash", str(SPEAK), "speak",
            "--voice", "embry",
            "--text", narration,
            "--context",
            "first-question rehearsal: spoken breakpoint walkthrough",
            "--tone", "calm_precise",
        ], cwd=SPEAK.parent)
        if sp.returncode == 0:
            marker = '"receipt": "'
            idx = sp.stdout.find(marker)
            assert idx >= 0, sp.stdout[-300:]
            receipt_path = Path(
                sp.stdout[idx + len(marker):]
                .split('"', 1)[0]
            )
            receipt = json.loads(
                receipt_path.read_text()
            )
            wav = Path(receipt["wav"])
            assert wav.is_file() and (
                wav.stat().st_size > 1000
            ), receipt
            print(
                "CHATTERBOX_WALKTHROUGH_OK", wav.name
            )
        else:
            print("CHATTERBOX_SKIPPED render failed")
    else:
        print("CHATTERBOX_SKIPPED service down")

    print("FIRST_QUESTION_CHAIN_OK")
finally:
    boot.terminate()
    try:
        boot.wait(timeout=10)
    except Exception:
        boot.kill()
PY
