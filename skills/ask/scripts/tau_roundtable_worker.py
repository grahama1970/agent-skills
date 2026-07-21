#!/usr/bin/env python3
"""Tau worker for live $ask roundtable browser handler nodes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
    parser.add_argument("--scillm-base-url", default="http://127.0.0.1:4001")
    parser.add_argument("--scillm-api-key", default="")
    parser.add_argument("--prior-node", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--codex-workspace", default="")
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
    prior_receipts = _load_prior_receipts(artifact_dir.parent, args.prior_node)
    prompt_path.write_text(
        _handler_prompt(
            request_text,
            handler,
            prior_receipts=prior_receipts,
            requires_verdict=_requires_verdict(request_text, prior_receipts),
        ),
        encoding="utf-8",
    )

    status = "ERROR"
    ok = False
    provider_live = False
    response_text = ""
    resolve_payload: dict[str, Any] = {}
    submit_meta: dict[str, Any] = {}
    failure = ""
    started = _now()
    try:
        prior_failures = [
            f"{item.get('node_id')}: {item.get('failure') or item.get('status')}"
            for item in prior_receipts
            if item.get("ok") is not True
        ]
        if prior_failures:
            raise RuntimeError("prior_handler_receipts_not_ready: " + "; ".join(prior_failures))
        if handler == "codex":
            response_text, submit_meta, codex_commands = _run_codex_handler(
                args,
                prompt_path=prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
            )
            commands.extend(codex_commands)
        elif handler in HANDLER_SUBMIT_COMMANDS:
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
            for prior in prior_receipts:
                prior_response = str(prior.get("response_path") or "")
                if prior_response and Path(prior_response).is_file():
                    submit_cmd.extend(["--attach-file", prior_response])
            if args.no_activate:
                submit_cmd.append("--no-activate")
            submit = _run_cmd(submit_cmd, cwd=Path(args.surf_run).parent, timeout=max(args.timeout + 90, 180))
            commands.append(submit.summary())
            if meta_path.is_file():
                submit_meta = _read_json(meta_path)
            if submit.returncode != 0:
                raise RuntimeError(submit.stderr or submit.stdout or f"{HANDLER_SUBMIT_COMMANDS[handler]} failed")
            response_text = response_path.read_text(encoding="utf-8")
        else:
            response_text, submit_meta = _run_scillm_handler(
                args,
                handler=handler,
                prompt_path=prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
            )
            commands.append(
                {
                    "command": ["scillm.chat", handler],
                    "returncode": 0,
                    "duration_seconds": submit_meta.get("duration_seconds"),
                    "stdout_excerpt": response_text[:1000],
                    "stderr_excerpt": "",
                }
            )
        ok = bool(response_text.strip())
        if ok and _requires_verdict(request_text, prior_receipts):
            ok = _has_verdict(response_text)
            if not ok:
                failure = "review_verdict_missing: expected PASS, FAIL, or NEEDS_ATTENTION"
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
        "prior_nodes": list(args.prior_node),
        "prior_handler_receipts": prior_receipts,
        "requires_verdict": _requires_verdict(request_text, prior_receipts),
        "verdict": _extract_verdict(response_text),
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
            "transport": HANDLER_SUBMIT_COMMANDS.get(handler, f"{handler}.local"),
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
            # Downstream nodes declare prior_handler_receipts as required
            # evidence; the handoff must name it or Tau's evidence gate
            # blocks the DAG even though the node itself passed.
            *(
                [
                    {
                        "kind": "prior_handler_receipts",
                        "node_id": args.node_id,
                        "prior_nodes": [
                            {
                                "node_id": item.get("node_id"),
                                "status": item.get("status"),
                                "path": item.get("path"),
                            }
                            for item in prior_receipts
                        ],
                    }
                ]
                if prior_receipts
                else []
            ),
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


def _handler_prompt(
    request_text: str,
    handler: str,
    *,
    prior_receipts: list[dict[str, Any]] | None = None,
    requires_verdict: bool = False,
) -> str:
    prior_receipts = prior_receipts or []
    lines = [
        "You are one participant in a Tau-managed roundtable.",
        f"Handler: {handler}",
        "",
        "Request:",
        request_text,
        "",
    ]
    if prior_receipts:
        lines.extend(["Prior handler receipts to use as input:", ""])
        for receipt in prior_receipts:
            lines.extend(
                [
                    # No local filesystem paths in a browser-bound prompt: surf's
                    # prompt preflight fails closed on them (the browser model
                    # cannot read local files). The path stays in the node receipt.
                    f"### {receipt.get('node_id')} / {receipt.get('handler')}",
                    f"- status: {receipt.get('status')}",
                    "",
                    # Inline only the summary portion. Raw git diffs contain
                    # tokens (Rust // comments, /paths) that trip the browser
                    # transport's local-path preflight; the full response is
                    # provided to browser handlers as a file attachment.
                    _excerpt_before_diff(str(receipt.get("response_excerpt") or "")),
                    "",
                ]
            )
    if requires_verdict:
        lines.extend(
            [
                "Return a review verdict using exactly one of:",
                "VERDICT: PASS",
                "VERDICT: FAIL",
                "VERDICT: NEEDS_ATTENTION",
                "",
            ]
        )
    lines.extend(
        [
            "Return a concise position with these Markdown headings:",
            "## Position",
            "## Evidence",
            "## Uncertainties",
            "## Blockers",
        ]
    )
    return "\n".join(lines)


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


def _run_codex_handler(
    args: argparse.Namespace,
    *,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Run the local codex coder inside its bound workspace.

    The node response is codex's final message PLUS the workspace's actual
    `git diff` so the downstream reviewer judges the real change. A run that
    produces no diff is a node failure, not a soft pass.
    """
    workspace = Path(args.codex_workspace).expanduser()
    if not workspace.is_dir() or not (workspace / ".git").exists():
        raise RuntimeError(f"codex workspace is not a git worktree: {workspace}")
    commands: list[dict[str, Any]] = []
    final_message_path = raw_path
    codex_cmd = [
        "codex",
        "exec",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        "features.hooks=false",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        # codex's bwrap sandbox cannot initialize in this environment
        # (RTM_NEWADDR loopback failure; workspace-write rejects all writes,
        # verified by direct probe 2026-07-21). Containment comes from the
        # isolated git worktree, the diff-only review, and the downstream
        # gates -- not from codex's own sandbox.
        "--sandbox",
        "danger-full-access",
        "--cd",
        str(workspace),
        "-o",
        str(final_message_path),
        "-",
    ]
    prompt_text = prompt_path.read_text(encoding="utf-8")
    started = time.monotonic()
    proc = subprocess.run(
        codex_cmd,
        input=prompt_text,
        capture_output=True,
        text=True,
        timeout=args.timeout,
        cwd=str(workspace),
    )
    duration = time.monotonic() - started
    commands.append(
        {
            "command": codex_cmd[:12] + ["..."],
            "returncode": proc.returncode,
            "duration_seconds": round(duration, 3),
            "stdout_excerpt": (proc.stdout or "")[-1500:],
            "stderr_excerpt": (proc.stderr or "")[-800:],
        }
    )
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed rc={proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}")
    diff = subprocess.run(
        ["git", "-C", str(workspace), "diff"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    status_out = subprocess.run(
        ["git", "-C", str(workspace), "status", "--short"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    commands.append(
        {
            "command": ["git", "-C", str(workspace), "diff"],
            "returncode": diff.returncode,
            "duration_seconds": 0,
            "stdout_excerpt": (diff.stdout or "")[:400],
            "stderr_excerpt": (diff.stderr or "")[:200],
        }
    )
    if not (diff.stdout or "").strip() and not (status_out.stdout or "").strip():
        raise RuntimeError("codex_no_workspace_change: coder ran but produced no diff")
    final_message = ""
    if final_message_path.is_file():
        final_message = final_message_path.read_text(encoding="utf-8")
    response = "\n".join(
        [
            "## Coder summary",
            final_message.strip() or "(codex produced no final message)",
            "",
            "## Workspace status",
            "```",
            (status_out.stdout or "").strip(),
            "```",
            "",
            "## Workspace diff (git diff)",
            "```diff",
            (diff.stdout or "").strip()[:60000],
            "```",
            "",
        ]
    )
    response_path.write_text(response, encoding="utf-8")
    meta = {
        "schema": "ask.codex_handler_meta.v1",
        "workspace": str(workspace),
        "codex_returncode": proc.returncode,
        "duration_seconds": round(duration, 3),
        "diff_bytes": len(diff.stdout or ""),
        "finished_at": _now(),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return response, meta, commands


def _run_scillm_handler(
    args: argparse.Namespace,
    *,
    handler: str,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
) -> tuple[str, dict[str, Any]]:
    prompt = prompt_path.read_text(encoding="utf-8")
    base_url = str(args.scillm_base_url).rstrip("/")
    payload = {
        "model": handler,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {args.scillm_api_key}",
            "Content-Type": "application/json",
            "X-Caller-Skill": "ask-tau-roundtable",
        },
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"scillm.chat failed HTTP {exc.code}: {raw[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"scillm.chat failed: {exc}") from exc
    raw_path.write_text(raw, encoding="utf-8")
    payload = _parse_json_object(raw)
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        text = "\n".join(str(item.get("text") or item) for item in content)
    else:
        text = str(content or "")
    response_path.write_text(text, encoding="utf-8")
    meta = {
        "schema": "ask.tau_dag_scillm_submit_meta.v1",
        "status_code": status_code,
        "model": handler,
        "duration_seconds": round(time.time() - started, 3),
        "usage": payload.get("usage"),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return text, meta


def _excerpt_before_diff(text: str) -> str:
    """Summary portion of a response: everything before a workspace diff block."""
    for marker in ("## Workspace status", "## Workspace diff", "```diff"):
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].strip() + "\n\n(full response including the git diff is attached as a file)"
    return text.strip()


def _load_prior_receipts(node_artifacts_root: Path, prior_nodes: list[str]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for node_id in prior_nodes:
        path = node_artifacts_root / node_id / "node-receipt.json"
        if not path.is_file():
            receipts.append(
                {
                    "node_id": node_id,
                    "status": "MISSING",
                    "ok": False,
                    "failure": f"missing prior receipt: {path}",
                    "path": str(path),
                }
            )
            continue
        receipt = _read_json(path)
        response_path = Path(str(receipt.get("response_path") or ""))
        response_excerpt = ""
        if response_path.is_file():
            response_excerpt = response_path.read_text(encoding="utf-8").strip()[:4000]
        receipts.append({"path": str(path), "response_excerpt": response_excerpt, **receipt})
    return receipts


def _requires_verdict(request_text: str, prior_receipts: list[dict[str, Any]]) -> bool:
    if not prior_receipts:
        return False
    lower = request_text.lower()
    return any(
        marker in lower
        for marker in (
            "pass/fail",
            "pass or fail",
            "pass fail",
            "pass-fail",
            "review for pass",
            "review it for pass",
            "review the work for pass",
        )
    )


def _extract_verdict(text: str) -> str | None:
    upper = text.upper()
    for verdict in ("NEEDS_ATTENTION", "PASS", "FAIL"):
        if f"VERDICT: {verdict}" in upper or f"VERDICT {verdict}" in upper:
            return verdict
    return None


def _has_verdict(text: str) -> bool:
    return _extract_verdict(text) is not None


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
