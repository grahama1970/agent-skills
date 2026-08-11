"""Persist a project-state snapshot to the target directory and to /memory.

Purpose: a project-state report that is only printed cannot be compared, so
drift and evolution are unassessable. This module makes each run durable in
two places: `PROJECT_STATE.md` + `project_state.json` inside the inspected
project or skill directory (the human/agent-readable artifact required by
`best-practices-project-state`), and one timeline document per run in the
`/memory` `project_states` collection keyed by project + UTC timestamp, so
snapshot N can be diffed against N-1.

Inputs: the report dict from generate_report(), and the inspected root.
Outputs: two files in the root, one timeline doc and one recallable lessons
summary in /memory, and a receipt dict describing what was written.

HTTP note: this module is imported inside project-state's uv environment,
which run.sh points at a volatile `/tmp` path that other lanes rebuild. Adding
a third-party HTTP client here made the module fail to import at runtime, so
the two daemon POSTs use stdlib urllib with an explicit timeout and status
handling — the intent of `io-httpx-timeout-status` without a fragile import.

Failure modes: a memory daemon that is down or refuses the write is reported
as `memory_stored: false` with the reason — never silently swallowed, and
never reported as success. Disk write failures raise. This module never
touches ArangoDB or Qdrant directly; persistence goes through the daemon's
HTTP API.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import subprocess
import urllib.error
import urllib.request

import yaml
from loguru import logger

SCHEMA = "project_state.snapshot.v1"
COLLECTION = "project_states"
_raw = os.environ.get("MEMORY_SERVICE_URL", "")
MEMORY_URL = _raw if _raw.startswith("http") else "http://127.0.0.1:8601"


# Extension -> code label. Used for the language axis so /memory recall can
# traverse "all rust projects" without substring-guessing at file paths.
LANG_BY_EXT = {
    ".py": "python", ".rs": "rust", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".go": "go", ".sh": "shell",
    ".qml": "qml", ".lean": "lean4", ".sql": "sql", ".java": "java",
    ".rb": "ruby", ".c": "c", ".cpp": "cpp", ".swift": "swift", ".kt": "kotlin",
}
# Which best-practices skill owns each detected violation class.
BP_OWNER_BY_ISSUE = {
    "hardcoded_secret": "best-practices-security",
    "print_instead_of_logger": "best-practices-python",
    "hardcoded_home_path": "best-practices-python",
    "bare_except": "best-practices-python",
    "sys_path_insert": "best-practices-python",
    "raw_aql": "best-practices-arangodb",
    "argparse_instead_of_typer": "best-practices-python",
}


def _languages(root: Path) -> dict[str, int]:
    """Code labels present in the tree, by file count. Deterministic."""
    counts: dict[str, int] = {}
    skip = {".venv", "node_modules", "__pycache__", ".git", "fixtures"}
    for f in root.rglob("*"):
        if not f.is_file() or any(part in skip for part in f.parts):
            continue
        lang = LANG_BY_EXT.get(f.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _frontmatter(root: Path) -> dict[str, Any]:
    """disciplines/domains/composes/provides/complies for graph traversal."""
    sm = root / "SKILL.md"
    if not sm.is_file():
        return {}
    try:
        return yaml.safe_load(sm.read_text(encoding="utf-8").split("---", 2)[1]) or {}
    except (yaml.YAMLError, IndexError) as exc:
        logger.error("frontmatter parse failed for {}: {}", root.name, exc)
        return {}


def _usage(root: Path) -> dict[str, Any]:
    """Last edited (git, deterministic) and last used (telemetry, absent).

    There is currently NO skill-usage telemetry: `checkpoints` is empty and
    `skill_chains` holds one row, so "when was this skill last used" cannot be
    answered. Recording `not_established` rather than substituting last-edited,
    which measures a different thing and would make unused-but-maintained
    skills look active.
    """
    r = subprocess.run(
        ["git", "log", "-1", "--format=%aI", "--", str(root)],
        capture_output=True, text=True, timeout=30, check=False, cwd=root,
    )
    return {
        "last_edited": r.stdout.strip() or None,
        "last_used": None,
        "last_used_status": "not_established",
        "last_used_blocked_by": "no skill-usage telemetry (checkpoints empty, skill_chains empty)",
    }


def _signals(report: dict[str, Any]) -> dict[str, Any]:
    """Extract the small set of fields drift comparison actually needs."""
    gaps = (report.get("phase_6_gaps") or {}).get("gaps") or []
    bp = report.get("phase_4_best_practices") or {}
    infra = report.get("phase_1_infrastructure") or {}
    drift = report.get("phase_3_doc_drift") or {}
    return {
        "gap_count": len(gaps),
        "gap_critical": sum(1 for g in gaps if g.get("severity") == "critical"),
        "best_practice_findings": bp.get("total_findings", 0),
        "best_practice_by_severity": bp.get("by_severity") or {},
        "doc_drift_count": drift.get("drift_count", 0),
        "tests_total": (infra.get("tests") or {}).get("total", 0),
        "has_sanity": (Path(report.get("project_root", ".")) / "sanity.sh").is_file(),
        "has_skill_md": (Path(report.get("project_root", ".")) / "SKILL.md").is_file(),
        "violations_by_issue": _violations(report),
    }


def _violations(report: dict[str, Any]) -> dict[str, int]:
    """Which best-practices rules were actually violated, by issue class."""
    out: dict[str, int] = {}
    for f in (report.get("phase_4_best_practices") or {}).get("findings") or []:
        issue = str(f.get("issue", "unknown"))
        out[issue] = out.get(issue, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _markdown(report: dict[str, Any], sig: dict[str, Any], ts: str) -> str:
    """Dated assessment artifact. Not a replacement for PROJECT_KNOWLEDGE.md."""
    project = report.get("project", "unknown")
    gaps = (report.get("phase_6_gaps") or {}).get("gaps") or []
    lines = [
        f"# Project State: {project}",
        "",
        f"**Generated {ts}** from `{report.get('project_root')}`.",
        "A dated assessment artifact, not rolling context — see `PROJECT_KNOWLEDGE.md`",
        "for current understanding. Claims below are `not established` unless a receipt",
        "is named.",
        "",
        "## Executive Summary",
        "",
        f"- Gaps: {sig['gap_count']} ({sig['gap_critical']} critical)",
        f"- Best-practice findings: {sig['best_practice_findings']} "
        f"({json.dumps(sig['best_practice_by_severity'])})",
        f"- Doc drift items: {sig['doc_drift_count']}",
        f"- `sanity.sh` present: {sig['has_sanity']}; `SKILL.md` present: {sig['has_skill_md']}",
        "",
        "## Evidence Receipts",
        "",
        f"- `project_state.json` in this directory (full machine-readable report)",
        f"- `/memory` collection `{COLLECTION}`, schema `{SCHEMA}`",
        "",
        "## Outstanding Gaps",
        "",
    ]
    if gaps:
        for g in gaps[:20]:
            lines.append(f"- **{g.get('severity', '?')}** ({g.get('category', '?')}): "
                         f"{g.get('gap', '')} — action: {g.get('action', 'not established')}")
    else:
        lines.append("- none reported by this run")
    lines += [
        "",
        "## Risks And Unknowns",
        "",
        "- Phases skipped by the selected profile are `not established`, not passing.",
        "- Findings under generated/backup directories are not live-source defects;",
        "  check the path before treating a count as a security result.",
        "",
        "## Recommended Next Actions",
        "",
        "- Compare against the previous snapshot in `project_states` to see direction of travel.",
        "",
    ]
    return "\n".join(lines)


def store(report: dict[str, Any], root: Path) -> dict[str, Any]:
    """Write the snapshot to `root` and upsert the timeline doc into /memory."""
    project = str(report.get("project") or root.name)
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    sig = _signals(report)
    langs = _languages(root)
    fm = _frontmatter(root)
    usage = _usage(root)
    complies = [str(x) for x in (fm.get("complies") or [])]
    violated_bp = sorted({
        BP_OWNER_BY_ISSUE[i] for i in sig["violations_by_issue"] if i in BP_OWNER_BY_ISSUE
    })

    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "project_state.json"
    md_path = root / "PROJECT_STATE.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report, sig, now.isoformat()), encoding="utf-8")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "project": project,
        "timestamp": now.isoformat(),
        "files": [str(json_path), str(md_path)],
        "signals": sig,
        "languages": list(langs),
        "best_practices_violated": violated_bp,
        "last_edited": usage["last_edited"],
        "last_used_status": usage["last_used_status"],
        "memory_stored": False,
    }

    doc = {
        "_key": f"project-state-{project}-{ts}".replace(".", "-"),
        "schema": SCHEMA,
        "project": project,
        "project_root": str(root),
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "signals": sig,
        # Graph axes: these fields make the snapshot traversable in /memory
        # (all rust projects -> which violated best-practices-python -> unused since X).
        "languages": list(langs),
        "language_file_counts": langs,
        "disciplines": [str(x) for x in (fm.get("disciplines") or [])],
        "domains": [str(x) for x in (fm.get("domains") or [])],
        "composes": [str(x) for x in (fm.get("composes") or [])],
        "provides": [str(x) for x in (fm.get("provides") or [])],
        "complies_declared": complies,
        "best_practices_violated": violated_bp,
        "violations_by_issue": sig["violations_by_issue"],
        "last_edited": usage["last_edited"],
        "last_used": usage["last_used"],
        "last_used_status": usage["last_used_status"],
        "last_used_blocked_by": usage["last_used_blocked_by"],
        "deprecation_signals": {
            "inbound_composes_unknown": True,
            "never_used_recorded": usage["last_used"] is None,
            "no_skill_md": not sig["has_skill_md"],
            "no_sanity": not sig["has_sanity"],
        },
        "question": f"What was the project state of {project} on {now:%Y-%m-%d}?",
        "answer": (
            f"{project}: {sig['gap_count']} gaps ({sig['gap_critical']} critical), "
            f"{sig['best_practice_findings']} best-practice findings, "
            f"{sig['doc_drift_count']} doc-drift items."
        ),
        "tags": ["project-state", "snapshot", project, now.strftime("%Y-%m-%d")]
                + list(langs)
                + [str(x) for x in (fm.get("disciplines") or [])]
                + [str(x) for x in (fm.get("domains") or [])]
                + violated_bp,
    }
    gaps_text = "; ".join(
        f"{g.get('category', 'general')}: {g.get('gap', '')}"
        for g in ((report.get("phase_6_gaps") or {}).get("gaps") or [])[:5]
    )

    def _post(payload: dict[str, Any]) -> None:
        req = urllib.request.Request(
            f"{MEMORY_URL}/store",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status >= 400:
                raise urllib.error.HTTPError(resp.url, resp.status, "store failed", resp.headers, None)

    # The two writes are independent: the timeline doc is the durable record,
    # the lessons summary only widens recall. Report each outcome separately so
    # a rejected summary is never reported as a lost snapshot.
    try:
        _post({"document": doc, "collection": COLLECTION})
        receipt["memory_stored"] = True
        receipt["memory_key"] = doc["_key"]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.error("project-state snapshot store failed for {}: {}", project, exc)
        receipt["memory_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    summary_text = (
        f"Project state snapshot for the {project} skill on {now:%Y-%m-%d}. "
        f"Readiness assessment and drift tracking: {sig['gap_count']} gaps "
        f"({sig['gap_critical']} critical), {sig['best_practice_findings']} "
        f"best-practice findings, {sig['doc_drift_count']} documentation drift items, "
        f"languages {', '.join(langs) or 'none detected'}. "
        + (f"Gaps: {gaps_text}. " if gaps_text else "")
        + f"Full snapshot stored in {COLLECTION}/{doc['_key']} for evolution comparison."
    )
    try:
        _post({"document": {
            "problem": (
                f"What is the current project state, readiness and known gaps "
                f"of the {project} skill in agent-skills?"
            ),
            "solution": summary_text,
            "tags": doc["tags"] + ["readiness", "drift", "assessment"],
        }})
        receipt["summary_stored"] = True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.error("project-state summary rejected for {}: {}", project, exc)
        receipt["summary_stored"] = False
        receipt["summary_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    return receipt
