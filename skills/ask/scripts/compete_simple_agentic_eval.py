#!/usr/bin/env python3
"""Agentic eval for the simple non-browser /ask compete path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ASK_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/ask/outputs/ask-compete-simple-agentic-eval")


POSITIVE_REQUEST = (
    "Each competitor must return: VERIFIED_FEATURE: ask-compete-simple-executed-<handler>. "
    "Then one short EVIDENCE line naming its handler. Do not use markdown tables."
)
POSITIVE_GOAL = (
    "Ask compete executes two isolated non-browser handlers, a separate non-browser judge "
    "names a real winner, and the join emits admitted compete scorecard receipts without "
    "touching browser transport."
)
FAIL_CLOSED_REQUEST = "Return exactly one line: COMPETE_SMOKE: <handler>."
FAIL_CLOSED_GOAL = (
    "Ask compete must dispatch isolated non-browser handlers but hold the join when no "
    "candidate emits explicit VERIFIED_FEATURE evidence and no clear winner exists."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("positive", "missing-verified-features"), required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_case(args.case, args.output_root)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(summary["marker"])
        print(f"status: {summary['status']}")
        print(f"run_dir: {summary.get('run_dir')}")
    return 0 if summary["ok"] else 1


def run_case(case: str, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    ask_id = f"ask-compete-simple-{case}-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    if case == "missing-verified-features":
        return _run_controlled_missing_verified_features(output_root, ask_id)

    if case == "positive":
        cmd = _positive_command(output_root, ask_id)
        expected_returncode = 0

    completed = subprocess.run(
        cmd,
        cwd=ASK_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=600,
    )
    payload = _parse_json_stdout(completed.stdout)
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    run_dir = Path(str(bundle.get("run_dir") or ""))
    receipts = _node_receipts(run_dir)
    scorecard = _read_json(run_dir / "node-artifacts" / "join" / "compete-scorecard.json")

    common_checks = [
        _check("returncode", completed.returncode == expected_returncode, {"actual": completed.returncode, "expected": expected_returncode}),
        _check("json_payload", bool(payload), {}),
        _check("schema", payload.get("schema") == "ask.tau_dag_cli_result.v1", {"schema": payload.get("schema")}),
        _check("mocked_false", payload.get("mocked") is False, {"mocked": payload.get("mocked")}),
        _check("live_true", payload.get("live") is True, {"live": payload.get("live")}),
        _check("browser_skipped", _browser_skipped(payload), {"browser_provider_availability": payload.get("browser_provider_availability"), "browser_tab_lifecycle": payload.get("browser_tab_lifecycle")}),
        _check("execution_reached_tau", execution.get("schema") == "ask.tau_dag_execution.v1", {"schema": execution.get("schema")}),
        _check("run_dir_exists", run_dir.is_dir(), {"run_dir": str(run_dir)}),
        _check("candidate_receipts_present", {"handler-gpt-5-5-low", "handler-claude-fable-low"} <= set(receipts), {"nodes": sorted(receipts)}),
        _check("candidate_receipts_pass", _receipts_pass(receipts, ["handler-gpt-5-5-low", "handler-claude-fable-low"]), {"receipt_statuses": _receipt_statuses(receipts)}),
        _check("candidate_scillm_meta_200", _scillm_meta_200(run_dir, ["handler-gpt-5-5-low", "handler-claude-fable-low"]), {"run_dir": str(run_dir)}),
        _check("scorecard_exists", bool(scorecard), {"path": str(run_dir / "node-artifacts" / "join" / "compete-scorecard.json")}),
    ]
    case_checks = _positive_checks(payload, execution, receipts, scorecard, run_dir) if case == "positive" else _fail_closed_checks(payload, execution, receipts, scorecard)
    checks = common_checks + case_checks
    ok = all(item["ok"] for item in checks)
    marker = "ASK_COMPETE_SIMPLE_POSITIVE_PASS" if case == "positive" else "ASK_COMPETE_SIMPLE_FAIL_CLOSED_PASS"
    summary = {
        "schema": "ask.compete_simple_agentic_eval.v1",
        "case": case,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "marker": marker if ok else marker.replace("_PASS", "_FAIL"),
        "mocked": False,
        "live": True,
        "provider_live": payload.get("provider_live") is True,
        "run_dir": str(run_dir) if run_dir else "",
        "receipt_path": execution.get("receipt_path"),
        "scorecard_path": str(run_dir / "node-artifacts" / "join" / "compete-scorecard.json") if run_dir else "",
        "checks": checks,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    (output_root / f"{ask_id}.summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _run_controlled_missing_verified_features(output_root: Path, ask_id: str) -> dict[str, Any]:
    run_dir = output_root / ask_id
    artifacts = run_dir / "node-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_request.v1",
                "request": FAIL_CLOSED_REQUEST,
                "criteria": ["receipt"],
                "immutable_goal": FAIL_CLOSED_GOAL,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for node_id, handler, response in (
        ("handler-gpt-5-5-low", "gpt-5.5-low", "COMPETE_SMOKE: gpt-5.5-low\n"),
        ("handler-claude-fable-low", "claude-fable-low", "COMPETE_SMOKE: claude-fable-low\n"),
    ):
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        response_path = node_dir / "response.md"
        response_path.write_text(response, encoding="utf-8")
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "PASS",
                    "ok": True,
                    "mocked": False,
                    "live": True,
                    "provider_live": True,
                    "failure": None,
                    "failure_code": None,
                    "response_path": str(response_path),
                    "response_chars": len(response),
                    "submit_meta": {"schema": "controlled.agentic_eval.submit_meta.v1", "status_code": 200},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    join_dir = artifacts / "join"
    goal_hash = "sha256:" + hashlib.sha256(FAIL_CLOSED_GOAL.encode("utf-8")).hexdigest()
    start = {
        "schema": "tau.agent_handoff.v1",
        "github": {"repo": "local/agent-skills", "target": "ask-compete-simple-fail-closed"},
        "goal": {
            "goal_id": "ask-compete-simple-fail-closed",
            "goal_version": 1,
            "immutable_goal": FAIL_CLOSED_GOAL,
            "goal_hash": goal_hash,
        },
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_DIR / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            str(ASK_DIR.parent / "surf" / "run.sh"),
            "--browser-oracle-run",
            str(ASK_DIR.parent / "browser-oracle" / "run.sh"),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=json.dumps(start),
        check=False,
        timeout=120,
    )
    receipts = _node_receipts(run_dir)
    scorecard = _read_json(join_dir / "compete-scorecard.json")
    checks = [
        _check("returncode", completed.returncode == 0, {"actual": completed.returncode, "expected": 0}),
        _check("candidate_receipts_present", {"handler-gpt-5-5-low", "handler-claude-fable-low"} <= set(receipts), {"nodes": sorted(receipts)}),
        _check("candidate_receipts_pass", _receipts_pass(receipts, ["handler-gpt-5-5-low", "handler-claude-fable-low"]), {"receipt_statuses": _receipt_statuses(receipts)}),
        _check("join_receipt_held", receipts.get("join", {}).get("status") == "NEEDS_ATTENTION" and receipts.get("join", {}).get("ok") is False, {"receipt_statuses": _receipt_statuses(receipts)}),
        _check("scorecard_held", scorecard.get("status") == "NEEDS_ATTENTION" and scorecard.get("ok") is False, {"status": scorecard.get("status"), "ok": scorecard.get("ok")}),
        _check("fail_closed_reason_codes", {"no_clear_winner_from_receipts", "no_explicit_verified_features_to_promote"} <= set(scorecard.get("blockers") or []), {"blockers": scorecard.get("blockers")}),
        _check("no_winner_promoted", not scorecard.get("winner_handler") and not scorecard.get("winner_node_id"), {"winner_handler": scorecard.get("winner_handler"), "winner_node_id": scorecard.get("winner_node_id")}),
    ]
    ok = all(item["ok"] for item in checks)
    marker = "ASK_COMPETE_SIMPLE_FAIL_CLOSED_PASS"
    summary = {
        "schema": "ask.compete_simple_agentic_eval.v1",
        "case": "missing-verified-features",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "marker": marker if ok else marker.replace("_PASS", "_FAIL"),
        "mocked": False,
        "live": False,
        "provider_live": False,
        "fixture_backed_handler_receipts": True,
        "run_dir": str(run_dir),
        "scorecard_path": str(join_dir / "compete-scorecard.json"),
        "checks": checks,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    (output_root / f"{ask_id}.summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _positive_command(output_root: Path, ask_id: str) -> list[str]:
    return [
        str(ASK_DIR / "run.sh"),
        "compete",
        POSITIVE_REQUEST,
        "--repo",
        "local/agent-skills",
        "--target",
        "ask-compete-simple-positive",
        "--immutable-goal",
        POSITIVE_GOAL,
        "--handler",
        "gpt-5.5-low",
        "--handler",
        "claude-fable-low",
        "--judge-handler",
        "gpt-5.5-medium",
        "--criterion",
        "receipt",
        "--criterion",
        "explicit-verified-feature",
        "--ask-id",
        ask_id,
        "--run-output-root",
        str(output_root),
        "--execution-timeout-seconds",
        "180",
        "--poll-timeout-seconds",
        "240",
        "--execute",
        "--json",
    ]

def _positive_checks(payload: dict[str, Any], execution: dict[str, Any], receipts: dict[str, dict[str, Any]], scorecard: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    return [
        _check("top_level_pass", payload.get("status") == "PASS" and payload.get("ok") is True, {"status": payload.get("status"), "ok": payload.get("ok")}),
        _check("execution_pass", execution.get("status") == "PASS" and execution.get("ok") is True, {"status": execution.get("status"), "ok": execution.get("ok")}),
        _check("judge_receipt_pass", _receipts_pass(receipts, ["judge"]), {"receipt_statuses": _receipt_statuses(receipts)}),
        _check("judge_scillm_meta_200", _scillm_meta_200(run_dir, ["judge"]), {"run_dir": str(run_dir)}),
        _check("join_receipt_pass", _receipts_pass(receipts, ["join"]), {"receipt_statuses": _receipt_statuses(receipts)}),
        _check("scorecard_pass", scorecard.get("status") == "PASS" and scorecard.get("ok") is True, {"status": scorecard.get("status"), "ok": scorecard.get("ok")}),
        _check("winner_from_judge", scorecard.get("winner_selected_by") == "judge_verdict" and bool(scorecard.get("winner_node_id")), {"winner_selected_by": scorecard.get("winner_selected_by"), "winner_node_id": scorecard.get("winner_node_id")}),
        _check("no_blockers", scorecard.get("blockers") == [], {"blockers": scorecard.get("blockers")}),
        _check("verified_features_promoted", set(scorecard.get("verified_features") or []) >= {"ask-compete-simple-executed-gpt-5.5-low", "ask-compete-simple-executed-claude-fable-low"}, {"verified_features": scorecard.get("verified_features")}),
    ]

def _browser_skipped(payload: dict[str, Any]) -> bool:
    availability = payload.get("browser_provider_availability") if isinstance(payload.get("browser_provider_availability"), dict) else {}
    lifecycle = payload.get("browser_tab_lifecycle") if isinstance(payload.get("browser_tab_lifecycle"), dict) else {}
    return availability.get("status") == "skipped" and availability.get("reason") == "no_browser_handlers" and lifecycle.get("status") == "skipped"


def _receipts_pass(receipts: dict[str, dict[str, Any]], node_ids: list[str]) -> bool:
    return all(receipts.get(node_id, {}).get("status") == "PASS" and receipts.get(node_id, {}).get("ok") is True for node_id in node_ids)


def _receipt_statuses(receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {node_id: {"status": receipt.get("status"), "ok": receipt.get("ok"), "handler": receipt.get("handler"), "provider_live": receipt.get("provider_live")} for node_id, receipt in sorted(receipts.items())}


def _scillm_meta_200(run_dir: Path, node_ids: list[str]) -> bool:
    for node_id in node_ids:
        meta = _read_json(run_dir / "node-artifacts" / node_id / "response.meta.json")
        if meta.get("schema") != "ask.tau_dag_scillm_submit_meta.v1" or meta.get("status_code") != 200:
            return False
    return True


def _node_receipts(run_dir: Path) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in sorted((run_dir / "node-artifacts").glob("*/node-receipt.json")):
        receipt = _read_json(path)
        node_id = str(receipt.get("node_id") or path.parent.name)
        receipts[node_id] = receipt
    return receipts


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_json_stdout(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else {}
    return {}


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


if __name__ == "__main__":
    raise SystemExit(main())
