#!/usr/bin/env python3
"""Deterministic WebGPT readiness loop for project-watchdog.

Purpose
    Keep the clean-room WebGPT reviewer as an explicit deployment gate: each
    iteration gathers the current local proof packet, submits it through the
    existing browser-oracle binding, and stops successfully only when WebGPT says
    ``ready-to-deploy``.

Inputs
    Repository root, bound browser-oracle project, optional prior response, and
    a maximum iteration count.

Outputs
    A JSON receipt recording the ordered steps, Ask artifact paths, reviewer
    response path, and readiness classification.

Failure modes
    The script exits non-zero when WebGPT is not ready, Ask fails before a
    proven WebGPT response, browser preflight fails, or the bound tab is not
    ready. It does not invent a ready verdict from local tests.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

READY_PHRASE = "ready-to-deploy"
NEGATIONS = (
    "not ready-to-deploy",
    "not yet ready-to-deploy",
    "no ready-to-deploy",
    "without a ready-to-deploy",
    "until ready-to-deploy",
)


def classify_response(text: str) -> dict[str, Any]:
    """Return a conservative readiness verdict from WebGPT text."""
    lower = text.lower()
    ready = READY_PHRASE in lower and not any(neg in lower for neg in NEGATIONS)
    lines = [line.strip() for line in text.splitlines()]
    findings = [line for line in lines if line.startswith(("### ", "## ", "- P", "P1", "P2", "P0"))][:40]
    return {
        "schema": "project_watchdog.webgpt_ready_verdict.v1",
        "ready_to_deploy": ready,
        "required_phrase": READY_PHRASE,
        "summary": "ready-to-deploy" if ready else "not_ready",
        "findings": findings,
    }


def run_cmd(argv: list[str], *, cwd: Path, timeout: int = 600) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "argv": argv,
        "returncode": proc.returncode,
        "duration_seconds": round(time.time() - started, 3),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def browser_safe(text: str) -> str:
    """Keep packets free of local path-shaped tokens that browser preflight rejects."""
    replacements = {
        "/home/graham/workspace/experiments/agent-skills/": "repo root slash ",
        "/mnt/storage12tb/": "storage artifact root slash ",
        "/tmp/": "temporary artifact root slash ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.replace("~/", "home slash ")


def build_packet(repo: Path, *, prior_response: Path | None, output: Path) -> Path:
    status = run_cmd(["git", "status", "--short", "--", "skills/project-watchdog"], cwd=repo, timeout=60)
    cron = run_cmd(["bash", "-lc", "crontab -l 2>/dev/null | grep -F project-watchdog || true"], cwd=repo, timeout=60)
    body = [
        "# project-watchdog WebGPT readiness iteration",
        "",
        "Required terminal verdict: ready-to-deploy.",
        "If not ready, return focused ticket-sized findings with severity, target area, acceptance gate, and next proof command.",
        "",
        "## Current local signals",
        "```text",
        "git status for project-watchdog:",
        status["stdout"],
        "project-watchdog crontab lines:",
        cron["stdout"],
        "```",
    ]
    if prior_response and prior_response.is_file():
        body.extend(["", "## Previous WebGPT response to close", "```text", prior_response.read_text(errors="replace")[-12000:], "```"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(browser_safe("\n".join(body)) + "\n", encoding="utf-8")
    return output


def latest_webgpt_response(ask_json: Path) -> Path | None:
    try:
        data = json.loads(ask_json.read_text())
    except (OSError, ValueError):
        return None
    base = data.get("run_dir") or data.get("ask_run_dir") or data.get("artifact_dir")
    if not base:
        text = json.dumps(data)
        marker = "/node-artifacts/handler-webgpt/response.md"
        idx = text.find(marker)
        if idx < 0:
            return None
        start = text.rfind('"', 0, idx)
        return Path(text[start + 1:idx + len(marker)]) if start >= 0 else None
    candidate = Path(base) / "node-artifacts" / "handler-webgpt" / "response.md"
    return candidate if candidate.is_file() else None


def ask_webgpt(repo: Path, packet: Path, *, project: str, output_root: Path, iteration: int) -> dict[str, Any]:
    prompt = (
        "Clean-room review this project-watchdog readiness packet against your prior single-cron recommendations. "
        "If the implementation is finished, include the exact phrase ready-to-deploy. "
        "If not, return focused ticket-sized findings with severity and concrete next proof commands."
    )
    preflight = run_cmd([
        sys.executable,
        "skills/ask/scripts/browser_prompt_preflight.py",
        "--prompt",
        prompt,
        str(packet),
    ], cwd=repo, timeout=120)
    if preflight["returncode"] != 0:
        return {"status": "PREFLIGHT_FAILED", "preflight": preflight}
    ask_json = output_root / f"webgpt-ready-iteration-{iteration}.json"
    cmd = [
        "skills/ask/run.sh", "tau-dag", prompt,
        "--repo", "grahama1970/agent-skills",
        "--target", "project-watchdog-ready-loop",
        "--immutable-goal", "Clean-room WebGPT must explicitly say ready-to-deploy before project-watchdog single-cron work is considered deployable.",
        "--dag-template", "single-call",
        "--handler", "webgpt",
        "--handler-project", f"webgpt={project}",
        "--browser-tab-lifecycle", "reuse-bound",
        "--attach-file", str(packet),
        "--run-output-root", str(output_root),
        "--execution-timeout-seconds", "2400",
        "--poll-timeout-seconds", "3000",
        "--execute", "--json",
    ]
    result = run_cmd(cmd, cwd=repo, timeout=3000)
    ask_json.write_text(result["stdout"], encoding="utf-8")
    response = latest_webgpt_response(ask_json)
    verdict = classify_response(response.read_text(errors="replace")) if response and response.is_file() else None
    return {"status": "OK" if verdict else "NO_RESPONSE", "command": result, "ask_json": str(ask_json), "response": str(response) if response else None, "verdict": verdict}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="iterate same-tab WebGPT review until an explicit ready verdict appears")
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--project", default="project-watchdog", help="browser-oracle project bound to the clean-room WebGPT tab")
    parser.add_argument("--prior-response", type=Path)
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/project-watchdog-webgpt-ready-loop"))
    parser.add_argument("--classify-response", type=Path, help="only classify an existing WebGPT response")
    parser.add_argument("--execute", action="store_true", help="actually submit to WebGPT; otherwise only write the packet and steps")
    args = parser.parse_args(argv)

    if args.classify_response:
        verdict = classify_response(args.classify_response.read_text(errors="replace"))
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return 0 if verdict["ready_to_deploy"] else 1

    repo = args.repo.resolve()
    args.output_root.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {"schema": "project_watchdog.webgpt_ready_loop.v1", "steps": [], "ready_to_deploy": False}
    prior = args.prior_response
    for iteration in range(1, args.max_iterations + 1):
        packet = build_packet(repo, prior_response=prior, output=args.output_root / f"packet-{iteration}.md")
        receipt["steps"].append({"iteration": iteration, "packet": str(packet)})
        if not args.execute:
            receipt["next_command"] = "rerun with --execute after local fixes are ready for clean-room WebGPT review"
            break
        result = ask_webgpt(repo, packet, project=args.project, output_root=args.output_root, iteration=iteration)
        receipt["steps"].append({"iteration": iteration, "ask": result})
        verdict = result.get("verdict") or {}
        if verdict.get("ready_to_deploy"):
            receipt["ready_to_deploy"] = True
            receipt["response"] = result.get("response")
            break
        if result.get("response"):
            prior = Path(str(result["response"]))
    out = args.output_root / "loop-receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["ready_to_deploy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
