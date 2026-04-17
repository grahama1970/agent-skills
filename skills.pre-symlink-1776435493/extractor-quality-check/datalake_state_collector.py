#!/usr/bin/env python3
"""Datalake state collector — reads live state from all data sources.

Pure-read script invoked by /ask consult before building persona prompt.
Outputs JSON to stdout with a _human_summary for prompt injection.

Data sources (all local JSON, no network calls):
  1. supervisor_corpus.json       — supervisor status, run metrics, failure buckets
  2. aggregate.json (latest)      — verdict counts, dimension scores, issue histogram
  3. gap_plan.json                — per-sector coverage, gap counts
  4. supervisor_memory_events.jsonl — convergence signals (last 10)
  5. report_*.json (latest daily)  — latest daily corpus report
"""

import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
import httpx

# ── Data source paths ──

_SKILLS_DIR = Path(__file__).resolve().parent.parent
LEARN_DATALAKE = _SKILLS_DIR / "learn-datalake"
REVIEW_PDF = _SKILLS_DIR / "review-pdf"
CORPUS_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "extractor_corpus"

SUPERVISOR_STATE = LEARN_DATALAKE / "state" / "watchdogs" / "supervisor_corpus.json"
MEMORY_EVENTS = LEARN_DATALAKE / "state" / "watchdogs" / "supervisor_memory_events.jsonl"
GAP_PLAN = LEARN_DATALAKE / "state" / "coverage" / "gap_plan.json"
REVIEW_REPORTS_DIR = REVIEW_PDF / "reports"
DAILY_REPORTS_DIR = CORPUS_ROOT / "reports" / "daily"
EXTRACTED_RUNS_DIR = REVIEW_PDF / "extracted_runs"

# Sector directories in the corpus
KNOWN_SECTORS = [
    "arxiv", "dtic", "faa", "nasa", "nist", "ietf",
    "industry", "adversarial", "edge_cases",
]


