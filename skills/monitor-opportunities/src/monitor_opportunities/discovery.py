"""Read-only source discovery with typed local receipts and no external effects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from .util import read_json, sha256_bytes, stable_id, utc_now, write_json, write_jsonl

LANES = ("A", "B", "C")
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=3.0)
MAX_RESPONSE_BYTES = 1_500_000


def _base_receipt(lane: str, provider: str, target: str, source_class: str) -> dict[str, Any]:
    return {
        "receipt_id": "",
        "lane": lane,
        "provider": provider,
        "target": target,
        "source_class": source_class,
        "observed_at": utc_now(),
        "request_summary": "",
        "response_status": None,
        "content_type": None,
        "response_bytes": 0,
        "content_sha256": None,
        "result_status": "NOT_SEARCHED",
        "parser_result": "NOT_RUN",
        "retry_count": 0,
        "limitations": [],
        "evidence_refs": [],
    }


def _finalize_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["receipt_id"] = stable_id(
        f"src:{receipt['lane'].lower()}:{receipt['provider']}",
        {
            "target": receipt["target"],
            "status": receipt["result_status"],
            "hash": receipt["content_sha256"],
        },
    )
    return receipt


def _fixture_sweep(fixture_dir: Path, lanes: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixture = read_json(fixture_dir / "discovery-run.json")
    receipts = [row for row in fixture["source_receipts"] if row["lane"] in lanes]
    candidates = [row for row in fixture["candidates"] if row["lane"] in lanes]
    attempted = {row["lane"] for row in receipts}
    for lane in sorted(lanes - attempted):
        receipt = _base_receipt(lane, "fixture", f"lane-{lane}", "fixture")
        receipt["result_status"] = "NOT_SEARCHED"
        receipt["limitations"] = ["Lane was requested but fixture has no source."]
        receipts.append(_finalize_receipt(receipt))
    return receipts, candidates


def _greenhouse_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "greenhouse", target["name"], "employer_ats")
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Greenhouse board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt), []
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    jobs = data.get("jobs", [])
    receipt["result_status"] = "MATCHES" if jobs else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in jobs[: target.get("limit", 20)]:
        location = (job.get("location") or {}).get("name") or "Unknown"
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "greenhouse",
            "source_identity": slug,
            "organization": job.get("company_name") or target["name"],
            "title": job.get("title") or "Untitled",
            "location_display": location,
            "workplace_type": _workplace_type(location),
            "relocation_required": "relocation" in location.lower() and "required" in location.lower(),
            "clearance_required": False,
            "posting_url": job.get("absolute_url"),
            "apply_url": job.get("absolute_url"),
            "published_at": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": (job.get("content") or "")[:4000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = stable_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _workplace_type(location: str) -> str:
    text = location.lower()
    if "buffalo" in text and "hybrid" in text:
        return "WNY_HYBRID"
    if "buffalo" in text:
        return "WNY_ONSITE"
    if "remote" in text:
        return "REMOTE"
    return "AMBIGUOUS"


def _sam_receipt() -> dict[str, Any]:
    receipt = _base_receipt("B", "sam.gov", "SAM.gov Opportunities", "federal_feed")
    api_key = os.getenv("SAM_GOV_API_KEY")
    receipt["request_summary"] = "SAM.gov opportunity probe; credential value redacted"
    if not api_key:
        receipt["result_status"] = "AUTH_REQUIRED"
        receipt["parser_result"] = "BLOCKED"
        receipt["limitations"].append("SAM_GOV_API_KEY is not present; no unauthenticated query was attempted.")
        return _finalize_receipt(receipt)
    url = "https://api.sam.gov/opportunities/v2/search?limit=1"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
            response = client.get(url, params={"api_key": api_key})
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(response.content[:MAX_RESPONSE_BYTES])
        receipt["result_status"] = "MATCHES" if response.status_code == 200 else "FEED_DOWN"
        receipt["parser_result"] = "PARSED" if response.status_code == 200 else "ERROR"
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"SAM.gov probe failed: {type(exc).__name__}")
    return _finalize_receipt(receipt)


def _commercial_receipt(target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt = _base_receipt("C", "primary-company-source", target["name"], "primary_company_source")
    receipt["request_summary"] = f"GET {target['url']} primary source; no credentials"
    candidates: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(target["url"])
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        response.raise_for_status()
        text = response.text.lower()
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Primary-source read failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []
    keywords = [word.lower() for word in target.get("need_keywords", [])]
    hits = [word for word in keywords if word in text]
    receipt["result_status"] = "MATCHES" if hits else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    if hits:
        payload = {
            "lane": "C",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "primary-company-source",
            "source_identity": target["url"],
            "organization": target["name"],
            "title": target.get("need_title", "Primary-source need signal"),
            "location_display": "Commercial signal; delivery model unknown",
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "posting_url": target["url"],
            "apply_url": None,
            "published_at": None,
            "updated_at": None,
            "content_hash": receipt["content_sha256"],
            "posting_text": f"Observed primary-source keywords: {', '.join(hits)}",
            "fit_score": target.get("default_fit_score", 0.65),
            "contact_state": "CONTACT_UNKNOWN",
            "unresolved_assumptions": ["Budget, buyer, and timing are unknown."],
        }
        payload["candidate_id"] = stable_id("candidate:c", payload)
        candidates.append(payload)
    return receipt, candidates


def _load_targets(skill_dir: Path) -> dict[str, Any]:
    return read_json(skill_dir / "config" / "target_accounts.json")


def sweep(
    *,
    skill_dir: Path,
    lanes: set[str],
    out_dir: Path,
    fixture_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if fixture_dir is not None:
        receipts, candidates = _fixture_sweep(fixture_dir, lanes)
    else:
        targets = _load_targets(skill_dir)
        receipts = []
        candidates = []
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
            if "A" in lanes:
                for target in targets.get("employment", []):
                    receipt, rows = _greenhouse_candidates(client, target)
                    receipts.append(receipt)
                    candidates.extend(rows)
        if "B" in lanes:
            receipts.append(_sam_receipt())
        if "C" in lanes:
            for target in targets.get("commercial", []):
                receipt, rows = _commercial_receipt(target)
                receipts.append(receipt)
                candidates.extend(rows)

    lane_summaries = []
    for lane in LANES:
        lane_receipts = [row for row in receipts if row["lane"] == lane]
        lane_candidates = [row for row in candidates if row["lane"] == lane]
        if lane not in lanes:
            status = "NOT_SEARCHED"
        elif any(row["result_status"] == "MATCHES" for row in lane_receipts):
            status = "MATCHES"
        elif any(row["result_status"] in {"FEED_DOWN", "AUTH_REQUIRED", "AUTH_FAILED"} for row in lane_receipts):
            status = lane_receipts[0]["result_status"]
        else:
            status = "NO_MATCHES"
        lane_summaries.append(
            {
                "lane": lane,
                "searched": lane in lanes,
                "result_status": status,
                "candidates_observed": len(lane_candidates),
                "source_receipt_ids": [row["receipt_id"] for row in lane_receipts],
            }
        )

    manifest = {
        "schema": "monitor_opportunities.discovery_run.v1",
        "run_id": stable_id("discovery", {"lanes": sorted(lanes), "receipts": receipts}),
        "generated_at": utc_now(),
        "mocked": False,
        "live": fixture_dir is None,
        "external_effects": False,
        "lanes_requested": sorted(lanes),
        "artifact_paths": {
            "source_receipts": str(out_dir / "source-receipts.jsonl"),
            "candidates": str(out_dir / "candidates.jsonl"),
            "lane_summaries": str(out_dir / "lane-summaries.json"),
        },
    }
    write_json(out_dir / "run-manifest.json", manifest)
    write_jsonl(out_dir / "source-receipts.jsonl", receipts)
    write_jsonl(out_dir / "candidates.jsonl", sorted(candidates, key=lambda row: row["candidate_id"]))
    write_json(out_dir / "lane-summaries.json", lane_summaries)
    return manifest
