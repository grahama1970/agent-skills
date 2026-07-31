#!/usr/bin/env python3
"""Opt-in sanity evals for /ask Tau roundtable browser handlers."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ASK_DIR = Path(__file__).resolve().parents[1]
BROWSER_ORACLE_RUN = ASK_DIR.parent / "browser-oracle" / "run.sh"
SCHEMA = "ask.tau_roundtable_sanity_eval.v1"
HANDLERS = ("webclaude", "webkimi", "webgemini", "webgpt")
DEFAULT_WEBGPT_PROJECT = "tau"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--webgpt-project", default=DEFAULT_WEBGPT_PROJECT)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root or Path(tempfile.mkdtemp(prefix="ask-tau-roundtable-eval-"))
    output_root.mkdir(parents=True, exist_ok=True)
    if args.plan_only:
        summary = build_plan(output_root=output_root, webgpt_project=args.webgpt_project)
    else:
        summary = run_eval(
            output_root=output_root,
            allow_live=args.allow_live,
            webgpt_project=args.webgpt_project,
            timeout_seconds=args.timeout_seconds,
        )
    report_path = output_root / "tau-roundtable-sanity-result.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["report_path"] = str(report_path)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"status: {summary['status']}")
        print(f"mocked: {summary['mocked']}")
        print(f"live: {summary['live']}")
        print(f"provider_live: {summary['provider_live']}")
        print(f"output_root: {summary['output_root']}")
        print(f"report_path: {report_path}")
        for case in summary["cases"]:
            print(f"{case['id']}: {case['status']}")
    return 0 if args.plan_only or summary["ok"] else 1


def build_plan(*, output_root: Path, webgpt_project: str) -> dict[str, Any]:
    cases = [
        _planned_case("browser_oracle_bindings", "Resolve configured browser-oracle projects for webclaude, webkimi, webgemini, and webgpt."),
        _planned_case("compile_concurrent_all_handlers", "Compile a concurrent Tau roundtable DAG for all four handlers."),
        _planned_case("compile_sequential_all_handlers", "Compile a sequential Tau roundtable DAG for all four handlers."),
        _planned_case("live_two_handler_smoke", "Execute a live Tau roundtable over webkimi and webgemini."),
        _planned_case("live_four_handler_sequential", "Execute a live Tau roundtable over webclaude, webkimi, webgemini, webgpt, then join."),
    ]
    return {
        "schema": SCHEMA,
        "status": "PLANNED",
        "ok": False,
        "mocked": False,
        "live": False,
        "provider_live": False,
        "created_at": _now(),
        "output_root": str(output_root),
        "webgpt_project": webgpt_project,
        "cases": cases,
        "what_was_exercised": [],
        "what_remains_unverified": ["plan-only: no Tau or browser handler command was executed"],
    }


def run_eval(
    *,
    output_root: Path,
    allow_live: bool,
    webgpt_project: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    cases = [
        _case_browser_oracle_bindings(webgpt_project),
        _case_compile_roundtable(output_root, topology="concurrent", webgpt_project=webgpt_project),
        _case_compile_roundtable(output_root, topology="sequential", webgpt_project=webgpt_project),
    ]
    if allow_live:
        cases.append(
            _case_live_roundtable(
                output_root,
                case_id="live-two-handler-smoke",
                prompt="Roundtable webkimi and webgemini sequentially. Each handler should identify itself and one browser orchestration risk.",
                handlers=["webkimi", "webgemini"],
                webgpt_project=webgpt_project,
                timeout_seconds=min(timeout_seconds, 900),
            )
        )
        cases.append(
            _case_live_roundtable(
                output_root,
                case_id="live-four-handler-sequential",
                prompt="Roundtable webclaude, webkimi, webgemini, and webgpt sequentially. Each handler should identify itself and one browser orchestration risk.",
                handlers=list(HANDLERS),
                webgpt_project=webgpt_project,
                timeout_seconds=timeout_seconds,
            )
        )
    else:
        cases.append(_not_run_case("live-two-handler-smoke", "live checks require --allow-live"))
        cases.append(_not_run_case("live-four-handler-sequential", "live checks require --allow-live"))

    ok = all(case["ok"] for case in cases)
    provider_live = any(case.get("provider_live") is True for case in cases)
    return {
        "schema": SCHEMA,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": provider_live,
        "created_at": _now(),
        "output_root": str(output_root),
        "webgpt_project": webgpt_project,
        "cases": cases,
        "what_was_exercised": [
            "browser-oracle resolve for webclaude, webkimi, webgemini, and webgpt",
            "/ask run.sh tau-dag concurrent roundtable compile path",
            "/ask run.sh tau-dag sequential roundtable compile path",
            "real Tau CLI dag-run plus Surf browser submits" if allow_live else "live Tau browser submits were intentionally not run",
        ],
        "what_remains_unverified": _remaining_unverified(allow_live=allow_live, provider_live=provider_live),
    }


def _case_browser_oracle_bindings(webgpt_project: str) -> dict[str, Any]:
    checks = []
    commands = []
    for handler in HANDLERS:
        project = webgpt_project if handler == "webgpt" else handler
        cmd = [
            str(BROWSER_ORACLE_RUN),
            "resolve",
            "--backend",
            handler,
            "--project",
            project,
            "--json",
        ]
        completed = subprocess.run(cmd, cwd=BROWSER_ORACLE_RUN.parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60)
        payload = _json_or_error(completed.stdout)
        commands.append(_command_summary(cmd, completed))
        checks.append(
            _check(
                f"{handler}_binding",
                completed.returncode == 0 and payload.get("status") == "ok" and bool(payload.get("tab_id")),
                {"project": project, "tab_id": payload.get("tab_id"), "url": payload.get("conversation_url"), "returncode": completed.returncode},
            )
        )
    return _case("browser-oracle-bindings", checks, commands=commands)


def _case_compile_roundtable(output_root: Path, *, topology: str, webgpt_project: str) -> dict[str, Any]:
    prompt = f"Roundtable webclaude, webkimi, webgemini, and webgpt {topology}, then join the answers."
    run_root = output_root / f"compile-{topology}"
    cmd = [
        str(ASK_DIR / "run.sh"),
        "tau-dag",
        prompt,
        "--repo",
        "local/agent-skills",
        "--target",
        f"roundtable-{topology}",
        "--topology",
        topology,
        "--handler-project",
        f"webgpt={webgpt_project}",
        "--run-output-root",
        str(run_root),
        "--json",
    ]
    completed = subprocess.run(cmd, cwd=ASK_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120)
    payload = _json_or_error(completed.stdout)
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    dag = bundle.get("dag") if isinstance(bundle.get("dag"), dict) else {}
    node_ids = [node.get("id") for node in dag.get("nodes", []) if isinstance(node, dict)]
    command_spec_root = Path(str(bundle.get("command_spec_root") or ""))
    checks = [
        _check("returncode", completed.returncode == 0, {"returncode": completed.returncode}),
        _check("status_ready", bundle.get("status") == "READY", {"status": bundle.get("status")}),
        _check("handler_neutral", dag.get("context", {}).get("transport_adapter") == "handler_neutral_adapter", {"context": dag.get("context")}),
        _check("provider_not_required", dag.get("provider_sensitive") is False and dag.get("requires_provider_route") is False, {}),
        _check("all_handlers_present", set(node_ids) >= {f"handler-{handler}" for handler in HANDLERS} | {"join"}, {"node_ids": node_ids}),
        _check("entry_is_first_handler", dag.get("entry_node") == "handler-webclaude", {"entry_node": dag.get("entry_node")}),
        _check("no_empty_join_command_args", _join_command_has_no_empty_args(command_spec_root), {"command_spec_root": str(command_spec_root)}),
    ]
    if topology == "concurrent":
        checks.append(_check("concurrent_edges_to_join", _has_all_join_edges(dag), {"edges": dag.get("edges")}))
    else:
        checks.append(_check("sequential_edges_chain", _has_sequential_chain(dag), {"edges": dag.get("edges")}))
    return _case(f"compile-{topology}-all-handlers", checks, commands=[_command_summary(cmd, completed)], payload_paths=_payload_paths(bundle))


def _case_live_roundtable(
    output_root: Path,
    *,
    case_id: str,
    prompt: str,
    handlers: list[str],
    webgpt_project: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    run_root = output_root / case_id
    cmd = [
        str(ASK_DIR / "run.sh"),
        "tau-dag",
        prompt,
        "--repo",
        "local/agent-skills",
        "--target",
        case_id,
        "--topology",
        "sequential",
        "--handler-project",
        f"webgpt={webgpt_project}",
        "--run-output-root",
        str(run_root),
        "--execute",
        "--poll-timeout-seconds",
        str(timeout_seconds),
        "--poll-interval-seconds",
        "2",
        "--json",
    ]
    completed = subprocess.run(cmd, cwd=ASK_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout_seconds + 120)
    payload = _json_or_error(completed.stdout)
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    run_dir = Path(str(bundle.get("run_dir") or ""))
    node_receipts = _node_receipts(run_dir)
    expected_nodes = {f"handler-{handler}" for handler in handlers} | {"join"}
    checks = [
        _check("returncode", completed.returncode == 0, {"returncode": completed.returncode}),
        _check("execution_pass", execution.get("status") == "PASS" and execution.get("ok") is True, {"status": execution.get("status"), "ok": execution.get("ok")}),
        _check("tau_receipt_exists", Path(str(execution.get("receipt_path") or "")).is_file(), {"receipt_path": execution.get("receipt_path")}),
        _check("all_node_receipts_present", set(node_receipts) >= expected_nodes, {"node_receipts": sorted(node_receipts)}),
        _check("all_expected_nodes_pass", all(node_receipts.get(node, {}).get("ok") is True for node in expected_nodes), {"statuses": _receipt_statuses(node_receipts)}),
        _check("all_handlers_provider_live", all(node_receipts.get(f"handler-{handler}", {}).get("provider_live") is True for handler in handlers), {"statuses": _receipt_statuses(node_receipts)}),
        _check("join_summary_exists", (run_dir / "node-artifacts" / "join" / "roundtable-summary.md").is_file(), {"run_dir": str(run_dir)}),
    ]
    return _case(
        case_id,
        checks,
        provider_live=execution.get("provider_live") is True,
        commands=[_command_summary(cmd, completed)],
        payload_paths=_payload_paths(bundle, execution),
    )


def _planned_case(case_id: str, detail: str) -> dict[str, Any]:
    return {"id": case_id, "status": "PLANNED", "ok": False, "mocked": False, "live": False, "provider_live": False, "detail": detail, "checks": []}


def _not_run_case(case_id: str, reason: str) -> dict[str, Any]:
    return {"id": case_id, "status": "NOT_RUN", "ok": True, "mocked": False, "live": False, "provider_live": False, "reason": reason, "checks": []}


def _case(case_id: str, checks: list[dict[str, Any]], *, provider_live: bool = False, commands: list[dict[str, Any]] | None = None, payload_paths: dict[str, str | None] | None = None) -> dict[str, Any]:
    ok = all(check["ok"] for check in checks)
    return {
        "id": case_id,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": provider_live,
        "checks": checks,
        "commands": commands or [],
        "payload_paths": payload_paths or {},
    }


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "evidence": evidence}


def _join_command_has_no_empty_args(command_spec_root: Path) -> bool:
    spec = _read_json(command_spec_root / "join" / "tau-dispatch-command.json")
    command = spec.get("command")
    return isinstance(command, list) and all(isinstance(item, str) and item for item in command)


def _has_all_join_edges(dag: dict[str, Any]) -> bool:
    edges = dag.get("edges")
    return isinstance(edges, list) and all({"from": f"handler-{handler}", "to": "join"} in edges for handler in HANDLERS)


def _has_sequential_chain(dag: dict[str, Any]) -> bool:
    return dag.get("edges") == [
        {"from": "handler-webclaude", "to": "handler-webkimi"},
        {"from": "handler-webkimi", "to": "handler-webgemini"},
        {"from": "handler-webgemini", "to": "handler-webgpt"},
        {"from": "handler-webgpt", "to": "join"},
        {"from": "join", "to": "human"},
    ]


def _node_receipts(run_dir: Path) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in sorted((run_dir / "node-artifacts").glob("*/node-receipt.json")):
        payload = _read_json(path)
        if payload:
            receipts[path.parent.name] = payload
    return receipts


def _receipt_statuses(receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {key: {"status": value.get("status"), "ok": value.get("ok"), "provider_live": value.get("provider_live")} for key, value in receipts.items()}


def _payload_paths(bundle: dict[str, Any], execution: dict[str, Any] | None = None) -> dict[str, str | None]:
    execution = execution or {}
    return {
        "run_dir": str(bundle.get("run_dir")) if bundle.get("run_dir") else None,
        "dag_path": str(bundle.get("dag_path")) if bundle.get("dag_path") else None,
        "receipt_path": str(execution.get("receipt_path")) if execution.get("receipt_path") else None,
    }


def _command_summary(command: list[str], completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_or_error(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"_json_error": True, "raw_tail": text[-4000:]}
    return payload if isinstance(payload, dict) else {"_json_error": True, "raw_tail": text[-4000:]}


def _remaining_unverified(*, allow_live: bool, provider_live: bool) -> list[str]:
    items = ["Semantic quality of handler prose beyond receipt/schema checks."]
    if not allow_live:
        items.append("Live browser submit behavior because --allow-live was not used.")
    if allow_live and not provider_live:
        items.append("At least one live handler did not produce provider_live receipts.")
    items.append("Concurrent live execution is compile-checked but not run by default to avoid browser focus contention.")
    return items


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
