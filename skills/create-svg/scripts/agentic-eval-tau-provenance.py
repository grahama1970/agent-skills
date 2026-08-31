#!/usr/bin/env python3
"""Agentic eval helper for create-svg Tau provenance gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run.sh"
PNG_BYTES = b"\x89PNG\r\n\x1a\nreal screenshot bytes"


def _sha_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_valid_bundle(work: Path) -> dict[str, Path]:
    run_dir = work / "run"
    svg = work / "winner.svg"
    screenshot = work / "winner.png"
    candidate = work / "candidate.json"
    visual = work / "visual-gate.json"
    launch = work / "launch-receipt.json"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><title>Tau</title></svg>\n', encoding="utf-8")
    screenshot.write_bytes(PNG_BYTES)
    (run_dir / "tau-receipts").mkdir(parents=True)
    (run_dir / "node-artifacts" / "handler-gpt-5-5-high").mkdir(parents=True)
    (run_dir / "node-artifacts" / "judge").mkdir(parents=True)
    (run_dir / "tau-receipts" / "dag-receipt.json").write_text(json.dumps({"schema": "tau.dag_receipt.v1", "ok": True, "status": "PASS"}), encoding="utf-8")
    (run_dir / "node-artifacts" / "handler-gpt-5-5-high" / "node-receipt.json").write_text(json.dumps({"schema": "ask.tau_dag_handler_receipt.v1", "ok": True, "status": "PASS", "node_id": "handler-gpt-5-5-high"}), encoding="utf-8")
    (run_dir / "node-artifacts" / "judge" / "node-receipt.json").write_text(json.dumps({"schema": "ask.tau_dag_handler_receipt.v1", "ok": True, "status": "PASS", "node_id": "judge"}), encoding="utf-8")
    launch.write_text(json.dumps({"kind": "create_svg.tau_variant_loop_plan.v1", "status": "EXECUTED", "run_dir": str(run_dir), "goal": "represent Tau", "target": "project-card", "target_size": "400x260"}), encoding="utf-8")
    candidate.write_text(json.dumps({"schema": "create_svg.variant_candidate.v1", "creator_node_id": "handler-gpt-5-5-high", "tau_run_dir": str(run_dir), "svg_path": str(svg), "svg_sha256": f"sha256:{_sha_hex(svg)}", "mocked": False, "live": True}), encoding="utf-8")
    visual.write_text(json.dumps({"kind": "create_svg.visual_gate.v1", "status": "PASS", "svg_path": str(svg), "svg_sha256": _sha_hex(svg), "screenshot_path": str(screenshot), "screenshot_sha256": _sha_hex(screenshot), "target": "project-card", "target_size": "400x260", "goal": "represent Tau", "represents_goal": True, "attractive": True, "issues": [], "next_edit": "", "proof_scope": "fixture", "does_not_prove": "deployment"}), encoding="utf-8")
    return {"launch": launch, "svg": svg, "candidate": candidate, "visual": visual}


def _invoke_gate(paths: dict[str, Path], receipt: Path) -> subprocess.CompletedProcess[str]:
    return _run([
        str(RUN),
        "tau-provenance-gate",
        str(paths["launch"]),
        str(paths["svg"]),
        "--candidate-receipt",
        str(paths["candidate"]),
        "--visual-gate-receipt",
        str(paths["visual"]),
        "--creator-node-id",
        "handler-gpt-5-5-high",
        "--judge-node-id",
        "judge",
        "--receipt",
        str(receipt),
    ])


def valid_bound_accepted(work: Path, out: Path) -> dict[str, object]:
    paths = _write_valid_bundle(work)
    receipt = work / "provenance.json"
    proc = _invoke_gate(paths, receipt)
    payload = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    ok = proc.returncode == 0 and payload.get("status") == "PASS" and payload.get("failure_code") is None
    return {"case": "valid_bound_accepted", "ok": ok, "status": "PASS" if ok else "FAIL", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "receipt": payload}


def local_preview_rejected(work: Path, out: Path) -> dict[str, object]:
    svg = work / "ledger-first.svg"
    launch = work / "launch-receipt.json"
    receipt = work / "provenance.json"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><title>preview</title></svg>\n', encoding="utf-8")
    launch.write_text(json.dumps({"kind": "create_svg.tau_variant_loop_plan.v1", "status": "NEEDS_ATTENTION", "run_dir": str(work / "missing-run"), "goal": "represent Tau", "target": "project-card", "target_size": "400x260"}), encoding="utf-8")
    proc = _invoke_gate({"launch": launch, "svg": svg, "candidate": work / "missing-candidate.json", "visual": work / "missing-visual.json"}, receipt)
    payload = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    ok = proc.returncode == 1 and payload.get("status") == "BLOCKED" and payload.get("failure_code") == "create_svg_tau_provenance_missing_candidate_receipt"
    return {"case": "local_preview_rejected", "ok": ok, "status": "PASS" if ok else "FAIL", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "receipt": payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("valid-bound-accepted", "local-preview-rejected"), required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    payload = valid_bound_accepted(args.work, args.out) if args.case == "valid-bound-accepted" else local_preview_rejected(args.work, args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
