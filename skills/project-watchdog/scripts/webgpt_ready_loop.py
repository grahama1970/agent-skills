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
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

READY_PHRASE = "ready-to-deploy"
READY_LINE = "VERDICT: ready-to-deploy"
NO_BLOCKERS_LINE = "BLOCKING_FINDINGS: none"
REQUIRED_PROOF_GATES = [
    {"name": "ready-loop exact digest verdict", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_classify_requires_evidence_bound_ready_verdict"]},
    {"name": "missing required case blocks qualification", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_declared_required_gate_failure_blocks_positive_reviewer"]},
    {"name": "skipped required case blocks qualification", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_skipped_required_case_blocks_qualification"]},
    {"name": "old provider receipt rejected", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_old_valid_provider_receipt_cannot_authorize_current_review"]},
    {"name": "post-review candidate stability", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_candidate_change_during_review_invalidates_approval"]},
    {"name": "packet canonical roundtrip", "pytest": ["skills/project-watchdog/tests/test_webgpt_ready_loop.py::test_packet_roundtrip_preserves_schema_paths_and_digest"]},
    {"name": "serial fleet admission", "pytest": ["skills/project-watchdog/tests/test_single_cron_fleet_adapter.py"]},
    {"name": "started creator charges slot", "pytest": ["skills/project-watchdog/tests/test_single_cron_fleet_adapter.py::test_started_creator_with_failed_review_is_charged_as_started"]},
    {"name": "retained operation not new admission", "pytest": ["skills/project-watchdog/tests/test_single_cron_fleet_adapter.py::test_retained_operation_is_not_a_new_creator_admission"]},
    {"name": "per-ticket notification scoping", "pytest": ["skills/project-watchdog/tests/test_watchdog_notify_bridge.py"]},
    {"name": "terminal transition beats replayed progress", "pytest": ["skills/project-watchdog/tests/test_notify_receipt_replay.py::test_terminal_transition_beats_replayed_progress"]},
    {"name": "restart recovers committed unregistered receipt", "pytest": ["skills/project-watchdog/tests/test_notify_receipt_replay.py::test_restart_recovers_committed_unregistered_receipt"]},
    {"name": "bounded delivery drain", "pytest": ["skills/project-watchdog/tests/test_notify_receipt_replay.py::test_drain_budget_and_acknowledgment_status"]},
    {"name": "human alert retry source-first", "pytest": ["skills/project-watchdog/tests/test_notify_receipt_replay.py::test_idle_tick_retries_human_alert_after_source_commit"]},
    {"name": "old-cursor receipt recovery", "pytest": ["skills/project-watchdog/tests/test_notify_receipt_replay.py::test_restart_recovers_unregistered_receipt_at_or_before_cursor"]},
    {"name": "quiet owner finalizes without dispatch", "pytest": ["skills/project-watchdog/tests/test_single_cron_owner.py::test_quiet_owner_finalizes_without_dispatch"]},
    {"name": "finalization preserves receipt on fault", "pytest": ["skills/project-watchdog/tests/test_single_cron_owner.py::test_finalization_fault_preserves_receipt_and_records_degradation"]},
    {"name": "cron installer singleton", "pytest": ["skills/project-watchdog/tests/test_single_cron_installer.py"]},
    {"name": "historical UI cron removal", "pytest": ["skills/project-watchdog/tests/test_single_cron_installer.py::test_installer_removes_original_watchdog_ui_snapshot_job"]},
]


def _junit_summary(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"tests": 0, "failures": 0, "errors": 1, "skipped": 0}
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def classify_response(text: str, *, candidate_digest: str | None = None, packet_digest: str | None = None) -> dict[str, Any]:
    """Return a conservative readiness verdict from WebGPT text."""
    raw_lines = [line for line in text.splitlines() if line.strip()]
    lines = [line.strip() for line in raw_lines]
    expected = [
        READY_LINE,
        f"CANDIDATE_DIGEST: {candidate_digest}",
        f"PACKET_DIGEST: {packet_digest}",
        NO_BLOCKERS_LINE,
    ]
    digest_inputs_present = bool(candidate_digest and packet_digest)
    terminal_record = lines if len(lines) == 4 else []
    field_lines = [line for line in lines if line.startswith(("VERDICT:", "CANDIDATE_DIGEST:", "PACKET_DIGEST:", "BLOCKING_FINDINGS:"))]
    unique_terminal_record = field_lines == expected
    candidate_bound = digest_inputs_present and f"CANDIDATE_DIGEST: {candidate_digest}" in terminal_record
    packet_bound = digest_inputs_present and f"PACKET_DIGEST: {packet_digest}" in terminal_record
    blockers = [line for line in lines if line.startswith(("- P", "P0", "P1", "P2", "R1", "R2", "R3", "### R", "### P"))]
    ready = digest_inputs_present and terminal_record == expected and unique_terminal_record and candidate_bound and packet_bound and not blockers
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


def run_cmd(argv: list[str], *, cwd: Path, timeout: int = 600, output_limit: int | None = 4000) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    stdout = proc.stdout if output_limit is None else proc.stdout[-output_limit:]
    stderr = proc.stderr if output_limit is None else proc.stderr[-output_limit:]
    return {
        "argv": argv,
        "returncode": proc.returncode,
        "duration_seconds": round(time.time() - started, 3),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": output_limit is not None and len(proc.stdout) > output_limit,
        "stderr_truncated": output_limit is not None and len(proc.stderr) > output_limit,
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


def _git_paths(repo: Path, *args: str) -> list[str]:
    proc = subprocess.run(["git", "ls-files", "-z", *args, "--", "skills/project-watchdog"], cwd=repo, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-500:])
    return [p.decode(errors="surrogateescape") for p in proc.stdout.split(b"\0") if p]


def candidate_manifest(repo: Path) -> dict[str, Any]:
    tracked = set(_git_paths(repo))
    untracked = set(_git_paths(repo, "--others", "--exclude-standard"))
    deleted = set(_git_paths(repo, "--deleted"))
    base_tree = run_cmd(["git", "rev-parse", "origin/main^{tree}"], cwd=repo, timeout=60)
    head = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo, timeout=60)
    files = []
    for path in sorted(tracked | untracked | deleted):
        p = repo / path
        item: dict[str, Any] = {"repo_path": display_path(path), "tracked": path in tracked, "untracked": path in untracked, "deleted": path in deleted}
        try:
            st = p.lstat()
            item["mode"] = oct(st.st_mode & 0o777777)
            if p.is_symlink():
                item["symlink_target"] = os.readlink(p)
                item["sha256"] = sha256_text(item["symlink_target"])
            elif p.is_file():
                raw = p.read_bytes()
                item["sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
                item["bytes"] = len(raw)
            else:
                item["kind"] = "non_file"
        except FileNotFoundError:
            item["missing"] = True
        files.append(item)
    manifest = {
        "base_tree": base_tree["stdout"].strip(),
        "head": head["stdout"].strip(),
        "inventory_scope": "skills/project-watchdog",
        "inventory_complete": True,
        "files": files,
    }
    manifest["candidate_digest"] = sha256_text(json.dumps(manifest, sort_keys=True))
    return manifest


def collect_proof_results(repo: Path, output_dir: Path, candidate_digest: str) -> dict[str, Any]:
    gates = []
    registry_names = {str(gate.get("name")) for gate in REQUIRED_PROOF_GATES if gate.get("name")}
    for index, gate_spec in enumerate(REQUIRED_PROOF_GATES, start=1):
        junit_path = output_dir / f"candidate-bound-gate-{index}.xml"
        command = ["uv", "run", "--project", "skills/project-watchdog", "pytest", "-q", f"--junitxml={junit_path}", *list(gate_spec["pytest"])]
        result = run_cmd(command, cwd=repo, timeout=240, output_limit=None)
        log_text = result["stdout"] + result["stderr"]
        log_path = output_dir / f"candidate-bound-gate-{index}.log"
        log_path.write_text(log_text, encoding="utf-8")
        junit = _junit_summary(junit_path)
        passed = result["returncode"] == 0 and junit["tests"] > 0 and junit["failures"] == 0 and junit["errors"] == 0 and junit["skipped"] == 0
        gates.append({
            "name": gate_spec["name"],
            "candidate_digest": candidate_digest,
            "command": command,
            "returncode": result["returncode"],
            "duration_seconds": result["duration_seconds"],
            "log_sha256": sha256_file(log_path),
            "junit_path": str(junit_path),
            "junit_sha256": sha256_file(junit_path) if junit_path.is_file() else None,
            "junit": junit,
            "stdout_tail": result["stdout"][-4000:],
            "stderr_tail": result["stderr"][-4000:],
            "passed": passed,
        })
    after_digest = candidate_manifest(repo)["candidate_digest"]
    missing = sorted(registry_names - {str(gate.get("name")) for gate in gates})
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    return {
        "candidate_digest_before": candidate_digest,
        "candidate_digest_after": after_digest,
        "candidate_stable": after_digest == candidate_digest,
        "declared_required_gates": sorted(registry_names),
        "gates": gates,
        "missing_mandatory_gates": missing,
        "failed_mandatory_gates": failed,
        "qualifies_candidate": after_digest == candidate_digest and bool(registry_names) and not missing and not failed,
    }


def build_packet(repo: Path, *, prior_response: Path | None, output: Path) -> tuple[Path, str, bool]:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = candidate_manifest(repo)
    diff = run_cmd(["git", "diff", "--", "skills/project-watchdog"], cwd=repo, timeout=120, output_limit=None)
    stat = run_cmd(["git", "diff", "--stat=200", "origin/main", "--", "skills/project-watchdog"], cwd=repo, timeout=120)
    tests = collect_proof_results(repo, output.parent, manifest["candidate_digest"])
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
        json.dumps({"candidate_bound_tests": tests, "crontab_returncode": cron["returncode"], "project_watchdog_cron_line_count": len(cron_lines)}, indent=2, sort_keys=True),
        "```",
    ]
    if prior_response and prior_response.is_file():
        body.extend(["", "## Previous WebGPT response to close", "```text", browser_safe(prior_response.read_text(errors="replace")[-12000:]), "```"])
    output.write_text("\n".join(body) + "\n", encoding="utf-8")
    return output, manifest["candidate_digest"], bool(tests.get("qualifies_candidate"))


def _parse_ask_json(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text()
        return json.loads(text)
    except (OSError, ValueError):
        return None


def latest_webgpt_response(ask_json: Path, output_root: Path) -> Path | None:
    data = _parse_ask_json(ask_json)
    if not data:
        return None
    candidates = []
    node_receipt = data.get("node_receipt_path") or data.get("handler_receipt_path")
    if node_receipt:
        candidates.append(Path(node_receipt).parent / "response.md")
    join_artifact = data.get("join_artifact_path")
    if join_artifact:
        candidates.append(Path(join_artifact).parents[1] / "handler-webgpt" / "response.md")
    execution = data.get("execution") or {}
    receipt_path = execution.get("receipt_path")
    if receipt_path:
        candidates.append(Path(receipt_path).parents[1] / "node-artifacts" / "handler-webgpt" / "response.md")
    for key in ("run_dir", "ask_run_dir", "artifact_dir"):
        base = data.get(key)
        if base:
            candidates.append(Path(base) / "node-artifacts" / "handler-webgpt" / "response.md")
    receipt_entries = (execution.get("node_provider_receipts") or []) if isinstance(execution, dict) else []
    webgpt_entry = next((entry for entry in receipt_entries if entry.get("node_id") == "handler-webgpt"), None)
    if not webgpt_entry or not webgpt_entry.get("ok") or webgpt_entry.get("status") != "PASS":
        return None
    node_receipt_path = Path(str(webgpt_entry.get("path") or ""))
    response_path = Path(str(webgpt_entry.get("response_path") or ""))
    if not node_receipt_path.is_file() or not response_path.is_file() or output_root not in response_path.parents:
        return None
    try:
        if response_path.stat().st_mtime < ask_json.stat().st_mtime:
            return None
    except OSError:
        return None
    try:
        node_receipt = json.loads(node_receipt_path.read_text())
    except (OSError, ValueError):
        return None
    if not (node_receipt.get("ok") is True and node_receipt.get("status") == "PASS" and node_receipt.get("node_id") == "handler-webgpt"):
        return None
    if node_receipt.get("response_path") != str(response_path):
        return None
    return response_path


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
    result = run_cmd(cmd, cwd=repo, timeout=3000, output_limit=None)
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
        packet, candidate_digest, proof_qualified = build_packet(repo, prior_response=prior, output=args.output_root / f"packet-{iteration}.md")
        receipt["steps"].append({"iteration": iteration, "packet": str(packet), "candidate_digest": candidate_digest, "proof_qualified": proof_qualified})
        if not args.execute:
            receipt["next_command"] = "rerun with --execute after local fixes are ready for clean-room WebGPT review"
            break
        result = ask_webgpt(repo, packet, project=args.project, output_root=args.output_root, iteration=iteration, candidate_digest=candidate_digest)
        receipt["steps"].append({"iteration": iteration, "ask": result})
        verdict = result.get("verdict") or {}
        post_review_digest = candidate_manifest(repo)["candidate_digest"]
        receipt["steps"].append({"iteration": iteration, "post_review_candidate_digest": post_review_digest, "candidate_stable_after_review": post_review_digest == candidate_digest})
        if proof_qualified and post_review_digest == candidate_digest and verdict.get("ready_to_deploy"):
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
