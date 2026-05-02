#!/usr/bin/env python3
"""Deterministic pre-plan governance gate."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False


load_dotenv()

APP = typer.Typer(help="Create and check deterministic pre-plan governance reports.")
SCHEMA = "governance.pre_plan_report.v1"
GATE_QUESTION = (
    "Have you read all relevant files required to fully understand deeply how to "
    "correctly implement with confidence?"
)
DEFAULT_ARTIFACT_ROOT = Path("/mnt/storage12tb/skills/governance")
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
SAFE_EXTERNAL_ROOTS = (Path("/mnt/storage12tb"), Path("/tmp"))
UNSAFE_ARTIFACT_ENV = "GOVERNANCE_ALLOW_UNSAFE_ARTIFACT_ROOT"
TEST_EVIDENCE_ENV = "GOVERNANCE_ALLOW_TMP_EVIDENCE"
URI_DIGEST_RE = re.compile(r"(^|[#?&])sha256=([0-9a-fA-F]{64})(?:$|[&#])")
SCOPED_CONTEXT_PATHS = (
    "skills/governance/SKILL.md",
    "skills/governance/agents/openai.yaml",
    "skills/governance/pyproject.toml",
    "skills/governance/run.sh",
    "skills/governance/sanity.sh",
    "skills/governance/scripts/governance_loop.py",
    "skills/governance/tests/test_governance_loop.py",
    "skills/governance/uv.lock",
    "skills/plan/SKILL.md",
    "skills/plan/plan.py",
    "skills/plan/pyproject.toml",
    "skills/plan/run.sh",
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)


def _git_output(args: list[str], cwd: Path) -> str:
    try:
        result = _run_git(args, cwd)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _repo_root(start: Optional[Path] = None) -> Path:
    start_path = (start or Path.cwd()).resolve()
    root = _git_output(["rev-parse", "--show-toplevel"], start_path)
    if root:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[3]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8", errors="replace"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_task(task: str) -> str:
    return re.sub(r"\s+", " ", task.strip()).lower()


def _task_hash(task: str) -> str:
    return _sha256_text(_normalize_task(task))[:16]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unsafe_storage_allowed() -> bool:
    return os.environ.get(UNSAFE_ARTIFACT_ENV) == "1"


def _validate_artifact_root(path: Path, *, purpose: str) -> None:
    resolved = path.expanduser().resolve()
    if _unsafe_storage_allowed():
        return

    repo = _repo_root()
    if _is_relative_to(resolved, repo):
        raise typer.BadParameter(
            f"{purpose} path is inside the repository: {resolved}. "
            f"Use /mnt/storage12tb or /tmp for tests, or set {UNSAFE_ARTIFACT_ENV}=1."
        )

    if not any(_is_relative_to(resolved, root) for root in SAFE_EXTERNAL_ROOTS):
        roots = ", ".join(str(root) for root in SAFE_EXTERNAL_ROOTS)
        raise typer.BadParameter(f"{purpose} path must be under one of: {roots}. Got: {resolved}")


def _artifact_root(output_dir: Optional[str] = None) -> Path:
    if output_dir:
        root = Path(output_dir).expanduser().resolve()
        _validate_artifact_root(root, purpose="governance output")
        return root

    configured = os.environ.get("GOVERNANCE_ARTIFACT_ROOT") or os.environ.get("AGENT_SKILLS_ARTIFACT_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
        if root.name != "governance":
            root = root / "governance"
        _validate_artifact_root(root, purpose="governance artifact root")
        return root

    _validate_artifact_root(DEFAULT_ARTIFACT_ROOT, purpose="governance artifact root")
    return DEFAULT_ARTIFACT_ROOT


def _tmp_evidence_allowed(allow_test_evidence_root: bool = False) -> bool:
    return allow_test_evidence_root or os.environ.get(TEST_EVIDENCE_ENV) == "1"


def _allowed_evidence_roots(repo_root: Path, *, allow_test_evidence_root: bool = False) -> tuple[Path, ...]:
    roots = [repo_root, Path("/mnt/storage12tb")]
    if _tmp_evidence_allowed(allow_test_evidence_root):
        roots.append(Path("/tmp"))
    return tuple(roots)


def _is_uri_evidence(value: str) -> bool:
    return re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value) is not None


def _uri_evidence(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    match = URI_DIGEST_RE.search(raw)
    if not match:
        return None, f"URI evidence requires sha256=<64 hex>: {raw}"
    return {"type": "uri", "uri": raw, "sha256": match.group(2).lower()}, None


def _file_evidence(
    raw: str,
    repo_root: Path,
    *,
    allow_test_evidence_root: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    raw_path = Path(raw).expanduser()
    path = raw_path if raw_path.is_absolute() else repo_root / raw_path
    path = path.resolve()

    allowed_roots = _allowed_evidence_roots(repo_root, allow_test_evidence_root=allow_test_evidence_root)
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        return None, f"Evidence path is outside allowed roots ({roots}): {raw}"
    if not path.exists():
        return None, f"Evidence path does not exist: {raw}"
    if not path.is_file():
        return None, f"Evidence path is not a file: {raw}"

    stat = path.stat()
    if stat.st_size <= 0:
        return None, f"Evidence file is empty: {raw}"

    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel = str(path)

    return {
        "type": "file",
        "path": rel,
        "absolute_path": str(path),
        "sha256": _sha256_file(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }, None


def _evidence_entries(
    files_read: list[str],
    repo_root: Path,
    *,
    allow_test_evidence_root: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()

    for raw in files_read:
        value = raw.strip()
        if not value:
            errors.append("Evidence entry is empty")
            continue
        if value in seen:
            continue
        seen.add(value)

        if _is_uri_evidence(value):
            entry, error = _uri_evidence(value)
        else:
            entry, error = _file_evidence(value, repo_root, allow_test_evidence_root=allow_test_evidence_root)
        if error:
            errors.append(error)
        elif entry:
            entries.append(entry)

    return entries, errors


def _has_repo_file_evidence(evidence: list[dict[str, Any]], repo_root: Path) -> bool:
    for entry in evidence:
        if entry.get("type") != "file":
            continue
        absolute_path = entry.get("absolute_path")
        if isinstance(absolute_path, str) and _is_relative_to(Path(absolute_path), repo_root):
            return True
    return False


def _skill_doc_entries(skills: list[str], repo_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for skill_name in sorted({skill.strip() for skill in skills if skill.strip()}):
        skill_doc = repo_root / "skills" / skill_name / "SKILL.md"
        if not skill_doc.is_file() or skill_doc.stat().st_size <= 0:
            continue
        entries.append({
            "skill": skill_name,
            "path": skill_doc.relative_to(repo_root).as_posix(),
            "sha256": _sha256_file(skill_doc),
            "size": skill_doc.stat().st_size,
            "mtime_ns": skill_doc.stat().st_mtime_ns,
        })
    return entries


def _repo_relative_evidence_paths(evidence: list[dict[str, Any]], repo_root: Path) -> list[str]:
    paths: list[str] = []
    for entry in evidence:
        if entry.get("type") != "file":
            continue
        absolute_path = entry.get("absolute_path")
        if not isinstance(absolute_path, str):
            continue
        path = Path(absolute_path)
        if not _is_relative_to(path, repo_root):
            continue
        try:
            paths.append(path.resolve().relative_to(repo_root).as_posix())
        except ValueError:
            continue
    return paths


def _git_status(repo_root: Path, paths: list[str] | None = None) -> str:
    args = ["status", "--porcelain=v1", "--untracked-files=all"]
    if paths:
        args.extend(["--", *paths])
    return _git_output(args, repo_root)


def _git_context(repo_root: Path, *, scoped_paths: list[str]) -> dict[str, Any]:
    head = _git_output(["rev-parse", "HEAD"], repo_root) or "unknown"
    branch = _git_output(["branch", "--show-current"], repo_root) or "unknown"
    full_status = _git_status(repo_root)
    scoped_status = _git_status(repo_root, scoped_paths)
    return {
        "repo_root": str(repo_root),
        "git_head": head,
        "git_branch": branch,
        "full_git_status_sha256": _sha256_text(full_status),
        "full_git_status_porcelain": full_status,
        "scoped_git_status_sha256": _sha256_text(scoped_status),
        "scoped_git_status_porcelain": scoped_status,
        "scoped_paths": scoped_paths,
    }


def _context_fingerprint(
    *,
    task: str,
    files_read: list[str],
    skills_used: list[str],
    allow_test_evidence_root: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    repo_root = _repo_root()
    evidence, evidence_errors = _evidence_entries(
        files_read,
        repo_root,
        allow_test_evidence_root=allow_test_evidence_root,
    )
    skill_docs = _skill_doc_entries(skills_used, repo_root)
    scoped_paths = sorted({
        *SCOPED_CONTEXT_PATHS,
        *(entry["path"] for entry in skill_docs),
        *_repo_relative_evidence_paths(evidence, repo_root),
    })
    repo_context = _git_context(repo_root, scoped_paths=scoped_paths)
    context: dict[str, Any] = {
        "task_normalized": _normalize_task(task),
        "repo": repo_context,
        "evidence": evidence,
        "skill_docs": skill_docs,
        "policy": {
            "allow_tmp_evidence": _tmp_evidence_allowed(allow_test_evidence_root),
            "normal_pass_requires_repo_file_evidence": True,
        },
    }
    stable_context = {
        "task_normalized": context["task_normalized"],
        "repo": {
            "repo_root": repo_context["repo_root"],
            "git_head": repo_context["git_head"],
            "git_branch": repo_context["git_branch"],
            "scoped_git_status_sha256": repo_context["scoped_git_status_sha256"],
            "scoped_paths": repo_context["scoped_paths"],
        },
        "evidence": context["evidence"],
        "skill_docs": context["skill_docs"],
    }
    context["fingerprint_sha256"] = _sha256_text(json.dumps(stable_context, sort_keys=True))
    return context, evidence_errors


def _html_list(items: list[str]) -> str:
    if not items:
        return "<li>None recorded</li>"
    return "\n".join(f"<li>{html.escape(item)}</li>" for item in items)


def _context_rows(context: dict[str, Any]) -> str:
    repo = context.get("repo") or {}
    rows = [
        ("Repository", str(repo.get("repo_root", "unknown"))),
        ("Git head", str(repo.get("git_head", "unknown"))),
        ("Scoped git status digest", str(repo.get("scoped_git_status_sha256", "unknown"))),
        ("Full git status digest", str(repo.get("full_git_status_sha256", "unknown"))),
        ("Fingerprint", str(context.get("fingerprint_sha256", "unknown"))),
    ]
    return "\n".join(
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td><code>{html.escape(value)}</code></td>"
        "</tr>"
        for label, value in rows
    )


def _render_html(report: dict[str, Any]) -> str:
    status = report["status"]
    status_class = "pass" if status == "PASS" else "blocked"
    checks = report["checks"]
    check_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(check['id'])}</td>"
        f"<td><span class=\"pill {html.escape(check['status'].lower())}\">{html.escape(check['status'])}</span></td>"
        f"<td>{html.escape(check['detail'])}</td>"
        "</tr>"
        for check in checks
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Governance Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1d2433;
      --muted: #5b6472;
      --line: #d6dbe3;
      --paper: #ffffff;
      --band: #f5f7fa;
      --pass: #176b3a;
      --blocked: #a23b2a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--band);
      line-height: 1.45;
    }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 48px; }}
    header, section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin: 14px 0;
    }}
    header {{ padding: 24px; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0 0 10px; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 4px 10px;
      border-radius: 6px;
      color: #fff;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .status.pass {{ background: var(--pass); }}
    .status.blocked {{ background: var(--blocked); }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    ul {{ margin: 0; padding-left: 20px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 700; }}
    .pill {{ display: inline-block; border-radius: 5px; padding: 2px 8px; font-weight: 700; color: #fff; }}
    .pill.pass {{ background: var(--pass); }}
    .pill.fail {{ background: var(--blocked); }}
    .task {{ font-weight: 700; overflow-wrap: anywhere; }}
    code {{ background: #eef1f5; border-radius: 4px; padding: 2px 5px; overflow-wrap: anywhere; }}
    @media (max-width: 760px) {{
      main {{ padding: 20px 12px 32px; }}
      .grid {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="status {status_class}">{html.escape(status)}</div>
      <h1>Pre-Plan Governance Report</h1>
      <p class="task">{html.escape(report["task"])}</p>
      <p class="meta">Task hash: <code>{html.escape(report["task_hash"])}</code> | Created: {html.escape(report["created_at"])}</p>
    </header>

    <section>
      <h2>Gate Question</h2>
      <p>{html.escape(report["gate_question"])}</p>
      <p><strong>Answer:</strong> {html.escape(report["gate_answer"])}</p>
    </section>

    <section>
      <h2>Deterministic Checks</h2>
      <table>
        <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>{check_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Context Fingerprint</h2>
      <table><tbody>{_context_rows(report.get("context", {}))}</tbody></table>
    </section>

    <div class="grid">
      <section>
        <h2>Files Read</h2>
        <ul>{_html_list(report["files_read"])}</ul>
      </section>
      <section>
        <h2>Skills Used</h2>
        <ul>{_html_list(report["skills_used"])}</ul>
      </section>
      <section>
        <h2>Assumptions</h2>
        <ul>{_html_list(report["assumptions"])}</ul>
      </section>
      <section>
        <h2>Risks</h2>
        <ul>{_html_list(report["risks"])}</ul>
      </section>
    </div>

    <section>
      <h2>Unknowns</h2>
      <ul>{_html_list(report["unknowns"])}</ul>
    </section>

    <section>
      <h2>Required Next Actions</h2>
      <ul>{_html_list(report["required_next_actions"])}</ul>
    </section>
  </main>
</body>
</html>
"""


