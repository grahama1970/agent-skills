#!/usr/bin/env python3
"""Local authoring, preflight, and sandbox controls for the Watchdog DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from uuid import uuid4

import watchdog_v2 as wd
from watchdog_graph import (
    GraphError,
    canonical_bytes,
    compile_script,
    promote_graph,
    read_graph,
    revision,
    save_graph,
    validate_graph,
)


RUN_ID = re.compile(r"^[0-9a-f]{32}$")
RUNS_DIR = wd.STATE_ROOT / "workflow-runs"


def output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def run_id_path(run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise GraphError(["invalid run id"])
    return RUNS_DIR / f"{run_id}.json"


def read_run(run_id: str) -> dict[str, Any]:
    path = run_id_path(run_id)
    if not path.is_file():
        raise GraphError(["run not found"])
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("run_id") != run_id:
        raise GraphError(["run receipt id mismatch"])
    return data


def retain_transcripts(run_id: str, pi_result: dict[str, Any]) -> dict[str, Any]:
    retained: dict[str, Any] = {}
    for node_id, result in (pi_result.get("nodes") or {}).items():
        if not isinstance(result, dict):
            continue
        source = next(
            (Path(path) for path in result.get("artifactPaths") or [] if isinstance(path, str) and path.endswith(".jsonl") and Path(path).is_file()),
            None,
        )
        if source is None:
            retained[node_id] = {"available": False, "reason": "session transcript unavailable"}
            continue
        if source.stat().st_size > 16 * 1024 * 1024:
            retained[node_id] = {"available": False, "reason": "session transcript exceeds 16 MiB"}
            continue
        target = RUNS_DIR / run_id / f"{node_id}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        retained[node_id] = {
            "available": True,
            "path": str(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
        }
    return retained


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True, timeout=30)


def sandbox_ticket() -> wd.Ticket:
    root = wd.STATE_ROOT / "sandboxes"
    root.mkdir(parents=True, exist_ok=True)
    repo = Path(tempfile.mkdtemp(prefix="watchdog-", dir=root))
    git("init", "-q", "-b", "main", cwd=repo)
    (repo / "marker.txt").write_text("BROKEN\n", encoding="utf-8")
    git("add", "marker.txt", cwd=repo)
    git("-c", "user.name=Watchdog Sandbox", "-c", "user.email=watchdog@example.invalid", "commit", "-qm", "Initial marker", cwd=repo)
    project = wd.Project(
        project_id="editor-sandbox", repo="example/editor-sandbox", cwd=str(repo),
        ready_label="agent-work", active_label="agent-active", done_label="agent-done",
        target_prefixes=(), target_excludes=(), default_state="active",
        proof_command=("bash", "-lc", 'test "$(cat marker.txt)" = FIXED'),
    )
    return wd.Ticket(
        project=project, number=1, title="Repair marker.txt", url="", labels=(),
        body="Target: marker.txt. Change its only line from BROKEN to FIXED. Do not change any other file. Run a focused read-back.",
    )


def native_validate(graph: dict[str, Any], ticket: wd.Ticket) -> dict[str, Any]:
    script = compile_script(
        graph,
        {
            "key": ticket.key,
            "title": ticket.title,
            "body": ticket.body,
            "proof_command": json.dumps(list(ticket.project.proof_command or ())),
        },
        os.environ.get("PROJECT_WATCHDOG_CHILD_MODEL", "zai/glm-5.3"),
    )
    wd.STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workflow-validate-", dir=wd.STATE_ROOT) as workdir:
        path = Path(workdir) / "ticket.js"
        path.write_text(script, encoding="utf-8")
        params = {"action": "validate", "workflowScriptPath": str(path)}
        prompt = "Call the native subagent tool exactly once with these parameters. Do not call another tool.\n" + json.dumps(params, sort_keys=True)
        command = [
            wd.pi_executable(), "--no-session", "--mode", "json", "--model",
            os.environ.get("PROJECT_WATCHDOG_PI_MODEL", "zai/glm-5.3"),
            "--extension", str(wd.PI_EXTENSION), "--tools", "subagent", "--approve", "-p", prompt,
        ]
        proc = subprocess.run(command, cwd=ticket.project.cwd, env=wd.pi_environment(), text=True, capture_output=True, check=False, timeout=180)
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message") or {}
            if event.get("type") == "message_end" and message.get("role") == "assistant":
                calls.extend(item for item in message.get("content") or [] if item.get("type") == "toolCall")
            if event.get("type") == "message_end" and message.get("role") == "toolResult" and message.get("toolName") == "subagent":
                results.append(message)
        if proc.returncode != 0 or len(calls) != 1 or len(results) != 1 or calls[0].get("name") != "subagent" or calls[0].get("arguments") != params or results[0].get("toolCallId") != calls[0].get("id"):
            return {"ok": False, "errors": ["native validation call failed or did not match"], "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}
        content = results[0].get("content") or []
        text = "\n".join(item.get("text", "") for item in content if item.get("type") == "text")
        try:
            validation = json.loads(text)
        except json.JSONDecodeError:
            return {"ok": False, "errors": ["native validation result was not JSON"]}
        return {"ok": validation.get("ok") is True and not results[0].get("isError"), "errors": validation.get("errors") or []}


def execute_sandbox(graph: dict[str, Any], origin: str, previous_run: str | None = None) -> dict[str, Any]:
    validate_graph(graph)
    run_id = uuid4().hex
    ticket = sandbox_ticket()
    graph_hash = revision(canonical_bytes(graph))
    receipt: dict[str, Any] = {
        "schema": "project_watchdog.dag_run.v1",
        "run_id": run_id,
        "created_at": wd.utc_now(),
        "origin": origin,
        "previous_run": previous_run,
        "graph_hash": graph_hash,
        "graph": graph,
        "ticket": {"key": ticket.key, "title": ticket.title, "body": ticket.body},
        "sandbox_repo": ticket.project.cwd,
    }
    try:
        native = native_validate(graph, ticket)
        receipt["native_preflight"] = native
        if not native.get("ok"):
            receipt.update({"ok": False, "error": "native preflight failed"})
        else:
            pi_result = wd.PiSubagents().run(ticket, graph=graph)
            transcripts = retain_transcripts(run_id, pi_result)
            proof = wd.run_proof(ticket)
            marker = (Path(ticket.project.cwd) / "marker.txt").read_text(encoding="utf-8")
            diff = subprocess.run(["git", "diff", "--", "marker.txt"], cwd=ticket.project.cwd, text=True, capture_output=True, check=True, timeout=30).stdout
            receipt.update({
                "pi_result": pi_result, "transcripts": transcripts, "proof": proof, "marker": marker, "diff": diff,
                "ok": bool(pi_result.get("ok") and proof.get("ok") and marker == "FIXED\n"),
            })
    except (OSError, subprocess.SubprocessError, GraphError) as exc:
        receipt.update({"ok": False, "error": str(exc)})
    receipt["finished_at"] = wd.utc_now()
    path = run_id_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise GraphError(["run id collision"])
    wd.write_json(path, receipt)
    saved = read_run(run_id)
    return {"run_id": run_id, "ok": saved["ok"], "graph_hash": graph_hash, "receipt": str(path), "error": saved.get("error")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-watchdog workflow")
    sub = parser.add_subparsers(dest="action", required=True)
    get = sub.add_parser("get")
    get.add_argument("--source", choices=["draft", "active"], default="draft")
    save = sub.add_parser("save")
    save.add_argument("--revision", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--source", choices=["draft", "active"], default="draft")
    validate.add_argument("--native", action="store_true")
    run = sub.add_parser("sandbox-run")
    run.add_argument("--source", choices=["draft", "active"], default="draft")
    run.add_argument("--revision", required=True)
    sub.add_parser("runs")
    read = sub.add_parser("run")
    read.add_argument("run_id")
    transcript = sub.add_parser("transcript")
    transcript.add_argument("run_id")
    transcript.add_argument("node_id")
    rerun = sub.add_parser("rerun")
    rerun.add_argument("run_id")
    promote = sub.add_parser("promote")
    promote.add_argument("run_id")
    promote.add_argument("--draft-revision", required=True)
    promote.add_argument("--active-revision", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "get":
            graph, current = read_graph(args.source)
            output({"graph": graph, "revision": current, "source": args.source})
        elif args.action == "save":
            request = json.load(sys.stdin)
            graph = request.get("graph") if isinstance(request, dict) else None
            current = save_graph(graph, args.revision)
            output({"ok": True, "revision": current, "source": "draft"})
        elif args.action == "validate":
            graph, current = read_graph(args.source)
            result: dict[str, Any] = {"ok": True, "revision": current, "source": args.source, "ordered_nodes": [node["id"] for node in validate_graph(graph)]}
            if args.native:
                ticket = sandbox_ticket()
                result["native"] = native_validate(graph, ticket)
                result["ok"] = result["native"]["ok"]
            output(result)
            if not result["ok"]:
                return 1
        elif args.action == "sandbox-run":
            graph, current = read_graph(args.source)
            if current != args.revision:
                raise GraphError(["graph changed before sandbox run"])
            result = execute_sandbox(graph, args.source)
            output(result)
            if not result["ok"]:
                return 1
        elif args.action == "runs":
            paths = sorted(RUNS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:30] if RUNS_DIR.is_dir() else []
            runs = []
            for path in paths:
                receipt = read_run(path.stem)
                runs.append({key: receipt.get(key) for key in ("run_id", "created_at", "ok", "graph_hash", "previous_run", "origin")})
            output({"runs": runs})
        elif args.action == "run":
            output(read_run(args.run_id))
        elif args.action == "transcript":
            receipt = read_run(args.run_id)
            entry = (receipt.get("transcripts") or {}).get(args.node_id) or {}
            expected = RUNS_DIR / args.run_id / f"{args.node_id}.jsonl"
            if not RUN_ID.fullmatch(args.run_id) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", args.node_id) or not entry.get("available") or entry.get("path") != str(expected) or not expected.is_file():
                raise GraphError(["transcript not found"])
            text = expected.read_text(encoding="utf-8", errors="replace")
            output({"run_id": args.run_id, "node_id": args.node_id, "text": text, "sha256": hashlib.sha256(expected.read_bytes()).hexdigest()})
        elif args.action == "rerun":
            prior = read_run(args.run_id)
            result = execute_sandbox(prior["graph"], "rerun", previous_run=args.run_id)
            output(result)
            if not result["ok"]:
                return 1
        elif args.action == "promote":
            prior = read_run(args.run_id)
            draft, draft_revision = read_graph("draft")
            if not prior.get("ok") or prior.get("graph_hash") != revision(canonical_bytes(draft)) or draft_revision != args.draft_revision:
                raise GraphError(["promotion requires a successful sandbox run of this exact draft"])
            active_revision = promote_graph(args.draft_revision, args.active_revision)
            output({"ok": True, "active_revision": active_revision, "promoted_run": args.run_id})
    except (GraphError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        issues = exc.issues if isinstance(exc, GraphError) else [str(exc)]
        output({"ok": False, "errors": issues})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
