"""Reporting and persistence for review-pdf.

Purpose:
- write per-document reports, aggregate summaries, markdown snapshots, and memory events.

Inputs:
- document report objects and aggregate stats.

Outputs:
- json/jsonl/markdown artifacts under review-pdf report directories.

Failure modes:
- filesystem write errors propagate to caller to avoid silent data loss.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .utils import write_json

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent

ISSUE_SKILL_MAP = {
    "table_recall_critical": ["table-lab", "create-table-classifier", "create-table"],
    "table_recall_low": ["table-lab", "create-table-classifier"],
    "section_alignment_critical": [
        "create-classifier",
        "classifier-lab",
        "create-intent-map",
    ],
    "section_alignment_low": ["create-classifier", "classifier-lab"],
    "equation_recall_critical": [
        "create-classifier",
        "prompt-lab",
        "create-intent-map",
    ],
    "math_symbol_loss": ["prompt-lab", "create-classifier", "normalize"],
    "content_coverage_critical": [
        "debug-pdf",
        "fixture-tricky",
        "create-pdf-fixture",
        "extractor",
    ],
    "content_coverage_low": ["debug-pdf", "create-pdf-fixture", "quality-audit"],
    "content_overextract_critical": [
        "debug-pdf",
        "normalize",
        "quality-audit",
        "fixture-tricky",
    ],
    "content_overextract_high": ["debug-pdf", "normalize", "quality-audit"],
    "bbox_order_violation": ["pdf-screenshot", "debug-pdf", "create-classifier"],
    "sort_order_violation": ["pdf-screenshot", "debug-pdf"],
    "empty_elements_high": ["normalize", "create-classifier", "quality-audit"],
    "duplicate_content_high": ["normalize", "create-classifier", "quality-audit"],
    "unknown_element_type": ["create-classifier", "classifier-lab"],
}


def _recommended_skills(aggregate: Dict[str, Any]) -> List[str]:
    skills: Dict[str, int] = {}
    for issue_code, count in aggregate.get("issue_histogram", {}).items():
        for skill in ISSUE_SKILL_MAP.get(issue_code, []):
            skills[skill] = skills.get(skill, 0) + int(count)
    return [
        name for name, _ in sorted(skills.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _aggregate_jobs(run_id: str) -> List[Dict[str, str]]:
    return [
        {
            "skill": "quality-audit",
            "command": (
                f"cd {_SKILLS_DIR}/quality-audit && "
                f"./run.sh report --input reports/{run_id}/per_doc --output reports/{run_id}/quality_audit.md"
            ),
            "reason": "validate stratified quality distribution across reviewed PDFs",
        },
        {
            "skill": "batch-quality",
            "command": (
                f"cd {_SKILLS_DIR}/batch-quality && "
                "./run.sh preflight --stage 11 --samples 5"
            ),
            "reason": "run preflight quality gate before large reruns",
        },
        {
            "skill": "corpus-report",
            "command": (
                f"cd {_SKILLS_DIR}/corpus-report && "
                "./run.sh quality --json"
            ),
            "reason": "measure corpus-level extraction trends and bottlenecks",
        },
        {
            "skill": "analytics",
            "command": (
                f"cd {_SKILLS_DIR}/analytics && "
                f"./run.sh describe reports/{run_id}/aggregate.json"
            ),
            "reason": "profile aggregate metrics for dashboard and change tracking",
        },
        {
            "skill": "monitor-pdfs",
            "command": (
                f"cd {_SKILLS_DIR}/monitor-pdfs && "
                "./run.sh status"
            ),
            "reason": "track extraction throughput and status while remediation runs",
        },
        {
            "skill": "data-audit",
            "command": (
                f"cd {_SKILLS_DIR}/data-audit && "
                "uv run python audit.py --help"
            ),
            "reason": "verify coverage completeness in downstream data products",
        },
        {
            "skill": "task-monitor",
            "command": (
                f"cd {_SKILLS_DIR}/task-monitor && "
                "./run.sh --help"
            ),
            "reason": "observe long-running classifier/prompt improvement tasks",
        },
    ]


def aggregate_reports(reports: List[Dict[str, Any]], run_id: str) -> Dict[str, Any]:
    """Aggregate document-level reports into corpus summary metrics."""
    completed = [report for report in reports if "overall" in report]
    totals = {"PASS": 0, "WARN": 0, "FAIL": 0}
    by_domain: Dict[str, Dict[str, Any]] = {}
    issue_hist: Dict[str, int] = {}
    dimension_values: Dict[str, List[float]] = {}

    for report in completed:
        verdict = report["overall"]["verdict"]
        totals[verdict] = totals.get(verdict, 0) + 1
        domain = report.get("domain", "unknown")
        bucket = by_domain.setdefault(
            domain, {"count": 0, "PASS": 0, "WARN": 0, "FAIL": 0}
        )
        bucket["count"] += 1
        bucket[verdict] += 1

        for issue in report.get("issues", []):
            code = issue.get("code", "unknown")
            issue_hist[code] = issue_hist.get(code, 0) + 1

        for name, payload in report.get("dimensions", {}).items():
            dimension_values.setdefault(name, []).append(
                float(payload.get("score", 0.0))
            )

    average_dimensions = {
        name: (sum(values) / len(values) if values else 0.0)
        for name, values in dimension_values.items()
    }
    overall_average_score = sum(average_dimensions.values()) / max(
        1, len(average_dimensions)
    )

    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "documents_total": len(reports),
        "documents_analyzed": len(completed),
        "documents_missing": len(reports) - len(completed),
        "verdict_counts": totals,
        "average_dimension_scores": average_dimensions,
        "overall_average_score": round(overall_average_score, 6),
        "issue_histogram": dict(
            sorted(issue_hist.items(), key=lambda pair: (-pair[1], pair[0]))
        ),
        "domain_summary": by_domain,
        "aggregate_jobs": _aggregate_jobs(run_id),
    }


def aggregate_markdown(aggregate: Dict[str, Any]) -> str:
    """Render aggregate summary to concise markdown report."""
    lines = [
        "# review-pdf aggregate report",
        "",
        f"- run_id: `{aggregate['run_id']}`",
        f"- documents_total: `{aggregate['documents_total']}`",
        f"- documents_analyzed: `{aggregate['documents_analyzed']}`",
        f"- documents_missing: `{aggregate['documents_missing']}`",
        f"- overall_average_score: `{aggregate['overall_average_score']:.4f}`",
        f"- extraction_events_count: `{int(aggregate.get('extraction_events_count', 0))}`",
        f"- extraction_failed_count: `{int(aggregate.get('extraction_failed_count', 0))}`",
        f"- extraction_succeeded_count: `{int(aggregate.get('extraction_succeeded_count', 0))}`",
        "",
        "## verdict counts",
    ]
    for verdict, count in aggregate["verdict_counts"].items():
        lines.append(f"- {verdict}: `{count}`")

    lines.append("")
    lines.append("## domain summary")
    for domain, summary in sorted(aggregate["domain_summary"].items()):
        lines.append(
            f"- {domain}: count={summary['count']} pass={summary['PASS']} "
            f"warn={summary['WARN']} fail={summary['FAIL']}"
        )

    lines.append("")
    lines.append("## top issue codes")
    top_codes = list(aggregate["issue_histogram"].items())[:20]
    if not top_codes:
        lines.append("- none")
    else:
        for code, count in top_codes:
            lines.append(f"- {code}: `{count}`")

    lines.append("")
    lines.append("## recommended helper skills")
    suggested = _recommended_skills(aggregate)[:12]
    if not suggested:
        lines.append("- none")
    else:
        for skill in suggested:
            lines.append(f"- {skill}")

    lines.append("")
    lines.append("## aggregate helper jobs")
    for job in aggregate.get("aggregate_jobs", []):
        lines.append(f"- [{job['skill']}] `{job['command']}`")
        lines.append(f"  reason: {job['reason']}")

    lines.append("")
    return "\n".join(lines)


def write_reports(
    output_dir: Path, reports: List[Dict[str, Any]], aggregate: Dict[str, Any]
) -> Dict[str, Path]:
    """Write all reporting artifacts and return key paths."""
    per_doc_dir = output_dir / "per_doc"
    per_doc_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        doc_id = report.get("doc_id")
        if not doc_id:
            continue
        write_json(per_doc_dir / f"{doc_id}.json", report)

    aggregate_json = output_dir / "aggregate.json"
    aggregate_md = output_dir / "aggregate.md"
    write_json(aggregate_json, aggregate)
    aggregate_md.write_text(aggregate_markdown(aggregate), encoding="utf-8")
    write_json(
        output_dir / "reports_index.json",
        {"reports": [report["doc_id"] for report in reports if report.get("doc_id")]},
    )
    return {
        "aggregate_json": aggregate_json,
        "aggregate_md": aggregate_md,
        "per_doc_dir": per_doc_dir,
    }


def print_summary(aggregate: Dict[str, Any], artifacts: Dict[str, Path]) -> None:
    """Emit concise terminal summary used by run.sh and orchestration."""
    print("review-pdf summary")
    print(f"run_id={aggregate['run_id']}")
    print(f"documents_total={aggregate['documents_total']}")
    print(f"documents_analyzed={aggregate['documents_analyzed']}")
    print(f"extraction_events_count={int(aggregate.get('extraction_events_count', 0))}")
    print(f"extraction_failed_count={int(aggregate.get('extraction_failed_count', 0))}")
    print(
        f"extraction_succeeded_count={int(aggregate.get('extraction_succeeded_count', 0))}"
    )
    print(
        "verdicts="
        f"PASS:{aggregate['verdict_counts'].get('PASS', 0)} "
        f"WARN:{aggregate['verdict_counts'].get('WARN', 0)} "
        f"FAIL:{aggregate['verdict_counts'].get('FAIL', 0)}"
    )
    print(f"aggregate_json={artifacts['aggregate_json']}")
    print(f"aggregate_md={artifacts['aggregate_md']}")
