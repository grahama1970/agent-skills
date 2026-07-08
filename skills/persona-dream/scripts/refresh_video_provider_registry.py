#!/usr/bin/env python3
"""Refresh video-provider discovery evidence from Brave/fal search results."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PROVIDER_REGISTRY_REFRESH"
BLOCKED_STATUS = "BLOCKED_PROVIDER_REGISTRY_REFRESH"
SCHEMA = "persona_dream.video_provider_registry_refresh_receipt.v1"

DEFAULT_QUERIES = [
    "site:fal.ai/explore video generation Kling Seedance Veo Runway Luma Pika fal.ai models",
    "fal.ai video generation models Kling Seedance Runway Luma Pika Veo Sora",
    "fal.ai explore models video image-to-video text-to-video Seedance Kling top",
    "site:fal.ai/models video API Kling Seedance Veo Runway Luma Pika",
    "site:fal.ai/docs video API Kling Seedance provider schema fal",
]

PROVIDER_KEYWORDS = {
    "kling": ["kling"],
    "bytedance-seedance": ["seedance", "bytedance"],
    "veo": ["veo"],
    "sora": ["sora"],
    "runway": ["runway"],
    "luma": ["luma", "ray2", "ray 2"],
    "pika": ["pika"],
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def brave_search_script() -> Path:
    return Path(__file__).resolve().parents[2] / "brave-search" / "brave_search.py"


def brave_python() -> str:
    return shutil.which("python3", path="/usr/bin:/usr/local/bin") or "python3"


def run_live_brave_search(queries: list[str], count: int) -> tuple[list[dict[str, Any]], list[str]]:
    script = brave_search_script()
    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in queries:
        try:
            completed = subprocess.run(
                [brave_python(), str(script), "web", query, "--count", str(count), "--json"],
                check=True,
                capture_output=True,
                text=True,
            )
            payloads.append(json.loads(completed.stdout))
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            errors.append(f"{query}: {exc}; stderr={stderr}")
        except json.JSONDecodeError as exc:
            errors.append(f"{query}: {exc}")
    return payloads, errors


def load_fixture_results(results_dir: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted(results_dir.glob("*.json"))]


def result_text(result: dict[str, Any]) -> str:
    return " ".join(
        str(result.get(key, ""))
        for key in ("title", "description", "url")
    ).lower()


def discover_from_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    discovered: dict[str, dict[str, Any]] = {}
    total_results = 0
    fal_result_urls: set[str] = set()

    for payload in payloads:
        for result in payload.get("results") or []:
            if not isinstance(result, dict):
                continue
            total_results += 1
            text = result_text(result)
            url = str(result.get("url", ""))
            is_fal = "fal.ai" in text
            if is_fal and url:
                fal_result_urls.add(url)
            for provider_id, keywords in PROVIDER_KEYWORDS.items():
                if any(keyword in text for keyword in keywords):
                    record = discovered.setdefault(
                        provider_id,
                        {
                            "provider_id": provider_id,
                            "result_count": 0,
                            "fal_hosted_observed": False,
                            "fal_api_or_docs_urls": [],
                            "source_urls": [],
                        },
                    )
                    record["result_count"] += 1
                    if is_fal:
                        record["fal_hosted_observed"] = True
                        if ("/models/" in url or "/docs" in url or "api" in text) and url not in record["fal_api_or_docs_urls"]:
                            record["fal_api_or_docs_urls"].append(url)
                    if url and url not in record["source_urls"]:
                        record["source_urls"].append(url)

    return {
        "result_count": total_results,
        "fal_result_urls": sorted(fal_result_urls),
        "discovered_providers": sorted(discovered.values(), key=lambda item: item["provider_id"]),
    }


def refresh_provider_registry(
    receipt_out: Path,
    fixture_results_dir: Path | None,
    live_brave_search: bool,
    count: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    if fixture_results_dir:
        payloads = load_fixture_results(fixture_results_dir)
        search_errors: list[str] = []
        mode = "BRAVE_FIXTURE_RESULTS"
    elif live_brave_search:
        payloads, search_errors = run_live_brave_search(DEFAULT_QUERIES, count)
        mode = "LIVE_BRAVE_SEARCH"
    else:
        payloads = []
        search_errors = []
        mode = "NOT_RUN"
        blockers.append("BLOCKED_PROVIDER_REGISTRY_REFRESH_NOT_RUN")
    if search_errors:
        blockers.append("BLOCKED_BRAVE_SEARCH_FAILED")

    discovery = discover_from_payloads(payloads)
    discovered_ids = {item["provider_id"] for item in discovery["discovered_providers"]}
    fal_hosted_ids = {item["provider_id"] for item in discovery["discovered_providers"] if item["fal_hosted_observed"]}
    fal_api_doc_ids = {
        item["provider_id"]
        for item in discovery["discovered_providers"]
        if item.get("fal_api_or_docs_urls")
    }

    if not discovery["fal_result_urls"]:
        blockers.append("BLOCKED_FAL_MODEL_CATALOG_NOT_FOUND")
    if not discovered_ids:
        blockers.append("BLOCKED_TOP_VIDEO_PROVIDER_DISCOVERY_EMPTY")
    for required in ("kling", "bytedance-seedance"):
        if required not in discovered_ids:
            blockers.append(f"BLOCKED_REQUIRED_PROVIDER_NOT_DISCOVERED:{required}")
    for required_fal in ("kling", "bytedance-seedance"):
        if required_fal not in fal_hosted_ids:
            blockers.append(f"BLOCKED_FAL_HOSTED_PROVIDER_NOT_OBSERVED:{required_fal}")
        if required_fal not in fal_api_doc_ids:
            blockers.append(f"BLOCKED_FAL_API_DOCS_NOT_OBSERVED:{required_fal}")

    receipt = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "mode": mode,
        "queries": DEFAULT_QUERIES,
        "query_count": len(DEFAULT_QUERIES) if payloads else 0,
        "search_errors": search_errors,
        "result_count": discovery["result_count"],
        "fal_result_urls": discovery["fal_result_urls"],
        "discovered_provider_ids": sorted(discovered_ids),
        "fal_hosted_provider_ids": sorted(fal_hosted_ids),
        "fal_api_doc_provider_ids": sorted(fal_api_doc_ids),
        "discovered_providers": discovery["discovered_providers"],
        "blockers": blockers,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "Brave/fal provider discovery evidence was parsed into local provider candidates",
                "no provider, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "current provider schema compatibility",
                "provider-accessible URLs",
                "paid-call authorization",
                "manual acceptance",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--fixture-results-dir", type=Path)
    parser.add_argument("--live-brave-search", action="store_true")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = refresh_provider_registry(
        args.receipt_out.resolve(),
        args.fixture_results_dir.resolve() if args.fixture_results_dir else None,
        args.live_brave_search,
        args.count,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
