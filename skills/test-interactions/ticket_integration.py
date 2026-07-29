"""Preview-first ticket integration for test-interactions findings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from visual_evidence import validate_visual_finding

TICKET_CANDIDATE_SCHEMA = "test-interactions.ticket-candidate.v1"
TICKET_RUN_SCHEMA = "test-interactions.ticket-run.v1"
VALID_POLICIES = {"off", "preview", "deterministic-only", "high-confidence", "apply-confirmed"}
DEFAULT_REQUIRED_SKILLS = ["test-interactions", "ticket", "best-practices-github-ticket", "best-practices-react"]
DEFAULT_CONTEXT_FILES = ["skills/test-interactions/SKILL.md", "skills/ticket/SKILL.md"]


@dataclass
class TicketCandidate:
    schema: str
    fingerprint: str
    source: str
    finding_kind: str
    target: str
    surface: str
    element: str
    qid: str
    selector: str
    expected_outcome: str
    observed_state: str
    reproduction: str
    evidence_paths: list[str] = field(default_factory=list)
    deterministic: bool = False
    visual: bool = False
    confidence: float | None = None
    eligible: bool = False
    report_only_reason: str = ""


def stable_fingerprint(*, repo: str, target: str, surface: str, identity: str, finding_kind: str, expected_outcome: str) -> str:
    payload = {
        "repo": repo,
        "target": target,
        "surface": surface,
        "identity": identity,
        "finding_kind": finding_kind,
        "expected_outcome": " ".join(expected_outcome.lower().split()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _candidate(
    *,
    repo: str,
    target: str,
    source: str,
    finding_kind: str,
    surface: str = "",
    element: str = "",
    qid: str = "",
    selector: str = "",
    expected_outcome: str,
    observed_state: str,
    reproduction: str,
    evidence_paths: list[str] | None = None,
    deterministic: bool = False,
    visual: bool = False,
    confidence: float | None = None,
) -> TicketCandidate:
    identity = qid or selector or element or observed_state
    return TicketCandidate(
        schema=TICKET_CANDIDATE_SCHEMA,
        fingerprint=stable_fingerprint(
            repo=repo,
            target=target,
            surface=surface,
            identity=identity,
            finding_kind=finding_kind,
            expected_outcome=expected_outcome,
        ),
        source=source,
        finding_kind=finding_kind,
        target=target,
        surface=surface,
        element=element,
        qid=qid,
        selector=selector,
        expected_outcome=expected_outcome,
        observed_state=observed_state,
        reproduction=reproduction,
        evidence_paths=evidence_paths or [],
        deterministic=deterministic,
        visual=visual,
        confidence=confidence,
    )


def candidates_from_results(path: Path | None, *, repo: str, target: str, replay_command: str) -> list[TicketCandidate]:
    if not path or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[TicketCandidate] = []
    for item in data.get("interactions") or []:
        if item.get("status") != "FAIL":
            continue
        out.append(_candidate(
            repo=repo,
            target=target,
            source=str(path),
            finding_kind="deterministic_failure",
            surface=str(item.get("surface") or ""),
            element=str(item.get("element") or ""),
            qid=str(item.get("qid") or item.get("element") or ""),
            selector=str(item.get("target") or ""),
            expected_outcome="interaction should pass deterministic assertions",
            observed_state=str(item.get("evidence") or "deterministic interaction failed"),
            reproduction=replay_command,
            evidence_paths=[p for p in [str(item.get("screenshot") or ""), str(path)] if p],
            deterministic=True,
        ))
    return out


def candidates_from_discovery(path: Path | None, *, repo: str, target: str, replay_command: str) -> list[TicketCandidate]:
    out: list[TicketCandidate] = []
    for item in _jsonl(path) if path else []:
        if item.get("schema") != "test-interactions.discovery-finding.v1":
            continue
        out.append(_candidate(
            repo=repo,
            target=target,
            source=str(path),
            finding_kind=str(item.get("finding_kind") or "discovery_finding"),
            surface=str(item.get("state_fingerprint") or ""),
            element=str(item.get("tag") or item.get("role") or ""),
            qid=str(item.get("qid") or ""),
            selector=str(item.get("selector") or ""),
            expected_outcome=f"live DOM should satisfy discovery invariant: {item.get('finding_kind')}",
            observed_state=str(item.get("message") or item.get("evidence") or ""),
            reproduction=replay_command,
            evidence_paths=[str(path)],
            deterministic=True,
        ))
    return out


def candidates_from_visual(path: Path | None, *, repo: str, target: str, replay_command: str, threshold: float) -> list[TicketCandidate]:
    out: list[TicketCandidate] = []
    for item in _jsonl(path) if path else []:
        ok, errors = validate_visual_finding(item)
        evidence = item.get("evidence") or {}
        evidence_paths = [str(v) for v in evidence.values() if isinstance(v, str) and v]
        confidence = float(item.get("confidence") or 0)
        complete = ok and confidence >= threshold and bool(item.get("reproduction")) and bool(evidence_paths)
        candidate = _candidate(
            repo=repo,
            target=target,
            source=str(path),
            finding_kind=str(item.get("finding_kind") or "visual_finding"),
            surface=str(item.get("surface") or ""),
            element=str(item.get("element") or ""),
            qid=str(item.get("qid") or ""),
            selector=str(item.get("selector") or ""),
            expected_outcome=str(item.get("expected_state") or "visual state should match expected outcome"),
            observed_state=str(item.get("observed_state") or ""),
            reproduction=str(item.get("reproduction") or replay_command),
            evidence_paths=evidence_paths + [str(path)],
            visual=True,
            confidence=confidence,
        )
        if not complete:
            candidate.report_only_reason = "; ".join(errors) if errors else "visual finding below confidence threshold or missing reproduction/evidence"
        out.append(candidate)
    return out


def apply_policy(candidates: list[TicketCandidate], policy: str, *, threshold: float) -> list[TicketCandidate]:
    if policy not in VALID_POLICIES:
        raise ValueError(f"unknown ticket policy: {policy}")
    for candidate in candidates:
        candidate.eligible = False
        if policy == "off":
            candidate.report_only_reason = candidate.report_only_reason or "ticket policy is off"
        elif policy == "deterministic-only":
            candidate.eligible = candidate.deterministic
            if not candidate.eligible:
                candidate.report_only_reason = candidate.report_only_reason or "visual-only candidate excluded by deterministic-only policy"
        elif policy == "high-confidence":
            candidate.eligible = candidate.visual and (candidate.confidence or 0) >= threshold and not candidate.report_only_reason
            if not candidate.eligible:
                candidate.report_only_reason = candidate.report_only_reason or "candidate is not a complete high-confidence visual finding"
        else:
            candidate.eligible = candidate.deterministic or (candidate.visual and (candidate.confidence or 0) >= threshold and not candidate.report_only_reason)
            if not candidate.eligible:
                candidate.report_only_reason = candidate.report_only_reason or "candidate is not eligible under preview/apply-confirmed policy"
    return candidates


def _resolve_ticket_skill(ticket_skill: Path) -> Path:
    if ticket_skill.exists():
        return ticket_skill
    if not ticket_skill.is_absolute():
        skills_dir = Path(__file__).resolve().parents[1]
        if ticket_skill.parts[:2] == ("skills", "ticket"):
            candidate = skills_dir / "ticket" / Path(*ticket_skill.parts[2:])
        else:
            candidate = Path(__file__).resolve().parent / ticket_skill
        if candidate.exists():
            return candidate
    return ticket_skill


def _run_ticket(ticket_skill: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    resolved = _resolve_ticket_skill(ticket_skill)
    if not resolved.exists() or not os.access(resolved, os.X_OK):
        raise FileNotFoundError(f"ticket entrypoint unavailable: {ticket_skill}")
    return subprocess.run([str(resolved), *args], text=True, capture_output=True, check=False)


def search_duplicate(ticket_skill: Path, *, repo: str, candidate: TicketCandidate) -> dict[str, Any] | None:
    proc = _run_ticket(ticket_skill, ["lookup", "--search", candidate.fingerprint, "--repo", repo, "--limit", "20"])
    if proc.returncode != 0:
        raise RuntimeError(f"ticket duplicate search failed: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        rows = json.loads(proc.stdout.strip() or "[]")
    except json.JSONDecodeError:
        rows = []
    for row in rows if isinstance(rows, list) else []:
        text = json.dumps(row)
        if candidate.fingerprint in text:
            return row
        issue = row.get("number") if isinstance(row, dict) else None
        if issue:
            readback = _run_ticket(ticket_skill, ["lookup", "--issue", str(issue), "--repo", repo])
            if readback.returncode != 0:
                continue
            try:
                issue_data = json.loads(readback.stdout.strip())
            except json.JSONDecodeError:
                continue
            if candidate.fingerprint in (issue_data.get("body") or ""):
                return issue_data
    return None


def _ticket_args(candidate: TicketCandidate, *, repo: str, as_json: bool, apply: bool) -> list[str]:
    title_identity = candidate.qid or candidate.element or candidate.selector or "unidentified interaction"
    observed = (
        f"{candidate.observed_state}\n\n"
        f"Source finding fingerprint: {candidate.fingerprint}\n"
        f"Finding kind: {candidate.finding_kind}\n"
        f"Surface/state: {candidate.surface}\n"
        f"QID: {candidate.qid or 'missing'}\n"
        f"Evidence paths:\n" + "\n".join(f"- `{path}`" for path in candidate.evidence_paths)
    )
    proof = (
        f"Replay command: `{candidate.reproduction}`\n\n"
        f"Read source finding artifact `{candidate.source}` and confirm source fingerprint "
        f"`{candidate.fingerprint}`. Use live CDP proof, not mocked evidence."
    )
    args = [
        "bug",
        f"[test-interactions] {candidate.finding_kind} on {title_identity}",
        "--target", candidate.target,
        "--observed", observed,
        "--expected", candidate.expected_outcome,
        "--repro", candidate.reproduction,
        "--proof", proof,
        "--route", "backend_python_or_skill_runtime",
        "--lane", "be",
        "--agent", "coder",
        "--non-goals", "Do not redesign ticket lifecycle, use selector fallbacks, or combine unrelated findings.",
    ]
    for item in DEFAULT_CONTEXT_FILES:
        args.extend(["--context-file", item])
    for item in DEFAULT_REQUIRED_SKILLS:
        args.extend(["--required-skill", item])
    args.extend(["--repo", repo])
    if as_json:
        args.append("--json")
    if apply:
        args.append("--apply")
    return args


def _issue_number_from_text(text: str) -> int | None:
    match = re.search(r"/issues/(\d+)", text)
    return int(match.group(1)) if match else None


def verify_created_issue(ticket_skill: Path, *, repo: str, issue: int, candidate: TicketCandidate) -> dict[str, Any]:
    proc = _run_ticket(ticket_skill, ["lookup", "--issue", str(issue), "--repo", repo])
    if proc.returncode != 0:
        raise RuntimeError(f"created issue read-back failed: {proc.stderr.strip() or proc.stdout.strip()}")
    data = json.loads(proc.stdout)
    body = data.get("body") or ""
    required = [
        candidate.target,
        "backend_python_or_skill_runtime",
        "coder",
        candidate.reproduction,
        "Required proof",
        candidate.fingerprint,
    ]
    missing = [item for item in required if item not in body]
    if missing:
        raise RuntimeError(f"created issue read-back missing required body terms: {missing}")
    return {"issue": issue, "url": data.get("url"), "state": data.get("state"), "verified": True}


def run_ticket_integration(
    *,
    repo: str,
    target: str,
    policy: str,
    output_dir: Path,
    ticket_skill: Path,
    replay_command: str,
    results: Path | None = None,
    visual_findings: Path | None = None,
    discovery_findings: Path | None = None,
    threshold: float = 0.85,
    max_apply: int = 1,
) -> dict[str, Any]:
    if not repo:
        raise ValueError("target repository is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = (
        candidates_from_results(results, repo=repo, target=target, replay_command=replay_command)
        + candidates_from_discovery(discovery_findings, repo=repo, target=target, replay_command=replay_command)
        + candidates_from_visual(visual_findings, repo=repo, target=target, replay_command=replay_command, threshold=threshold)
    )
    apply_policy(candidates, policy, threshold=threshold)

    previews: list[dict[str, Any]] = []
    duplicate_comments: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for candidate in [item for item in candidates if item.eligible]:
        try:
            duplicate = search_duplicate(ticket_skill, repo=repo, candidate=candidate)
            if duplicate:
                duplicate_comments.append({
                    "fingerprint": candidate.fingerprint,
                    "existing_issue": duplicate,
                    "proposed_comment": f"Additional test-interactions evidence for fingerprint `{candidate.fingerprint}`: {candidate.source}",
                })
                continue
            preview_proc = _run_ticket(ticket_skill, _ticket_args(candidate, repo=repo, as_json=True, apply=False))
            if preview_proc.returncode != 0:
                raise RuntimeError(f"ticket preview failed: {preview_proc.stderr.strip() or preview_proc.stdout.strip()}")
            preview = json.loads(preview_proc.stdout)
            previews.append({"candidate": asdict(candidate), "ticket_preview": preview})
            if policy == "apply-confirmed":
                if len(created) >= max_apply:
                    candidate.report_only_reason = "max apply limit reached"
                    continue
                apply_proc = _run_ticket(ticket_skill, _ticket_args(candidate, repo=repo, as_json=False, apply=True))
                if apply_proc.returncode != 0:
                    raise RuntimeError(f"ticket apply failed: {apply_proc.stderr.strip() or apply_proc.stdout.strip()}")
                issue = _issue_number_from_text(apply_proc.stdout + "\n" + apply_proc.stderr)
                if issue is None:
                    raise RuntimeError("ticket apply did not return a parseable issue URL")
                readback = verify_created_issue(ticket_skill, repo=repo, issue=issue, candidate=candidate)
                created.append({"candidate": asdict(candidate), "apply_stdout": apply_proc.stdout.strip(), "readback": readback})
        except Exception as exc:  # noqa: BLE001
            failures.append({"candidate": asdict(candidate), "error": str(exc)})

    result = {
        "schema": TICKET_RUN_SCHEMA,
        "repo": repo,
        "target": target,
        "policy": policy,
        "mocked": False,
        "live": policy == "apply-confirmed",
        "candidate_count": len(candidates),
        "eligible_count": sum(1 for item in candidates if item.eligible),
        "preview_count": len(previews),
        "duplicate_count": len(duplicate_comments),
        "created_count": len(created),
        "failure_count": len(failures),
        "candidates": [asdict(item) for item in candidates],
        "previews": previews,
        "duplicate_comments": duplicate_comments,
        "created": created,
        "failures": failures,
    }
    (output_dir / "ticket-candidates.json").write_text(json.dumps([asdict(item) for item in candidates], indent=2) + "\n")
    (output_dir / "ticket-previews.json").write_text(json.dumps(previews, indent=2) + "\n")
    (output_dir / "ticket-duplicate-comments.json").write_text(json.dumps(duplicate_comments, indent=2) + "\n")
    (output_dir / "ticket-apply-result.json").write_text(json.dumps(result, indent=2) + "\n")
    if failures:
        (output_dir / "ticket-failure.json").write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"ticket integration recorded {len(failures)} failure(s); see {output_dir / 'ticket-failure.json'}")
    return result
