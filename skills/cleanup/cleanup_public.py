"""Public-readiness and security disclosure cleanup lane."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PUBLIC_READINESS_DIR = Path("artifacts/cleanup/public_readiness")
HISTORY_REPORT = PUBLIC_READINESS_DIR / "gitleaks-history.json"
DIR_REPORT = PUBLIC_READINESS_DIR / "gitleaks-dir.json"
GITHUB_SETTINGS_REPORT = PUBLIC_READINESS_DIR / "github-settings.json"

RUNTIME_NOISE_PARTS = {
    ".cache",
    ".codex",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "local",
    "node_modules",
    "tmp",
}

SYNTHETIC_SECRET_TOKENS = {
    "_key",
    "api_key",
    "expected_key",
    "fake",
    "fixture",
    "mock",
    "sample",
    "synthetic",
    "test",
}


def _load_json_report(path: Path) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Load a gitleaks JSON report with a status string and parse error."""
    if not path.exists():
        return "missing", [], None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return "corrupt", [], str(exc)
    if isinstance(payload, list):
        return "loaded", [item for item in payload if isinstance(item, dict)], None
    if isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        return "loaded", [item for item in payload["findings"] if isinstance(item, dict)], None
    return "unsupported_schema", [], "expected a list or an object with findings[]"


def _finding_text(finding: Dict[str, Any]) -> str:
    fields = [
        "RuleID",
        "Description",
        "File",
        "Match",
        "Secret",
        "Fingerprint",
    ]
    return " ".join(str(finding.get(field, "")) for field in fields).lower()


def _path_has_runtime_noise(path: str) -> bool:
    return bool(set(Path(path).parts) & RUNTIME_NOISE_PARTS)


