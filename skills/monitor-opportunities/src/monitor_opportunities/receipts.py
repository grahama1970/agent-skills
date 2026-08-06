"""Source-receipt construction helpers.

Shared receipt scaffolding used by discovery and the mandatory required-source
receipts. Inputs: lane/provider/target/source_class strings and receipt dicts.
Outputs: typed receipt dicts. No IO, no external effects.
"""

from __future__ import annotations

from typing import Any

from .util import stable_id, utc_now


def base_receipt(lane: str, provider: str, target: str, source_class: str) -> dict[str, Any]:
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


def finalize_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["receipt_id"] = stable_id(
        f"src:{receipt['lane'].lower()}:{receipt['provider']}",
        {
            "target": receipt["target"],
            "status": receipt["result_status"],
            "hash": receipt["content_sha256"],
        },
    )
    return receipt
