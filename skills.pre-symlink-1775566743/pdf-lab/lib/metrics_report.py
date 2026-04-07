"""metrics_report — JSON + Markdown report generation and ArangoDB storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from loguru import logger

from .metrics_models import Severity, VerificationReport

_BASE = "http://localhost:8601"
_TIMEOUT = 30.0


def render_json(report: VerificationReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)


def render_markdown(report: VerificationReport) -> str:
    s = report.integrity_summary
    scope = report.scope or "all"
    lines = [
        f"# Datalake Metrics Report: {scope}",
        "",
        f"Generated at: `{report.generated_at.isoformat()}`",
        "",
        "## Integrity Summary",
        "",
        f"- Documents: **{s.documents_count}**",
        f"- Sections: **{s.sections_count}**",
        f"- Text coverage: **{s.coverage_text:.1%}** {_bar(s.coverage_text)}",
        f"- Visual coverage: **{s.coverage_visual:.1%}** {_bar(s.coverage_visual)}",
    ]
    if s.edge_counts:
        for edge, count in sorted(s.edge_counts.items()):
            lines.append(f"- Edge `{edge}`: **{count}**")

    if report.retrieval_metrics is not None:
        m = report.retrieval_metrics
        lines += ["", "## Retrieval Evaluation", "",
                   f"Queries: **{m.num_queries}**", "",
                   "| K | Recall@K | nDCG@K | MRR@K | HitRate@K |",
                   "|---|---:|---:|---:|---:|"]
        for k in sorted(m.recall_at_k):
            lines.append(f"| {k} | {m.recall_at_k[k]:.4f} | {m.ndcg_at_k[k]:.4f} "
                         f"| {m.mrr_at_k[k]:.4f} | {m.hit_rate_at_k[k]:.4f} |")

    if report.visual_verification:
        v = report.visual_verification
        lines += ["", "## Visual Verification", "",
                   f"- Mean score: **{v.get('mean_score', 0):.4f}**",
                   f"- Low confidence: **{v.get('low_confidence', 0)}**"]

    _icons = {Severity.OK: "\u2705", Severity.WARN: "\u26a0\ufe0f", Severity.ERROR: "\u274c"}
    lines += ["", "## Issues", ""]
    if not report.integrity_issues:
        lines.append("No issues detected.")
    else:
        for issue in report.integrity_issues[:50]:
            icon = _icons.get(issue.severity, "")
            lines.append(f"- {icon} `{issue.code}` **{issue.entity_type}** "
                         f"`{issue.entity_id or '-'}`: {issue.message}")

    return "\n".join(lines) + "\n"


def _bar(ratio: float) -> str:
    if ratio >= 0.99:
        return "\U0001f7e2"  # green circle
    if ratio >= 0.95:
        return "\U0001f7e0"  # orange circle
    return "\U0001f534"  # red circle


def store_report(report: VerificationReport) -> str | None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    scope = report.scope or "all"
    key = f"metrics_{scope}_{ts}"
    doc = {**report.to_dict(), "_key": key, "type": "metrics_report",
           "tags": ["metrics", "datalake", scope]}
    try:
        r = httpx.post(f"{_BASE}/upsert",
                       json={"collection": "metrics_reports", "documents": [doc]},
                       timeout=_TIMEOUT)
        r.raise_for_status()
        logger.info("stored metrics report {}", key)
        return key
    except Exception as exc:
        logger.error("store_report failed: {}", exc)
        return None


def load_latest_report(scope: str | None = None) -> dict | None:
    try:
        r = httpx.post(f"{_BASE}/list",
                       json={"collection": "metrics_reports", "k": 1},
                       timeout=_TIMEOUT)
        r.raise_for_status()
        docs = r.json().get("documents") or r.json().get("results") or []
        return docs[0] if docs else None
    except Exception as exc:
        logger.error("load_latest_report failed: {}", exc)
        return None