def classify_gitleaks_finding(finding: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Classify a gitleaks finding without treating any hit as safe by default."""
    path = str(finding.get("File") or finding.get("file") or "")
    rule = str(finding.get("RuleID") or finding.get("rule") or "unknown")
    line = finding.get("StartLine") or finding.get("line")
    fingerprint = str(finding.get("Fingerprint") or finding.get("fingerprint") or "")
    text = _finding_text(finding)
    runtime_noise = _path_has_runtime_noise(path)
    synthetic_candidate = rule == "generic-api-key" and any(
        token in text for token in SYNTHETIC_SECRET_TOKENS
    )

    if source == "working_directory" and runtime_noise:
        classification = "working_dir_runtime_noise"
        blocker = "scan_scope_noisy"
        action = "Exclude ignored runtime folders or run a narrowed dir scan, then rerun gitleaks."
    elif synthetic_candidate:
        classification = "synthetic_secret_candidate"
        blocker = "needs_explicit_triage_or_allowlist"
        action = "Triage as synthetic or false positive and commit an allowlist/config receipt."
    else:
        classification = "untriaged_secret_candidate"
        blocker = "needs_secret_triage"
        action = "Triage as real secret, synthetic, or false positive before public release."

    return {
        "source": source,
        "path": path,
        "line": line,
        "rule": rule,
        "fingerprint": fingerprint,
        "classification": classification,
        "blocker": blocker,
        "valid_next_action": action,
    }


def _run_gitleaks(command: List[str], report_path: Path) -> Dict[str, Any]:
    """Run one gitleaks command and capture a deterministic receipt."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError:
        return {
            "command": command,
            "report_path": str(report_path),
            "status": "tool_missing",
            "exit_code": None,
            "stderr_excerpt": "gitleaks executable was not found",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "report_path": str(report_path),
            "status": "timeout",
            "exit_code": None,
            "stderr_excerpt": (exc.stderr or "")[:1000],
        }
    return {
        "command": command,
        "report_path": str(report_path),
        "status": "ran",
        "exit_code": proc.returncode,
        "stderr_excerpt": proc.stderr[-1000:],
    }


def _gitleaks_commands() -> List[Tuple[str, List[str], Path]]:
    return [
        (
            "history",
            [
                "gitleaks",
                "detect",
                "--source",
                ".",
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                str(HISTORY_REPORT),
                "--exit-code",
                "0",
            ],
            HISTORY_REPORT,
        ),
        (
            "working_directory",
            [
                "gitleaks",
                "dir",
                ".",
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                str(DIR_REPORT),
                "--exit-code",
                "0",
            ],
            DIR_REPORT,
        ),
    ]


def _github_settings_status() -> Dict[str, Any]:
    status, _, error = _load_json_report(GITHUB_SETTINGS_REPORT)
    if status == "loaded":
        return {
            "status": "loaded",
            "artifact": str(GITHUB_SETTINGS_REPORT),
            "blocker": None,
            "valid_next_action": "Review captured GitHub visibility/security/reporting settings.",
        }
    return {
        "status": status,
        "artifact": str(GITHUB_SETTINGS_REPORT),
        "blocker": "github_settings_review_not_established",
        "error": error,
        "valid_next_action": (
            "Maintainer captures GitHub visibility, security, secret scanning, "
            "branch protection, issue/reporting, and disclosure settings before public release."
        ),
    }


def scan_public_readiness(run_scans: bool = False) -> Dict[str, Any]:
    """Assess whether cleanup can support a public-release readiness claim.

    This lane is non-mutating. It may produce local receipt artifacts when
    explicitly selected, but it never changes repository visibility, gitleaks
    configuration, allowlists, history, or remote settings.
    """
    run_receipts: List[Dict[str, Any]] = []
    if run_scans and shutil.which("gitleaks"):
        for _, command, report_path in _gitleaks_commands():
            run_receipts.append(_run_gitleaks(command, report_path))
    elif run_scans:
        run_receipts.append({
            "command": ["gitleaks"],
            "status": "tool_missing",
            "stderr_excerpt": "gitleaks executable was not found",
        })

    history_status, history_findings, history_error = _load_json_report(HISTORY_REPORT)
    dir_status, dir_findings, dir_error = _load_json_report(DIR_REPORT)

    triage_items = [
        classify_gitleaks_finding(item, "history")
        for item in history_findings
    ]
    triage_items.extend(
        classify_gitleaks_finding(item, "working_directory")
        for item in dir_findings
    )

    blockers: List[Dict[str, Any]] = []
    if history_status != "loaded":
        blockers.append({
            "id": "gitleaks_history_scan_not_established",
            "evidence": history_status,
            "artifact": str(HISTORY_REPORT),
            "detail": history_error,
            "valid_next_action": "Run the public-readiness lane and preserve the history scan report.",
        })
    for item in triage_items:
        blockers.append({
            "id": item["blocker"],
            "evidence": f"{item['rule']} at {item['path']}:{item.get('line')}",
            "artifact": item.get("fingerprint"),
            "valid_next_action": item["valid_next_action"],
        })
    if dir_status == "loaded" and any(
        item["classification"] == "working_dir_runtime_noise"
        for item in triage_items
    ):
        blockers.append({
            "id": "gitleaks_working_directory_scan_noisy",
            "evidence": str(DIR_REPORT),
            "valid_next_action": "Exclude ignored runtime folders or run a narrowed dir scan.",
        })
    elif dir_status != "loaded":
        blockers.append({
            "id": "gitleaks_working_directory_scan_not_established",
            "evidence": dir_status,
            "artifact": str(DIR_REPORT),
            "detail": dir_error,
            "valid_next_action": "Run a narrowed working-directory scan that excludes local runtime noise.",
        })

    github_settings = _github_settings_status()
    if github_settings.get("blocker"):
        blockers.append({
            "id": github_settings["blocker"],
            "evidence": github_settings["status"],
            "artifact": github_settings["artifact"],
            "valid_next_action": github_settings["valid_next_action"],
        })

    return {
        "schema": "cleanup.public_readiness.v1",
        "generated_at": datetime.now().isoformat(),
        "status": "blocked" if blockers else "prepared_for_public_review",
        "public_flip": "blocked" if blockers else "maintainer_decision_required",
        "mutation": "not_authorized",
        "run_receipts": run_receipts,
        "gitleaks": {
            "installed": shutil.which("gitleaks") is not None,
            "history": {
                "status": history_status,
                "artifact": str(HISTORY_REPORT),
                "finding_count": len(history_findings),
                "error": history_error,
            },
            "working_directory": {
                "status": dir_status,
                "artifact": str(DIR_REPORT),
                "finding_count": len(dir_findings),
                "error": dir_error,
            },
        },
        "triage_items": triage_items,
        "github_settings": github_settings,
        "blockers": blockers,
        "closure_criteria": [
            "gitleaks history scan receipt exists and all findings are triaged.",
            "synthetic generic-api-key hits are explicitly allowlisted or documented as false positives.",
            "working-directory gitleaks scan excludes ignored local runtime noise or justifies each runtime hit.",
            "GitHub visibility, security, secret scanning, branch protection, issue/reporting, and disclosure settings are inventoried by a maintainer.",
            "Cleanup report states public release remains blocked until every readiness blocker is resolved.",
        ],
        "non_claims": [
            "Does not prove the repository is safe to make public.",
            "Does not mutate GitHub settings, history, gitleaks config, or allowlists.",
            "Does not treat synthetic-looking secrets as safe without explicit triage.",
        ],
    }


def append_public_readiness_markdown(plan: List[str], readiness: Dict[str, Any]) -> None:
    """Append public-readiness report details to a cleanup markdown report."""
    blockers = readiness.get("blockers", [])
    plan.append("## Public-Readiness / Security Cleanup")
    plan.append("")
    plan.append(
        "This lane checks whether cleanup can support a public-release readiness "
        "claim. It is non-mutating: it reports gitleaks, working-directory noise, "
        "and GitHub settings blockers, but never changes repository visibility, "
        "history, allowlists, or remote settings."
    )
    plan.append("")
    plan.append(f"- Status: `{readiness.get('status', 'unknown')}`")
    plan.append(f"- Public flip: `{readiness.get('public_flip', 'blocked')}`")
    plan.append(
        f"- Gitleaks history findings: "
        f"`{readiness.get('gitleaks', {}).get('history', {}).get('finding_count', 0)}`"
    )
    plan.append(
        f"- Working-directory findings: "
        f"`{readiness.get('gitleaks', {}).get('working_directory', {}).get('finding_count', 0)}`"
    )
    plan.append(f"- GitHub settings artifact: `{readiness.get('github_settings', {}).get('artifact')}`")
    plan.append("")
    if blockers:
        plan.append("| Blocker | Evidence | Valid Next Action |")
        plan.append("| --- | --- | --- |")
        for blocker in blockers:
            evidence = blocker.get("evidence") or blocker.get("artifact") or "not established"
            plan.append(
                f"| `{blocker['id']}` | {evidence} | {blocker['valid_next_action']} |"
            )
        plan.append("")
    plan.append("Closure criteria:")
    plan.append("")
    for criterion in readiness.get("closure_criteria", []):
        plan.append(f"- {criterion}")
    plan.append("")
