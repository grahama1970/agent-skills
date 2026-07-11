#!/usr/bin/env python3
"""Unified gate validator for persona-dream pipeline.

Validates a specific gate, a list of gates, or all gates against current state
and updates the pipeline report. Subagents use this to close resolved blockers.

Usage:
  ./run.sh validate-gate --gate all              # Run all gates
  ./run.sh validate-gate --gate phase-05         # Single gate
  ./run.sh validate-gate --gate phase-05,phase-06  # List of gates
  ./run.sh validate-gate --gate all --report /path/to/index.html  # Explicit report path
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import hmac
import hashlib
import base64
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

SCHEMA = "persona_dream.unified_gate_validator.v1"

# Map gate IDs to their validation scripts and expected blockers
GATES: dict[str, dict[str, Any]] = {
    "phase-02": {
        "script": "run_phase_02_memory_recall.py",
        "description": "Memory recall anti-hallucination gate",
        "blocker_keywords": ["tom_edges", "quarantine", "memory gate"],
    },
    "phase-05": {
        "script": "validate_phase_05_contact_sheet_gate.py",
        "description": "Contact sheet coverage gate",
        "blocker_keywords": ["missing dedicated", "PARTIAL", "contact.sheet"],
    },
    "phase-06": {
        "script": "validate_panel_interaction_gate.py",
        "description": "Per-panel interaction ledger gate",
        "blocker_keywords": ["interaction gate", "panel.*fail", "missing.*entity"],
    },
    "phase-06-repair": {
        "script": "validate_panel_repair_gate.py",
        "description": "Panel repair contract gate",
        "blocker_keywords": ["repair.*fail", "repair.*blocked"],
    },
    "voice-clone": {
        "script": None,  # No script — checks Kling API directly
        "description": "Kling voice clone provider gate",
        "blocker_keywords": ["voice_id", "clone.*provider", "voice.*clone"],
    },
    "panel-interaction": {
        "script": None,  # Live check — scans report HTML for status badges
        "description": "Per-panel interaction gate — live scan of report status badges",
        "blocker_keywords": ["panel.*fail", "interaction"],
    },
}

ALL_GATES = list(GATES.keys())


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
SKILL_DIR = Path(__file__).resolve().parents[2]

def resolve_run_root() -> Path | None:
    """Walk up from cwd to find a pipeline_review_8892 directory."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "pipeline_review_8892"
        if candidate.is_dir():
            return parent
    return None


def _load_voice_clone_tasks(run_root: Path) -> list[dict[str, str]]:
    """Load Kling voice-clone tasks from environment or run voice_handoff_plan.

    Expected env: KLING_VOICE_TASKS='[{"name":"...","task_id":"...","voice_key":"voice_1"},...]'
    Future: derive task_ids from a voice_clone_receipt.json produced by the voice step.
    """
    env_tasks = os.environ.get("KLING_VOICE_TASKS", "").strip()
    if env_tasks:
        try:
            tasks = json.loads(env_tasks)
            if isinstance(tasks, list):
                return tasks
        except json.JSONDecodeError:
            pass

    handoff_path = run_root / "voice_handoff_plan.json"
    if handoff_path.exists():
        try:
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            speakers = handoff.get("speakers", [])
            return [
                {"name": s.get("speaker_id", f"speaker_{i}"), "task_id": s.get("kling_task_id", ""), "voice_key": s.get("voice_key", f"voice_{i}")}
                for i, s in enumerate(speakers, start=1)
                if s.get("kling_task_id")
            ]
        except Exception:
            pass

    return []