def _build_checks(
    *,
    files_read: list[str],
    evidence_errors: list[str],
    has_repo_file_evidence: bool,
    allow_test_evidence_root: bool,
    unknowns: list[str],
    understanding_confirmed: bool,
    needs_interview: bool,
    needs_research: bool,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    checks.append({
        "id": "understanding_confirmed",
        "status": "PASS" if understanding_confirmed else "FAIL",
        "detail": "Agent explicitly confirmed the gate question." if understanding_confirmed else "Run /interview, /dogpile, or read more files before planning.",
    })
    checks.append({
        "id": "evidence_present",
        "status": "PASS" if files_read else "FAIL",
        "detail": f"{len(files_read)} evidence item(s) recorded." if files_read else "No files or artifacts were recorded as read.",
    })
    checks.append({
        "id": "evidence_valid",
        "status": "PASS" if not evidence_errors else "FAIL",
        "detail": "All evidence paths/URIs resolved and were fingerprinted." if not evidence_errors else "; ".join(evidence_errors[:3]),
    })
    checks.append({
        "id": "repo_file_evidence",
        "status": "PASS" if has_repo_file_evidence or _tmp_evidence_allowed(allow_test_evidence_root) else "FAIL",
        "detail": (
            "At least one repository file was recorded as evidence."
            if has_repo_file_evidence
            else "Test evidence root override enabled."
            if _tmp_evidence_allowed(allow_test_evidence_root)
            else "Normal PASS requires at least one repository file evidence item; /tmp and URI-only evidence are test-only."
        ),
    })
    checks.append({
        "id": "unknowns_resolved",
        "status": "PASS" if not unknowns else "FAIL",
        "detail": "No unresolved unknowns recorded." if not unknowns else f"{len(unknowns)} unresolved unknown(s) remain.",
    })
    checks.append({
        "id": "human_decision_gate",
        "status": "FAIL" if needs_interview else "PASS",
        "detail": "Human interview is required before planning." if needs_interview else "No human decision blocker recorded.",
    })
    checks.append({
        "id": "research_gate",
        "status": "FAIL" if needs_research else "PASS",
        "detail": "Research/dogpile is required before planning." if needs_research else "No research blocker recorded.",
    })
    return checks


def _required_actions(checks: list[dict[str, str]]) -> list[str]:
    actions: list[str] = []
    failed = {check["id"] for check in checks if check["status"] != "PASS"}
    if "evidence_present" in failed or "evidence_valid" in failed:
        actions.append("Read valid files/artifacts and rerun /governance with evidence paths or digest-bearing URIs.")
    if "repo_file_evidence" in failed:
        actions.append("Record at least one relevant repository file as evidence before planning.")
    if "understanding_confirmed" in failed:
        actions.append("Do not plan yet; close the understanding gap before setting --understanding-confirmed.")
    if "unknowns_resolved" in failed:
        actions.append("Resolve unknowns through more file reading, /interview, or /dogpile.")
    if "human_decision_gate" in failed:
        actions.append("Use /interview to collect the missing human decision.")
    if "research_gate" in failed:
        actions.append("Use /dogpile for research insight, then rerun /governance.")
    if not actions:
        actions.append("Proceed to /plan.")
    return actions


def _latest_path(root: Path, task_hash: str) -> Path:
    return root / "reports" / task_hash / "latest.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _load_latest(root: Path, task_hash: str) -> Optional[dict[str, Any]]:
    path = _latest_path(root, task_hash)
    if not path.exists():
        return None
    return _load_json(path)


def _status_result(status_value: str, task: str, task_hash: str, message: str, actions: list[str]) -> dict[str, Any]:
    return {
        "task": task,
        "task_hash": task_hash,
        "status": status_value,
        "message": message,
        "required_next_actions": actions,
    }


def _validate_report_for_task(
    *,
    latest: dict[str, Any],
    task: str,
    task_hash: str,
    max_age_seconds: int,
    allow_test_evidence_root: bool,
) -> dict[str, Any]:
    report_path_value = latest.get("report_json")
    if not isinstance(report_path_value, str) or not report_path_value:
        return _status_result("INVALID", task, task_hash, "latest.json does not contain report_json.", ["Rerun /governance."])

    report_path = Path(report_path_value).expanduser().resolve()
    if not report_path.is_file():
        return _status_result("INVALID", task, task_hash, f"Referenced report does not exist: {report_path}", ["Rerun /governance."])

    try:
        report = _load_json(report_path)
    except Exception as exc:
        return _status_result("INVALID", task, task_hash, f"Cannot load report JSON: {exc}", ["Rerun /governance."])

    if report.get("schema") != SCHEMA:
        return _status_result("INVALID", task, task_hash, "Report schema mismatch.", ["Rerun /governance with the current skill version."])
    if report.get("task_hash") != task_hash or _normalize_task(str(report.get("task", ""))) != _normalize_task(task):
        return _status_result("INVALID", task, task_hash, "Report task does not match requested task.", ["Rerun /governance for the exact task text."])
    if report.get("status") != "PASS":
        result = dict(report)
        result["status"] = report.get("status", "BLOCKED")
        return result

    checks = report.get("checks")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or check.get("status") != "PASS" for check in checks):
        return _status_result("INVALID", task, task_hash, "Report status is PASS but deterministic checks are not all PASS.", ["Rerun /governance."])

    created_at = str(report.get("created_at", ""))
    try:
        age_seconds = (datetime.now(timezone.utc) - _parse_stamp(created_at)).total_seconds()
    except ValueError:
        return _status_result("INVALID", task, task_hash, "Report created_at timestamp is invalid.", ["Rerun /governance."])
    if max_age_seconds >= 0 and age_seconds > max_age_seconds:
        return _status_result("STALE", task, task_hash, "Governance PASS is older than the allowed max age.", ["Rerun /governance with current context."])

    files_read = [str(item) for item in report.get("files_read") or []]
    skills_used = [str(item) for item in report.get("skills_used") or []]
    current_context, evidence_errors = _context_fingerprint(
        task=task,
        files_read=files_read,
        skills_used=skills_used,
        allow_test_evidence_root=allow_test_evidence_root,
    )
    if evidence_errors:
        return _status_result("STALE", task, task_hash, "; ".join(evidence_errors[:3]), ["Rerun /governance with valid evidence."])

    recorded_context = report.get("context")
    if not isinstance(recorded_context, dict) or not recorded_context.get("fingerprint_sha256"):
        return _status_result("STALE", task, task_hash, "Report has no context fingerprint.", ["Rerun /governance with the current skill version."])

    if recorded_context.get("fingerprint_sha256") != current_context.get("fingerprint_sha256"):
        return _status_result("STALE", task, task_hash, "Scoped repo, evidence, integration, or skill-doc fingerprint changed.", ["Rerun /governance with current context."])

    result = dict(report)
    result["report_json"] = str(report_path)
    result["report_html"] = latest.get("report_html")
    return result


