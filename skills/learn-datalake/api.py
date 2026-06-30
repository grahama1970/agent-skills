#!/usr/bin/env python3
"""FastAPI backend for the /learn-datalake viewer.

Serves REST endpoints reading from supervisor state files, shadow JSONL,
convergence logs, worker state, and corpus coverage data.

Usage:
    uvicorn api:app --port 8004 --reload
"""

import base64
import io
import json
import math
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Optional pdf_oxide for on-demand extraction and rendering
try:
    import pdf_oxide
    HAS_PDF_OXIDE = True
except ImportError:
    HAS_PDF_OXIDE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_ROOT = Path(__file__).resolve().parent
STATE_DIR = SKILL_ROOT / "state"
WATCHDOG_DIR = STATE_DIR / "watchdogs"
TASK_MONITOR_DIR = STATE_DIR / "task_monitor"
COVERAGE_DIR = STATE_DIR / "coverage"
SHADOW_DIR = Path.home() / ".pi" / "skills" / "extract-pdf" / "shadow"
CORPUS_ROOT = Path(os.environ.get("CORPUS_ROOT", "/mnt/storage12tb/extractor_corpus"))
EXTRACTOR_REGISTRY = Path(
    os.environ.get(
        "EXTRACTOR_REGISTRY",
        "${HOME}/workspace/experiments/extractor/src/extractor/core/providers/registry.py",
    )
)
VIEWER_DIST = SKILL_ROOT / "viewer" / "dist"