def _read_json(path: Path) -> dict | None:
    """Read a JSON file, return None on failure."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.debug("JSON parse failed: {}", e)
    return None


def _read_jsonl_tail(path: Path, n: int = 10) -> list[dict]:
    """Read last N lines of a JSONL file."""
    try:
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()
        result = []
        for line in lines[-n:]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result
    except Exception:
        return []


def _find_latest_aggregate() -> dict | None:
    """Find the latest review-pdf aggregate report."""
    if not REVIEW_REPORTS_DIR.exists():
        return None
    dirs = sorted(REVIEW_REPORTS_DIR.glob("review_pdf_loop_c1_*"))
    for d in reversed(dirs):
        agg = d / "aggregate.json"
        if agg.exists():
            data = _read_json(agg)
            if data and data.get("documents_analyzed", 0) > 0:
                return data
            # Even if empty, return latest
            if data:
                return data
    return None


def _find_latest_daily_report() -> dict | None:
    """Find the latest daily corpus report."""
    if not DAILY_REPORTS_DIR.exists():
        return None
    reports = sorted(DAILY_REPORTS_DIR.glob("report_*.json"))
    if reports:
        return _read_json(reports[-1])
    return None


def _quick_corpus_coverage() -> dict:
    """Fast coverage scan from profile.json files on disk.

    Mirrors the logic from run.sh _status_supervised():
      1. Count total PDFs in corpus (excluding results/ dirs)
      2. Find all 00_profile_detector/profile.json in corpus + extracted_runs
      3. Extract .file field, filter for .pdf, deduplicate
      4. Count per-sector and total
    """
    extracted_pdfs: set[str] = set()
    total_pdf_count = 0
    sector_total_counts: dict[str, int] = {}

    # Count total PDFs per directory — match supervisor's fd -e pdf methodology
    # We count ALL .pdf files recursively (same as run.sh _status_supervised)
    try:
        result = subprocess.run(
            ["find", str(CORPUS_ROOT), "-name", "*.pdf", "-type", "f"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                total_pdf_count += 1
                # Extract sector from path: /mnt/.../extractor_corpus/{sector}/...
                rel = line.replace(str(CORPUS_ROOT) + "/", "")
                sector = rel.split("/")[0] if "/" in rel else "root"
                sector_total_counts[sector] = sector_total_counts.get(sector, 0) + 1
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    # Scan profile.json files from both locations
    search_roots = [CORPUS_ROOT]
    if EXTRACTED_RUNS_DIR.is_dir():
        search_roots.append(EXTRACTED_RUNS_DIR)

    for root in search_roots:
        try:
            result = subprocess.run(
                ["find", str(root), "-path", "*/00_profile_detector/profile.json", "-type", "f"],
                capture_output=True, text=True, timeout=60,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0:
                for profile_path in result.stdout.strip().splitlines():
                    profile_path = profile_path.strip()
                    if not profile_path:
                        continue
                    try:
                        data = json.loads(Path(profile_path).read_text())
                        pdf_file = data.get("file", "")
                        if pdf_file.lower().endswith(".pdf"):
                            extracted_pdfs.add(pdf_file)
                    except Exception:
                        continue
        except Exception:
            continue

    # Map extracted PDFs to sectors
    sector_extracted_counts: dict[str, int] = {}
    corpus_prefix = str(CORPUS_ROOT) + "/"
    for pdf_path in extracted_pdfs:
        if pdf_path.startswith(corpus_prefix):
            rel = pdf_path[len(corpus_prefix):]
            sector = rel.split("/")[0] if "/" in rel else "root"
            sector_extracted_counts[sector] = sector_extracted_counts.get(sector, 0) + 1

    extracted_count = len(extracted_pdfs)
    coverage_pct = (100.0 * extracted_count / total_pdf_count) if total_pdf_count > 0 else 0.0

    return {
        "total_pdfs": total_pdf_count,
        "extracted_pdfs": extracted_count,
        "coverage_pct": round(coverage_pct, 2),
        "sector_total_counts": sector_total_counts,
        "sector_extracted_counts": sector_extracted_counts,
        "source": "disk_scan",
    }


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def _query_datalake_arango() -> dict | None:
    """Query datalake content stats via /memory subprocess.

    Returns counts so personas can reference actual datalake state.
    """
    result: dict = {}

    # Use /memory count for each collection-like scope
    for scope_label in ["datalake_docs", "datalake_chunks", "datalake_edges"]:
        try:
            count_result = _memory_cmd(["count", "--scope", scope_label])
            result[f"{scope_label}_count"] = count_result.get("count", 0)
        except Exception:
            result[f"{scope_label}_count"] = 0

    return result if any(v > 0 for v in result.values()) else None


def collect_state() -> dict:
    """Collect all datalake state into a single dict."""
    state = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "supervisor": None,
        "review_aggregate": None,
        "coverage": None,
        "convergence_events": [],
        "daily_report": None,
        "datalake_arango": None,
        "_human_summary": "",
    }

    # 1. Supervisor state
    supervisor = _read_json(SUPERVISOR_STATE)
    if supervisor:
        state["supervisor"] = {
            "status": supervisor.get("status"),
            "run_id": supervisor.get("run_id"),
            "restart_count": supervisor.get("restart_count"),
            "run_count": supervisor.get("run_count"),
            "failure_buckets": supervisor.get("failure_buckets", {}),
            "run_metrics": supervisor.get("run_metrics", {}),
            "updated_at": supervisor.get("updated_at"),
        }

    # 2. Latest review-pdf aggregate
    aggregate = _find_latest_aggregate()
    if aggregate:
        state["review_aggregate"] = {
            "run_id": aggregate.get("run_id"),
            "documents_total": aggregate.get("documents_total", 0),
            "documents_analyzed": aggregate.get("documents_analyzed", 0),
            "verdict_counts": aggregate.get("verdict_counts", {}),
            "average_dimension_scores": aggregate.get("average_dimension_scores", {}),
            "overall_average_score": aggregate.get("overall_average_score", 0.0),
            "issue_histogram": aggregate.get("issue_histogram", {}),
        }

    # 3. Coverage / gap plan
    gap_plan = _read_json(GAP_PLAN)
    if gap_plan:
        coverage_report = gap_plan.get("coverage_report", {})
        sectors = coverage_report.get("sectors", {})
        state["coverage"] = {
            "target_per_sector": gap_plan.get("target_pdf_per_sector", 500),
            "total_pdfs": coverage_report.get("totals", {}).get("pdf", 0),
            "sector_counts": sectors.get("pdf_counts", {}),
            "sector_gaps": sectors.get("pdf_gap_counts", {}),
            "sectors_below_target": sectors.get("sectors_below_target", []),
            "candidate_urls_total": gap_plan.get("candidate_urls_total", 0),
            "selected_url_count": gap_plan.get("selected_url_count", 0),
        }

    # 3b. Fallback coverage from disk scan if gap_plan has empty/zero sectors
    coverage_counts = (state["coverage"] or {}).get("sector_counts", {})
    has_real_counts = sum(coverage_counts.values()) > 0 if coverage_counts else False
    if state["coverage"] is None or not has_real_counts:
        disk_coverage = _quick_corpus_coverage()
        if disk_coverage["total_pdfs"] > 0:
            state["coverage"] = {
                "target_per_sector": 500,
                "total_pdfs": disk_coverage["total_pdfs"],
                "extracted_pdfs": disk_coverage["extracted_pdfs"],
                "coverage_pct": disk_coverage["coverage_pct"],
                "sector_counts": disk_coverage["sector_extracted_counts"],
                "sector_total_counts": disk_coverage.get("sector_total_counts", {}),
                "sector_gaps": {},
                "sectors_below_target": [],
                "source": "disk_scan",
            }

    # 4. Recent convergence events
    events = _read_jsonl_tail(MEMORY_EVENTS, n=10)
    state["convergence_events"] = [
        {
            "event_type": e.get("event_type"),
            "timestamp": e.get("timestamp"),
            "summary": e.get("summary"),
            "run_id": e.get("run_id"),
        }
        for e in events
    ]

    # 5. Latest daily report
    daily = _find_latest_daily_report()
    if daily:
        state["daily_report"] = {
            "date": daily.get("date"),
            "total": daily.get("total", 0),
            "completed": daily.get("completed", 0),
            "failed": daily.get("failed", 0),
            "total_pages": daily.get("total_pages", 0),
            "quality_distribution": daily.get("quality_distribution", {}),
            "failure_reasons": daily.get("failure_reasons", {}),
        }

    # 6. ArangoDB datalake content stats
    arango_state = _query_datalake_arango()
    if arango_state:
        state["datalake_arango"] = arango_state

    # Build human-readable summary
    state["_human_summary"] = _build_summary(state)
    return state


def _build_summary(state: dict) -> str:
    """Build a concise human-readable summary for prompt injection."""
    parts = []
    parts.append("## Datalake State Summary")
    parts.append(f"Collected: {state['collected_at']}")
    parts.append("")

    # Supervisor
    sup = state.get("supervisor")
    if sup:
        metrics = sup.get("run_metrics", {})
        parts.append(f"### Supervisor: {sup.get('status', 'unknown')}")
        parts.append(f"- Run ID: {sup.get('run_id')}")
        parts.append(f"- Restarts: {sup.get('restart_count', 0)} | Runs: {sup.get('run_count', 0)}")
        parts.append(f"- Phase: {metrics.get('phase', 'unknown')}")
        parts.append(f"- Extractions: {metrics.get('extraction_success_count', 0)} success, "
                      f"{metrics.get('extraction_failed_count', 0)} failed, "
                      f"{metrics.get('extraction_timeout_count', 0)} timeout")
        parts.append(f"- Throughput: {metrics.get('extraction_throughput_per_hour', 0):.1f} PDFs/hr")
        parts.append(f"- Quality gate: {metrics.get('quality_gate_action', 'N/A')} "
                      f"({metrics.get('quality_gate_reason', 'N/A')})")
        parts.append(f"- Gate consecutive failures: {metrics.get('quality_gate_consecutive_failures', 0)}")
        parts.append(f"- Dead letters: {metrics.get('memory_retry_dead_letter_count', 0)}")

        buckets = sup.get("failure_buckets", {})
        if buckets:
            parts.append(f"- Failure buckets: {json.dumps(buckets)}")
        parts.append("")

    # Review aggregate
    agg = state.get("review_aggregate")
    if agg:
        parts.append("### Review Aggregate")
        parts.append(f"- Documents analyzed: {agg.get('documents_analyzed', 0)}")
        vc = agg.get("verdict_counts", {})
        parts.append(f"- Verdicts: PASS={vc.get('PASS', 0)}, WARN={vc.get('WARN', 0)}, FAIL={vc.get('FAIL', 0)}")
        parts.append(f"- Overall avg score: {agg.get('overall_average_score', 0.0):.3f}")
        dims = agg.get("average_dimension_scores", {})
        if dims:
            parts.append(f"- Dimension scores: {json.dumps(dims)}")
        parts.append("")

    # Coverage
    cov = state.get("coverage")
    if cov:
        parts.append("### Coverage")
        source = cov.get("source", "gap_plan")
        parts.append(f"- Source: {source}")
        parts.append(f"- Target: {cov.get('target_per_sector', 500)} PDFs/sector")
        parts.append(f"- Total PDFs in corpus: {cov.get('total_pdfs', 0)}")
        if cov.get("extracted_pdfs") is not None:
            parts.append(f"- Extracted PDFs: {cov.get('extracted_pdfs', 0)}")
        if cov.get("coverage_pct") is not None:
            parts.append(f"- Overall coverage: {cov['coverage_pct']:.1f}%")
        counts = cov.get("sector_counts", {})
        gaps = cov.get("sector_gaps", {})
        if counts:
            for sector, count in sorted(counts.items()):
                gap = gaps.get(sector, 0)
                suffix = f" (gap: {gap})" if gap else ""
                parts.append(f"  - {sector}: {count} extracted{suffix}")
        below = cov.get("sectors_below_target", [])
        if below:
            parts.append(f"- Sectors below target: {', '.join(below)}")
        parts.append("")

    # Daily report
    daily = state.get("daily_report")
    if daily:
        parts.append("### Latest Daily Report")
        parts.append(f"- Date: {daily.get('date', 'N/A')}")
        parts.append(f"- Total: {daily.get('total', 0)}, Completed: {daily.get('completed', 0)}, "
                      f"Failed: {daily.get('failed', 0)}")
        parts.append(f"- Pages processed: {daily.get('total_pages', 0)}")
        qd = daily.get("quality_distribution", {})
        if qd:
            parts.append(f"- Quality: {json.dumps(qd)}")
        parts.append("")

    # Datalake ArangoDB content
    dl = state.get("datalake_arango")
    if dl:
        parts.append("### Datalake Content (ArangoDB)")
        parts.append(f"- Documents: {dl.get('datalake_docs_count', 0)}")
        parts.append(f"- Chunks: {dl.get('datalake_chunks_count', 0)}")
        parts.append(f"- Edges: {dl.get('datalake_edges_count', 0)}")
        parts.append(f"- Search view active: {dl.get('datalake_chunks_search_exists', False)}")
        dist = dl.get("asset_type_distribution", {})
        if dist:
            parts.append(f"- Asset types: {json.dumps(dist)}")
        embed = dl.get("embedding_quality", {})
        if embed:
            total = embed.get("total", 0)
            real = embed.get("real_embed", 0)
            pct = (100.0 * real / total) if total > 0 else 0.0
            parts.append(f"- Embeddings: {real}/{total} real ({pct:.0f}%), {embed.get('zero_embed', 0)} zero-vector")
        tax = dl.get("taxonomy_coverage", {})
        if tax:
            total = tax.get("total", 0)
            tagged = tax.get("with_tags", 0)
            pct = (100.0 * tagged / total) if total > 0 else 0.0
            parts.append(f"- Taxonomy: {tagged}/{total} tagged ({pct:.0f}%)")
        top = dl.get("top_docs_by_chunks", [])
        if top:
            parts.append("- Top docs by chunk count:")
            for d in top[:5]:
                parts.append(f"  - {d.get('doc_id', '?')}: {d.get('chunk_count', 0)} chunks")
        parts.append("")

    # Convergence events
    events = state.get("convergence_events", [])
    if events:
        parts.append("### Recent Convergence Events (last 10)")
        for e in events[-5:]:
            parts.append(f"- [{e.get('event_type', '?')}] {e.get('timestamp', '?')}: {e.get('summary', '')}")
        parts.append("")

    return "\n".join(parts)


def main():
    state = collect_state()
    json.dump(state, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