@APP.command("run")
def run_gate(
    task: str = typer.Option(..., "--task", help="Exact task text that would be planned."),
    files_read: Optional[list[str]] = typer.Option(None, "--files-read", help="Relevant file path or digest-bearing URI read before planning."),
    skill: Optional[list[str]] = typer.Option(None, "--skill", help="Skill used while building understanding."),
    assumption: Optional[list[str]] = typer.Option(None, "--assumption", help="Assumption made explicit in the report."),
    risk: Optional[list[str]] = typer.Option(None, "--risk", help="Risk or caveat to show the human."),
    unknown: Optional[list[str]] = typer.Option(None, "--unknown", help="Unresolved unknown that blocks planning."),
    understanding_confirmed: bool = typer.Option(False, "--understanding-confirmed", help="Affirm the gate question."),
    needs_interview: bool = typer.Option(False, "--needs-interview", help="Block until /interview is used."),
    needs_research: bool = typer.Option(False, "--needs-research", help="Block until /dogpile is used."),
    allow_test_evidence_root: bool = typer.Option(False, "--allow-test-evidence-root", help="Allow /tmp or URI-only evidence for tests; not for normal planning."),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Override artifact root for tests."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON report."),
) -> None:
    """Write a governance report and latest markers."""
    root = _artifact_root(output_dir)
    task_hash = _task_hash(task)
    stamp = _utc_stamp()
    report_dir = root / "reports" / task_hash / stamp
    files = list(files_read or [])
    skills_used = list(skill or [])
    unknowns = list(unknown or [])
    context, evidence_errors = _context_fingerprint(
        task=task,
        files_read=files,
        skills_used=skills_used,
        allow_test_evidence_root=allow_test_evidence_root,
    )
    has_repo_file_evidence = _has_repo_file_evidence(context["evidence"], _repo_root())
    checks = _build_checks(
        files_read=files,
        evidence_errors=evidence_errors,
        has_repo_file_evidence=has_repo_file_evidence,
        allow_test_evidence_root=allow_test_evidence_root,
        unknowns=unknowns,
        understanding_confirmed=understanding_confirmed,
        needs_interview=needs_interview,
        needs_research=needs_research,
    )
    status_value = "PASS" if all(check["status"] == "PASS" for check in checks) else "BLOCKED"
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "task": task,
        "task_hash": task_hash,
        "created_at": stamp,
        "status": status_value,
        "gate_question": GATE_QUESTION,
        "gate_answer": "yes" if understanding_confirmed else "no",
        "files_read": files,
        "skills_used": skills_used,
        "assumptions": list(assumption or []),
        "risks": list(risk or []),
        "unknowns": unknowns,
        "checks": checks,
        "context": context,
        "required_next_actions": _required_actions(checks),
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    html_path = report_dir / "index.html"
    _write_json(report_path, report)
    html_path.write_text(_render_html(report), encoding="utf-8")

    latest = {
        "schema": f"{SCHEMA}.latest",
        "task": task,
        "task_hash": task_hash,
        "created_at": stamp,
        "report_json": str(report_path),
        "report_html": str(html_path),
    }
    _write_json(_latest_path(root, task_hash), latest)
    _write_json(root / "latest.json", latest)

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Governance status: {status_value}")
        print(f"Report: {report_path}")
        print(f"HTML: {html_path}")
        for action in report["required_next_actions"]:
            print(f"- {action}")

    raise typer.Exit(0 if status_value == "PASS" else 2)


