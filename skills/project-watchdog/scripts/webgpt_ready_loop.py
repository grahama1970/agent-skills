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
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

READY_PHRASE = "ready-to-deploy"
READY_LINE = "VERDICT: ready-to-deploy"
NO_BLOCKERS_LINE = "BLOCKING_FINDINGS: none"


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def classify_response(text: str, *, candidate_digest: str | None = None, packet_digest: str | None = None) -> dict[str, Any]:
    """Return a conservative readiness verdict from WebGPT text."""
    lines = [line.strip() for line in text.splitlines()]
    has_ready_line = READY_LINE in lines
    has_no_blockers = NO_BLOCKERS_LINE in lines
    candidate_bound = candidate_digest is None or f"CANDIDATE_DIGEST: {candidate_digest}" in lines
    packet_bound = packet_digest is None or f"PACKET_DIGEST: {packet_digest}" in lines
    blockers = [line for line in lines if line.startswith(("P0", "P1", "P2", "R1", "R2", "R3", "### R", "### P"))]
    ready = has_ready_line and has_no_blockers and candidate_bound and packet_bound and not blockers
    findings = [line for line in lines if line.startswith(("### ", "## ", "- P", "P1", "P2", "P0", "R1", "R2", "R3"))][:40]
    return {
        "schema": "project_watchdog.webgpt_ready_verdict.v1",
        "ready_to_deploy": ready,
        "required_phrase": READY_PHRASE,
        "required_lines": [READY_LINE, NO_BLOCKERS_LINE],
        "candidate_bound": candidate_bound,
        "packet_bound": packet_bound,
        "blocking_findings": blockers[:20],
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
    """Redact absolute local paths while preserving Markdown and repo-relative paths."""
    text = text.replace("~/", "home slash ")
    text = text.replace("skills/project-watchdog/", "skills > project-watchdog > ")
    text = text.replace("../", "parent > ")
    text = text.replace("a/skills >", "a > skills >").replace("b/skills >", "b > skills >")
    return re.sub(r"(?<![A-Za-z0-9])/(home|mnt|tmp|usr|dev)/[^\s)>'\"]+", "<local-path>", text)


def display_path(path: str) -> str:
    return path.replace("/", " > ")


def candidate_manifest(repo: Path) -> dict[str, Any]:
    status = run_cmd(["git", "status", "--porcelain", "--", "skills/project-watchdog"], cwd=repo, timeout=60)
    files = []
    for line in status["stdout"].splitlines():
        path = line[3:].strip()
        if not path or path.endswith("/"):
            continue
        p = repo / path
        if p.is_file():
            text = p.read_text(errors="replace")
            files.append({"repo_path": display_path(path), "status": line[:2], "sha256": sha256_text(text), "bytes": len(text.encode())})
        else:
            files.append({"repo_path": display_path(path), "status": line[:2], "missing": True})
    commits = run_cmd(["git", "log", "--oneline", "--max-count", "8", "origin/main", "--", "skills/project-watchdog"], cwd=repo, timeout=60)
    manifest = {"status_returncode": status["returncode"], "files": files, "recent_origin_main_commits": commits["stdout"].splitlines()}
    manifest["candidate_digest"] = sha256_text(json.dumps(manifest, sort_keys=True))
    return manifest


def build_packet(repo: Path, *, prior_response: Path | None, output: Path) -> tuple[Path, str]:
    manifest = candidate_manifest(repo)
    diff = run_cmd(["git", "diff", "--", "skills/project-watchdog"], cwd=repo, timeout=120)
    stat = run_cmd(["git", "diff", "--stat", "origin/main", "--", "skills/project-watchdog"], cwd=repo, timeout=120)
    tests = run_cmd(["bash", "-lc", "tail -1 /tmp/pw-webgpt-loop-tests.txt /tmp/pw-webgpt-loop-sanitize-tests.txt 2>&1"], cwd=repo, timeout=60)
    cron = run_cmd(["crontab", "-l"], cwd=repo, timeout=60)
    cron_lines = [line for line in cron["stdout"].splitlines() if "project-watchdog" in line]
    body = [
        "# project-watchdog WebGPT readiness iteration",
        "",
        "Required terminal verdict lines if and only if deployable:",
        READY_LINE,
        f"CANDIDATE_DIGEST: {manifest['candidate_digest']}",
        "PACKET_DIGEST: provided in the prompt that accompanies this packet",
        NO_BLOCKERS_LINE,
        "",
        "If not ready, return focused ticket-sized findings with severity, target area, acceptance gate, and next proof command.",
        "",
        "## Candidate manifest",
        "```json",
        json.dumps(manifest, indent=2, sort_keys=True),
        "```",
        "",
        "## Relevant diff stat",
        "```text",
        stat["stdout"] or "no working-tree diff against origin main for project-watchdog",
        "```",
        "",
        "## Relevant working-tree diff bytes",
        "```diff",
        browser_safe(diff["stdout"][-20000:]) or "no uncommitted project-watchdog diff",
        "```",
        "",
        "## Proof command results",
        "```json",
        json.dumps({"tests_tail": tests, "crontab_returncode": cron["returncode"], "project_watchdog_cron_line_count": len(cron_lines)}, indent=2, sort_keys=True),
        "```",
    ]
    if prior_response and prior_response.is_file():
        body.extend(["", "## Previous WebGPT response to close", "```text", browser_safe(prior_response.read_text(errors="replace")[-12000:]), "```"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(browser_safe("\n".join(body)) + "\n", encoding="utf-8")
    return output, manifest["candidate_digest"]


def latest_webgpt_response(ask_json: Path, output_root: Path) -> Path | None:
    try:
        data = json.loads(ask_json.read_text())
    except (OSError, ValueError):
        data = {}
    for key in ("run_dir", "ask_run_dir", "artifact_dir"):
        base = data.get(key)
        if base:
            candidate = Path(base) / "node-artifacts" / "handler-webgpt" / "response.md"
            if candidate.is_file():
                return candidate
    responses = sorted(output_root.glob("ask-tau-*/node-artifacts/handler-webgpt/response.md"), key=lambda p: p.stat().st_mtime)
    return responses[-1] if responses else None


def ask_webgpt(repo: Path, packet: Path, *, project: str, output_root: Path, iteration: int, candidate_digest: str) -> dict[str, Any]:
    packet_digest = sha256_file(packet)
    prompt = (
        "Clean-room review this project-watchdog readiness packet against your prior single-cron recommendations. "
        f"Candidate digest is {candidate_digest}. Packet digest is {packet_digest}. "
        "If and only if the implementation is deployable, include these exact lines: "
        f"{READY_LINE}; CANDIDATE_DIGEST: {candidate_digest}; PACKET_DIGEST: {packet_digest}; {NO_BLOCKERS_LINE}. "
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
    response = latest_webgpt_response(ask_json, output_root)
    verdict = classify_response(response.read_text(errors="replace"), candidate_digest=candidate_digest, packet_digest=packet_digest) if response and response.is_file() else None
    return {"status": "OK" if verdict else "NO_RESPONSE", "command": result, "ask_json": str(ask_json), "response": str(response) if response else None, "candidate_digest": candidate_digest, "packet_digest": packet_digest, "verdict": verdict}


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
        packet, candidate_digest = build_packet(repo, prior_response=prior, output=args.output_root / f"packet-{iteration}.md")
        receipt["steps"].append({"iteration": iteration, "packet": str(packet), "candidate_digest": candidate_digest})
        if not args.execute:
            receipt["next_command"] = "rerun with --execute after local fixes are ready for clean-room WebGPT review"
            break
        result = ask_webgpt(repo, packet, project=args.project, output_root=args.output_root, iteration=iteration, candidate_digest=candidate_digest)
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
