#!/usr/bin/env python3
"""Build a staged SPARTA execution manifest using native /memory lookups only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx


SENTINEL_JOB_IDS = {"canon::CM-NA"}


def memory_base_url() -> str:
    url = (
        os.getenv("MEMORY_SERVICE_URL")
        or os.getenv("MEMORY_API_URL")
        or os.getenv("MEMORY_SERVER_URL")
        or "http://127.0.0.1:8601"
    ).rstrip("/")
    if url.startswith(("unix://", "http+unix://")):
        return "http://127.0.0.1:8601"
    return url


def summarize_existing_v2_jobs(client: httpx.Client, jobs: list[dict]) -> list[dict]:
    existing_jobs: list[dict] = []

    canonical_counts: dict[str, int] = {}
    relationship_counts: dict[str, int] = {}

    def fetch_all(collection: str, return_fields: list[str]) -> list[dict]:
        docs: list[dict] = []
        offset = 0
        limit = 500
        while True:
            resp = client.post(
                "/list",
                json={
                    "collection": collection,
                    "allow_full_scan": True,
                    "offset": offset,
                    "limit": limit,
                    "return_fields": return_fields,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            docs.extend(data.get("documents", []))
            offset += data.get("count", 0)
            if offset >= data.get("total", 0) or data.get("count", 0) == 0:
                break
        return docs

    for doc in fetch_all("sparta_qra_canonical", ["source_control_id"]):
        control_id = doc.get("source_control_id")
        if control_id:
            canonical_counts[control_id] = canonical_counts.get(control_id, 0) + 1

    for doc in fetch_all("sparta_qra_relationship", ["source_control_id", "target_control_id"]):
        source_id = doc.get("source_control_id")
        target_id = doc.get("target_control_id")
        if source_id and target_id:
            relationship_counts[f"{source_id}:{target_id}"] = relationship_counts.get(f"{source_id}:{target_id}", 0) + 1

    for job in jobs:
        identity = job.get("identity", {})
        if job.get("job_type") == "canonical":
            source_id = identity.get("source_control_id")
            existing_count = canonical_counts.get(source_id, 0)
            if existing_count:
                existing_jobs.append({
                    "job_id": job.get("job_id"),
                    "collection": "sparta_qra_canonical",
                    "existing_count": existing_count,
                    "source_control_id": source_id,
                })
        else:
            source_id = identity.get("technique_id")
            target_id = (
                identity.get("target_control_id")
                or identity.get("countermeasure_id")
                or identity.get("tactic_id")
            )
            pair_key = f"{source_id}:{target_id}"
            existing_count = relationship_counts.get(pair_key, 0)
            if existing_count:
                existing_jobs.append({
                    "job_id": job.get("job_id"),
                    "collection": "sparta_qra_relationship",
                    "existing_count": existing_count,
                    "source_control_id": source_id,
                    "target_control_id": target_id,
                })

    return existing_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_manifest", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path. Defaults to <output>.report.json",
    )
    args = parser.parse_args()

    data = json.loads(args.input_manifest.read_text())
    jobs = data.get("jobs", [])

    with httpx.Client(base_url=memory_base_url(), timeout=60.0) as client:
        existing_jobs = summarize_existing_v2_jobs(client, jobs)

    existing_ids = {item["job_id"] for item in existing_jobs}
    cleaned_jobs = []
    exclusions = []
    for job in jobs:
        job_id = job.get("job_id")
        if job_id in SENTINEL_JOB_IDS:
            exclusions.append({"job_id": job_id, "reason": "sentinel"})
            continue
        if job_id in existing_ids:
            existing = next(item for item in existing_jobs if item["job_id"] == job_id)
            exclusions.append({"job_id": job_id, "reason": "existing_v2", **existing})
            continue
        cleaned_jobs.append(job)

    cleaned = dict(data)
    cleaned["jobs"] = cleaned_jobs
    args.output_manifest.write_text(json.dumps(cleaned, indent=2) + "\n")

    report_path = args.report or args.output_manifest.with_suffix(".report.json")
    report = {
        "input_manifest": str(args.input_manifest.resolve()),
        "output_manifest": str(args.output_manifest.resolve()),
        "input_jobs": len(jobs),
        "output_jobs": len(cleaned_jobs),
        "excluded_jobs": len(exclusions),
        "excluded_sentinel_jobs": sorted(item["job_id"] for item in exclusions if item["reason"] == "sentinel"),
        "excluded_existing_v2_jobs": sorted(item["job_id"] for item in exclusions if item["reason"] == "existing_v2"),
        "exclusions": exclusions,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
