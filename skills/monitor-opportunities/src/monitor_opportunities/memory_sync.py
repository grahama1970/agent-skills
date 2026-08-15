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
READBACK_BATCH_SIZE = 500


class MemorySyncError(ValueError):
    """Stable memory sync error."""


def morning_documents(
    report: dict[str, Any],
    run_dir: str,
    include_relationship_signals: bool = True,
) -> list[dict[str, Any]]:
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
    relationship_signals = report.get("relationship_signals", []) if include_relationship_signals else []
    for signal in relationship_signals:
        sid = signal["signal_id"]
        org = str(signal.get("organization") or "").strip()
        subject = str(signal.get("subject") or "").strip()
        path = signal.get("relationship_path") or []
        contact_path = signal.get("contact_path") or []
        text = "\n".join(
            [
                f"Relationship signal for {subject} at {org}.",
                f"Type: {signal.get('signal_type')}.",
                f"Degree: {signal.get('degree_label')} ({signal.get('relationship_degree')}).",
                f"Confidence: {signal.get('confidence')}.",
                "Path: " + " -> ".join(str(item) for item in path),
                f"Provenance: {signal.get('provenance')}.",
                f"Recommended local action: {signal.get('recommended_action')}.",
                f"Contact channel risk: {signal.get('contact_channel_risk')}.",
                f"Recommended human channel: {signal.get('recommended_human_channel')}.",
                f"Channel rationale: {signal.get('channel_rationale')}.",
                "Preferred human channels: "
                + ", ".join(str(item) for item in signal.get("preferred_human_channels", []) or ["n/a"]),
                "Channel guidance: "
                + " ".join(str(item) for item in signal.get("channel_guidance", []) or ["n/a"]),
                "Channel limitations: "
                + " ".join(str(item) for item in signal.get("channel_limitations", []) or ["n/a"]),
                "Contact path evidence: "
                + " | ".join(
                    f"{edge.get('from')} -> {edge.get('to')} ({edge.get('relationship')}, {edge.get('evidence_status')})"
                    for edge in contact_path
                ),
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
                "contact_path": contact_path,
                "relationship_degree": signal.get("relationship_degree"),
                "degree_label": signal.get("degree_label"),
                "confidence": signal.get("confidence"),
                "confidence_reasons": signal.get("confidence_reasons", []),
                "contact_channel_risk": signal.get("contact_channel_risk"),
                "preferred_human_channels": signal.get("preferred_human_channels", []),
                "channel_guidance": signal.get("channel_guidance", []),
                "recommended_human_channel": signal.get("recommended_human_channel"),
                "channel_rationale": signal.get("channel_rationale"),
                "channel_limitations": signal.get("channel_limitations", []),
                "human_decision_options": signal.get("human_decision_options", []),
                "relationship_graph": {
                    "nodes": [
                        {"id": str(node).lower().replace(" ", "-"), "label": str(node)}
                        for node in path
                    ],
                    "edges": [
                        {
                            "from": str(edge.get("from")).lower().replace(" ", "-"),
                            "to": str(edge.get("to")).lower().replace(" ", "-"),
                            "relationship": edge.get("relationship"),
                            "evidence_status": edge.get("evidence_status"),
                            "evidence_refs": edge.get("evidence_refs", []),
                        }
                        for edge in contact_path
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


def sync_run_to_memory(
    run_dir: Path,
    memory_url: str = MEMORY_URL_DEFAULT,
    include_relationship_signals: bool = True,
) -> dict[str, Any]:
    """Store one run's shortlist docs and read one back for proof."""

    report_path = run_dir / "report" / "report.json"
    if not report_path.exists():
        raise MemorySyncError("RUN_REPORT_MISSING")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    documents = morning_documents(
        report,
        str(run_dir),
        include_relationship_signals=include_relationship_signals,
    )
    stored: list[str] = []
    readback_documents: list[dict[str, Any]] = []
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        for document in documents:
            response = client.post(
                f"{memory_url}/store",
                json={"document": document, "collection": MORNING_COLLECTION},
            )
            if response.status_code != 200 or not response.json().get("stored"):
                raise MemorySyncError(f"MEMORY_STORE_FAILED:{document['_key']}:{response.status_code}")
            stored.append(document["_key"])
        for start in range(0, len(stored), READBACK_BATCH_SIZE):
            key_batch = stored[start : start + READBACK_BATCH_SIZE]
            readback = client.post(
                f"{memory_url}/recall/by-keys",
                json={
                    "collection": MORNING_COLLECTION,
                    "keys": key_batch,
                    "return_fields": ["_key", "schema", "external_effects"],
                },
            )
            if readback.status_code != 200:
                raise MemorySyncError(f"MEMORY_READBACK_FAILED:{readback.status_code}")
            readback_documents.extend(readback.json().get("documents", []) or [])
    readback_keys = [str(item.get("_key")) for item in readback_documents if item.get("_key")]
    readback_key_set = set(readback_keys)
    missing_keys = [key for key in stored if key not in readback_key_set]
    relationship_keys = [
        document["_key"]
        for document in documents
        if document.get("schema") == "monitor_opportunities.relationship_signal.v1"
    ]
    return {
        "schema": "monitor_opportunities.memory_sync_receipt.v1",
        "collection": MORNING_COLLECTION,
        "stored_keys": stored,
        "readback_keys": readback_keys,
        "readback_missing_keys": missing_keys,
        "readback_count": len(readback_keys),
        "readback_found": not missing_keys,
        "relationship_readback_found": all(key in readback_key_set for key in relationship_keys),
        "readback_external_effects_false": all(
            item.get("external_effects") is False for item in readback_documents
        ),
        "memory_url": memory_url,
        "relationship_signals_included": include_relationship_signals,
        "external_effects": False,
    }
