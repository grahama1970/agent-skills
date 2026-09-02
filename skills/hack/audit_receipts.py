"""Structured receipts and Memory persistence for Hack SAST audits."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BANDIT_ISSUE_RE = re.compile(r">> Issue: \[(?P<test_id>[^:\]]+):(?P<test_name>[^\]]+)\] (?P<message>.*?)(?=\n-{10,}|\Z)", re.S)
SEVERITY_RE = re.compile(r"Severity: (?P<severity>\w+)\s+Confidence: (?P<confidence>\w+)")
CWE_RE = re.compile(r"CWE: (?P<cwe>CWE-\d+)|(?P<cwe_plain>CWE-\d+)")
LOCATION_RE = re.compile(r"Location: (?P<location>[^\n]+)")
SEMGREP_TEXT_RE = re.compile(r"(?P<rule>[\w.-]+)\s+\n\s+(?P<message>[^\n]+)\s+\n\s+❯❱ (?P<location>[^\n]+)", re.S)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_bandit(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for match in BANDIT_ISSUE_RE.finditer(text or ""):
        block = match.group(0)
        sev = SEVERITY_RE.search(block)
        cwe = CWE_RE.search(block)
        loc = LOCATION_RE.search(block)
        findings.append({
            "tool": "bandit",
            "rule_id": match.group("test_id"),
            "rule_name": match.group("test_name"),
            "message": " ".join(match.group("message").splitlines()[0].split()),
            "severity": sev.group("severity").upper() if sev else "UNKNOWN",
            "confidence": sev.group("confidence").upper() if sev else "UNKNOWN",
            "cwe": (cwe.group("cwe") or cwe.group("cwe_plain")) if cwe else None,
            "location": loc.group("location").strip() if loc else None,
        })
    return findings


def parse_semgrep(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        findings = []
        for item in payload["results"]:
            extra = item.get("extra") or {}
            findings.append({
                "tool": "semgrep",
                "rule_id": item.get("check_id", "unknown"),
                "rule_name": item.get("check_id", "unknown"),
                "message": extra.get("message", ""),
                "severity": str(extra.get("severity", "UNKNOWN")).upper(),
                "confidence": "UNKNOWN",
                "cwe": _first_cwe(extra),
                "location": _semgrep_location(item),
            })
        return findings
    return [
        {
            "tool": "semgrep",
            "rule_id": m.group("rule"),
            "rule_name": m.group("rule"),
            "message": " ".join(m.group("message").split()),
            "severity": "UNKNOWN",
            "confidence": "UNKNOWN",
            "cwe": _first_cwe({"metadata": {"cwe": CWE_RE.findall(m.group(0))}}),
            "location": m.group("location").strip(),
        }
        for m in SEMGREP_TEXT_RE.finditer(text)
    ]


def _first_cwe(extra: dict[str, Any]) -> str | None:
    text = json.dumps(extra, sort_keys=True, default=str)
    match = re.search(r"CWE-\d+", text)
    return match.group(0) if match else None


def _semgrep_location(item: dict[str, Any]) -> str | None:
    path = item.get("path")
    start = item.get("start") or {}
    if not path:
        return None
    return f"{path}:{start.get('line', '?')}:{start.get('col', '?')}"


def summarize_findings(findings: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts: dict[str, int] = {}
    cwes: set[str] = set()
    for finding in findings:
        severity = str(finding.get("severity") or "UNKNOWN").upper()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if finding.get("cwe"):
            cwes.add(str(finding["cwe"]))
    return {
        "finding_count": len(findings),
        "severity_counts": severity_counts,
        "high_count": severity_counts.get("HIGH", 0) + severity_counts.get("ERROR", 0),
        "cwes": sorted(cwes),
    }


def build_audit_receipt(
    *,
    target: str,
    tool: str,
    severity: str,
    profile: str,
    mount_path: str,
    scan_target: str,
    tool_results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    memory_recall: dict[str, Any] | None,
    memory_ref: str | None = None,
    memory_error: str | None = None,
) -> dict[str, Any]:
    summary = summarize_findings(findings)
    receipt = {
        "schema": "hack.audit_receipt.v1",
        "status": "PASS",
        "created_at": _utc_now(),
        "target": str(target),
        "tool": tool,
        "severity": severity,
        "profile": profile,
        "isolation": {
            "executor": "docker",
            "network": "none",
            "mount_path": str(mount_path),
            "scan_target": scan_target,
            "target_mount": "read_only",
        },
        "memory": {
            "recall_attempted": memory_recall is not None,
            "recall_found": bool((memory_recall or {}).get("found")),
            "store_ref": memory_ref,
            "store_error": memory_error,
        },
        "summary": summary,
        "findings": findings,
        "tool_results": tool_results,
        "non_claims": [
            "does_not_confirm_exploitability",
            "does_not_run_proof_exploits",
            "does_not_patch_target",
        ],
    }
    receipt["receipt_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps({k: v for k, v in receipt.items() if k != "receipt_sha256"}, sort_keys=True).encode()
    ).hexdigest()
    return receipt


def write_receipt(path: str | Path, receipt: dict[str, Any]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True))
    return out


def memory_document(receipt: dict[str, Any], receipt_path: str | None = None) -> dict[str, Any]:
    summary = receipt.get("summary") or {}
    digest = str(receipt.get("receipt_sha256", "sha256:missing")).removeprefix("sha256:")[:24]
    return {
        "_key": f"hack-audit-{digest}",
        "schema": "hack.audit_memory_summary.v1",
        "kind": "hack_audit_summary",
        "status": receipt.get("status"),
        "target": receipt.get("target"),
        "tool": receipt.get("tool"),
        "finding_count": summary.get("finding_count", 0),
        "severity_counts": summary.get("severity_counts", {}),
        "cwes": summary.get("cwes", []),
        "receipt_path": receipt_path,
        "receipt_sha256": receipt.get("receipt_sha256"),
        "classification": "internal",
        "tags": ["hack", "security", "sast", "cyber-safety"],
        "retrieval_text": (
            f"Hack SAST audit target={receipt.get('target')} tool={receipt.get('tool')} "
            f"findings={summary.get('finding_count', 0)} cwes={' '.join(summary.get('cwes', []))}"
        ),
    }


__all__ = [
    "build_audit_receipt",
    "memory_document",
    "parse_bandit",
    "parse_semgrep",
    "summarize_findings",
    "write_receipt",
]
