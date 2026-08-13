"""Publish one completed run's shortlist into the memory service.

The memory collections are the product surface: chat/Buzz agents answer
"what came in overnight?" from `morning_opportunities` and record decisions
through the ledger-backed `decision` command. The rendered report remains a
frozen per-run receipt, not the interaction surface. Writes go through the
memory daemon's `/store` endpoint, which upserts by `_key` and performs
Qdrant semantic sync for keyed documents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

MEMORY_URL_DEFAULT = "http://127.0.0.1:8601"
MORNING_COLLECTION = "morning_opportunities"
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=3.0)


class MemorySyncError(ValueError):
    """Stable memory sync error."""


def morning_documents(report: dict[str, Any], run_dir: str) -> list[dict[str, Any]]:
    """Build keyed memory documents for one run's shortlist and summary."""

    run_id = report.get("run_id")
    if not run_id:
        raise MemorySyncError("REPORT_MISSING_RUN_ID")
    generated = str(report.get("generated_at") or "")
    date_slug = generated[:10] or "undated"
    packets_by_opportunity: dict[str, list[dict[str, Any]]] = {}
    for packet in report.get("outreach_packets", []):
        packets_by_opportunity.setdefault(packet["opportunity_id"], []).append(packet)
    documents: list[dict[str, Any]] = []
    lane_lines = [
        f"Lane {lane['lane']}: {lane['result_status']} ({lane['candidates_admitted']}/{lane['candidates_observed']})"
        for lane in report.get("lane_coverage", [])
    ]
    for opportunity in report.get("opportunities", []):
        oid = opportunity["opportunity_id"]
        packets = packets_by_opportunity.get(oid, [])
        text = "\n".join(
            [
                f"{opportunity['title']} at {opportunity['organization']} (lane {opportunity['lane']}, "
                f"fit {opportunity.get('fit_score')}, {opportunity.get('eligibility_state')}).",
                *[f"Why: {line}" for line in opportunity.get("why_candidate", [])],
                f"Posting: {opportunity.get('posting_url') or opportunity.get('primary_evidence_url') or 'n/a'}",
                f"Outreach packets: {len(packets)}; decisions are recorded via the run decision ledger.",
            ]
        )
        documents.append(
            {
                "_key": f"{date_slug}-{oid.replace(':', '-')}",
                "schema": "monitor_opportunities.morning_opportunity.v1",
                "title": f"Morning opportunity {date_slug}: {opportunity['title']} — {opportunity['organization']}",
                "text": text,
                "run_id": run_id,
                "run_dir": run_dir,
                "opportunity_id": oid,
                "organization": opportunity["organization"],
                "lane": opportunity["lane"],
                "fit_score": opportunity.get("fit_score"),
                "posting_url": opportunity.get("posting_url"),
                "date": date_slug,
                "tags": ["morning-opportunities", "career", date_slug, opportunity["organization"].lower().replace(" ", "-")],
                "scope": "",
                "external_effects": False,
            }
        )
    for signal in report.get("relationship_signals", []):
        sid = signal["signal_id"]
        org = str(signal.get("organization") or "").strip()
        subject = str(signal.get("subject") or "").strip()
        path = signal.get("relationship_path") or []
        text = "\n".join(
            [
                f"Relationship signal for {subject} at {org}.",
                f"Type: {signal.get('signal_type')}.",
                "Path: " + " -> ".join(str(item) for item in path),
                f"Provenance: {signal.get('provenance')}.",
                f"Recommended local action: {signal.get('recommended_action')}.",
                "External effects: false; the human decides whether to reconnect, attend, watch, skip, or defer.",
                "Evidence: " + ", ".join(str(ref) for ref in signal.get("evidence_refs", []) or ["n/a"]),
            ]
        )
        documents.append(
            {
                "_key": f"{date_slug}-{sid}",
                "schema": "monitor_opportunities.relationship_signal.v1",
                "title": f"Relationship signal {date_slug}: {subject} — {org}",
                "text": text,
                "run_id": run_id,
                "run_dir": run_dir,
                "date": date_slug,
                "relationship_signal_id": sid,
                "source_opportunity_id": signal.get("source_opportunity_id"),
                "subject": subject,
                "organization": org,
                "signal_type": signal.get("signal_type"),
                "relationship_path": path,
                "relationship_graph": {
                    "nodes": [
                        {"id": str(node).lower().replace(" ", "-"), "label": str(node)}
                        for node in path
                    ],
                    "edges": [
                        {
                            "from": str(path[idx]).lower().replace(" ", "-"),
                            "to": str(path[idx + 1]).lower().replace(" ", "-"),
                            "relationship": signal.get("signal_type"),
                        }
                        for idx in range(max(0, len(path) - 1))
                    ],
                },
                "evidence_refs": signal.get("evidence_refs", []),
                "tags": [
                    "morning-opportunities",
                    "relationship-signal",
                    "monitor-contacts",
                    "reconnect",
                    date_slug,
                    org.lower().replace(" ", "-") if org else "unknown-org",
                ],
                "scope": "",
                "external_effects": False,
            }
        )
    accounting = report.get("artifact_accounting", {})
    documents.append(
        {
            "_key": f"{date_slug}-run-summary-{str(run_id).replace(':', '-')[-16:]}",
            "schema": "monitor_opportunities.morning_summary.v1",
            "title": f"Morning opportunity summary {date_slug}: {len(report.get('opportunities', []))} shortlisted",
            "text": "\n".join(
                [
                    f"Run {run_id} shortlisted {len(report.get('opportunities', []))} opportunities.",
                    *lane_lines,
                    f"Hidden action-worthy artifacts: {accounting.get('hidden_total')}.",
                    f"Run directory (frozen report receipt): {run_dir}",
                ]
            ),
            "run_id": run_id,
            "run_dir": run_dir,
            "date": date_slug,
            "tags": ["morning-opportunities", "career", "summary", date_slug],
            "scope": "",
            "external_effects": False,
        }
    )
    return documents


def sync_run_to_memory(run_dir: Path, memory_url: str = MEMORY_URL_DEFAULT) -> dict[str, Any]:
    """Store one run's shortlist docs and read one back for proof."""

    report_path = run_dir / "report" / "report.json"
    if not report_path.exists():
        raise MemorySyncError("RUN_REPORT_MISSING")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    documents = morning_documents(report, str(run_dir))
    stored: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        for document in documents:
            response = client.post(
                f"{memory_url}/store",
                json={"document": document, "collection": MORNING_COLLECTION},
            )
            if response.status_code != 200 or not response.json().get("stored"):
                raise MemorySyncError(f"MEMORY_STORE_FAILED:{document['_key']}:{response.status_code}")
            stored.append(document["_key"])
        readback = client.post(
            f"{memory_url}/recall",
            json={"q": documents[-1]["title"], "collections": [MORNING_COLLECTION], "k": 3},
        )
    readback_keys = [item.get("_key") for item in readback.json().get("items", [])] if readback.status_code == 200 else []
    return {
        "schema": "monitor_opportunities.memory_sync_receipt.v1",
        "collection": MORNING_COLLECTION,
        "stored_keys": stored,
        "readback_found": documents[-1]["_key"] in readback_keys,
        "memory_url": memory_url,
        "external_effects": False,
    }
