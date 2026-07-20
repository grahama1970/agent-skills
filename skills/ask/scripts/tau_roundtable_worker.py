#!/usr/bin/env python3
"""Tau worker for live $ask roundtable browser handler nodes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HANDLER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
}
HANDLER_SUBMIT_COMMANDS = {
    "webgpt": "webgpt.submit",
    "webclaude": "claude.submit",
    "webkimi": "kimi.submit",
    "webgemini": "gemini.submit",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--handler", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--browser-oracle-project", default="")
    parser.add_argument("--next-agent", default="human")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--surf-run", required=True)
    parser.add_argument("--browser-oracle-run", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()

    start = _read_stdin_handoff()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if args.node_id == "join":
        result = _run_join(args, start, artifact_dir)
    else:
        result = _run_handler(args, start, artifact_dir)
    print(json.dumps(result["handoff"], sort_keys=True))
    return int(result["exit_code"])


def _run_handler(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    request_payload = _read_json(Path(args.request_file))
    request_text = str(request_payload.get("request") or "")
    handler = args.handler
    response_path = artifact_dir / "response.md"
    raw_path = artifact_dir / "response.raw.md"
    meta_path = artifact_dir / "response.meta.json"
    prompt_path = artifact_dir / "prompt.md"
    receipt_path = artifact_dir / "node-receipt.json"
    commands: list[dict[str, Any]] = []
    prompt_path.write_text(_handler_prompt(request_text, handler), encoding="utf-8")

    status = "ERROR"
    ok = False
    provider_live = False
    response_text = ""
    resolve_payload: dict[str, Any] = {}
    submit_meta: dict[str, Any] = {}
    failure = ""
    started = _now()
    try:
        project = args.browser_oracle_project or handler
        resolve = _run_cmd(
            [
                str(args.browser_oracle_run),
                "resolve",
                "--backend",
                HANDLER_BACKENDS[handler],
                "--project",
                project,
                "--json",
            ],
            cwd=Path(args.browser_oracle_run).parent,
            timeout=60,
        )
        commands.append(resolve.summary())
        if resolve.returncode != 0:
            raise RuntimeError(resolve.stderr or resolve.stdout)
        resolve_payload = _parse_json_object(resolve.stdout)
        tab_id = str(resolve_payload.get("tab_id") or "")
        url = str(resolve_payload.get("conversation_url") or "")
        if not tab_id:
            raise RuntimeError(f"browser-oracle project {project!r} resolved without tab_id")

        submit_cmd = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[handler],
            "--input",
            str(prompt_path),
            "--output",
            str(response_path),
            "--raw-output",
            str(raw_path),
            "--meta-output",
            str(meta_path),
            "--tab-id",
            tab_id,
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
        ]
        if url:
            if handler == "webgpt":
                submit_cmd.extend(["--expect-url", url])
            else:
                submit_cmd.extend(["--url", url])
        if args.no_activate:
            submit_cmd.append("--no-activate")
        submit = _run_cmd(submit_cmd, cwd=Path(args.surf_run).parent, timeout=max(args.timeout + 90, 180))
        commands.append(submit.summary())
        if meta_path.is_file():
            submit_meta = _read_json(meta_path)
        if submit.returncode != 0:
            raise RuntimeError(submit.stderr or submit.stdout or f"{HANDLER_SUBMIT_COMMANDS[handler]} failed")
        response_text = response_path.read_text(encoding="utf-8")
        ok = bool(response_text.strip())
        status = "PASS" if ok else "ERROR"
        provider_live = ok
    except Exception as exc:
        failure = str(exc)
        status = "ERROR"
        ok = False
        provider_live = False
        if response_path.is_file():
            response_text = response_path.read_text(encoding="utf-8")

    receipt = {
        "schema": "ask.tau_dag_handler_receipt.v1",
        "created_at": _now(),
        "started_at": started,
        "node_id": args.node_id,
        "handler": handler,
        "topology": args.topology,
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": bool(commands),
        "provider_live": provider_live,
        "response_path": str(response_path),
        "raw_response_path": str(raw_path),
        "meta_path": str(meta_path),
        "prompt_path": str(prompt_path),
        "response_chars": len(response_text),
        "browser_oracle": resolve_payload,
        "submit_meta": submit_meta,
        "commands": commands,
        "failure": failure or None,
        "provider_receipt": {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": status,
            "ok": ok,
            "mocked": False,
            "live": bool(commands),
            "provider_live": provider_live,
            "route": "tau_roundtable_handler_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$surf",
            "handler": handler,
            "transport": HANDLER_SUBMIT_COMMANDS[handler],
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    handoff = _handoff(
        args,
        start,
        status=status,
        summary=f"{args.node_id} {status.lower()} via {HANDLER_SUBMIT_COMMANDS.get(handler, handler)}.",
        artifacts=[receipt_path, prompt_path, response_path, raw_path, meta_path],
        evidence=[
            {
                "kind": "handler_response_receipt",
                "node_id": args.node_id,
                "handler": handler,
                "path": str(receipt_path),
                "status": status,
            },
            {
                "kind": "normalized_handler_receipt",
                "node_id": args.node_id,
                "handler": handler,
                "response_path": str(response_path),
                "response_chars": len(response_text),
            },
            {
                "kind": "transport_metadata",
                "node_id": args.node_id,
                "handler": handler,
                "meta_path": str(meta_path),
            },
        ],
    )
    return {"exit_code": 0 if ok else 1, "handoff": handoff}


def _run_join(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    receipt_path = artifact_dir / "node-receipt.json"
    summary_path = artifact_dir / "roundtable-summary.md"
    node_artifacts_root = artifact_dir.parent
    handler_receipts = []
    failures = []
    for path in sorted(node_artifacts_root.glob("handler-*/node-receipt.json")):
        receipt = _read_json(path)
        if receipt.get("schema") != "ask.tau_dag_handler_receipt.v1":
            continue
        handler_receipts.append({"path": str(path), **receipt})
        if receipt.get("ok") is not True:
            failures.append(f"{receipt.get('node_id')}: {receipt.get('failure') or receipt.get('status')}")
    lines = [
        "# Tau Roundtable Join",
        "",
        f"- topology: `{args.topology}`",
        f"- handlers: `{len(handler_receipts)}`",
        "",
    ]
    for receipt in handler_receipts:
        lines.extend(
            [
                f"## {receipt.get('handler')}",
                "",
                f"- status: `{receipt.get('status')}`",
                f"- response: `{receipt.get('response_path')}`",
                "",
            ]
        )
        response_path = Path(str(receipt.get("response_path") or ""))
        if response_path.is_file():
            text = response_path.read_text(encoding="utf-8").strip()
            lines.append(text[:2000])
            lines.append("")
    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    ok = bool(handler_receipts) and not failures
    status = "PASS" if ok else "BLOCKED"
    receipt = {
        "schema": "ask.tau_dag_roundtable_join_receipt.v1",
        "created_at": _now(),
        "node_id": args.node_id,
        "handler": args.handler,
        "topology": args.topology,
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": any(item.get("live") is True for item in handler_receipts),
        "provider_live": ok and all(item.get("provider_live") is True for item in handler_receipts),
        "handler_response_index": handler_receipts,
        "summary_path": str(summary_path),
        "unresolved_gaps": failures,
        "provider_receipt": {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": status,
            "ok": ok,
            "mocked": False,
            "live": any(item.get("live") is True for item in handler_receipts),
            "provider_live": ok and all(item.get("provider_live") is True for item in handler_receipts),
            "route": "tau_roundtable_join_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$surf",
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    handoff = _handoff(
        args,
        start,
        status=status,
        summary=f"Roundtable join {status.lower()} over {len(handler_receipts)} handler receipts.",
        artifacts=[receipt_path, summary_path],
        evidence=[
            {"kind": "roundtable_join_receipt", "path": str(receipt_path), "status": status},
            {"kind": "handler_response_index", "count": len(handler_receipts), "failures": failures},
            {"kind": "unresolved_gaps", "items": failures},
        ],
    )
    return {"exit_code": 0 if ok else 1, "handoff": handoff}


def _handler_prompt(request_text: str, handler: str) -> str:
    return "\n".join(
        [
            "You are one participant in a Tau-managed roundtable.",
            f"Handler: {handler}",
            "",
            "Request:",
            request_text,
            "",
            "Return a concise position with these Markdown headings:",
            "## Position",
            "## Evidence",
            "## Uncertainties",
            "## Blockers",
        ]
    )


def _handoff(
    args: argparse.Namespace,
    start: dict[str, Any],
    *,
    status: str,
    summary: str,
    artifacts: list[Path],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": start.get("github", {"repo": "unknown", "target": "unknown"}),
        "goal": start.get("goal", {}),
        "previous_subagent": args.node_id,
        "context": {
            "summary": summary,
            "artifacts": [str(path) for path in artifacts if path.exists()],
        },
        "result": {
            "status": status,
            "summary": summary,
            "evidence": evidence,
        },
        "rationale": "The node emitted receipt-backed Tau roundtable evidence.",
        "next_agent": {
            "name": args.next_agent,
            "executor": "human" if args.next_agent == "human" else "local",
            "reason": "Return node evidence to the Tau scheduler.",
        },
        "required_evidence": list(args.evidence),
        "stop_condition": "Stop after emitting a single tau.agent_handoff.v1 response.",
    }


class CmdResult:
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str, duration: float) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

    def summary(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration, 3),
            "stdout_excerpt": self.stdout.strip()[:1000],
            "stderr_excerpt": self.stderr.strip()[:1000],
        }


def _run_cmd(command: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    started = time.time()
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return CmdResult(command, proc.returncode, proc.stdout, proc.stderr, time.time() - started)


def _read_stdin_handoff() -> dict[str, Any]:
    text = sys.stdin.read()
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root is not an object: {path}")
    return payload


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    start = stripped.find("{")
    if start > 0:
        stripped = stripped[start:]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise RuntimeError("JSON root is not an object")
    return payload


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
