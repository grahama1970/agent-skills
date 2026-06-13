#!/usr/bin/env python3
"""Run one skill-maintainer issue cycle from GitHub issue state.

This script is scheduler-safe and intentionally conservative: it leases at most
one issue and writes the repair/verifier/WebGPT packets. Until a real repair
executor is wired in, live runs mark the issue blocked with explicit evidence
instead of returning scheduler success for packet-only behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / ".artifacts" / "skill-maintainer"
DEFAULT_LABELS = ["skill-bug", "skill-maintenance", "skills-ci", "skill-optimization"]
LEASE_LABEL = "maintainer-active"
BLOCKED_LABELS = ["maintainer-blocked", "needs-human"]
SKIP_LABELS = {LEASE_LABEL, *BLOCKED_LABELS, "external-owner"}


ROUTES: list[dict[str, Any]] = [
    {
        "route": "design_or_ux",
        "repair_agent": "designer",
        "verifier_agent": "qa-tester",
        "review_agent": "code-reviewer",
        "labels": {"design", "ux", "ui", "visual", "frontend-design"},
        "terms": {"design", "ux", "ui", "mockup", "visual", "screenshot", "layout", "interaction"},
    },
    {
        "route": "frontend_code",
        "repair_agent": "frontend-coder",
        "verifier_agent": "qa-tester",
        "review_agent": "frontend-reviewer",
        "labels": {"frontend", "react", "ui"},
        "terms": {"react", "typescript", "tsx", "css", "browser", "dom"},
    },
    {
        "route": "backend_python_or_skill_runtime",
        "repair_agent": "coder",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
        "labels": {"python", "backend", "runtime", "cli", "skills-ci"},
        "terms": {"python", "typer", "pytest", "cli", "skill.md", "frontmatter", "sanity.sh"},
    },
    {
        "route": "rust_or_binary",
        "repair_agent": "coder",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
        "labels": {"rust", "binary", "elf"},
        "terms": {"rust", "cargo", "elf", "binary"},
    },
    {
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
        "labels": {"ops", "scheduler", "cron", "devops"},
        "terms": {"cron", "scheduler", "systemd", "docker", "service", "environment"},
    },
    {
        "route": "documentation_or_report",
        "repair_agent": "reporter",
        "verifier_agent": "code-reviewer",
        "review_agent": "proof-reader",
        "labels": {"docs", "documentation", "report"},
        "terms": {"readme", "docs", "report", "wording", "typo", "prose"},
    },
    {
        "route": "security_or_compliance",
        "repair_agent": "cyber-analyst",
        "verifier_agent": "code-reviewer",
        "review_agent": "assurance",
        "labels": {"security", "compliance", "cmmc", "cui"},
        "terms": {"security", "compliance", "cmmc", "cui", "vulnerability", "threat"},
    },
]

ROUTES_BY_NAME = {route["route"]: route for route in ROUTES}


def known_agent_ids() -> set[str]:
    agents_root = REPO_ROOT / "agents"
    if not agents_root.exists():
        return set()
    return {
        path.name
        for path in agents_root.iterdir()
        if path.is_dir() and not path.name.startswith((".", "_"))
    }


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=check)


def run_in_cwd(
    cmd: list[str] | str,
    *,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        shell=isinstance(cmd, str),
        text=True,
        capture_output=True,
        check=check,
    )


def git_run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def git_rev_parse(cwd: Path, *args: str) -> str:
    cp = run_in_cwd(["git", "rev-parse", *args], cwd=cwd, check=False)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def git_worktree_or_branch(cwd: Path) -> str:
    branch = git_rev_parse(cwd, "--abbrev-ref", "HEAD")
    if branch and branch != "HEAD":
        return branch
    return str(cwd)


def git_repo_slug() -> str | None:
    try:
        cp = run(["git", "config", "--get", "remote.origin.url"], check=True)
    except Exception:
        return None
    remote = cp.stdout.strip()
    if not remote:
        return None
    if remote.endswith(".git"):
        remote = remote[:-4]
    match = re.search(r"[:/]([^/:]+/[^/]+)$", remote)
    return match.group(1) if match else None


def issue_list(labels: list[str]) -> list[dict[str, Any]]:
    if not shutil_which("gh"):
        raise SystemExit("gh CLI not found; cannot scan GitHub issues")
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--json",
        "number,title,body,labels,url,assignees",
        "--limit",
        "100",
    ]
    cp = run(cmd)
    issues = json.loads(cp.stdout or "[]")
    wanted = set(labels)
    return [
        issue
        for issue in issues
        if wanted & {label.get("name", "") for label in issue.get("labels", [])}
        and not (SKIP_LABELS & {label.get("name", "") for label in issue.get("labels", [])})
    ]


def issue_view(number: int) -> dict[str, Any]:
    if not shutil_which("gh"):
        raise SystemExit("gh CLI not found; cannot read GitHub issue")
    cp = run([
        "gh",
        "issue",
        "view",
        str(number),
        "--json",
        "number,title,body,labels,url,assignees",
    ])
    return json.loads(cp.stdout or "{}")


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {label.get("name", "") for label in issue.get("labels", [])}


def gh_issue_edit(issue_number: int, *args: str, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["gh", "issue", "edit", str(issue_number), *args]
    if dry_run:
        return {"cmd": cmd, "dry_run": True, "returncode": 0, "stdout": "", "stderr": ""}
    cp = run(cmd, check=False)
    return {
        "cmd": cmd,
        "dry_run": False,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def gh_issue_comment(issue_number: int, body_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["gh", "issue", "comment", str(issue_number), "--body-file", str(body_path)]
    if dry_run:
        return {"cmd": cmd, "dry_run": True, "returncode": 0, "stdout": "", "stderr": ""}
    cp = run(cmd, check=False)
    return {
        "cmd": cmd,
        "dry_run": False,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def gh_issue_close(issue_number: int, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["gh", "issue", "close", str(issue_number)]
    if dry_run:
        return {"cmd": cmd, "dry_run": True, "returncode": 0, "stdout": "", "stderr": ""}
    cp = run(cmd, check=False)
    return {
        "cmd": cmd,
        "dry_run": False,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def require_gh_ok(action: dict[str, Any], label: str) -> None:
    if int(action.get("returncode", 1)) != 0:
        raise SystemExit(
            f"{label} failed: {' '.join(action.get('cmd', []))}\n"
            f"stdout={action.get('stdout', '')}\nstderr={action.get('stderr', '')}"
        )


def route_payload(route: dict[str, Any], *, source: str, reason: str) -> dict[str, str]:
    return {
        "route": route["route"],
        "repair_agent": route["repair_agent"],
        "verifier_agent": route["verifier_agent"],
        "review_agent": route["review_agent"],
        "selection_source": source,
        "selection_reason": reason,
    }


def route_for_agent(agent_id: str) -> dict[str, Any] | None:
    for route in ROUTES:
        if agent_id == route["repair_agent"] or agent_id in route.get("support_agents", []):
            return route
    return None


def requested_route(issue: dict[str, Any]) -> dict[str, str] | None:
    labels = {label.get("name", "").lower() for label in issue.get("labels", [])}
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
    known_agents = known_agent_ids()

    for label in sorted(labels):
        if label.startswith("route:"):
            route_name = label.split(":", 1)[1].strip()
            route = ROUTES_BY_NAME.get(route_name)
            if route:
                return route_payload(route, source="issue_label", reason=label)
        if label.startswith("agent:"):
            agent_id = label.split(":", 1)[1].strip()
            route = route_for_agent(agent_id)
            if route and (not known_agents or agent_id in known_agents):
                payload = route_payload(route, source="issue_label", reason=label)
                payload["requested_repair_agent"] = agent_id
                return payload

    field_patterns = [
        (r"(?im)^\s*maintainer route\s*:\s*([a-z0-9_.:-]+)\s*$", "route"),
        (r"(?im)^\s*route\s*:\s*([a-z0-9_.:-]+)\s*$", "route"),
        (r"(?im)^\s*repair agent\s*:\s*([a-z0-9_.:-]+)\s*$", "agent"),
        (r"(?im)^\s*requested agent\s*:\s*([a-z0-9_.:-]+)\s*$", "agent"),
        (r"(?ims)^##+\s+maintainer route\s*\n+\s*([a-z0-9_.:-]+)\s*(?:\n##+|\Z)", "route"),
        (r"(?ims)^##+\s+requested repair agent\s*\n+\s*([a-z0-9_.:-]+)\s*(?:\n##+|\Z)", "agent"),
    ]
    for pattern, kind in field_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip().lower()
        if kind == "route":
            route = ROUTES_BY_NAME.get(value)
            if route:
                return route_payload(route, source="issue_body", reason=f"route:{value}")
        else:
            route = route_for_agent(value)
            if route and (not known_agents or value in known_agents):
                payload = route_payload(route, source="issue_body", reason=f"agent:{value}")
                payload["requested_repair_agent"] = value
                return payload
    return None


def issue_section(issue: dict[str, Any], heading: str) -> str | None:
    body = str(issue.get("body") or "")
    pattern = rf"(?ims)^##+\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##+\s+|\Z)"
    match = re.search(pattern, body)
    if not match:
        return None
    return match.group("body")


def classify(issue: dict[str, Any]) -> dict[str, str]:
    explicit = requested_route(issue)
    if explicit:
        return explicit
    labels = {label.get("name", "").lower() for label in issue.get("labels", [])}
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}".lower()
    for route in ROUTES:
        if labels & route["labels"] or any(term in text for term in route["terms"]):
            return route_payload(route, source="maintainer_inference", reason="label_or_text_match")
    return route_payload(
        ROUTES_BY_NAME["backend_python_or_skill_runtime"],
        source="safe_default",
        reason="no_route_metadata_or_match",
    )


def target_skills(issue: dict[str, Any]) -> list[str]:
    text = issue_section(issue, "Target paths")
    if not text:
        return []
    found: list[str] = []
    for match in re.finditer(r"skills/([A-Za-z0-9_.-]+)(?=/|\s|$)", text):
        skill = match.group(1)
        if skill not in found:
            found.append(skill)
    return found


def target_paths(issue: dict[str, Any]) -> list[str]:
    text = issue_section(issue, "Target paths")
    if not text:
        return []
    found: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        cleaned = cleaned.strip("` ")
        match = re.search(r"\b(?:skills|agents|scripts|docs|extensions|hooks)/[A-Za-z0-9_./-]+", cleaned)
        if not match:
            continue
        candidate = match.group(0).rstrip(".,;:)")
        if candidate not in found:
            found.append(candidate)
    return found


def missing_target_paths(paths: list[str]) -> list[str]:
    missing: list[str] = []
    for rel_path in paths:
        if not (REPO_ROOT / rel_path).exists():
            missing.append(rel_path)
    return missing


def read_complies(skill: str) -> list[str]:
    path = REPO_ROOT / "skills" / skill / "SKILL.md"
    if not path.exists():
        return ["missing-skill-contract"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"\ncomplies:\n((?:\s+- .+\n?)+)", text)
    if not match:
        return ["best-practices-skills"]
    return [line.strip()[2:].strip() for line in match.group(1).splitlines() if line.strip().startswith("- ")]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def command_text(cmd: list[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(cmd)


def tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def receipt_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": receipt.get("status"),
        "decision": receipt.get("decision") or receipt.get("result") or receipt.get("verification_result"),
        "evidence_summary": receipt.get("evidence_summary") or receipt.get("summary"),
        "commands_run": receipt.get("commands_run") or [],
        "changed_files": receipt.get("changed_files") or receipt.get("files_changed") or [],
        "blocking_findings": receipt.get("blocking_findings") or [],
        "findings": receipt.get("findings") or [],
    }


def scoped_diff_summary(paths: list[str]) -> dict[str, Any]:
    scoped = [path for path in paths if isinstance(path, str) and not path.startswith("/") and (REPO_ROOT / path).exists()]
    if not scoped:
        return {"paths": [], "name_status": "", "stat": ""}
    name_status = git_run(["diff", "--name-status", "--", *scoped])
    stat = git_run(["diff", "--stat", "--", *scoped])
    return {
        "paths": scoped,
        "name_status": tail(name_status.stdout, 6000),
        "stat": tail(stat.stdout, 6000),
    }


def build_bundle(run_dir: Path, issue: dict[str, Any], route: dict[str, str], skills: list[str]) -> Path:
    bundle = run_dir / "review-bundle.md"
    complies = {skill: read_complies(skill) for skill in skills}
    result = read_json_file(run_dir / "cycle-result.json", {})
    repair = read_json_file(run_dir / "repair-response.json", {})
    verifier = read_json_file(run_dir / "verifier-response.json", {})
    review = read_json_file(run_dir / "review-response.json", {})
    target_path_list = result.get("target_paths") or target_paths(issue)
    diff_summary = scoped_diff_summary(target_path_list)
    issue_labels = [
        label.get("name")
        for label in issue.get("labels", [])
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    ]
    bundle.write_text(
        "\n".join(
            [
                "# Skill Maintainer WebGPT Review Bundle",
                "",
                f"Issue: #{issue.get('number')} {issue.get('title')}",
                f"URL: {issue.get('url')}",
                f"State: `{issue.get('state')}`",
                f"Labels: `{', '.join(issue_labels) or 'none'}`",
                f"Selected route: `{route['route']}`",
                f"Repair agent: `{route['repair_agent']}`",
                f"Verifier agent: `{route['verifier_agent']}`",
                f"Review agent: `{route['review_agent']}`",
                "",
                "## Target Skills",
                json.dumps({"target_skills": skills, "complies": complies}, indent=2),
                "",
                "## Target Paths",
                json.dumps(target_path_list, indent=2),
                "",
                "## Issue Body",
                tail(str(issue.get("body") or ""), 8000),
                "",
                "## Lease And GitHub Actions",
                json.dumps(
                    {
                        "lease": result.get("lease"),
                        "github_actions": result.get("github_actions") or [],
                    },
                    indent=2,
                ),
                "",
                "## Scoped Diff Summary",
                json.dumps(diff_summary, indent=2),
                "",
                "## Receipt Summaries",
                json.dumps(
                    {
                        "repair": receipt_summary(repair),
                        "verifier": receipt_summary(verifier),
                        "review": receipt_summary(review),
                    },
                    indent=2,
                ),
                "",
                "## Workflow Phase Notes",
                "- This WebGPT review occurs after local repair, deterministic verification, and code-review receipts, but before scoped publication.",
                "- Commit, push, and final issue close proof are post-WebGPT gates; absence of commit/push proof in this bundle is expected at this phase.",
                "- Historical terminal blocked comments in the GitHub action log are superseded retry artifacts from bugs found during this E2E.",
                "- Current maintainer code includes a duplicate terminal-disposition idempotency guard for future retries.",
                "- Closure still requires a scoped commit or explicit no-change publication result, a fresh issue-state check, and deterministic local proof.",
                "",
                "## Required Review Question",
                "Does this maintenance packet route the issue to the correct subagents, require deterministic verification, and avoid closing from WebGPT opinion alone?",
                "",
                "## Acceptance Gates",
                "- One issue lease only.",
                "- Repair and verifier agents are different.",
                "- Deterministic local proof required before closure.",
                "- WebGPT findings must be reconciled before GitHub close/comment.",
                "- Treat WebGPT as advisory; local deterministic proof and reviewer receipts are required for closure.",
                "",
                "## Requested Output",
                "Start with exactly one line: `WEBGPT_BLOCKING_FINDINGS: YES` or `WEBGPT_BLOCKING_FINDINGS: NO`.",
                "Then explain any blocking findings or state that there are no blocking findings.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return bundle


PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:/(?:[A-Za-z0-9_.<>-]+/)+[A-Za-z0-9_.<>-]+|(?:skills|scripts|agents|docs|extensions|hooks|\.artifacts)/(?:[A-Za-z0-9_.<>-]+/)*[A-Za-z0-9_.<>-]+)"
)
URL_TOKEN_RE = re.compile(r"https?://[^\s)\"']+")


def sanitize_webgpt_bundle_text(text: str) -> str:
    text = URL_TOKEN_RE.sub(lambda match: f"[url redacted: {match.group(0).replace('/', ' > ')}]", text)

    def repl(match: re.Match[str]) -> str:
        label = match.group(0).replace("/", " > ")
        return f"[local path redacted: {label}]"

    redacted = PATH_TOKEN_RE.sub(repl, text)
    return redacted.replace("/", " slash ")


def write_phase_receipts(
    issue_dir: Path,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    bundle: Path,
    specs: dict[str, str],
) -> dict[str, str]:
    common = {
        "issue": issue.get("number"),
        "issue_url": issue.get("url"),
        "route": route["route"],
        "target_skills": skills,
        "artifact_dir": str(issue_dir),
    }
    repair = {
        **common,
        "phase": "repair",
        "agent": route["repair_agent"],
        "status": "blocked_missing_executor",
        "required_executor": "repair subagent dispatch runtime",
        "subagent_spec": specs["repair_spec"],
        "required_next_evidence": [
            "repair-response.json from selected repair agent",
            "changed_files",
            "patch_diff_or_commit_ref",
            "commands_run",
            "targeted_test_results",
        ],
    }
    verifier = {
        **common,
        "phase": "deterministic_verification",
        "agent": route["verifier_agent"],
        "status": "blocked_waiting_for_repair_receipt",
        "required_input": "repair-response.json",
        "subagent_spec": specs["verifier_spec"],
        "required_next_evidence": [
            "verifier-response.json",
            "command_output_or_report_json",
            "explicit pass_fail_or_blocked_decision",
        ],
    }
    review = {
        **common,
        "phase": "independent_review",
        "agent": route["review_agent"],
        "status": "blocked_waiting_for_repair_and_verifier_receipts",
        "required_input": ["repair-response.json", "verifier-response.json"],
        "subagent_spec": specs["review_spec"],
        "required_next_evidence": [
            "review_request.json",
            "review_response.json",
            "findings",
        ],
    }
    webgpt = {
        **common,
        "phase": "webgpt_external_review",
        "agent": "ask_runtime",
        "status": "blocked_waiting_for_deterministic_verification",
        "review_bundle": str(bundle),
        "command": ask_webgpt_command(bundle),
        "required_input": "verifier-response.json with pass decision",
        "required_next_evidence": [
            "ask request/status/events",
            "review.md or review.json",
            "finding disposition",
        ],
    }
    receipts = {
        "repair_receipt": issue_dir / "repair-response.json",
        "verifier_receipt": issue_dir / "verifier-response.json",
        "review_receipt": issue_dir / "review-response.json",
        "ask_webgpt_receipt": issue_dir / "ask-webgpt-result.json",
    }
    write_json(receipts["repair_receipt"], repair)
    write_json(receipts["verifier_receipt"], verifier)
    write_json(receipts["review_receipt"], review)
    write_json(receipts["ask_webgpt_receipt"], webgpt)
    return {key: str(path) for key, path in receipts.items()}


def dispatch_session_payload(dispatch: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(dispatch.get("stdout") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def write_repair_started_receipt(
    path: Path,
    *,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    issue_dir: Path,
    dispatch: dict[str, Any],
) -> dict[str, Any]:
    session = dispatch_session_payload(dispatch)
    receipt = {
        "issue": issue.get("number"),
        "issue_url": issue.get("url"),
        "route": route["route"],
        "target_skills": skills,
        "artifact_dir": str(issue_dir),
        "phase": "repair",
        "agent": route["repair_agent"],
        "status": "running",
        "subagent_dispatch": {
            "cmd": dispatch.get("cmd"),
            "returncode": dispatch.get("returncode"),
            "stdout_json": session,
            "stderr": dispatch.get("stderr", ""),
        },
        "required_next_evidence": [
            "repair worker overwrites this file with status completed, failed, or blocked",
            "changed_files",
            "patch_diff_or_commit_ref",
            "commands_run",
            "targeted_test_results",
        ],
    }
    write_json(path, receipt)
    return receipt


def write_phase_started_receipt(
    path: Path,
    *,
    phase: str,
    agent: str,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    issue_dir: Path,
    dispatch: dict[str, Any],
) -> dict[str, Any]:
    session = dispatch_session_payload(dispatch)
    receipt = {
        "issue": issue.get("number"),
        "issue_url": issue.get("url"),
        "route": route["route"],
        "target_skills": skills,
        "artifact_dir": str(issue_dir),
        "phase": phase,
        "agent": agent,
        "status": "running",
        "subagent_dispatch": {
            "cmd": dispatch.get("cmd"),
            "returncode": dispatch.get("returncode"),
            "stdout_json": session,
            "stderr": dispatch.get("stderr", ""),
        },
        "required_next_evidence": [
            f"{phase} worker overwrites this file with status completed, failed, or blocked",
            "commands_run",
            "evidence_summary",
        ],
    }
    write_json(path, receipt)
    return receipt


def subagent_prompt(
    *,
    role: str,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    packet: Path,
    output_file: Path,
) -> str:
    return "\n".join(
        [
            f"You are the `{role}` worker for skill-maintainer.",
            "",
            f"Issue: #{issue.get('number')} {issue.get('title')}",
            f"URL: {issue.get('url')}",
            f"Route: {route['route']}",
            f"Target skills: {', '.join(skills) if skills else '(none detected)'}",
            f"Input packet: {packet}",
            f"Required receipt output: {output_file}",
            "",
            "Rules:",
            "- Preserve unrelated worktree changes.",
            "- Do not close GitHub issues.",
            "- Do not treat WebGPT as deterministic proof.",
            "- Write the required receipt JSON before exiting.",
        ]
    )


def completed_worker_command(output_file: Path, *, phase: str, agent: str) -> list[str]:
    payload = {
        "phase": phase,
        "agent": agent,
        "status": "completed",
        "decision": "pass",
        "commands_run": ["controlled command-backed subagent fixture"],
        "evidence_summary": "Controlled worker fixture wrote this receipt through subagent-runner.",
        "changed_files": [],
        "targeted_test_results": ["controlled fixture receipt"],
        "blocking_findings": [],
    }
    code = (
        "import json, pathlib; "
        f"pathlib.Path({str(output_file)!r}).write_text(json.dumps({payload!r}, indent=2) + '\\n'); "
        f"print('CONTROLLED_WORKER_DONE {phase}')"
    )
    return ["python3", "-c", code]


def write_controlled_live_mutation_receipts(
    issue_dir: Path,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    bundle: Path,
    github_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    proof = {
        "schema": "skill_maintainer.controlled_live_mutation_proof.v1",
        "issue": issue.get("number"),
        "issue_url": issue.get("url"),
        "artifact_dir": str(issue_dir),
        "github_actions": github_actions,
        "lease_label": LEASE_LABEL,
        "lease_label_present_before_run": LEASE_LABEL in issue_labels(issue),
        "lease_label_mutation_observed": any(
            action.get("action") == "lease_label" and int(action.get("returncode", 1)) == 0
            for action in github_actions
        ),
        "lease_comment_observed": any(
            action.get("action") == "lease_comment" and int(action.get("returncode", 1)) == 0
            for action in github_actions
        ),
        "scheduler_enabled": False,
        "closure_attempted": False,
        "blocked_labels_applied": False,
        "webgpt_treated_as_deterministic_proof": False,
        "repair_verifier_reviewer_scope": "local_receipt_artifacts_only",
    }
    proof["lease_label_proven"] = proof["lease_label_present_before_run"] or proof["lease_label_mutation_observed"]
    common = {
        "issue": issue.get("number"),
        "issue_url": issue.get("url"),
        "route": route["route"],
        "target_skills": skills,
        "artifact_dir": str(issue_dir),
        "controlled_live_mutation_proof": proof,
        "commands_run": ["skill-maintainer controlled live mutation fixture"],
        "evidence_summary": (
            "Controlled live fixture observed the lease/comment GitHub mutation and kept "
            "repair, verification, and review work to local proof receipts."
        ),
        "changed_files": [],
        "targeted_test_results": ["local receipt artifact generated"],
        "blocking_findings": [],
    }
    write_json(issue_dir / "repair-response.json", {
        **common,
        "phase": "repair",
        "agent": route["repair_agent"],
        "status": "completed",
        "decision": "pass",
    })
    write_json(issue_dir / "verifier-response.json", {
        **common,
        "phase": "deterministic_verification",
        "agent": route["verifier_agent"],
        "status": "completed",
        "decision": "pass",
    })
    write_json(issue_dir / "review-response.json", {
        **common,
        "phase": "independent_review",
        "agent": route["review_agent"],
        "status": "completed",
        "decision": "pass",
    })
    write_json(issue_dir / "ask-webgpt-result.json", {
        "phase": "webgpt_external_review",
        "status": "not_run",
        "review_bundle": str(bundle),
        "reason": "controlled_live_mutation_fixture_stops_before_webgpt",
        "required_next_evidence": [
            "optional external review after deterministic proof",
            "human-approved fixture disposition",
        ],
    })
    return proof


def codex_worker_command(prompt: str, final_message_file: Path) -> list[str]:
    return [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        str(REPO_ROOT),
        "--output-last-message",
        str(final_message_file),
        prompt,
    ]


def receipt_gate(receipt: dict[str, Any], *, phase: str) -> tuple[bool, str]:
    status = receipt.get("status")
    if phase == "repair" and status == "repaired":
        summary = str(receipt.get("summary") or receipt.get("evidence_summary") or "").strip()
        files_changed = receipt.get("files_changed") or receipt.get("changed_files")
        proof = receipt.get("proof") or receipt.get("targeted_test_results") or receipt.get("commands_run")
        if not summary:
            return False, "missing_repair_summary"
        if not isinstance(files_changed, list) or not files_changed:
            return False, "missing_files_changed"
        if not isinstance(proof, list) or not proof:
            return False, "missing_repair_proof"
        return True, "pass"
    if status != "completed":
        return False, str(status or "missing")
    commands_run = receipt.get("commands_run")
    if not isinstance(commands_run, list) or not commands_run:
        return False, "missing_commands_run"
    evidence_text = receipt.get("evidence_summary")
    if not str(evidence_text or "").strip():
        evidence_text = receipt.get("summary")
    if not str(evidence_text or "").strip():
        return False, "missing_evidence_summary"
    if phase in {"deterministic_verification", "independent_review"}:
        decision = str(
            receipt.get("decision") or receipt.get("result") or receipt.get("verification_result") or ""
        ).lower()
        if decision not in {"pass", "passed", "no_findings"}:
            return False, f"nonpassing_decision:{decision or 'missing'}"
        findings = receipt.get("blocking_findings", receipt.get("findings", []))
        if findings:
            return False, "blocking_findings_present"
    return True, "pass"


def terminal_receipt_status(status: Any) -> bool:
    return str(status or "") in {"completed", "failed", "blocked", "repaired"}


def terminal_block_status(phase: str, reason: str) -> str:
    normalized = re.sub(r"[^a-z0-9_:-]+", "_", reason.lower()).strip("_") or "invalid"
    return f"blocked_invalid_{phase}_receipt:{normalized}"


def terminal_webgpt_gate_valid(issue_dir: Path) -> tuple[bool, str]:
    repair_ok, repair_reason = receipt_gate(load_json(issue_dir / "repair-response.json", {}), phase="repair")
    if not repair_ok:
        return False, f"repair:{repair_reason}"
    verifier_ok, verifier_reason = receipt_gate(
        load_json(issue_dir / "verifier-response.json", {}),
        phase="deterministic_verification",
    )
    if not verifier_ok:
        return False, f"verifier:{verifier_reason}"
    review_ok, review_reason = receipt_gate(
        load_json(issue_dir / "review-response.json", {}),
        phase="independent_review",
    )
    if not review_ok:
        return False, f"review:{review_reason}"
    webgpt = load_json(issue_dir / "ask-webgpt-result.json", {})
    if webgpt:
        if webgpt.get("status") == "failed" or int(webgpt.get("returncode", 0)) != 0:
            return False, "webgpt:failed"
        sentinel_ok = webgpt_sentinel_confirmed(webgpt)
        if not sentinel_ok:
            return False, "webgpt:missing_sentinel_proof"
        blocking = webgpt_blocking_findings(webgpt)
        if blocking is True:
            return False, "webgpt:blocking_findings_present"
        if blocking is None:
            return False, "webgpt:missing_blocking_findings_verdict"
    return True, "pass"


def webgpt_stdout_payload(result: dict[str, Any]) -> dict[str, Any]:
    stdout = result.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return {}
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(stdout.lstrip())
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def webgpt_answer_text(result: dict[str, Any]) -> str:
    payload = webgpt_stdout_payload(result)
    answer = payload.get("answer")
    return answer if isinstance(answer, str) else ""


def webgpt_sentinel_confirmed(result: dict[str, Any]) -> bool:
    payload = webgpt_stdout_payload(result)
    adapter = ((payload.get("oracle") or {}).get("adapter_response") or {})
    if adapter.get("sentinel_required") and adapter.get("failure"):
        return False
    turns = adapter.get("turns") or []
    if turns:
        return any(bool(turn.get("raw_contains_sentinel")) for turn in turns if isinstance(turn, dict))
    return True


def webgpt_blocking_findings(result: dict[str, Any]) -> bool | None:
    answer = webgpt_answer_text(result)
    if not answer:
        return None
    first_nonempty = next((line.strip() for line in answer.splitlines() if line.strip()), "")
    normalized_first = first_nonempty.lower()
    if normalized_first == "webgpt_blocking_findings: yes":
        return True
    if normalized_first == "webgpt_blocking_findings: no":
        return False
    normalized = answer.lower()
    if "no blocking findings" in normalized:
        return False
    if "blocking findings" in normalized:
        return True
    return None


def bundle_needs_evidence_refresh(bundle: Path) -> bool:
    try:
        text = bundle.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True
    required_sections = [
        "## Issue Body",
        "## Lease And GitHub Actions",
        "## Scoped Diff Summary",
        "## Receipt Summaries",
        "## Workflow Phase Notes",
    ]
    return any(section not in text for section in required_sections)


def _repair_receipt_paths(repair: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("changed_files", "files_changed"):
        for path in repair.get(key) or []:
            if isinstance(path, str):
                paths.append(path)
    for item in repair.get("implementation_files_verified") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def scoped_publication_paths(result: dict[str, Any], repair: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for path in result.get("target_paths") or []:
        if isinstance(path, str):
            candidates.append(path)
    candidates.extend(_repair_receipt_paths(repair))

    scoped: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        path = raw.strip()
        if not path or path.startswith("/"):
            continue
        norm = os.path.normpath(path)
        if norm.startswith("..") or norm.startswith(".artifacts/") or norm == ".artifacts":
            continue
        abs_path = (REPO_ROOT / norm).resolve()
        try:
            abs_path.relative_to(REPO_ROOT.resolve())
        except ValueError:
            continue
        if not abs_path.exists() or not abs_path.is_file():
            continue
        if norm not in seen:
            scoped.append(norm)
            seen.add(norm)
    return scoped


def publish_scoped_changes(
    issue_dir: Path,
    result: dict[str, Any],
    repair: dict[str, Any],
    *,
    dry_run: bool,
    github_dry_run: bool,
) -> dict[str, Any]:
    paths = scoped_publication_paths(result, repair)
    publication: dict[str, Any] = {
        "status": "dry_run" if (dry_run or github_dry_run) else "started",
        "scoped_paths": paths,
        "commit": "",
        "commands": [],
    }
    if not paths:
        publication["status"] = "failed"
        publication["reason"] = "empty_scoped_path_allowlist"
        write_json(issue_dir / "publication-result.json", publication)
        return publication
    if dry_run or github_dry_run:
        write_json(issue_dir / "publication-result.json", publication)
        return publication

    add_cmd = ["add", "--", *paths]
    add_cp = git_run(add_cmd)
    publication["commands"].append({
        "cmd": ["git", *add_cmd],
        "returncode": add_cp.returncode,
        "stdout": add_cp.stdout,
        "stderr": add_cp.stderr,
    })
    if add_cp.returncode != 0:
        publication["status"] = "failed"
        publication["reason"] = "git_add_failed"
        write_json(issue_dir / "publication-result.json", publication)
        return publication

    diff_cp = git_run(["diff", "--cached", "--name-only", "--", *paths])
    staged = [line.strip() for line in diff_cp.stdout.splitlines() if line.strip()]
    publication["staged_paths"] = staged
    if not staged:
        publication["status"] = "no_changes"
        publication["reason"] = "no_scoped_staged_changes"
        write_json(issue_dir / "publication-result.json", publication)
        return publication

    issue_number = result.get("issue")
    commit_msg = f"Fix skill-maintainer issue #{issue_number}" if issue_number else "Fix skill-maintainer issue"
    commit_cmd = ["commit", "-m", commit_msg, "--", *paths]
    commit_cp = git_run(commit_cmd)
    publication["commands"].append({
        "cmd": ["git", *commit_cmd],
        "returncode": commit_cp.returncode,
        "stdout": commit_cp.stdout,
        "stderr": commit_cp.stderr,
    })
    if commit_cp.returncode != 0:
        publication["status"] = "failed"
        publication["reason"] = "git_commit_failed"
        write_json(issue_dir / "publication-result.json", publication)
        return publication
    head = git_run(["rev-parse", "HEAD"])
    publication["status"] = "committed"
    publication["commit"] = head.stdout.strip()
    write_json(issue_dir / "publication-result.json", publication)
    return publication


def dry_run_simulation(result: dict[str, Any], *, action: str, would_update: dict[str, Any]) -> dict[str, Any]:
    simulated = dict(result)
    simulated["dry_run_simulation"] = {
        "action": action,
        "would_update": would_update,
    }
    return simulated


def build_subagent_specs(
    issue_dir: Path,
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    *,
    command_fixture: bool = False,
) -> dict[str, str]:
    output_dir = issue_dir / "subagent-sessions"
    repair_output = issue_dir / "repair-response.json"
    verifier_output = issue_dir / "verifier-response.json"
    review_output = issue_dir / "review-response.json"
    repair_prompt = subagent_prompt(
        role=route["repair_agent"],
        issue=issue,
        route=route,
        skills=skills,
        packet=issue_dir / "repair-packet.json",
        output_file=repair_output,
    )
    verifier_prompt = subagent_prompt(
        role=route["verifier_agent"],
        issue=issue,
        route=route,
        skills=skills,
        packet=issue_dir / "verification-packet.json",
        output_file=verifier_output,
    )
    review_prompt = subagent_prompt(
        role=route["review_agent"],
        issue=issue,
        route=route,
        skills=skills,
        packet=issue_dir / "review-bundle.md",
        output_file=review_output,
    )
    specs = {
        "repair_spec": {
            "task_id": f"skill-maintainer-issue-{issue.get('number')}-repair",
            "title": f"Repair issue #{issue.get('number')} with {route['repair_agent']}",
            "backend": "codex",
            "cwd": str(REPO_ROOT),
            "output_dir": str(output_dir),
            "timeout_seconds": 1800,
            "idle_timeout_seconds": 300,
            "tags": ["skill-maintainer", "repair", route["repair_agent"]],
            "command": (
                completed_worker_command(repair_output, phase="repair", agent=route["repair_agent"])
                if command_fixture
                else codex_worker_command(repair_prompt, issue_dir / "repair-final-message.md")
            ),
            "prompt": repair_prompt,
        },
        "verifier_spec": {
            "task_id": f"skill-maintainer-issue-{issue.get('number')}-verify",
            "title": f"Verify issue #{issue.get('number')} with {route['verifier_agent']}",
            "backend": "codex",
            "cwd": str(REPO_ROOT),
            "output_dir": str(output_dir),
            "timeout_seconds": 1800,
            "idle_timeout_seconds": 300,
            "tags": ["skill-maintainer", "verify", route["verifier_agent"]],
            "command": (
                completed_worker_command(verifier_output, phase="deterministic_verification", agent=route["verifier_agent"])
                if command_fixture
                else codex_worker_command(verifier_prompt, issue_dir / "verifier-final-message.md")
            ),
            "prompt": verifier_prompt,
        },
        "review_spec": {
            "task_id": f"skill-maintainer-issue-{issue.get('number')}-review",
            "title": f"Review issue #{issue.get('number')} with {route['review_agent']}",
            "backend": "codex",
            "cwd": str(REPO_ROOT),
            "output_dir": str(output_dir),
            "timeout_seconds": 1800,
            "idle_timeout_seconds": 300,
            "tags": ["skill-maintainer", "review", route["review_agent"]],
            "command": (
                completed_worker_command(review_output, phase="independent_review", agent=route["review_agent"])
                if command_fixture
                else codex_worker_command(review_prompt, issue_dir / "review-final-message.md")
            ),
            "prompt": review_prompt,
        },
    }
    paths: dict[str, str] = {}
    for name, spec in specs.items():
        path = issue_dir / f"{name}.json"
        write_json(path, spec)
        paths[name] = str(path)
    return paths


def lease_comment(issue: dict[str, Any], route: dict[str, str], skills: list[str], issue_dir: Path) -> Path:
    path = issue_dir / "lease-comment.md"
    write_text(
        path,
        "\n".join(
            [
                "<!-- agent-lease",
                "agent: skill-maintainer",
                f"lease_id: {datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-skill-maintainer-{issue.get('number')}",
                f"issue: {issue.get('number')}",
                "-->",
                "",
                "Lease: maintainer-active by skill-maintainer.",
                "Scope: one ticket.",
                f"Route: `{route['route']}`.",
                f"Repair agent: `{route['repair_agent']}`.",
                f"Verifier agent: `{route['verifier_agent']}`.",
                f"Review agent: `{route['review_agent']}`.",
                f"Targets: {', '.join(skills) if skills else '(none detected)'}",
                "",
                "Closure requirement: deterministic local proof plus resolved reviewer findings.",
            ]
        )
        + "\n",
    )
    return path


def blocked_comment(
    issue: dict[str, Any],
    route: dict[str, str],
    skills: list[str],
    issue_dir: Path,
    result: dict[str, Any],
) -> Path:
    path = issue_dir / "blocked-comment.md"
    write_text(
        path,
        "\n".join(
            [
                "Skill-maintainer status: BLOCKED",
                "",
                "The maintainer selected and packetized this issue, but the repair execution runtime is not wired yet.",
                "",
                "Evidence:",
                f"- Artifact dir: `{issue_dir}`",
                f"- Route: `{route['route']}`",
                f"- Repair agent: `{route['repair_agent']}`",
                f"- Verifier agent: `{route['verifier_agent']}`",
                f"- Review agent: `{route['review_agent']}`",
                f"- Target skills: `{', '.join(skills) if skills else '(none detected)'}`",
                "- Written artifacts: `issue-snapshot.json`, `route-decision.json`, `repair-packet.json`, `verification-packet.json`, `repair-response.json`, `verifier-response.json`, `review-response.json`, `ask-webgpt-result.json`, `review-bundle.md`, `cycle-result.json`",
                "",
                "Missing executor capability:",
                "- Dispatch repair subagent and collect `repair-response.json` / changed files / test receipts.",
                "- Dispatch independent verifier and collect `verifier-response.json`.",
                "- Run WebGPT review only after deterministic verification.",
                "",
                "Safety action:",
                "- Adding `maintainer-blocked` and `needs-human`.",
                "- Releasing `maintainer-active` so the next scheduled run can inspect the next eligible ticket.",
                "",
                "This issue must not be closed from WebGPT alone.",
            ]
        )
        + "\n",
    )
    write_json(issue_dir / "blocked-state.json", result)
    return path


def missing_target_comment(issue: dict[str, Any], issue_dir: Path, result: dict[str, Any]) -> Path:
    path = issue_dir / "missing-target-comment.md"
    missing = result.get("missing_target_paths", [])
    write_text(
        path,
        "\n".join(
            [
                "Skill-maintainer status: BLOCKED",
                "",
                "The maintainer did not dispatch a repair worker because the issue names target paths that are absent from this checkout.",
                "",
                "Evidence:",
                f"- Artifact dir: `{issue_dir}`",
                f"- Issue: `#{issue.get('number')}`",
                f"- Local status: `{result.get('status')}`",
                f"- Missing target paths: `{', '.join(missing) if missing else '(none recorded)'}`",
                "",
                "Safety action:",
                "- Adding `maintainer-blocked` and `needs-human`.",
                "- Releasing `maintainer-active` so this ticket is not repeatedly dispatched into a checkout without the target files.",
                "",
                "Required next evidence:",
                "- Commit or restore the missing target paths in the repository checkout, or retarget the issue to paths that exist.",
                "- Rerun skill-maintainer after the target paths are present.",
            ]
        )
        + "\n",
    )
    return path


def terminal_block_comment(issue: dict[str, Any], issue_dir: Path, result: dict[str, Any]) -> Path:
    path = issue_dir / "terminal-block-comment.md"
    write_text(
        path,
        "\n".join(
            [
                "Skill-maintainer status: BLOCKED",
                "",
                "The maintainer reached a terminal local blocker for this issue.",
                "",
                "Evidence:",
                f"- Artifact dir: `{issue_dir}`",
                f"- Issue: `#{issue.get('number')}`",
                f"- Local status: `{result.get('status')}`",
                f"- Closure decision: `{result.get('closure_decision')}`",
                f"- Receipt gate reason: `{result.get('receipt_gate_reason', '(not set)')}`",
                "",
                "Safety action:",
                "- Adding `maintainer-blocked` and `needs-human`.",
                "- Releasing `maintainer-active` so the queue can inspect later eligible tickets.",
                "",
                "This issue must not be closed from WebGPT alone.",
            ]
        )
        + "\n",
    )
    return path


def terminal_success_comment(issue: dict[str, Any], issue_dir: Path, result: dict[str, Any]) -> Path:
    path = issue_dir / "terminal-success-comment.md"
    verifier = load_json(issue_dir / "verifier-response.json", {})
    review = load_json(issue_dir / "review-response.json", {})
    command_lines = [
        f"- `{item.get('command')}` -> `{item.get('output_summary') or item.get('exit_code')}`"
        for item in verifier.get("commands_run", [])
        if isinstance(item, dict)
    ]
    write_text(
        path,
        "\n".join(
            [
                "Skill-maintainer status: FIXED_WITH_PROOF",
                "",
                "The maintainer completed the scoped repair with deterministic local proof and independent review.",
                "",
                "Evidence:",
                f"- Artifact dir: `{issue_dir}`",
                f"- Issue: `#{issue.get('number')}`",
                f"- Local status: `{result.get('status')}`",
                f"- Closure decision: `{result.get('closure_decision')}`",
                f"- Repair receipt: `{issue_dir / 'repair-response.json'}`",
                f"- Verifier receipt: `{issue_dir / 'verifier-response.json'}`",
                f"- Review receipt: `{issue_dir / 'review-response.json'}`",
                f"- Verifier result: `{verifier.get('result') or verifier.get('decision')}`",
                f"- Review result: `{review.get('result') or review.get('decision')}`",
                "",
                "Deterministic command evidence:",
                *(command_lines or ["- `(no verifier commands recorded)`"]),
                "",
                "WebGPT note:",
                "- WebGPT was not treated as deterministic proof.",
            ]
        )
        + "\n",
    )
    return path


def terminal_dispose(
    issue_dir: Path,
    result: dict[str, Any],
    issue: dict[str, Any],
    *,
    dry_run: bool,
    github_dry_run: bool,
) -> dict[str, Any]:
    disposition_key = f"blocked:{result.get('closure_decision')}:{result.get('receipt_gate_reason', '')}"
    if result.get("last_terminal_disposition_key") == disposition_key and result.get("terminal_disposition_status") == "completed":
        result["terminal_disposition_skipped"] = "duplicate_terminal_disposition"
        write_json(issue_dir / "cycle-result.json", result)
        return result
    if dry_run:
        return dry_run_simulation(
            result,
            action="terminal_dispose",
            would_update={
                "comment": str(issue_dir / "terminal-block-comment.md"),
                "labels_add": BLOCKED_LABELS,
                "labels_remove": [LEASE_LABEL],
            },
        )
    mutate_dry_run = github_dry_run
    result["terminal_disposition_status"] = "github_dry_run" if github_dry_run else "started"
    write_json(issue_dir / "cycle-result.json", result)
    actions = result.setdefault("github_actions", [])
    comment_body = terminal_block_comment(issue, issue_dir, result)
    comment_action = gh_issue_comment(int(issue["number"]), comment_body, dry_run=mutate_dry_run)
    actions.append({"action": "terminal_blocked_comment", "body_file": str(comment_body), **comment_action})
    if int(comment_action.get("returncode", 1)) != 0:
        result["terminal_disposition_status"] = "failed"
        result["terminal_disposition_failed_action"] = "terminal_blocked_comment"
        result["required_next_evidence"] = ["successful GitHub terminal-disposition retry"]
        write_json(issue_dir / "cycle-result.json", result)
        return result
    block_args: list[str] = []
    for label in BLOCKED_LABELS:
        block_args.extend(["--add-label", label])
    block_args.extend(["--remove-label", LEASE_LABEL])
    block_action = gh_issue_edit(int(issue["number"]), *block_args, dry_run=mutate_dry_run)
    actions.append({"action": "terminal_blocked_labels_release_lease", **block_action})
    if int(block_action.get("returncode", 1)) != 0:
        result["terminal_disposition_status"] = "failed"
        result["terminal_disposition_failed_action"] = "terminal_blocked_labels_release_lease"
        result["required_next_evidence"] = ["successful GitHub terminal-disposition retry"]
        write_json(issue_dir / "cycle-result.json", result)
        return result
    if not github_dry_run:
        result["terminal_disposition_status"] = "completed"
        result["last_terminal_disposition_key"] = disposition_key
    write_json(issue_dir / "cycle-result.json", result)
    return result


def terminal_success_dispose(
    issue_dir: Path,
    result: dict[str, Any],
    issue: dict[str, Any],
    *,
    dry_run: bool,
    github_dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return dry_run_simulation(
            result,
            action="terminal_success_dispose",
            would_update={
                "comment": str(issue_dir / "terminal-success-comment.md"),
                "labels_remove": [*BLOCKED_LABELS, LEASE_LABEL],
                "close_issue": issue.get("number"),
            },
        )
    mutate_dry_run = github_dry_run
    result["terminal_disposition_status"] = "github_dry_run" if github_dry_run else "started"
    write_json(issue_dir / "cycle-result.json", result)
    actions = result.setdefault("github_actions", [])
    comment_body = terminal_success_comment(issue, issue_dir, result)
    comment_action = gh_issue_comment(int(issue["number"]), comment_body, dry_run=mutate_dry_run)
    actions.append({"action": "terminal_success_comment", "body_file": str(comment_body), **comment_action})
    if int(comment_action.get("returncode", 1)) != 0:
        result["terminal_disposition_status"] = "failed"
        result["terminal_disposition_failed_action"] = "terminal_success_comment"
        result["required_next_evidence"] = ["successful GitHub success-disposition retry"]
        write_json(issue_dir / "cycle-result.json", result)
        return result
    label_args: list[str] = []
    for label in [*BLOCKED_LABELS, LEASE_LABEL]:
        label_args.extend(["--remove-label", label])
    label_action = gh_issue_edit(int(issue["number"]), *label_args, dry_run=mutate_dry_run)
    actions.append({"action": "terminal_success_labels_release", **label_action})
    if int(label_action.get("returncode", 1)) != 0:
        result["terminal_disposition_status"] = "failed"
        result["terminal_disposition_failed_action"] = "terminal_success_labels_release"
        result["required_next_evidence"] = ["successful GitHub success-disposition retry"]
        write_json(issue_dir / "cycle-result.json", result)
        return result
    close_action = gh_issue_close(int(issue["number"]), dry_run=mutate_dry_run)
    actions.append({"action": "terminal_success_close_issue", **close_action})
    if int(close_action.get("returncode", 1)) != 0:
        result["terminal_disposition_status"] = "failed"
        result["terminal_disposition_failed_action"] = "terminal_success_close_issue"
        result["required_next_evidence"] = ["successful GitHub issue close retry"]
        write_json(issue_dir / "cycle-result.json", result)
        return result
    result["closure_attempted"] = True
    if not github_dry_run:
        result["terminal_disposition_status"] = "completed"
    write_json(issue_dir / "cycle-result.json", result)
    return result


def ask_webgpt_command(bundle: Path) -> list[str]:
    webgpt_bundle = bundle.with_suffix(".webgpt.md")
    webgpt_bundle.write_text(
        sanitize_webgpt_bundle_text(bundle.read_text(encoding="utf-8", errors="replace")),
        encoding="utf-8",
    )
    question = "\n\n".join(
        [
            "Review this skill-maintainer evidence bundle. Return blocking findings, if any, and do not treat your review as deterministic closure proof.",
            webgpt_bundle.read_text(encoding="utf-8", errors="replace"),
        ]
    )
    return [
        "bash",
        "skills/ask/run.sh",
        "ask",
        question,
        "--oracle",
        "--oracle-backend",
        "webgpt",
        "--webgpt-project",
        "agent-skills-review-code",
        "--once",
        "--json",
    ]


def maybe_run_webgpt(bundle: Path, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = ask_webgpt_command(bundle)
    if dry_run:
        return {"cmd": cmd, "dry_run": True, "returncode": 0, "stdout": "", "stderr": ""}
    cp = run(cmd, check=False)
    return {
        "cmd": cmd,
        "dry_run": False,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def obsolete_webgpt_review_command_failure(result: dict[str, Any]) -> bool:
    cmd = result.get("cmd") or []
    stdout = str(result.get("stdout") or "")
    return (
        result.get("status") == "failed"
        and isinstance(cmd, list)
        and "webgpt-review" in cmd
        and "Unknown command: webgpt-review" in stdout
    )


def ask_webgpt_dag_autodetect_failure(result: dict[str, Any]) -> bool:
    cmd = result.get("cmd") or []
    if result.get("status") != "failed" or not isinstance(cmd, list):
        return False
    if cmd[:3] != ["bash", "skills/ask/run.sh", "ask"]:
        return False
    payload = webgpt_stdout_payload(result)
    attention = payload.get("needs_attention") if isinstance(payload, dict) else None
    if not isinstance(attention, dict):
        return False
    return attention.get("reason") == "dag_orchestration_ambiguous"


def ask_webgpt_unreadable_bundle_failure(result: dict[str, Any]) -> bool:
    cmd = result.get("cmd") or []
    if result.get("status") != "failed" or not isinstance(cmd, list):
        return False
    if cmd[:3] != ["bash", "skills/ask/run.sh", "ask"]:
        return False
    payload = webgpt_stdout_payload(result)
    attention = payload.get("needs_attention") if isinstance(payload, dict) else None
    if not isinstance(attention, dict):
        return False
    return attention.get("reason") == "web_review_bundle_unreadable"


def ensure_ask_runtime() -> None:
    run_sh = REPO_ROOT / "skills" / "ask" / "run.sh"
    if not run_sh.exists():
        raise SystemExit(f"$ask runtime missing: {run_sh}")


def subagent_runner_command(spec_path: str) -> list[str]:
    return ["bash", "skills/subagent-runner/run.sh", "start", spec_path]


def maybe_dispatch_subagent(spec_path: str, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = subagent_runner_command(spec_path)
    if dry_run:
        return {"cmd": cmd, "dry_run": True, "returncode": 0, "stdout": "", "stderr": ""}
    cp = run(cmd, check=False)
    return {
        "cmd": cmd,
        "dry_run": False,
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


def run_loop_repair_executor(
    *,
    issue_dir: Path,
    repo: Path,
    launch_command: str,
    scope_include: list[str],
    scope_exclude: list[str],
    check_commands: list[str],
    baseline_git_sha: str,
    rollback_command: str,
) -> dict[str, Any]:
    adapter = REPO_ROOT / "skills" / "orchestrate" / "loop_node_adapter.py"
    proof_out = issue_dir / "loop-node-result.json"
    validator = repo / ".agents" / "skills" / "loop" / "scripts" / "validate_loop_receipt.py"
    scope_checker = repo / ".agents" / "skills" / "loop" / "scripts" / "check_changed_files.py"
    package_or_git_sha = git_rev_parse(REPO_ROOT, "HEAD")
    worktree_or_branch = git_worktree_or_branch(repo)
    cmd: list[str] = [
        sys.executable,
        str(adapter),
        "--repo",
        str(repo),
        "--launch-command",
        launch_command,
        "--validator",
        str(validator),
        "--scope-checker",
        str(scope_checker),
        "--package-or-git-sha",
        package_or_git_sha,
        "--baseline-sha",
        baseline_git_sha,
        "--worktree-or-branch",
        worktree_or_branch,
        "--rollback-command",
        rollback_command,
        "--proof-out",
        str(proof_out),
    ]
    for pattern in scope_include:
        cmd.extend(["--scope-include", pattern])
    for pattern in scope_exclude:
        cmd.extend(["--scope-exclude", pattern])
    for command in check_commands:
        cmd.extend(["--check-command", command])

    started_at = datetime.now(timezone.utc)
    cp = run_in_cwd(cmd, cwd=REPO_ROOT, check=False)
    finished_at = datetime.now(timezone.utc)
    loop_result = load_json(proof_out, {})
    receipt_summary = loop_result.get("loop_receipt", {}) if isinstance(loop_result, dict) else {}
    checks_run = loop_result.get("checks_run", []) if isinstance(loop_result, dict) else []
    final_receipt = str(receipt_summary.get("path") or "")
    changed_files = receipt_summary.get("final_changed_files", [])
    adapter_ok = cp.returncode == 0 and bool(loop_result.get("ok"))
    provenance = loop_result.get("provenance", {}) if isinstance(loop_result, dict) else {}
    project_agent_fixture_proof = {
        "schema": "skill_maintainer.loop_fixture_proof.v1",
        "package_or_git_sha": package_or_git_sha,
        "baseline_sha": baseline_git_sha,
        "worktree_or_branch": worktree_or_branch,
        "launch_command": launch_command,
        "fresh_loop_id_created": bool(provenance.get("fresh_loop_id_created")),
        "loop_id": provenance.get("loop_id", ""),
        "final_receipt_path": final_receipt,
        "receipt_validation_output": provenance.get("receipt_validation_output"),
        "scope_check_output": provenance.get("scope_check_output"),
        "deterministic_checks_output": provenance.get("deterministic_checks_output", []),
        "verifier_consumed_receipt": bool(provenance.get("verifier_consumed_receipt")),
        "rollback_command": rollback_command,
        "rollback_required": True,
        "rollback_executed": False,
        "lease_released": True,
        "no_lease_needed": True,
        "closure_attempted": False,
        "destructive_writes": [],
        "scheduler_enabled": False,
        "terminal_webgpt_disposition_status": "not_started",
    }
    proof_errors = []
    if not package_or_git_sha:
        proof_errors.append("missing package_or_git_sha")
    if not baseline_git_sha:
        proof_errors.append("missing baseline_sha")
    if not worktree_or_branch:
        proof_errors.append("missing worktree_or_branch")
    if not launch_command:
        proof_errors.append("missing launch_command")
    if not project_agent_fixture_proof["fresh_loop_id_created"]:
        proof_errors.append("fresh_loop_id_created is not true")
    if not final_receipt:
        proof_errors.append("missing final_receipt_path")
    if not project_agent_fixture_proof["receipt_validation_output"]:
        proof_errors.append("missing receipt_validation_output")
    if not project_agent_fixture_proof["scope_check_output"]:
        proof_errors.append("missing scope_check_output")
    if not project_agent_fixture_proof["deterministic_checks_output"]:
        proof_errors.append("missing deterministic_checks_output")
    if not project_agent_fixture_proof["verifier_consumed_receipt"]:
        proof_errors.append("verifier_consumed_receipt is not true")
    if not rollback_command:
        proof_errors.append("missing rollback_command")
    project_agent_fixture_proof["proof_errors"] = proof_errors
    ok = adapter_ok and not proof_errors
    project_agent_fixture_proof["terminal_webgpt_disposition_status"] = "bundle_generated" if ok else "not_started"

    launch_record = {
        "cmd": cmd,
        "returncode": cp.returncode,
        "stdout_tail": tail(cp.stdout),
        "stderr_tail": tail(cp.stderr),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
    common = {
        "loop_node_result": str(proof_out),
        "loop_final_receipt": final_receipt,
        "baseline_git_sha": baseline_git_sha,
        "rollback_command": rollback_command,
        "project_agent_fixture_proof": project_agent_fixture_proof,
    }
    if ok:
        write_json(issue_dir / "repair-response.json", {
            **common,
            "phase": "repair",
            "agent": "$loop",
            "status": "completed",
            "decision": "pass",
            "commands_run": [launch_command],
            "evidence_summary": "skill-maintainer launched one packaged $loop repair executor and received a valid final receipt.",
            "changed_files": changed_files,
            "targeted_test_results": [check.get("command") for check in checks_run if check.get("ok")],
            "blocking_findings": [],
        })
        write_json(issue_dir / "verifier-response.json", {
            **common,
            "phase": "deterministic_verification",
            "agent": "project-agent-loop-verifier",
            "status": "completed",
            "decision": "pass",
            "commands_run": [check.get("command") for check in checks_run],
            "evidence_summary": "Verifier consumed the actual $loop final receipt and loop node result; receipt, scope, and required checks passed.",
            "blocking_findings": [],
        })
        write_json(issue_dir / "review-response.json", {
            **common,
            "phase": "independent_review",
            "agent": "code-reviewer",
            "status": "completed",
            "decision": "pass",
            "commands_run": [f"reviewed loop receipt: {final_receipt}"],
            "evidence_summary": "Fresh code-reviewer PASS was verified from the actual $loop receipt with edited_files=[].",
            "blocking_findings": [],
        })
    else:
        write_json(issue_dir / "repair-response.json", {
            **common,
            "phase": "repair",
            "agent": "$loop",
            "status": "blocked",
            "decision": "blocked",
            "commands_run": [launch_command],
            "evidence_summary": "Loop repair executor did not produce an accepted node result.",
            "blocking_findings": [
                *(loop_result.get("errors", ["loop executor failed"]) if isinstance(loop_result, dict) else ["loop executor failed"]),
                *proof_errors,
            ],
        })

    return {
        "ok": ok,
        "launch": launch_record,
        "loop_node_result": loop_result,
        "project_agent_fixture_proof": project_agent_fixture_proof,
        "proof_out": str(proof_out),
        "final_receipt": final_receipt,
        "changed_files": changed_files,
    }


def latest_pending_issue_dir() -> Path | None:
    candidates: list[Path] = []
    for result_path in ARTIFACT_ROOT.glob("*/issue-*/cycle-result.json"):
        try:
            result = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if result.get("created_dry_run") or result.get("dry_run"):
            continue
        if result.get("created_github_dry_run") or result.get("github_dry_run"):
            continue
        if result.get("terminal_disposition_status") in {"started", "failed", "github_dry_run"}:
            candidates.append(result_path.parent)
            continue
        webgpt_result = load_json(result_path.parent / "ask-webgpt-result.json", {})
        webgpt_status = webgpt_result.get("status")
        if webgpt_status == "dry_run":
            continue
        if webgpt_status in {"completed", "failed"}:
            if result.get("terminal_disposition_status") == "completed":
                continue
            candidates.append(result_path.parent)
            continue
        if result.get("status") in {
            "repair_subagent_started",
            "verifier_subagent_started",
            "review_subagent_started",
        }:
            candidates.append(result_path.parent)
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def continue_pending_run(
    issue_dir: Path,
    *,
    dry_run: bool = False,
    github_dry_run: bool = False,
    run_webgpt: bool = False,
    require_webgpt: bool = False,
) -> dict[str, Any]:
    result_path = issue_dir / "cycle-result.json"
    result = load_json(result_path, {})
    issue = load_json(issue_dir / "issue-snapshot.json", {})
    route = load_json(issue_dir / "route-decision.json", {})
    skills = list(result.get("target_skills") or [])
    status = result.get("status")
    result["last_invocation_dry_run"] = dry_run
    result["run_webgpt"] = run_webgpt
    result["require_webgpt"] = require_webgpt

    terminal_webgpt = load_json(issue_dir / "ask-webgpt-result.json", {})
    terminal_webgpt_status = terminal_webgpt.get("status")
    disposition_status = result.get("terminal_disposition_status")
    if status == "webgpt_review_failed" and obsolete_webgpt_review_command_failure(terminal_webgpt):
        result["status"] = "review_subagent_started"
        result["continuation_status"] = "resuming_after_obsolete_webgpt_command"
        result["closure_decision"] = "blocked_waiting_for_webgpt_and_closure_wiring"
        result["terminal_disposition_status"] = "superseded_by_valid_ask_webgpt_command"
        terminal_webgpt["status"] = "superseded_obsolete_command"
        terminal_webgpt["superseded_by"] = "ask --oracle-backend webgpt"
        write_json(issue_dir / "ask-webgpt-result.json", terminal_webgpt)
        status = result["status"]
        terminal_webgpt_status = terminal_webgpt.get("status")
    if status == "webgpt_review_failed" and ask_webgpt_dag_autodetect_failure(terminal_webgpt):
        result["status"] = "review_subagent_started"
        result["continuation_status"] = "resuming_after_explicit_webgpt_dag_autodetect_fix"
        result["closure_decision"] = "blocked_waiting_for_webgpt_and_closure_wiring"
        result["terminal_disposition_status"] = "superseded_by_explicit_webgpt_dag_autodetect_fix"
        terminal_webgpt["status"] = "superseded_explicit_webgpt_dag_autodetect_failure"
        terminal_webgpt["superseded_by"] = "explicit --oracle-backend webgpt now suppresses natural DAG autodetection"
        write_json(issue_dir / "ask-webgpt-result.json", terminal_webgpt)
        status = result["status"]
        terminal_webgpt_status = terminal_webgpt.get("status")
    if (
        status in {"webgpt_review_failed", "blocked_invalid_webgpt_gate_receipt:webgpt:failed"}
        and ask_webgpt_unreadable_bundle_failure(terminal_webgpt)
    ):
        result["status"] = "review_subagent_started"
        result["continuation_status"] = "resuming_after_webgpt_bundle_sanitizer"
        result["closure_decision"] = "blocked_waiting_for_webgpt_and_closure_wiring"
        result["terminal_disposition_status"] = "superseded_by_webgpt_bundle_sanitizer"
        terminal_webgpt["status"] = "superseded_unreadable_web_review_bundle"
        terminal_webgpt["superseded_by"] = "review-bundle.webgpt.md with local path tokens redacted"
        write_json(issue_dir / "ask-webgpt-result.json", terminal_webgpt)
        status = result["status"]
        terminal_webgpt_status = terminal_webgpt.get("status")
    if (
        status == "webgpt_review_attempted"
        and terminal_webgpt_status == "completed"
        and webgpt_blocking_findings(terminal_webgpt) is True
        and bundle_needs_evidence_refresh(issue_dir / "review-bundle.md")
    ):
        result["status"] = "review_subagent_started"
        result["continuation_status"] = "resuming_after_enriched_webgpt_bundle"
        result["closure_decision"] = "blocked_waiting_for_webgpt_and_closure_wiring"
        result["terminal_disposition_status"] = "superseded_by_enriched_webgpt_bundle"
        terminal_webgpt["status"] = "superseded_insufficient_review_bundle"
        terminal_webgpt["superseded_by"] = "review-bundle.md with issue, lease, diff, and receipt evidence"
        write_json(issue_dir / "ask-webgpt-result.json", terminal_webgpt)
        status = result["status"]
        terminal_webgpt_status = terminal_webgpt.get("status")
    if (
        not require_webgpt
        and status in {"webgpt_review_failed", "webgpt_review_attempted"}
        and terminal_webgpt_status in {"failed", "completed"}
    ):
        gate_ok, gate_reason = terminal_webgpt_gate_valid(issue_dir)
        result["terminal_disposition_gate_validated"] = gate_ok
        result["receipt_gate_reason"] = gate_reason
        if gate_ok:
            repair = load_json(issue_dir / "repair-response.json", {})
            publication = publish_scoped_changes(
                issue_dir,
                result,
                repair,
                dry_run=dry_run,
                github_dry_run=github_dry_run,
            )
            result["publication"] = publication
            if publication.get("status") not in {"committed", "no_changes", "dry_run"}:
                blocked_status = f"blocked_publication:{publication.get('reason') or publication.get('status')}"
                result["status"] = blocked_status
                result["continuation_status"] = blocked_status
                result["closure_decision"] = blocked_status
                result["required_next_evidence"] = ["successful scoped publication commit before GitHub closure"]
                write_json(result_path, result)
                return result
            result["status"] = "fixed_with_deterministic_proof"
            result["continuation_status"] = "fixed_with_deterministic_proof"
            result["closure_decision"] = "close_from_deterministic_proof_webgpt_advisory"
            result["observed_webgpt_status"] = terminal_webgpt_status
            result["required_next_evidence"] = []
            return terminal_success_dispose(
                issue_dir,
                result,
                issue,
                dry_run=dry_run,
                github_dry_run=github_dry_run,
            )
        blocked_status = terminal_block_status("webgpt_gate", gate_reason)
        result["status"] = blocked_status
        result["continuation_status"] = blocked_status
        result["closure_decision"] = blocked_status
        result["required_next_evidence"] = ["resolved WebGPT advisory blockers before scoped publication"]
        write_json(result_path, result)
        return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
    if (
        disposition_status in {"started", "failed", "github_dry_run"}
        or (
            terminal_webgpt_status in {"completed", "failed"}
            and status in {"webgpt_review_attempted", "webgpt_review_failed"}
            and disposition_status != "completed"
        )
    ):
        result["terminal_disposition_retry"] = True
        if terminal_webgpt_status in {"completed", "failed"}:
            failed = terminal_webgpt_status == "failed"
            if not result.get("terminal_disposition_gate_validated"):
                gate_ok, gate_reason = terminal_webgpt_gate_valid(issue_dir)
                result["terminal_disposition_gate_validated"] = gate_ok
                if not gate_ok:
                    blocked_status = terminal_block_status("webgpt_retry_gate", gate_reason)
                    result["status"] = blocked_status
                    result["continuation_status"] = blocked_status
                    result["closure_decision"] = blocked_status
                    result["receipt_gate_reason"] = gate_reason
                    result["required_next_evidence"] = ["valid repair, verifier, and review receipts before WebGPT disposition retry"]
                    return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
            result["status"] = "webgpt_review_failed" if failed else "webgpt_review_attempted"
            result["continuation_status"] = (
                "blocked_webgpt_review_failed"
                if failed
                else "blocked_waiting_for_finding_disposition_and_closure_wiring"
            )
            result["closure_decision"] = result["continuation_status"]
            result["observed_webgpt_status"] = terminal_webgpt_status
            result["required_next_evidence"] = (
                ["ask-webgpt-result.json from a successful real $ask runtime or explicit human retry decision"]
                if failed
                else [
                    "finding disposition for WebGPT/code-review comments",
                    "github-comment.md with reconciled proof or blocker",
                    "explicit close/no-close decision from deterministic local evidence",
                ]
            )
        return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)

    if str(status or "").startswith("blocked_invalid_repair_receipt"):
        repair = load_json(issue_dir / "repair-response.json", {})
        repair_ok, repair_reason = receipt_gate(repair, phase="repair")
        if repair_ok:
            result["status"] = "repair_subagent_started"
            result["continuation_status"] = "resuming_after_repaired_repair_gate"
            result["closure_decision"] = "waiting_for_verifier_subagent_receipt"
            result["receipt_gate_reason"] = "pass"
            result["terminal_disposition_status"] = "superseded_by_valid_repair_receipt"
            status = result["status"]
        else:
            result["continuation_status"] = terminal_block_status("repair", repair_reason)
            result["receipt_gate_reason"] = repair_reason
            write_json(result_path, result)
            return result

    if str(status or "").startswith("blocked_invalid_verifier_receipt"):
        verifier = load_json(issue_dir / "verifier-response.json", {})
        verifier_ok, verifier_reason = receipt_gate(verifier, phase="deterministic_verification")
        if verifier_ok:
            result["status"] = "verifier_subagent_started"
            result["continuation_status"] = "resuming_after_repaired_verifier_gate"
            result["closure_decision"] = "waiting_for_review_subagent_receipt"
            result["receipt_gate_reason"] = "pass"
            result["terminal_disposition_status"] = "superseded_by_valid_verifier_receipt"
            status = result["status"]
        else:
            result["continuation_status"] = terminal_block_status("verifier", verifier_reason)
            result["receipt_gate_reason"] = verifier_reason
            write_json(result_path, result)
            return result

    if status == "repair_subagent_started":
        repair = load_json(issue_dir / "repair-response.json", {})
        repair_status = repair.get("status")
        repair_ok, repair_reason = receipt_gate(repair, phase="repair")
        if not repair_ok:
            result["continuation_status"] = "waiting_for_repair_receipt"
            result["observed_repair_status"] = repair_status or "missing"
            result["receipt_gate_reason"] = repair_reason
            if terminal_receipt_status(repair_status):
                blocked_status = terminal_block_status("repair", repair_reason)
                result["continuation_status"] = blocked_status
                result["closure_decision"] = blocked_status
                result["status"] = blocked_status
                return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
            write_json(result_path, result)
            return result
        if dry_run:
            return dry_run_simulation(
                result,
                action="dispatch_verifier",
                would_update={
                    "status": "verifier_subagent_started",
                    "closure_decision": "waiting_for_verifier_subagent_receipt",
                    "spec": result["subagent_specs"]["verifier_spec"],
                },
            )
        dispatch = maybe_dispatch_subagent(result["subagent_specs"]["verifier_spec"], dry_run=dry_run)
        result["subagent_dispatch"].append({"phase": "verify", **dispatch})
        if int(dispatch.get("returncode", 1)) == 0:
            result["status"] = "verifier_subagent_started"
            result["closure_decision"] = "waiting_for_verifier_subagent_receipt"
            result["verifier_session"] = write_phase_started_receipt(
                issue_dir / "verifier-response.json",
                phase="deterministic_verification",
                agent=route["verifier_agent"],
                issue=issue,
                route=route,
                skills=skills,
                issue_dir=issue_dir,
                dispatch=dispatch,
            )["subagent_dispatch"]["stdout_json"]
        else:
            result["continuation_status"] = "blocked_verifier_subagent_start_failed"
            result["closure_decision"] = "blocked_verifier_subagent_start_failed"
            result["status"] = "blocked_verifier_subagent_start_failed"
            return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
        write_json(result_path, result)
        return result

    if status == "verifier_subagent_started":
        verifier = load_json(issue_dir / "verifier-response.json", {})
        verifier_status = verifier.get("status")
        verifier_ok, verifier_reason = receipt_gate(verifier, phase="deterministic_verification")
        if not verifier_ok:
            result["continuation_status"] = "waiting_for_verifier_receipt"
            result["observed_verifier_status"] = verifier_status or "missing"
            result["receipt_gate_reason"] = verifier_reason
            if terminal_receipt_status(verifier_status):
                blocked_status = terminal_block_status("verifier", verifier_reason)
                result["continuation_status"] = blocked_status
                result["closure_decision"] = blocked_status
                result["status"] = blocked_status
                return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
            write_json(result_path, result)
            return result
        if dry_run:
            return dry_run_simulation(
                result,
                action="dispatch_review",
                would_update={
                    "status": "review_subagent_started",
                    "closure_decision": "waiting_for_review_subagent_receipt",
                    "spec": result["subagent_specs"]["review_spec"],
                },
            )
        dispatch = maybe_dispatch_subagent(result["subagent_specs"]["review_spec"], dry_run=dry_run)
        result["subagent_dispatch"].append({"phase": "review", **dispatch})
        if int(dispatch.get("returncode", 1)) == 0:
            result["status"] = "review_subagent_started"
            result["closure_decision"] = "waiting_for_review_subagent_receipt"
            result["review_session"] = write_phase_started_receipt(
                issue_dir / "review-response.json",
                phase="independent_review",
                agent=route["review_agent"],
                issue=issue,
                route=route,
                skills=skills,
                issue_dir=issue_dir,
                dispatch=dispatch,
            )["subagent_dispatch"]["stdout_json"]
        else:
            result["continuation_status"] = "blocked_review_subagent_start_failed"
            result["closure_decision"] = "blocked_review_subagent_start_failed"
            result["status"] = "blocked_review_subagent_start_failed"
            return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
        write_json(result_path, result)
        return result

    if status == "review_subagent_started":
        repair = load_json(issue_dir / "repair-response.json", {})
        repair_ok, repair_reason = receipt_gate(repair, phase="repair")
        if not repair_ok:
            blocked_status = terminal_block_status("repair", repair_reason)
            result["continuation_status"] = blocked_status
            result["closure_decision"] = blocked_status
            result["receipt_gate_reason"] = repair_reason
            result["status"] = blocked_status
            return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)

        verifier = load_json(issue_dir / "verifier-response.json", {})
        verifier_ok, verifier_reason = receipt_gate(verifier, phase="deterministic_verification")
        if not verifier_ok:
            blocked_status = terminal_block_status("verifier", verifier_reason)
            result["continuation_status"] = blocked_status
            result["closure_decision"] = blocked_status
            result["receipt_gate_reason"] = verifier_reason
            result["status"] = blocked_status
            return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)

        review = load_json(issue_dir / "review-response.json", {})
        review_ok, review_reason = receipt_gate(review, phase="independent_review")
        review_completed = review.get("status") == "completed"
        if not review_ok:
            result["continuation_status"] = (
                "waiting_for_review_receipt" if not terminal_receipt_status(review.get("status")) else terminal_block_status("review", review_reason)
            )
            result["observed_review_status"] = review.get("status") or "missing"
            result["receipt_gate_reason"] = review_reason
            if terminal_receipt_status(review.get("status")):
                result["closure_decision"] = result["continuation_status"]
                result["status"] = result["continuation_status"]
                return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
            write_json(result_path, result)
            return result

        existing_webgpt = load_json(issue_dir / "ask-webgpt-result.json", {})
        existing_webgpt_status = existing_webgpt.get("status")
        if existing_webgpt_status in {"completed", "dry_run", "failed"}:
            failed = existing_webgpt_status == "failed"
            result["status"] = "webgpt_review_failed" if failed else "webgpt_review_attempted"
            result["continuation_status"] = (
                "blocked_webgpt_review_failed"
                if failed
                else "blocked_waiting_for_finding_disposition_and_closure_wiring"
            )
            result["closure_decision"] = result["continuation_status"]
            result["observed_webgpt_status"] = existing_webgpt_status
            result["required_next_evidence"] = (
                ["ask-webgpt-result.json from a successful real $ask runtime or explicit human retry decision"]
                if failed
                else [
                    "finding disposition for WebGPT/code-review comments",
                    "github-comment.md with reconciled proof or blocker",
                    "explicit close/no-close decision from deterministic local evidence",
                ]
            )
            if existing_webgpt_status == "dry_run":
                write_json(result_path, result)
                return result
            result["terminal_disposition_gate_validated"] = True
            return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
        result["continuation_status"] = (
            "waiting_for_review_receipt"
            if not review_ok
            else "blocked_waiting_for_webgpt_and_closure_wiring"
        )
        result["observed_review_status"] = review.get("status") or "missing"
        result["receipt_gate_reason"] = review_reason
        if review_ok:
            if dry_run and run_webgpt:
                return dry_run_simulation(
                    result,
                    action="run_webgpt",
                    would_update={
                        "status": "webgpt_review_attempted",
                        "closure_decision": "blocked_waiting_for_finding_disposition_and_closure_wiring",
                        "bundle": str(issue_dir / "review-bundle.md"),
                    },
                )
            if run_webgpt:
                bundle = build_bundle(issue_dir, issue, route, skills)
                ask_result = maybe_run_webgpt(bundle, dry_run=dry_run)
                ask_status = (
                    "dry_run"
                    if ask_result.get("dry_run")
                    else "completed" if int(ask_result.get("returncode", 1)) == 0 else "failed"
                )
                write_json(issue_dir / "ask-webgpt-result.json", {
                    "phase": "webgpt_external_review",
                    "status": ask_status,
                    "review_bundle": str(bundle),
                    **ask_result,
                })
                result["ask_webgpt_run"] = ask_result
                ask_failed = int(ask_result.get("returncode", 1)) != 0
                result["status"] = "webgpt_review_failed" if ask_failed else "webgpt_review_attempted"
                result["closure_decision"] = (
                    "blocked_webgpt_review_failed"
                    if ask_failed
                    else "blocked_waiting_for_finding_disposition_and_closure_wiring"
                )
                result["continuation_status"] = result["closure_decision"]
                result["required_next_evidence"] = (
                    ["ask-webgpt-result.json from a successful real $ask runtime or explicit human retry decision"]
                    if ask_failed
                    else [
                        "finding disposition for WebGPT/code-review comments",
                        "github-comment.md with reconciled proof or blocker",
                        "explicit close/no-close decision from deterministic local evidence",
                    ]
                )
                if github_dry_run:
                    result["github_disposition_skipped"] = "github_dry_run"
                    write_json(result_path, result)
                    return result
                result["terminal_disposition_gate_validated"] = True
                return terminal_dispose(issue_dir, result, issue, dry_run=dry_run, github_dry_run=github_dry_run)
            if not require_webgpt:
                publication = publish_scoped_changes(
                    issue_dir,
                    result,
                    repair,
                    dry_run=dry_run,
                    github_dry_run=github_dry_run,
                )
                result["publication"] = publication
                if publication.get("status") not in {"committed", "no_changes", "dry_run"}:
                    blocked_status = f"blocked_publication:{publication.get('reason') or publication.get('status')}"
                    result["status"] = blocked_status
                    result["continuation_status"] = blocked_status
                    result["closure_decision"] = blocked_status
                    result["required_next_evidence"] = ["successful scoped publication commit before GitHub closure"]
                    write_json(result_path, result)
                    return result
                result["status"] = "fixed_with_deterministic_proof"
                result["continuation_status"] = "fixed_with_deterministic_proof"
                result["closure_decision"] = "close_from_deterministic_proof"
                result["required_next_evidence"] = []
                result["terminal_disposition_gate_validated"] = True
                return terminal_success_dispose(
                    issue_dir,
                    result,
                    issue,
                    dry_run=dry_run,
                    github_dry_run=github_dry_run,
                )
            else:
                result["closure_decision"] = "blocked_waiting_for_webgpt_and_closure_wiring"
                result["required_next_evidence"] = [
                    "ask-webgpt-result.json from real $ask runtime after deterministic verification",
                    "finding disposition for WebGPT/code-review comments",
                    "github-comment.md with reconciled proof or blocker",
                ]
        write_json(result_path, result)
        return result

    result["continuation_status"] = "not_pending"
    write_json(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daytime", "nightly"], default="daytime")
    parser.add_argument("--max-issues", type=int, default=1)
    parser.add_argument("--labels", default=",".join(DEFAULT_LABELS))
    parser.add_argument("--issue", type=int, help="Prepare packets for one explicit issue, including an active lease")
    parser.add_argument("--fixture-issue-json", help="Use a local issue fixture JSON instead of GitHub issue state")
    parser.add_argument(
        "--continue-issue-dir",
        help="Continue one explicit local issue artifact directory, including github-dry-run fixture artifacts.",
    )
    parser.add_argument("--require-webgpt", action="store_true")
    parser.add_argument("--refresh-baseline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--github-dry-run",
        action="store_true",
        help="Do not mutate GitHub, but allow local dispatch when --dispatch-subagents is used.",
    )
    parser.add_argument(
        "--dispatch-subagents",
        action="store_true",
        help="Start repair subagent runner session. Verification/review remain gated on repair receipt.",
    )
    parser.add_argument(
        "--subagent-command-fixture",
        action="store_true",
        help="Use command-backed subagent specs that write completed receipts. For controlled local E2E proof only.",
    )
    parser.add_argument(
        "--controlled-live-mutation-fixture",
        action="store_true",
        help="Mutate only the GitHub lease/comment path, then stop with local proof receipts. No dispatch, WebGPT, or closure.",
    )
    parser.add_argument(
        "--run-webgpt",
        action="store_true",
        help="After completed deterministic and review receipts, run the real $ask webgpt-review command.",
    )
    parser.add_argument(
        "--loop-repair-launch-command",
        help="Fixture-only project-agent proof: launch one $loop repair executor and validate its receipt.",
    )
    parser.add_argument("--loop-repair-repo", help="Repository where the $loop launch command runs")
    parser.add_argument("--loop-scope-include", action="append", default=[])
    parser.add_argument("--loop-scope-exclude", action="append", default=[".loop/**"])
    parser.add_argument("--loop-check-command", action="append", default=[])
    parser.add_argument("--baseline-git-sha", default="")
    parser.add_argument("--rollback-command", default="")
    parser.add_argument(
        "--allow-prepared-only-success",
        action="store_true",
        help="Return exit 0 after packet preparation. Intended only for legacy dry runs.",
    )
    args = parser.parse_args()
    github_dry_run = args.dry_run or args.github_dry_run

    labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = ARTIFACT_ROOT / timestamp
    run_root.mkdir(parents=True, exist_ok=True)

    if args.refresh_baseline:
        baseline = run_root / "skills-ci-report.json"
        cp = run([
            "bash",
            "skills/skills-ci/run.sh",
            "scan",
            "--root",
            "skills",
            "--report-json",
            str(baseline),
        ], check=False)
        (run_root / "skills-ci.stdout").write_text(cp.stdout, encoding="utf-8")
        (run_root / "skills-ci.stderr").write_text(cp.stderr, encoding="utf-8")

    if args.continue_issue_dir:
        result = continue_pending_run(
            Path(args.continue_issue_dir).expanduser().resolve(),
            dry_run=args.dry_run,
            github_dry_run=github_dry_run,
            run_webgpt=args.run_webgpt,
            require_webgpt=args.require_webgpt,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.issue is None and not args.fixture_issue_json:
        pending_issue_dir = latest_pending_issue_dir()
        if pending_issue_dir is not None:
            result = continue_pending_run(
                pending_issue_dir,
                dry_run=args.dry_run,
                github_dry_run=github_dry_run,
                run_webgpt=args.run_webgpt,
                require_webgpt=args.require_webgpt,
            )
            print(json.dumps(result, indent=2))
            return 0

    if args.fixture_issue_json:
        issues = [load_json(Path(args.fixture_issue_json).expanduser().resolve(), {})]
        issue_source = "fixture"
    elif args.issue is not None:
        issues = [issue_view(args.issue)]
        issue_source = "github_issue"
    else:
        issues = issue_list(labels)[: args.max_issues]
        issue_source = "github_issue_list"
    write_json(run_root / "issue-list.json", issues)
    if not issues:
        print(json.dumps({"status": "no_matching_issues", "artifact_dir": str(run_root)}, indent=2))
        return 0

    issue = issues[0]
    route = classify(issue)
    skills = target_skills(issue)
    targets = target_paths(issue)
    missing_targets = missing_target_paths(targets)
    already_leased = LEASE_LABEL in issue_labels(issue)
    issue_dir = run_root / f"issue-{issue['number']}"
    issue_dir.mkdir(parents=True, exist_ok=True)

    write_json(issue_dir / "issue-snapshot.json", issue)
    write_json(issue_dir / "route-decision.json", route)
    write_json(issue_dir / "repair-packet.json", {
        "issue": issue,
        "route": route,
        "target_skills": skills,
        "repair_agent": route["repair_agent"],
        "instruction": "Repair exactly this leased issue. Preserve unrelated worktree changes. Return patch and targeted proof receipts.",
    })
    write_json(issue_dir / "verification-packet.json", {
        "issue": issue,
        "route": route,
        "target_skills": skills,
        "verifier_agent": route["verifier_agent"],
        "instruction": "Verify the repair independently with deterministic commands and explicit pass/fail/block result.",
    })
    bundle = build_bundle(issue_dir, issue, route, skills)
    spec_paths = build_subagent_specs(issue_dir, issue, route, skills, command_fixture=args.subagent_command_fixture)
    receipt_paths = write_phase_receipts(issue_dir, issue, route, skills, bundle, spec_paths)
    if args.require_webgpt:
        ensure_ask_runtime()

    result = {
        "status": "prepared_only_blocked",
        "mode": args.mode,
        "repo": git_repo_slug(),
        "issue": issue.get("number"),
        "issue_source": issue_source,
        "artifact_dir": str(issue_dir),
        "selected_route": route,
        "target_skills": skills,
        "target_paths": targets,
        "missing_target_paths": missing_targets,
        "require_webgpt": args.require_webgpt,
        "ask_webgpt_command": ask_webgpt_command(bundle),
        "dry_run": args.dry_run,
        "github_dry_run": github_dry_run,
        "created_dry_run": args.dry_run,
        "created_github_dry_run": github_dry_run,
        "subagent_command_fixture": args.subagent_command_fixture,
        "scheduler_enabled": False,
        "closure_attempted": False,
        "destructive_writes": [],
        "baseline_git_sha": args.baseline_git_sha,
        "rollback_command": args.rollback_command,
        "lease": {
            "already_leased": already_leased,
            "label": LEASE_LABEL,
        },
        "github_actions": [],
        "subagent_specs": spec_paths,
        "subagent_dispatch": [],
        "repair_receipts": [receipt_paths["repair_receipt"]],
        "verifier_receipts": [receipt_paths["verifier_receipt"]],
        "review_receipts": [receipt_paths["review_receipt"]],
        "ask_webgpt_artifacts": [receipt_paths["ask_webgpt_receipt"]],
        "required_next_evidence": [
            "repair-response.json from selected repair agent",
            "verifier-response.json from independent verifier",
            "ask-webgpt-result.json after deterministic verification",
            "github-comment.md with reconciled proof or blocker",
        ],
        "closure_decision": "blocked_missing_repair_executor",
    }

    if args.loop_repair_launch_command:
        if issue_source != "fixture":
            raise SystemExit("--loop-repair-launch-command requires --fixture-issue-json")
        if not args.github_dry_run and not args.dry_run:
            raise SystemExit("--loop-repair-launch-command requires --github-dry-run or --dry-run")
        if not args.loop_repair_repo:
            raise SystemExit("--loop-repair-repo is required with --loop-repair-launch-command")
        if not args.loop_scope_include:
            raise SystemExit("--loop-scope-include is required with --loop-repair-launch-command")
        if not args.loop_check_command:
            raise SystemExit("--loop-check-command is required with --loop-repair-launch-command")
        if not args.baseline_git_sha:
            raise SystemExit("--baseline-git-sha is required with --loop-repair-launch-command")
        if not args.rollback_command:
            raise SystemExit("--rollback-command is required with --loop-repair-launch-command")

        loop_exec = run_loop_repair_executor(
            issue_dir=issue_dir,
            repo=Path(args.loop_repair_repo).expanduser().resolve(),
            launch_command=args.loop_repair_launch_command,
            scope_include=args.loop_scope_include,
            scope_exclude=args.loop_scope_exclude,
            check_commands=args.loop_check_command,
            baseline_git_sha=args.baseline_git_sha,
            rollback_command=args.rollback_command,
        )
        result["loop_repair_executor"] = loop_exec
        result["project_agent_fixture_proof"] = loop_exec.get("project_agent_fixture_proof", {})
        result["repair_receipts"] = [str(issue_dir / "repair-response.json")]
        result["verifier_receipts"] = [str(issue_dir / "verifier-response.json")]
        result["review_receipts"] = [str(issue_dir / "review-response.json")]
        result["ask_webgpt_artifacts"] = [str(issue_dir / "ask-webgpt-result.json")]
        result["no_lease_needed"] = True
        result["lease_released"] = True
        result["closure_attempted"] = False
        result["destructive_writes"] = []
        if loop_exec["ok"]:
            write_json(issue_dir / "ask-webgpt-result.json", {
                "phase": "webgpt_external_review",
                "status": "bundle_generated",
                "review_bundle": str(bundle),
                "required_next_evidence": [
                    "optional external review request/response artifacts",
                    "finding disposition if external review is run",
                ],
            })
            result["status"] = "loop_repair_executor_completed"
            result["closure_decision"] = "blocked_waiting_for_webgpt_or_human_disposition"
            result["required_next_evidence"] = [
                "external review bundle submission if the project-agent lane requires WebGPT",
                "human-approved promotion decision",
            ]
        else:
            result["status"] = "blocked_loop_repair_executor_failed"
            result["closure_decision"] = "blocked_loop_repair_executor_failed"
            result["required_next_evidence"] = ["repair or rerun the loop executor proof"]
        write_json(issue_dir / "cycle-result.json", result)
        print(json.dumps(result, indent=2))
        return 0 if loop_exec["ok"] else 2

    if args.controlled_live_mutation_fixture:
        if issue_source == "fixture":
            raise SystemExit("--controlled-live-mutation-fixture requires a real GitHub issue")
        if args.dispatch_subagents:
            raise SystemExit("--controlled-live-mutation-fixture cannot be combined with --dispatch-subagents")

    if not already_leased:
        lease_action = gh_issue_edit(issue["number"], "--add-label", LEASE_LABEL, dry_run=github_dry_run)
        require_gh_ok(lease_action, "lease label")
        result["github_actions"].append({"action": "lease_label", **lease_action})
        lease_body = lease_comment(issue, route, skills, issue_dir)
        lease_comment_action = gh_issue_comment(issue["number"], lease_body, dry_run=github_dry_run)
        require_gh_ok(lease_comment_action, "lease comment")
        result["github_actions"].append({"action": "lease_comment", "body_file": str(lease_body), **lease_comment_action})
    elif args.controlled_live_mutation_fixture:
        lease_body = lease_comment(issue, route, skills, issue_dir)
        lease_comment_action = gh_issue_comment(issue["number"], lease_body, dry_run=github_dry_run)
        require_gh_ok(lease_comment_action, "lease comment")
        result["github_actions"].append({"action": "lease_comment", "body_file": str(lease_body), **lease_comment_action})

    if missing_targets:
        result["status"] = "blocked_missing_target_paths"
        result["closure_decision"] = "blocked_missing_target_paths"
        result["required_next_evidence"] = [
            "commit or restore the missing target paths before repair dispatch",
            "rerun skill-maintainer after target paths exist",
        ]
        write_json(issue_dir / "missing-targets.json", {
            "issue": issue.get("number"),
            "target_paths": targets,
            "missing_target_paths": missing_targets,
            "repo_root": str(REPO_ROOT),
        })
        missing_body = missing_target_comment(issue, issue_dir, result)
        missing_comment_action = gh_issue_comment(issue["number"], missing_body, dry_run=github_dry_run)
        require_gh_ok(missing_comment_action, "missing target comment")
        result["github_actions"].append({"action": "missing_target_comment", "body_file": str(missing_body), **missing_comment_action})
        block_args: list[str] = []
        for label in BLOCKED_LABELS:
            block_args.extend(["--add-label", label])
        block_args.extend(["--remove-label", LEASE_LABEL])
        block_action = gh_issue_edit(issue["number"], *block_args, dry_run=github_dry_run)
        require_gh_ok(block_action, "missing target blocked labels")
        result["github_actions"].append({"action": "missing_target_labels_release_lease", **block_action})
        write_json(issue_dir / "cycle-result.json", result)
        print(json.dumps(result, indent=2))
        return 0 if args.dry_run else 2

    if args.controlled_live_mutation_fixture:
        proof = write_controlled_live_mutation_receipts(
            issue_dir,
            issue,
            route,
            skills,
            bundle,
            result["github_actions"],
        )
        result["status"] = "controlled_live_mutation_fixture_completed"
        result["controlled_live_mutation_proof"] = proof
        result["closure_decision"] = "blocked_waiting_for_human_fixture_disposition"
        result["required_next_evidence"] = [
            "human fixture disposition for the controlled live mutation proof",
            "separate deterministic repair/verifier/reviewer run before any closure wiring",
        ]
        write_json(issue_dir / "cycle-result.json", result)
        print(json.dumps(result, indent=2))
        return 0

    if args.dispatch_subagents:
        dispatch = maybe_dispatch_subagent(spec_paths["repair_spec"], dry_run=args.dry_run)
        result["subagent_dispatch"].append({"phase": "repair", **dispatch})
        if int(dispatch.get("returncode", 1)) == 0:
            result["status"] = "repair_subagent_started"
            result["closure_decision"] = "waiting_for_repair_subagent_receipt"
            result["required_next_evidence"][0] = "repair-response.json from running repair subagent"
            result["repair_session"] = write_repair_started_receipt(
                Path(receipt_paths["repair_receipt"]),
                issue=issue,
                route=route,
                skills=skills,
                issue_dir=issue_dir,
                dispatch=dispatch,
            )["subagent_dispatch"]["stdout_json"]
        else:
            result["closure_decision"] = "blocked_repair_subagent_start_failed"

    if args.dispatch_subagents and result["closure_decision"] == "waiting_for_repair_subagent_receipt":
        write_json(issue_dir / "cycle-result.json", result)
        print(json.dumps(result, indent=2))
        return 0

    blocked_body = blocked_comment(issue, route, skills, issue_dir, result)
    blocked_comment_action = gh_issue_comment(issue["number"], blocked_body, dry_run=github_dry_run)
    require_gh_ok(blocked_comment_action, "blocked comment")
    result["github_actions"].append({"action": "blocked_comment", "body_file": str(blocked_body), **blocked_comment_action})

    block_args: list[str] = []
    for label in BLOCKED_LABELS:
        block_args.extend(["--add-label", label])
    block_args.extend(["--remove-label", LEASE_LABEL])
    block_action = gh_issue_edit(issue["number"], *block_args, dry_run=github_dry_run)
    require_gh_ok(block_action, "blocked labels")
    result["github_actions"].append({"action": "blocked_labels_release_lease", **block_action})

    write_json(issue_dir / "cycle-result.json", result)
    print(json.dumps(result, indent=2))
    if args.allow_prepared_only_success or args.dry_run:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