@APP.command("status")
def status(
    task: str = typer.Option(..., "--task", help="Exact task text to check."),
    require_pass: bool = typer.Option(False, "--require-pass", help="Exit nonzero unless latest report is fresh PASS."),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Override artifact root for tests."),
    max_age_seconds: int = typer.Option(DEFAULT_MAX_AGE_SECONDS, "--max-age-seconds", help="Maximum age for a PASS report; use -1 to disable."),
    allow_test_evidence_root: bool = typer.Option(False, "--allow-test-evidence-root", help="Allow test-only /tmp evidence while validating reports."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON status."),
) -> None:
    """Check the latest report for a task."""
    root = _artifact_root(output_dir)
    task_hash = _task_hash(task)
    latest = _load_latest(root, task_hash)
    if latest is None:
        result = _status_result(
            "MISSING",
            task,
            task_hash,
            "No governance report exists for this task.",
            ["Run /governance before /plan with --understanding-confirmed only after reading the relevant files."],
        )
    else:
        result = _validate_report_for_task(
            latest=latest,
            task=task,
            task_hash=task_hash,
            max_age_seconds=max_age_seconds,
            allow_test_evidence_root=allow_test_evidence_root,
        )

    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Governance status: {result['status']}")
        if result.get("message"):
            print(f"Reason: {result['message']}")
        if result.get("report_json"):
            print(f"Report: {result['report_json']}")
        for action in result.get("required_next_actions", []):
            print(f"- {action}")

    if require_pass and result.get("status") != "PASS":
        raise typer.Exit(2)


@APP.command("doctor")
def doctor(
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Override artifact root for tests."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON status."),
) -> None:
    """Check local storage and renderer prerequisites."""
    root = _artifact_root(output_dir)
    storage_parent = root.parent
    checks = [
        {
            "id": "artifact_root_parent",
            "status": "PASS" if storage_parent.exists() else "FAIL",
            "detail": str(storage_parent),
        },
        {
            "id": "artifact_root_writable",
            "status": "PASS" if _is_writable(root) else "FAIL",
            "detail": str(root),
        },
        {
            "id": "html_renderer",
            "status": "PASS",
            "detail": "Built-in static renderer available.",
        },
    ]
    ready = all(check["status"] == "PASS" for check in checks)
    result = {"schema": f"{SCHEMA}.doctor", "ready": ready, "checks": checks}
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"{check['status']}: {check['id']} - {check['detail']}")
    raise typer.Exit(0 if ready else 1)


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


@APP.command("clean-test-output")
def clean_test_output(
    output_dir: str = typer.Option(..., "--output-dir", help="Test output directory to remove."),
) -> None:
    """Remove an explicit temporary output directory used by tests."""
    path = Path(output_dir).expanduser().resolve()
    if not str(path).startswith("/tmp/"):
        typer.echo("Refusing to remove non-/tmp path.")
        raise typer.Exit(2)
    if path.exists():
        shutil.rmtree(path)
    typer.echo(f"Removed {path}")


if __name__ == "__main__":
    APP()