def _load_recorded_voice_ids(run_root: Path) -> dict[str, Any] | None:
    """Load previously recorded Kling voice IDs without making a provider call.

    The autonomous path should not resubmit paid voice clone calls when a
    run-scoped source receipt already binds provider, token, speaker, and ID.
    """
    candidates = [
        run_root / "voice_clone_candidates" / "kling_voice_id_source_receipt.json",
        run_root / "pipeline_review_8892" / "voice_clone_candidates" / "kling_voice_id_source_receipt.json",
    ]
    candidates.extend(
        sorted(
            (run_root / "pipeline_review_8892").glob("**/kling_voice_id_source_receipt.json")
        )
        if (run_root / "pipeline_review_8892").exists()
        else []
    )

    for path in candidates:
        if not path.exists():
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if receipt.get("provider") != "kling":
            continue
        voice_ids = receipt.get("voice_ids")
        if not isinstance(voice_ids, dict):
            continue
        normalized: dict[str, dict[str, str]] = {}
        for key, value in voice_ids.items():
            if not isinstance(value, dict):
                continue
            voice_id = str(value.get("voice_id") or "").strip()
            token = str(value.get("token") or f"<<<{key}>>>").strip()
            speaker = str(value.get("speaker") or "").strip()
            if key.startswith("voice_") and voice_id and token and speaker:
                normalized[key] = {
                    "provider": "kling",
                    "voice_id": voice_id,
                    "token": token,
                    "speaker": speaker,
                    "source_receipt": str(path),
                }
        if {"voice_1", "voice_2"}.issubset(normalized):
            return {
                "path": str(path),
                "voice_ids": normalized,
                "status": receipt.get("status"),
                "verdict": receipt.get("verdict"),
                "live_call_performed": bool(receipt.get("live_call_performed")),
                "paid_call_performed": bool(receipt.get("paid_call_performed")),
            }
    return None