# JSONL data files
DEFERRED_REVIEW_JSONL = STATE_DIR / "deferred_review.jsonl"
BLACKLIST_JSONL = STATE_DIR / "failed_pdf_blacklist.jsonl"
CONVERGENCE_LOG = STATE_DIR / "memory_convergence_log.jsonl"
SAMPLE_LOG = STATE_DIR / "stratified_sample_log.jsonl"
QUARANTINE_ACTIONS_JSONL = STATE_DIR / "quarantine_actions.jsonl"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="learn-datalake viewer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5181",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5181",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Any | None:
    """Read a JSON file, returning None if missing or malformed."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _read_jsonl(path: Path, max_lines: int = 0) -> list[dict]:
    """Read a JSONL file, returning empty list if missing."""
    entries: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if max_lines and len(entries) >= max_lines:
                    break
    except (FileNotFoundError, OSError):
        pass
    return entries


def _wilson_lower_bound(pos: int, total: int, z: float = 2.576) -> float:
    """Wilson score interval lower bound (99% CI by default)."""
    if total == 0:
        return 0.0
    phat = pos / total
    denom = 1 + z * z / total
    center = phat + z * z / (2 * total)
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return (center - spread) / denom


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/supervisors")
async def get_supervisors() -> list[dict]:
    """Read all supervisor_*.json state files."""
    results = []
    if not WATCHDOG_DIR.exists():
        return results
    for f in sorted(WATCHDOG_DIR.glob("supervisor_*.json")):
        data = _read_json(f)
        if data:
            results.append(data)
    return results


@app.get("/api/supervisors/{label}")
async def get_supervisor(label: str) -> JSONResponse:
    """Read a single supervisor state file by label."""
    path = WATCHDOG_DIR / f"supervisor_{label}.json"
    data = _read_json(path)
    if data is None:
        return JSONResponse({"error": f"supervisor '{label}' not found"}, status_code=404)
    return JSONResponse(data)


@app.get("/api/quarantine")
async def get_quarantine(
    reason: str | None = Query(None),
    domain: str | None = Query(None),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """Read quarantine entries from deferred_review.jsonl + failed_pdf_blacklist.jsonl."""
    entries: list[dict] = []

    # Deferred review entries
    for item in _read_jsonl(DEFERRED_REVIEW_JSONL):
        item.setdefault("id", item.get("path", str(uuid.uuid4())))
        item.setdefault("reason", "low-confidence")
        entries.append(item)

    # Blacklisted PDFs
    for item in _read_jsonl(BLACKLIST_JSONL):
        item.setdefault("id", item.get("path", str(uuid.uuid4())))
        item.setdefault("reason", "extraction-error")
        entries.append(item)

    # Filters
    if reason:
        entries = [e for e in entries if e.get("reason") == reason]
    if domain:
        entries = [e for e in entries if domain.lower() in (e.get("category", "") + e.get("domain", "")).lower()]

    # Sort
    if sort == "oldest":
        entries.sort(key=lambda e: e.get("timestamp", ""))
    elif sort == "worst-score":
        entries.sort(key=lambda e: e.get("fail_rate", 0), reverse=True)
    else:  # newest
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    total = len(entries)
    start = (page - 1) * page_size
    return {
        "items": entries[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/api/quarantine/{entry_id}/action")
async def quarantine_action(entry_id: str, body: dict) -> dict:
    """Record an approve/reject/reextract action for a quarantine entry."""
    action = body.get("action", "unknown")
    record = {
        "id": entry_id,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "notes": body.get("notes", ""),
    }
    QUARANTINE_ACTIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(QUARANTINE_ACTIONS_JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")
    return {"status": "ok", "action": action, "id": entry_id}


def _find_quarantine_entry(entry_id: str) -> dict | None:
    """Find a quarantine entry by ID across both JSONL sources."""
    for item in _read_jsonl(DEFERRED_REVIEW_JSONL):
        item.setdefault("id", item.get("path", ""))
        if item["id"] == entry_id:
            return item
    for item in _read_jsonl(BLACKLIST_JSONL):
        item.setdefault("id", item.get("path", ""))
        if item["id"] == entry_id:
            return item
    return None


def _search_shadow_for_pdf(filename: str, max_per_file: int = 50) -> list[dict]:
    """Search cascade shadow JSONL files for entries matching a PDF filename."""
    results = []
    for shadow_name in ["header-verdict", "pdf-profile", "pdf-strategy"]:
        shadow_path = SHADOW_DIR / f"{shadow_name}.jsonl"
        if not shadow_path.exists():
            continue
        try:
            with open(shadow_path) as f:
                count = 0
                for line in f:
                    if count >= max_per_file:
                        break
                    line = line.strip()
                    if not line or filename not in line:
                        continue
                    try:
                        entry = json.loads(line)
                        pdf_path = entry.get("pdf_path", entry.get("path", ""))
                        if filename in pdf_path:
                            entry["_decision_point"] = shadow_name
                            results.append(entry)
                            count += 1
                    except json.JSONDecodeError:
                        continue
        except (FileNotFoundError, OSError):
            continue
    return results


@app.get("/api/quarantine/{entry_id}/detail")
async def get_quarantine_detail(entry_id: str) -> JSONResponse:
    """Extract text and cascade decisions for a quarantined PDF.

    Returns blocks of extracted text, cascade decision log entries,
    page count, and extraction metadata.
    """
    entry = _find_quarantine_entry(entry_id)
    if entry is None:
        return JSONResponse({"error": "entry not found"}, status_code=404)

    pdf_path = entry.get("path", "")
    result: dict[str, Any] = {
        "id": entry_id,
        "pdf_path": pdf_path,
        "blocks": [],
        "cascade_log": [],
        "page_count": 0,
        "extraction_available": False,
    }

    # Extract text blocks via pdf_oxide if available and file exists
    if HAS_PDF_OXIDE and pdf_path and Path(pdf_path).exists():
        try:
            doc = pdf_oxide.PdfDocument(pdf_path)
            result["page_count"] = doc.page_count()
            result["extraction_available"] = True

            # Extract spans per page for the detail view
            blocks = []
            for page_idx in range(min(result["page_count"], 20)):  # cap at 20 pages
                try:
                    spans = doc.extract_spans(page_idx)
                    page_text = doc.extract_text(page_idx)
                    blocks.append({
                        "page": page_idx,
                        "text": page_text[:5000],  # truncate very long pages
                        "span_count": len(spans) if spans else 0,
                    })
                except Exception:
                    blocks.append({"page": page_idx, "text": "", "span_count": 0})
            result["blocks"] = blocks
        except Exception as e:
            result["extraction_error"] = str(e)

    # Search cascade shadow files for this PDF
    filename = Path(pdf_path).name if pdf_path else ""
    if filename:
        result["cascade_log"] = _search_shadow_for_pdf(filename)

    return JSONResponse(result)


@app.get("/api/quarantine/{entry_id}/screenshot/{page_num}")
async def get_quarantine_screenshot(entry_id: str, page_num: int) -> Response:
    """Render a page of a quarantined PDF as PNG.

    Returns a PNG image (binary) for the given page number.
    """
    entry = _find_quarantine_entry(entry_id)
    if entry is None:
        return JSONResponse({"error": "entry not found"}, status_code=404)

    pdf_path = entry.get("path", "")
    if not pdf_path or not Path(pdf_path).exists():
        return JSONResponse({"error": "PDF file not found"}, status_code=404)

    if not HAS_PDF_OXIDE:
        return JSONResponse({"error": "pdf_oxide not available"}, status_code=503)

    try:
        doc = pdf_oxide.PdfDocument(pdf_path)
        if page_num < 0 or page_num >= doc.page_count():
            return JSONResponse({"error": "page out of range"}, status_code=400)

        png_bytes = doc.render_page(page_num, dpi=150)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/corpus")
async def get_corpus() -> dict:
    """Read corpus coverage from gap_plan.json + scan corpus root for sector counts."""
    gap_plan = _read_json(COVERAGE_DIR / "gap_plan.json") or {}

    sectors: list[dict] = []
    sector_names = ["arxiv", "defense", "nasa", "nist", "engineering", "industry", "adversarial"]
    gap_sectors = {}
    if "coverage_report" in gap_plan:
        gap_sectors = gap_plan["coverage_report"].get("sectors", {}).get("pdf_counts", {})

    target_per_sector = gap_plan.get("target_pdf_per_sector", 500)
    total_pdfs = 0
    total_extracted = 0

    for name in sector_names:
        sector_dir = CORPUS_ROOT / name
        try:
            pdf_count = len(list(sector_dir.glob("*.pdf"))) if sector_dir.exists() else 0
        except OSError:
            pdf_count = gap_sectors.get(name, 0)

        # Use gap plan count as fallback
        if pdf_count == 0:
            pdf_count = gap_sectors.get(name, 0)

        target = target_per_sector
        deficit = max(0, target - pdf_count)
        coverage_pct = round(min(100.0, pdf_count / target * 100), 1) if target > 0 else 0.0

        sectors.append({
            "name": name,
            "total": pdf_count,
            "extracted": pdf_count,  # Approximate: assume extracted = available
            "pending": 0,
            "failed": 0,
            "coverage_pct": coverage_pct,
            "target": target,
            "deficit": deficit,
        })
        total_pdfs += pdf_count
        total_extracted += pdf_count

    overall_pct = round(total_extracted / (total_pdfs or 1) * 100, 1)
    return {
        "sectors": sectors,
        "total_pdfs": total_pdfs,
        "total_extracted": total_extracted,
        "overall_coverage_pct": overall_pct,
    }


@app.get("/api/providers")
async def get_providers() -> list[dict]:
    """Read extractor provider registry and return provider info."""
    # Parse the registry.py to extract provider registrations
    providers = _parse_provider_registry()
    return providers


def _parse_provider_registry() -> list[dict]:
    """Parse the extractor provider registry for provider metadata."""
    # Hardcoded provider data based on the known registry
    # This is more reliable than parsing Python source
    providers = [
        {"name": "PDF (pdf_oxide)", "class_name": "PdfOxideProvider", "extensions": [".pdf"], "family": "pdf"},
        {"name": "HTML", "class_name": "HTMLProvider", "extensions": [".html", ".htm"], "family": "web"},
        {"name": "Schematron HTML", "class_name": "SchematronHTMLProvider", "extensions": [".html", ".htm"], "family": "web"},
        {"name": "DOCX", "class_name": "DOCXProvider", "extensions": [".docx"], "family": "document"},
        {"name": "PPTX", "class_name": "PPTXProvider", "extensions": [".pptx"], "family": "presentation"},
        {"name": "EPUB", "class_name": "EPUBProvider", "extensions": [".epub"], "family": "document"},
        {"name": "Markdown", "class_name": "MarkdownProvider", "extensions": [".md", ".markdown"], "family": "markup"},
        {"name": "RST", "class_name": "RSTProvider", "extensions": [".rst"], "family": "markup"},
        {"name": "XML", "class_name": "XMLProvider", "extensions": [".xml"], "family": "markup"},
        {"name": "ReqIF", "class_name": "ReqIFProvider", "extensions": [".reqif", ".reqifz"], "family": "markup"},
        {"name": "JSON", "class_name": "JSONProvider", "extensions": [".json"], "family": "data"},
        {"name": "YAML", "class_name": "YAMLProvider", "extensions": [".yaml", ".yml"], "family": "data"},
        {"name": "CSV/TSV", "class_name": "CSVProvider", "extensions": [".csv", ".tsv"], "family": "spreadsheet"},
        {"name": "Excel", "class_name": "ExcelProvider", "extensions": [".xlsx", ".xls"], "family": "spreadsheet"},
        {"name": "Plain Text", "class_name": "TextProvider", "extensions": [".txt", ".log", ".cfg", ".ini", ".conf"], "family": "data"},
        {"name": "Image", "class_name": "ImageProvider", "extensions": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"], "family": "image"},
        {"name": "Jupyter Notebook", "class_name": "NotebookProvider", "extensions": [".ipynb"], "family": "data"},
        {"name": "Code", "class_name": "CodeProvider", "extensions": [".py", ".rs", ".js", ".ts", ".go", ".java", ".c", ".cpp", ".h"], "family": "data"},
    ]
    for p in providers:
        p.setdefault("extraction_count", 0)
        p.setdefault("success_rate", 0.0)
        p.setdefault("avg_time_ms", 0)
    return providers


@app.get("/api/cascade")
async def get_cascade() -> list[dict]:
    """Read shadow JSONL files and compute per-decision-point aggregates."""
    decision_points = []
    shadow_files = {
        "header-verdict": SHADOW_DIR / "header-verdict.jsonl",
        "pdf-profile": SHADOW_DIR / "pdf-profile.jsonl",
        "pdf-strategy": SHADOW_DIR / "pdf-strategy.jsonl",
    }

    for name, path in shadow_files.items():
        dp = _aggregate_shadow(name, path)
        decision_points.append(dp)

    return decision_points


def _aggregate_shadow(name: str, path: Path) -> dict:
    """Aggregate a shadow JSONL file into decision point metrics."""
    disposition_counts: dict[str, int] = defaultdict(int)
    confidences: list[float] = []
    timestamps: list[str] = []
    agree_count = 0
    agree_total = 0

    try:
        file_size = path.stat().st_size
    except (FileNotFoundError, OSError):
        file_size = 0

    # For large files, sample from head and tail
    entries = []
    try:
        with open(path) as f:
            # Read first 5000 lines for stats
            for i, line in enumerate(f):
                if i >= 5000:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (FileNotFoundError, OSError):
        pass

    for entry in entries:
        pred = entry.get("predicted", "unknown")
        disposition_counts[pred] += 1
        conf = entry.get("confidence")
        if conf is not None:
            confidences.append(float(conf))
        ts = entry.get("timestamp")
        if ts:
            timestamps.append(ts)
        if entry.get("agree") is not None:
            agree_total += 1
            if entry["agree"]:
                agree_count += 1

    # Confidence histogram: 5 bins [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]
    bins = [0, 0, 0, 0, 0]
    for c in confidences:
        idx = min(4, int(c * 5))
        bins[idx] += 1

    # Date range
    date_range = {"start": "", "end": ""}
    if timestamps:
        timestamps_sorted = sorted(timestamps)
        date_range = {"start": timestamps_sorted[0], "end": timestamps_sorted[-1]}

    # Promotion status
    total_samples = len(entries)
    threshold = 200
    agreement_rate = agree_count / agree_total if agree_total > 0 else 0.0
    wilson = _wilson_lower_bound(agree_count, agree_total)

    if total_samples < threshold:
        status = "Early"
    elif agreement_rate >= 0.90 and wilson >= 0.85:
        status = "Ready"
    else:
        status = "Learning"

    return {
        "name": name,
        "total_samples": total_samples,
        "shadow_file_size_bytes": file_size,
        "date_range": date_range,
        "disposition_counts": dict(disposition_counts),
        "confidence_distribution": bins,
        "promotion_status": status,
        "agreement_rate": round(agreement_rate, 4),
        "wilson_lower_bound": round(wilson, 4),
        "samples_vs_threshold": {"current": total_samples, "threshold": threshold},
    }


@app.get("/api/quality/trends")
async def get_quality_trends(days: int = Query(7, ge=1, le=365)) -> list[dict]:
    """Read convergence + sample logs and return time-series data."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    # Aggregate by date
    by_date: dict[str, dict] = defaultdict(lambda: {
        "fail_rates": [],
        "throughputs": [],
        "quality_scores": [],
        "sample_sizes": [],
    })

    # Convergence log
    for entry in _read_jsonl(CONVERGENCE_LOG):
        ts = entry.get("timestamp", "")
        if ts < cutoff_str:
            continue
        date = ts[:10]  # YYYY-MM-DD
        score = entry.get("overall_score")
        if score is not None:
            by_date[date]["quality_scores"].append(score)
        coverage = entry.get("coverage_pct")
        if coverage is not None:
            by_date[date]["throughputs"].append(coverage)

    # Sample log
    for entry in _read_jsonl(SAMPLE_LOG):
        ts = entry.get("timestamp", "")
        if ts < cutoff_str:
            continue
        date = ts[:10]
        fail_pct = entry.get("fail_pct")
        if fail_pct is not None:
            by_date[date]["fail_rates"].append(fail_pct)
        sample_size = entry.get("sample_size")
        if sample_size is not None:
            by_date[date]["sample_sizes"].append(sample_size)

    # Build time series
    result = []
    for date in sorted(by_date.keys()):
        d = by_date[date]
        point: dict[str, Any] = {"date": date}
        if d["fail_rates"]:
            point["fail_rate"] = round(sum(d["fail_rates"]) / len(d["fail_rates"]), 4)
        if d["throughputs"]:
            point["throughput"] = round(sum(d["throughputs"]) / len(d["throughputs"]), 4)
        if d["quality_scores"]:
            point["quality_score"] = round(sum(d["quality_scores"]) / len(d["quality_scores"]), 4)
        result.append(point)

    return result


@app.get("/api/workers")
async def get_workers() -> list[dict]:
    """Read per-worker state files."""
    workers = []
    if not TASK_MONITOR_DIR.exists():
        return workers
    for f in sorted(TASK_MONITOR_DIR.glob("review_state_worker_*.json")):
        data = _read_json(f)
        if data:
            # Extract worker ID from filename
            match = re.search(r"worker_(\d+)", f.name)
            if match and "stats" in data:
                data["stats"].setdefault("worker_id", int(match.group(1)))
            workers.append(data)
    return workers


# ---------------------------------------------------------------------------
# Static files (viewer dist) — mount LAST so API routes take precedence
# ---------------------------------------------------------------------------
if VIEWER_DIST.exists():
    app.mount("/", StaticFiles(directory=str(VIEWER_DIST), html=True), name="viewer")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
