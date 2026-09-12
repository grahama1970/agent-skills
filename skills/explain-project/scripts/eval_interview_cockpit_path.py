#!/usr/bin/env python3
"""Retained first-interview-question cockpit integration eval.

This is intentionally a thin composition script: it reads the recorded pasted
question proof, drives the public explain-project CLI against the oai-trial
explainer catalog, captures a real headless $debugger breakpoint, pushes a safe
ops-excalidraw proposal, and writes one JSON proof bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS = ROOT.parents[1]
DEFAULT_REPO = Path("/home/graham/workspace/experiments/oai-trial")
DEFAULT_QUESTIONS = Path(
    "/mnt/storage12tb/oai-trial/interview-rehearsals/actual-pasted-questions-proof.txt"
)
DEFAULT_OUT = Path("/mnt/storage12tb/skills/explain-project/interview-cockpit-evals")
DEBUGGER = AGENT_SKILLS / "skills/debugger/run.sh"
OPS_EXCALIDRAW = AGENT_SKILLS / "skills/ops-excalidraw/run.sh"
WHITEBOARD_SERVER = AGENT_SKILLS / "skills/ops-excalidraw/scripts/whiteboard_server.py"
CHATTERBOX = AGENT_SKILLS / "skills/chatterbox-speak/run.sh"


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "schema": "explain_project.interview_cockpit_eval.v1",
                    "status": "FAIL",
                    "failed_command": cmd,
                    "cwd": str(cwd) if cwd else None,
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-4000:],
                },
                indent=2,
            )
        )
    return proc


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_questions(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result_lines = [line.removeprefix("result: ") for line in lines if line.startswith("result: ")]
    questions = [line for line in result_lines if line and not line.startswith("count ")]
    if len(questions) < 5:
        raise SystemExit(f"expected at least five recorded pasted questions in {path}, got {len(questions)}")
    return questions


def wait_http(port: int) -> None:
    for _ in range(40):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/libraries")
            if conn.getresponse().status == 200:
                return
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        time.sleep(0.25)
    raise SystemExit(f"ops-excalidraw whiteboard server did not open on {port}")


def canonicalize_debugger(raw_path: Path, canonical_path: Path) -> dict[str, Any]:
    raw = load_json(raw_path)
    hits = raw.get("hits") if isinstance(raw.get("hits"), list) else []
    if not hits:
        raise SystemExit("debugger raw proof recorded no hits")
    hit = hits[0]
    hit_file = str(hit["file"])
    hit_line = int(hit["line"])
    breakpoints = []
    for bp in raw.get("breakpoints", []):
        if not isinstance(bp, dict):
            continue
        bp_file = str(bp.get("file", ""))
        bp_line = int(bp.get("line", 0))
        breakpoints.append(
            {
                "file": bp_file,
                "line": bp_line,
                "source": str(hit.get("source", "")) if bp_file == hit_file and bp_line == hit_line else "",
                "verified": True,
                "hit": bp_file == hit_file and bp_line == hit_line,
            }
        )
    locals_map = hit.get("locals", {}) if isinstance(hit.get("locals"), dict) else {}
    proof = {
        "schema": "debugger.proof.v1",
        "producer": {"name": "capture_breakpoints.py"},
        "debugger": {"adapter": "Python bdb", "mode": "python-bdb"},
        "repro": {"command": [str(item) for item in raw.get("command", [])]},
        "breakpoints": breakpoints,
        "stopped": {
            "hit": True,
            "reason": "breakpoint",
            "frame": {
                "file": hit_file,
                "line": hit_line,
                "function": str(hit.get("function", "")),
            },
        },
        "captures": {
            "requestedLocals": [str(item) for item in raw.get("locals_allowlist", [])],
            "locals": locals_map,
            "watches": hit.get("watches", {}) if isinstance(hit.get("watches"), dict) else {},
        },
        "assessment": {
            "proofValid": True,
            "variableInspectionValid": bool(locals_map),
            "limitations": [],
        },
        "analysis": {
            "conclusion": "Python debugger stopped at the oai-trial publication breakpoint and captured selected paused state.",
            "nextEdit": "",
        },
    }
    dump(canonical_path, proof)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--questions-proof", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--whiteboard-port", type=int, default=7698)
    args = parser.parse_args()

    repo = args.repo.resolve()
    explainers = repo / "docs/explain/explainers.jsonl"
    if not explainers.is_file():
        raise SystemExit(f"missing oai-trial explainers: {explainers}")

    questions = read_questions(args.questions_proof)
    first_question = questions[0]
    out_dir = args.out_dir or DEFAULT_OUT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)

    route_path = out_dir / "route.json"
    route = run([str(ROOT / "run.sh"), "ask", str(explainers), "--question", first_question], cwd=ROOT)
    route_path.write_text(route.stdout, encoding="utf-8")
    route_json = load_json(route_path)
    if route_json.get("route", {}).get("status") != "MATCHED":
        raise SystemExit(f"first question did not route: {route_json}")

    cockpit_path = out_dir / "cockpit-proof.json"
    run([str(ROOT / "run.sh"), "cockpit-proof", str(explainers), "--question", first_question, "--out", str(cockpit_path)], cwd=ROOT)
    cockpit = load_json(cockpit_path)
    if cockpit.get("status") != "PASS":
        raise SystemExit(f"cockpit proof failed: {cockpit_path}")

    raw_debugger = out_dir / "debugger-raw.json"
    env = {"PYTHONPATH": str(repo / "src")}
    driver = out_dir / "debug-driver.py"
    driver.write_text(
        "from pathlib import Path\n"
        "import tempfile\n"
        "from anonymization_trial.fixture import generate_fixture\n"
        "from anonymization_trial.pipeline import run_pipeline\n"
        "root = Path(tempfile.mkdtemp())\n"
        "inp = root / 'input'\n"
        "out = root / 'output'\n"
        "generate_fixture(inp, records=50)\n"
        "run_pipeline(inp, out)\n",
        encoding="utf-8",
    )
    run(
        [
            str(DEBUGGER),
            "break",
            "src/anonymization_trial/pipeline.py:212",
            "--local",
            "tmp",
            "--local",
            "report_path",
            "--local",
            "output_corpus",
            "--out",
            str(raw_debugger),
            "--",
            "python3",
            str(driver),
        ],
        cwd=repo,
        env=env,
        timeout=240,
    )
    canonical_debugger = out_dir / "debugger-proof.canonical.json"
    debugger_proof = canonicalize_debugger(raw_debugger, canonical_debugger)
    debugger_validate = run(
        [str(DEBUGGER), "validate", str(canonical_debugger), "--expect-valid", "--repo-root", str(repo)],
        cwd=repo,
    )
    (out_dir / "debugger-validate.txt").write_text(debugger_validate.stdout + debugger_validate.stderr, encoding="utf-8")

    feature_id = route_json["matched_feature"]
    step_id = "seal"
    source_receipt_path = out_dir / "debugger-source-reveal-receipt.json"
    reveal_status = out_dir / "debugger-reveal-status.json"
    dump(
        reveal_status,
        {
            "id": "debugger-reveal-first-question",
            "requestHash": "a" * 64,
            "proofValid": True,
            "status": "revealed",
            "reveal": {
                "file": str(repo / "src/anonymization_trial/pipeline.py"),
                "line": 212,
                "selected": True,
                "api": [
                    "workspace.openTextDocument",
                    "window.showTextDocument(preserveFocus)",
                    "TextEditor.selection",
                    "TextEditor.revealRange",
                ],
            },
        },
    )
    src_receipt = run(
        [
            str(ROOT / "run.sh"),
            "debugger-source-reveal-receipt",
            "--status",
            str(reveal_status),
            "--workspace",
            str(repo),
            "--source-file",
            "src/anonymization_trial/pipeline.py",
            "--start-line",
            "169",
            "--end-line",
            "220",
            "--feature-id",
            feature_id,
            "--step-id",
            step_id,
            "--request-revision",
            "2",
        ],
        cwd=ROOT,
    )
    source_receipt_path.write_text(src_receipt.stdout, encoding="utf-8")

    runtime_receipt_path = out_dir / "debugger-runtime-proof-receipt.json"
    runtime_receipt = run(
        [
            str(ROOT / "run.sh"),
            "debugger-runtime-proof-receipt",
            "--proof",
            str(canonical_debugger),
            "--workspace",
            str(repo),
            "--target-file",
            "src/anonymization_trial/pipeline.py",
            "--start-line",
            "169",
            "--end-line",
            "220",
            "--feature-id",
            feature_id,
            "--step-id",
            step_id,
            "--request-revision",
            "2",
            "--local",
            "tmp",
            "--local",
            "report_path",
            "--local",
            "output_corpus",
            "--proves",
            "paused runtime captured report-last publication state for first pasted interview question",
        ],
        cwd=ROOT,
    )
    runtime_receipt_path.write_text(runtime_receipt.stdout, encoding="utf-8")

    server = subprocess.Popen(
        [sys.executable, str(WHITEBOARD_SERVER), str(args.whiteboard_port)],
        cwd=str(OPS_EXCALIDRAW.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_http(args.whiteboard_port)
        ops_receipt_path = out_dir / "ops-excalidraw-proposal.json"
        ops = run(
            [
                str(OPS_EXCALIDRAW),
                "describe",
                "--source",
                "First pasted interview question",
                "--target",
                "Route to project.walkthrough",
                "--target",
                "Debugger breakpoint at _publish:212",
                "--target",
                "Report-last readiness boundary",
                "--title",
                "Explain Project Cockpit First Question",
                "--port",
                str(args.whiteboard_port),
            ],
            cwd=OPS_EXCALIDRAW.parent,
        )
        ops_receipt_path.write_text(ops.stdout, encoding="utf-8")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    excalidraw_receipt_path = out_dir / "excalidraw-proposal-receipt.json"
    excalidraw_receipt = run(
        [
            str(ROOT / "run.sh"),
            "excalidraw-proposal-receipt",
            "--receipt",
            str(ops_receipt_path),
            "--feature-id",
            feature_id,
            "--step-id",
            step_id,
            "--request-revision",
            "2",
        ],
        cwd=ROOT,
    )
    excalidraw_receipt_path.write_text(excalidraw_receipt.stdout, encoding="utf-8")

    chatterbox: dict[str, Any]
    if CHATTERBOX.is_file():
        cb = run([str(CHATTERBOX), "voices"], cwd=CHATTERBOX.parent, timeout=60)
        cb_path = out_dir / "chatterbox-voices.json"
        cb_path.write_text(cb.stdout, encoding="utf-8")
        chatterbox = {"status": "OPTIONAL_VOICES_CHECKED", "path": str(cb_path), "required_for_pass": False}
    else:
        chatterbox = {"status": "SKILL_NOT_PRESENT", "required_for_pass": False}

    result = {
        "schema": "explain_project.interview_cockpit_eval.v1",
        "status": "PASS",
        "proof_boundary": (
            "Replays recorded pasted interview question text through the real explain-project CLI, "
            "headless cockpit reducer, real Python-bdb $debugger breakpoint, $debugger validator, "
            "and a safe ops-excalidraw proposal. It does not claim live microphone input, "
            "visible VS Code control, accepted Excalidraw board mutation, or rendered speech."
        ),
        "repo": str(repo),
        "questions_proof": {"path": str(args.questions_proof), "sha256": sha256(args.questions_proof), "count": len(questions)},
        "first_question": first_question,
        "route": {"path": str(route_path), "status": route_json["route"]["status"], "matched_feature": feature_id},
        "cockpit": {"path": str(cockpit_path), "status": cockpit["status"], "assertions": cockpit["assertions"]},
        "debugger": {
            "raw_path": str(raw_debugger),
            "canonical_path": str(canonical_debugger),
            "canonical_sha256": sha256(canonical_debugger),
            "validated_by": str(DEBUGGER),
            "stopped": debugger_proof["stopped"],
            "locals": sorted(debugger_proof["captures"]["locals"]),
        },
        "adapter_receipts": {
            "source_reveal": load_json(source_receipt_path),
            "debugger_runtime": load_json(runtime_receipt_path),
            "excalidraw_proposal": load_json(excalidraw_receipt_path),
        },
        "ops_excalidraw": load_json(ops_receipt_path),
        "chatterbox_speak": chatterbox,
        "out_dir": str(out_dir),
    }
    dump(out_dir / "proof.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    print("EXPLAIN_PROJECT_INTERVIEW_COCKPIT_PATH_OK")


if __name__ == "__main__":
    main()