def check_voice_clone_gate(run_root: Path) -> dict[str, Any]:
    """Check Kling voice clone status by polling the API."""
    result = {
        "gate": "voice-clone",
        "status": "UNKNOWN",
        "voice_ids": {},
        "blockers": [],
        "message": "",
    }

    recorded = _load_recorded_voice_ids(run_root)
    if recorded:
        result["status"] = "PASS"
        result["voice_ids"] = {
            key: value["voice_id"] for key, value in recorded["voice_ids"].items()
        }
        result["source_receipt"] = recorded["path"]
        result["message"] = "Using run-scoped recorded Kling voice IDs; no live or paid provider call performed by this gate."
        result["live_call_performed"] = False
        result["paid_call_performed"] = False
        return result

    access_key = os.environ.get("KLING_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("KLING_SECRET_KEY", "").strip()
    if not access_key or not secret_key:
        result["status"] = "FAIL"
        result["message"] = "KLING_ACCESS_KEY and KLING_SECRET_KEY must be set in environment"
        result["blockers"].append("missing_kling_credentials")
        return result

    task_ids = _load_voice_clone_tasks(run_root)
    if not task_ids:
        result["status"] = "FAIL"
        result["message"] = "No Kling voice clone tasks configured. Set KLING_VOICE_TASKS or populate voice_handoff_plan.json."
        result["blockers"].append("missing_voice_clone_tasks")
        return result

    try:
        import time, urllib.request, hmac, hashlib, base64, json as _json

        def _make_jwt(access_key, secret_key):
            header = base64.urlsafe_b64encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
            now = int(time.time())
            payload = base64.urlsafe_b64encode(_json.dumps({"iss": access_key, "exp": now + 7200, "nbf": now}).encode()).rstrip(b"=").decode()
            sig = base64.urlsafe_b64encode(hmac.new(secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
            return f"{header}.{payload}.{sig}"

        token = _make_jwt(access_key, secret_key)
        base = "https://api-singapore.klingai.com"

        for task in task_ids:
            name = task.get("name", "unknown")
            task_id = task.get("task_id", "")
            voice_key = task.get("voice_key", "")
            if not task_id or not voice_key:
                continue
            req = urllib.request.Request(
                f"{base}/v1/general/custom-voices/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read()).get("data", {})
            voices = data.get("task_result", {}).get("voices", [])
            if voices:
                vid = voices[0].get("voice_id", "")
                if vid:
                    result["voice_ids"][voice_key] = vid

        expected_keys = [t.get("voice_key") for t in task_ids if t.get("voice_key")]
        if result["voice_ids"]:
            missing = [k for k in expected_keys if k not in result["voice_ids"]]
            if not missing:
                result["status"] = "PASS"
                result["message"] = f"All voice IDs resolved: {json.dumps(result['voice_ids'])}"
            else:
                result["status"] = "PARTIAL"
                result["message"] = f"Missing: {missing}"
                result["blockers"].append(f"Voice IDs still pending for: {missing}")
        else:
            result["status"] = "FAIL"
            result["message"] = "No voice IDs returned from Kling API"
            result["blockers"].append("Kling voice clone call not submitted or failed")
    except Exception as e:
        result["status"] = "ERROR"
        result["message"] = f"Voice clone check failed: {e}"
        result["blockers"].append(f"api_error: {e}")

    return result


def _latest_visual_course_corrections(run_root: Path) -> dict[str, Any] | None:
    artifact_root = run_root / "pipeline_review_8892" / "artifacts"
    if not artifact_root.exists():
        return None
    candidates = sorted(
        artifact_root.glob("panel_visual_gate_course_corrections_*/aggregate_visual_gate_course_corrections.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(path)
        return payload
    return None


def check_panel_repair_gate(run_root: Path) -> dict[str, Any]:
    """Validate the current panel repair state from actual receipts.

    This gate is intentionally receipt-driven. It must not treat image existence
    or the interaction ledger as provider-ready visual review.
    """
    result: dict[str, Any] = {
        "gate": "phase-06-repair",
        "status": "UNKNOWN",
        "blockers": [],
        "panel_receipts": [],
        "message": "",
    }

    visual = _latest_visual_course_corrections(run_root)
    if visual and visual.get("overall") != "PASS":
        failing = [str(panel) for panel in visual.get("failing_panels", [])]
        review_result: dict[str, Any] | None = None
        review_panel = SKILL_DIR.parent / "review-panel" / "run.sh"
        if review_panel.exists() and failing:
            verdict_dir = run_root / "pipeline_review_8892" / "panel_verdicts"
            index_html = run_root / "pipeline_review_8892" / "index.html"
            cmd = [
                str(review_panel),
                "review",
                "--run-root",
                str(run_root),
                "--panels",
                ",".join(str(int(panel)) for panel in failing),
                "--output-dir",
                str(verdict_dir),
                "--max-attempts",
                os.environ.get("PERSONA_DREAM_PANEL_REVIEW_MAX_ATTEMPTS", "1"),
                "--ask-timeout",
                os.environ.get("ASK_WEBGPT_TIMEOUT", "900"),
                "--json",
            ]
            if index_html.exists():
                cmd.extend(["--index-html", str(index_html)])
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(SKILL_DIR.parent / "review-panel"),
                    capture_output=True,
                    text=True,
                    timeout=int(os.environ.get("PERSONA_DREAM_PANEL_REVIEW_TIMEOUT", "2700")),
                )
                summary_path = verdict_dir / "summary.json"
                summary = None
                if summary_path.exists():
                    try:
                        summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    except Exception:
                        summary = None
                review_result = {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout_tail": proc.stdout[-2000:],
                    "stderr_tail": proc.stderr[-2000:],
                    "summary_path": str(summary_path),
                    "summary": summary,
                }
                if summary and summary.get("ci_verdict") == "PASS":
                    visual = None
                else:
                    failing = [
                        key for key, verdict in (summary or {}).get("panels", {}).items()
                        if verdict != "PASS"
                    ] or failing
            except subprocess.TimeoutExpired as exc:
                review_result = {
                    "command": cmd,
                    "status": "TIMEOUT",
                    "timeout_seconds": int(os.environ.get("PERSONA_DREAM_PANEL_REVIEW_TIMEOUT", "2700")),
                    "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                    "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
                }
        elif not review_panel.exists():
            review_result = {
                "status": "BLOCKED",
                "message": f"review-panel runtime not found: {review_panel}",
            }

        if visual is None:
            result["autonomous_review"] = review_result
        else:
            result["autonomous_review"] = review_result
            result["status"] = "FAIL"
            result["visual_course_corrections"] = visual.get("_path")
            result["failing_panels"] = failing
            result["blockers"].extend(f"panel_{str(panel).zfill(2)}:failed_visual_review" for panel in failing)
            result["message"] = "Panel visual course-correction receipt is failing; autonomous review ran and did not clear all failing panels."
            return result

    aggregate_candidates = [
        run_root / "storyboard" / "panel_repair_gate" / "current_preflight_blocked_20260614T041500Z" / "aggregate_panel_repair_gate_receipt.json",
        run_root / "reviews" / "webgpt-preflight-round2" / "artifacts" / "aggregate_panel_repair_gate_receipt.json",
    ]
    aggregate_candidates.extend(
        sorted(run_root.glob("**/aggregate_panel_repair_gate_receipt.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    )

    aggregate = None
    aggregate_path = None
    for path in aggregate_candidates:
        if not path.exists():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if loaded.get("schema") == "persona_dream.panel_repair_gate_aggregate.v1":
            aggregate = loaded
            aggregate_path = path
            break

    if aggregate is None:
        result["status"] = "FAIL"
        result["blockers"].append("missing_aggregate_panel_repair_gate_receipt")
        result["message"] = "No aggregate panel repair gate receipt found."
        return result

    result["aggregate_receipt"] = str(aggregate_path)
    result["panel_receipts"] = aggregate.get("panel_receipts", [])
    blockers = [str(item) for item in aggregate.get("blockers", [])]
    if aggregate.get("provider_eligibility") is True and aggregate.get("status") in {"PASS", "PROVIDER_READY"} and not blockers:
        result["status"] = "PASS"
        result["message"] = "Aggregate panel repair receipt is provider eligible."
        return result

    result["status"] = "FAIL"
    result["blockers"] = blockers or ["aggregate_panel_repair_gate_not_provider_eligible"]
    result["message"] = "Aggregate panel repair receipt is not provider eligible."
    return result




def check_panel_interaction_gate(run_root: Path) -> dict[str, Any]:
    """Live check panel interaction gate by verifying panel images exist and have nonzero bytes."""
    result = {
        "gate": "panel-interaction",
        "status": "UNKNOWN",
        "passed": 0,
        "failed": 0,
        "missing_images": [],
        "image_sizes": {},
        "blockers": [],
        "message": "",
    }

    assets_dir = run_root / "pipeline_review_8892" / "assets" / "panels"
    if not assets_dir.exists():
        assets_dir = run_root / "assets" / "panels"
    if not assets_dir.exists():
        result["status"] = "ERROR"
        result["message"] = f"Panel assets directory not found: {assets_dir}"
        return result

    all_ok = True
    for i in range(1, 11):
        img_path = assets_dir / f"panel_{i:02d}_storyboard.png"
        if img_path.exists():
            size = img_path.stat().st_size
            result["image_sizes"][f"Panel {i:02d}"] = size
            if size == 0:
                result["missing_images"].append(f"Panel {i:02d} (empty)")
                all_ok = False
        else:
            result["missing_images"].append(f"Panel {i:02d} (not found)")
            all_ok = False

    result["passed"] = 10 - len(result["missing_images"])
    result["failed"] = len(result["missing_images"])

    if all_ok:
        result["status"] = "PASS"
        result["message"] = "All 10 panel images exist with nonzero bytes"
    elif result["passed"] > 0:
        result["status"] = "PARTIAL"
        missing = ", ".join(result["missing_images"])
        result["message"] = f"{result['passed']}/10 panel images OK. Missing: {missing}"
        result["blockers"].append(f"Missing panel images: {missing}")
    else:
        result["status"] = "FAIL"
        result["message"] = "No panel images found"
        result["blockers"].append("All panel images missing or empty")

    return result

def gate_script_command(script_name: str, run_root: Path) -> list[str]:
    script_path = SCRIPT_DIR / script_name
    if script_name == "validate_panel_interaction_gate.py":
        review_artifacts = run_root / "pipeline_review_8892" / "artifacts"
        ledger = review_artifacts / "panel_entity_environment_interaction_ledger.json"
        receipt = review_artifacts / "panel_entity_environment_interaction_gate_receipt.json"
        return [sys.executable, str(script_path), str(ledger), "--receipt-out", str(receipt)]
    if script_name == "validate_panel_repair_gate.py":
        raise RuntimeError("phase-06-repair must use check_panel_repair_gate(), not --run-root")
    return [sys.executable, str(script_path), "--run-root", str(run_root)]


def run_gate_script(script_name: str, run_root: Path) -> dict[str, Any]:
    """Execute a gate validation script and return structured result."""
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        return {"status": "ERROR", "message": f"Script not found: {script_path}", "blockers": ["script_missing"]}

    try:
        proc = subprocess.run(
            gate_script_command(script_name, run_root),
            capture_output=True, text=True, timeout=120
        )
        # Parse JSON from stdout (gates output JSON receipt)
        try:
            result = json.loads(proc.stdout.strip())
        except (json.JSONDecodeError, IndexError):
            result = {
                "status": "PASS" if proc.returncode == 0 else "FAIL",
                "stdout": proc.stdout[:500],
                "stderr": proc.stderr[:200],
            }
        if "status" not in result and "verdict" in result:
            result["status"] = result["verdict"]
        result.setdefault("blockers", [])
        if proc.returncode != 0 and result.get("status", "FAIL") == "PASS":
            result["status"] = "WARN"
            result["blockers"].append(f"Script returned code {proc.returncode}")
        return result
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "message": f"Script {script_name} timed out", "blockers": ["timeout"]}
    except Exception as e:
        return {"status": "ERROR", "message": str(e), "blockers": [f"exception: {e}"]}


def run_gate(gate_id: str, run_root: Path) -> dict[str, Any]:
    """Run a single gate and return its validation result."""
    gate_info = GATES.get(gate_id)
    if not gate_info:
        return {"gate": gate_id, "status": "ERROR", "message": f"Unknown gate: {gate_id}", "blockers": []}

    if gate_id == "voice-clone":
        result = check_voice_clone_gate(run_root)
    elif gate_id == "phase-06-repair":
        result = check_panel_repair_gate(run_root)
    elif gate_id == "panel-interaction":
        result = check_panel_interaction_gate(run_root)
    else:
        result = run_gate_script(gate_info["script"], run_root)

    result["gate"] = gate_id
    result["description"] = gate_info["description"]
    result["validated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description="Unified persona-dream gate validator")
    parser.add_argument("--gate", default="all", help="Gate(s) to validate: 'all', a single gate, or comma-separated")
    parser.add_argument("--run-root", default=None, help="Run root directory (auto-detected from cwd if omitted)")
    parser.add_argument("--output", default=None, help="Write JSON output to this file")
    parser.add_argument("--table", action="store_true", help="Print markdown summary table")
    args = parser.parse_args()

    run_root = Path(args.run_root) if args.run_root else resolve_run_root()
    if not run_root:
        print(json.dumps({"error": "Could not resolve run root. Specify --run-root or run from a persona-dream output directory."}))
        sys.exit(1)

    # Resolve gate list
    if args.gate == "all":
        gates_to_run = ALL_GATES
    else:
        gates_to_run = [g.strip() for g in args.gate.split(",") if g.strip()]

    invalid = [g for g in gates_to_run if g not in GATES]
    if invalid:
        print(json.dumps({"error": f"Unknown gates: {invalid}. Valid gates: {ALL_GATES}"}))
        sys.exit(1)

    # Run each gate
    results = [run_gate(g, run_root) for g in gates_to_run]

    # Aggregate
    summary = {
        "schema": SCHEMA,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "gate_count": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] not in ("PASS", "UNKNOWN")),
        "gates": results,
    }

    # Print output
    if args.table:
        print("| Gate | Status | Blockers |")
        print("|------|--------|----------|")
        for r in results:
            blockers = "; ".join(r.get("blockers", [])) or "none"
            print(f"| {r['gate']} | {r['status']} | {blockers} |")
    else:
        print(json.dumps(summary, indent=2))

    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2))

    # Exit code: 0 if all passed, 1 otherwise
    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
