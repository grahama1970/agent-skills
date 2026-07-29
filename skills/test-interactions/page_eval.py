"""Strict page-evaluation finding normalization.

This module keeps Impeccable design findings and test-interactions evidence in
one schema without collapsing their proof boundaries.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PAGE_EVAL_FINDING_SCHEMA = "page-eval.finding.v1"
PAGE_EVAL_RUN_SCHEMA = "page-eval.normalization-run.v1"
VALID_FINDING_TYPES = {"design", "interaction", "instrumentation", "visual"}
VALID_EVIDENCE_CLASSES = {"design", "interaction", "instrumentation", "visual"}
VALID_PROOF_GRADES = {"advisory", "deterministic"}


def _jsonl(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _json_payload(path: Path | None) -> Any:
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def stable_page_eval_fingerprint(
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    finding_type: str,
    source_tool: str,
    target_identity: str,
    finding_kind: str,
    expected: str,
) -> str:
    payload = {
        "repo": repo,
        "target": target,
        "route": route,
        "viewport": viewport,
        "finding_type": finding_type,
        "source_tool": source_tool,
        "target_identity": target_identity,
        "finding_kind": finding_kind,
        "expected": _normalize_text(expected).lower(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _finding(
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    finding_type: str,
    evidence_class: str,
    proof_grade: str,
    source_tool: str,
    source_path: str,
    source_index: int,
    target_info: dict[str, Any],
    finding_kind: str,
    severity: str,
    observed: str,
    expected: str,
    reproduction: str,
    deterministic_status: str = "",
    evidence_paths: list[str] | None = None,
    raw_finding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_identity = (
        str(target_info.get("qid") or "")
        or str(target_info.get("selector") or "")
        or str(target_info.get("source_locator") or "")
        or observed
    )
    fingerprint = stable_page_eval_fingerprint(
        repo=repo,
        target=target,
        route=route,
        viewport=viewport,
        finding_type=finding_type,
        source_tool=source_tool,
        target_identity=target_identity,
        finding_kind=finding_kind,
        expected=expected,
    )
    return {
        "schema": PAGE_EVAL_FINDING_SCHEMA,
        "finding_id": f"page-eval-{fingerprint}",
        "fingerprint": fingerprint,
        "repo": repo,
        "target": target,
        "route": route,
        "viewport": viewport,
        "finding_type": finding_type,
        "evidence_class": evidence_class,
        "proof_grade": proof_grade,
        "source_tool": source_tool,
        "source_path": source_path,
        "source_index": source_index,
        "target_info": {
            "qid": str(target_info.get("qid") or ""),
            "selector": str(target_info.get("selector") or ""),
            "selector_source": str(target_info.get("selector_source") or ""),
            "source_locator": str(target_info.get("source_locator") or ""),
            "element": str(target_info.get("element") or ""),
        },
        "finding_kind": finding_kind,
        "severity": severity,
        "observed": observed,
        "expected": expected,
        "reproduction": reproduction,
        "deterministic_status": deterministic_status,
        "evidence_paths": evidence_paths or [],
        "raw_finding": raw_finding or {},
    }


def validate_page_eval_finding(item: dict[str, Any]) -> tuple[bool, list[str]]:
    required = {
        "schema",
        "finding_id",
        "fingerprint",
        "repo",
        "target",
        "route",
        "viewport",
        "finding_type",
        "evidence_class",
        "proof_grade",
        "source_tool",
        "source_path",
        "source_index",
        "target_info",
        "finding_kind",
        "severity",
        "observed",
        "expected",
        "reproduction",
        "deterministic_status",
        "evidence_paths",
        "raw_finding",
    }
    errors: list[str] = []
    missing = sorted(required - set(item))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if item.get("schema") != PAGE_EVAL_FINDING_SCHEMA:
        errors.append(f"schema must be {PAGE_EVAL_FINDING_SCHEMA}")
    if item.get("finding_type") not in VALID_FINDING_TYPES:
        errors.append("finding_type must be one of design, interaction, instrumentation, visual")
    if item.get("evidence_class") not in VALID_EVIDENCE_CLASSES:
        errors.append("evidence_class must be one of design, interaction, instrumentation, visual")
    if item.get("proof_grade") not in VALID_PROOF_GRADES:
        errors.append("proof_grade must be advisory or deterministic")
    if item.get("finding_type") == "design" and item.get("proof_grade") != "advisory":
        errors.append("design findings must remain proof_grade=advisory")
    if item.get("source_tool") == "impeccable" and item.get("evidence_class") != "design":
        errors.append("impeccable findings must use evidence_class=design")
    if item.get("source_tool") == "impeccable" and item.get("deterministic_status") in {"PASS", "FAIL"}:
        errors.append("impeccable findings must not carry deterministic PASS/FAIL status")
    if not isinstance(item.get("target_info"), dict):
        errors.append("target_info must be an object")
    if not isinstance(item.get("evidence_paths"), list):
        errors.append("evidence_paths must be a list")
    if not isinstance(item.get("raw_finding"), dict):
        errors.append("raw_finding must be an object")
    return not errors, errors


def _impeccable_rows(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("findings", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if "antipattern" in payload or "category" in payload:
            return [payload]
    return []


def findings_from_impeccable(
    path: Path | None,
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    replay_command: str,
    disabled: bool = False,
) -> list[dict[str, Any]]:
    if disabled or not path:
        return []
    rows = _impeccable_rows(_json_payload(path))
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        finding_kind = str(row.get("antipattern") or row.get("rule") or row.get("name") or "design_finding")
        source_locator = ":".join(
            part for part in [str(row.get("file") or ""), str(row.get("line") or "")] if part
        )
        observed = str(row.get("description") or row.get("message") or row.get("snippet") or row)
        expected = str(row.get("expected") or row.get("advisory") or f"design should avoid {finding_kind}")
        out.append(_finding(
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            finding_type="design",
            evidence_class="design",
            proof_grade="advisory",
            source_tool="impeccable",
            source_path=str(path),
            source_index=index,
            target_info={
                "qid": row.get("qid") or "",
                "selector": row.get("selector") or "",
                "selector_source": "qid" if row.get("qid") else ("source" if source_locator else ""),
                "source_locator": source_locator,
                "element": row.get("snippet") or row.get("name") or "",
            },
            finding_kind=finding_kind,
            severity=str(row.get("severity") or "info"),
            observed=observed,
            expected=expected,
            reproduction=replay_command,
            deterministic_status="",
            evidence_paths=[str(path)],
            raw_finding=row,
        ))
    return out


def findings_from_discovery(
    path: Path | None,
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    replay_command: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(_jsonl(path) if path else []):
        if row.get("schema") != "test-interactions.discovery-finding.v1":
            continue
        kind = str(row.get("finding_kind") or "discovery_finding")
        finding_type = "instrumentation" if kind in {"missing_qid", "duplicate_qid", "qs_action_missing", "title_missing", "manifest_uncovered_interactive"} else "interaction"
        out.append(_finding(
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            finding_type=finding_type,
            evidence_class=finding_type,
            proof_grade="deterministic",
            source_tool="test-interactions",
            source_path=str(path),
            source_index=index,
            target_info={
                "qid": row.get("qid") or "",
                "selector": row.get("selector") or "",
                "selector_source": "qid" if row.get("qid") else "",
                "source_locator": row.get("state_fingerprint") or "",
                "element": row.get("tag") or row.get("role") or "",
            },
            finding_kind=kind,
            severity="error",
            observed=str(row.get("message") or row.get("evidence") or ""),
            expected=f"live DOM should satisfy discovery invariant: {kind}",
            reproduction=replay_command,
            deterministic_status="FAIL",
            evidence_paths=[str(path)],
            raw_finding=row,
        ))
    return out


def findings_from_results(
    path: Path | None,
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    replay_command: str,
) -> list[dict[str, Any]]:
    payload = _json_payload(path)
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for index, row in enumerate(payload.get("interactions") or []):
        if not isinstance(row, dict) or row.get("status") != "FAIL":
            continue
        out.append(_finding(
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            finding_type="interaction",
            evidence_class="interaction",
            proof_grade="deterministic",
            source_tool="test-interactions",
            source_path=str(path),
            source_index=index,
            target_info={
                "qid": row.get("qid") or row.get("element") or "",
                "selector": row.get("target") or "",
                "selector_source": "qid",
                "source_locator": row.get("surface") or "",
                "element": row.get("element") or "",
            },
            finding_kind="deterministic_failure",
            severity="error",
            observed=str(row.get("evidence") or "deterministic interaction failed"),
            expected="interaction should pass deterministic assertions",
            reproduction=replay_command,
            deterministic_status="FAIL",
            evidence_paths=[p for p in [str(path), str(row.get("screenshot") or "")] if p],
            raw_finding=row,
        ))
    return out


def findings_from_visual(
    path: Path | None,
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    replay_command: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(_jsonl(path) if path else []):
        if row.get("schema") != "test-interactions.visual-finding.v1":
            continue
        evidence = row.get("evidence") or {}
        evidence_paths = [str(v) for v in evidence.values() if isinstance(v, str) and v]
        out.append(_finding(
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            finding_type="visual",
            evidence_class="visual",
            proof_grade="advisory",
            source_tool="test-interactions",
            source_path=str(path),
            source_index=index,
            target_info={
                "qid": row.get("qid") or "",
                "selector": row.get("selector") or "",
                "selector_source": "qid" if row.get("qid") else "",
                "source_locator": row.get("run_id") or "",
                "element": row.get("element") or "",
            },
            finding_kind=str(row.get("finding_kind") or "visual_finding"),
            severity="warning",
            observed=str(row.get("observed_state") or ""),
            expected=str(row.get("expected_state") or "visual state should match expected outcome"),
            reproduction=str(row.get("reproduction") or replay_command),
            deterministic_status=str(row.get("deterministic_status") or ""),
            evidence_paths=evidence_paths + [str(path)],
            raw_finding=row,
        ))
    return out


def normalize_page_eval_findings(
    *,
    repo: str,
    target: str,
    route: str,
    viewport: str,
    replay_command: str,
    output: Path,
    summary_output: Path | None = None,
    impeccable_findings: Path | None = None,
    disable_impeccable: bool = False,
    results: Path | None = None,
    discovery_findings: Path | None = None,
    visual_findings: Path | None = None,
) -> dict[str, Any]:
    if not repo:
        raise ValueError("repo is required")
    if not replay_command:
        raise ValueError("replay_command is required")

    findings = (
        findings_from_impeccable(
            impeccable_findings,
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            replay_command=replay_command,
            disabled=disable_impeccable,
        )
        + findings_from_results(results, repo=repo, target=target, route=route, viewport=viewport, replay_command=replay_command)
        + findings_from_discovery(discovery_findings, repo=repo, target=target, route=route, viewport=viewport, replay_command=replay_command)
        + findings_from_visual(visual_findings, repo=repo, target=target, route=route, viewport=viewport, replay_command=replay_command)
    )

    invalid: list[dict[str, Any]] = []
    for item in findings:
        ok, errors = validate_page_eval_finding(item)
        if not ok:
            invalid.append({"fingerprint": item.get("fingerprint"), "errors": errors, "finding": item})
    if invalid:
        raise ValueError(f"page-eval normalization produced invalid finding(s): {invalid}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in findings), encoding="utf-8")
    summary = {
        "schema": PAGE_EVAL_RUN_SCHEMA,
        "repo": repo,
        "target": target,
        "route": route,
        "viewport": viewport,
        "mocked": False,
        "live": False,
        "disable_impeccable": disable_impeccable,
        "impeccable_included": bool(impeccable_findings and not disable_impeccable),
        "finding_count": len(findings),
        "counts": {
            "design": sum(1 for item in findings if item["finding_type"] == "design"),
            "interaction": sum(1 for item in findings if item["finding_type"] == "interaction"),
            "instrumentation": sum(1 for item in findings if item["finding_type"] == "instrumentation"),
            "visual": sum(1 for item in findings if item["finding_type"] == "visual"),
        },
        "output": str(output),
        "proof_boundary": {
            "proves": ["Strict page-eval JSON schema normalization and provenance tagging."],
            "does_not_prove": ["Impeccable diagnosis correctness.", "Interaction behavior unless deterministic source findings were provided.", "Ticket creation."],
        },
    }
    if summary_output:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
