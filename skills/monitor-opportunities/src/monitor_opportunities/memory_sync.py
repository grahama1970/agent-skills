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
import re
from pathlib import Path
from typing import Any

import httpx

MEMORY_URL_DEFAULT = "http://127.0.0.1:8601"
MORNING_COLLECTION = "morning_opportunities"
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=3.0)
RECALL_TIMEOUT = httpx.Timeout(connect=2.0, read=8.0, write=3.0, pool=2.0)
RECALL_HEALTH_TIMEOUT = httpx.Timeout(connect=1.0, read=2.0, write=1.0, pool=1.0)
READBACK_BATCH_SIZE = 500
RECALL_BATCH_LIMIT = 24
RECALL_K = 5
RECALL_CIRCUIT_FAILURE_LIMIT = 3
RECALL_CIRCUIT_TOTAL_FAILURE_LIMIT = 3
RECALL_CIRCUIT_OPEN_LIMITATION = (
    "Memory /recall circuit opened after repeated failures; "
    "remaining recall queries skipped with no raw database fallback."
)
RECALL_HEALTH_LIMITATION = (
    "Memory /health failed before governed recall; no raw database fallback attempted."
)


class MemorySyncError(ValueError):
    """Stable memory sync error."""


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return text[:80] or "unknown"


def _dedupe_queries(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        key = str(row.get("q") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def governed_recall_queries(
    opportunities: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]],
    *,
    limit: int = RECALL_BATCH_LIMIT,
) -> list[dict[str, str]]:
    """Build bounded question-shaped Memory recall requests for report context."""

    rows: list[dict[str, str]] = [
        {
            "category": "prior_projects",
            "target": "DARPA ARCOS formal methods aerospace R&D",
            "q": (
                "What memory evidence connects Graham Anderson to DARPA ARCOS, "
                "formal methods, aerospace R&D, Galois, GE, SRI, Lockheed, STR, or Vanderbilt?"
            ),
        }
    ]
    for opportunity in opportunities[:limit]:
        org = str(opportunity.get("organization") or "").strip()
        if org:
            rows.append(
                {
                    "category": "target_organization",
                    "target": org,
                    "q": (
                        f"What memory evidence do we have about {org} relevant to opportunities, "
                        "consulting, prior projects, contracts, contacts, or hiring?"
                    ),
                }
            )
    for signal in relationship_signals[:limit]:
        subject = str(signal.get("subject") or "").strip()
        org = str(signal.get("organization") or "").strip()
        path = " -> ".join(str(item) for item in signal.get("relationship_path") or [] if str(item).strip())
        if subject:
            rows.append(
                {
                    "category": "known_contacts",
                    "target": subject,
                    "q": (
                        f"What memory evidence do we have for contact {subject}"
                        f"{' at ' + org if org else ''} as a monitor contact or adjacent relationship?"
                    ),
                }
            )
        if path:
            rows.append(
                {
                    "category": "relationship_candidate",
                    "target": subject or org or path,
                    "q": f"What memory evidence supports this relationship path: {path}?",
                }
            )
    return _dedupe_queries(rows, limit)


def governed_memory_recall(
    memory_url: str,
    *,
    opportunities: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]],
    limit: int = RECALL_BATCH_LIMIT,
    k: int = RECALL_K,
) -> dict[str, Any]:
    """Run bounded Memory `/recall` requests and record fail-soft degradation.

    This never calls `/list`, ArangoDB, Qdrant, or any raw database fallback.
    """

    queries = governed_recall_queries(opportunities, relationship_signals, limit=limit)
    rows: list[dict[str, Any]] = []
    if not memory_url:
        return {
            "schema": "monitor_opportunities.governed_memory_recall.v1",
            "memory_url": memory_url,
            "attempted": 0,
            "succeeded": 0,
            "degraded": True,
            "degradation_reasons": ["memory_url_missing"],
            "queries": [],
            "external_effects": False,
        }
    with httpx.Client(timeout=RECALL_TIMEOUT) as client:
        try:
            health_response = client.get(f"{memory_url}/health", timeout=RECALL_HEALTH_TIMEOUT)
            health_response.raise_for_status()
            health = health_response.json()
            if health.get("ok") is not True:
                raise MemorySyncError("MEMORY_HEALTH_NOT_OK")
        except Exception as exc:  # noqa: BLE001 - recall must degrade instead of failing the run
            return {
                "schema": "monitor_opportunities.governed_memory_recall.v1",
                "memory_url": memory_url,
                "attempted": 0,
                "succeeded": 0,
                "skipped": len(queries),
                "circuit_open": False,
                "degraded": True,
                "degradation_reasons": [RECALL_HEALTH_LIMITATION],
                "queries": [
                    {
                        "query_id": f"memory-recall-{idx:02d}-{query['category']}-{_slug(query['target'])}",
                        **query,
                        "status": "SKIPPED_HEALTHCHECK_FAILED",
                        "found": False,
                        "confidence": 0.0,
                        "item_keys": [],
                        "score_channels": {"bm25": False, "dense": False, "graph": False},
                        "limitations": [RECALL_HEALTH_LIMITATION],
                        "error": type(exc).__name__,
                    }
                    for idx, query in enumerate(queries, start=1)
                ],
                "external_effects": False,
            }
        consecutive_failures = 0
        total_failures = 0
        for idx, query in enumerate(queries, start=1):
            query_id = f"memory-recall-{idx:02d}-{query['category']}-{_slug(query['target'])}"
            payload = {"q": query["q"], "k": k}
            try:
                response = client.post(f"{memory_url}/recall", json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as exc:
                rows.append(
                    {
                        "query_id": query_id,
                        **query,
                        "status": "DEGRADED_TIMEOUT",
                        "found": False,
                        "confidence": 0.0,
                        "item_keys": [],
                        "score_channels": {"bm25": False, "dense": False, "graph": False},
                        "limitations": ["Memory /recall timed out; no raw database fallback attempted."],
                        "error": type(exc).__name__,
                    }
                )
                consecutive_failures += 1
                total_failures += 1
            except Exception as exc:  # noqa: BLE001 - recall degradation must not fail the run
                rows.append(
                    {
                        "query_id": query_id,
                        **query,
                        "status": "DEGRADED_ERROR",
                        "found": False,
                        "confidence": 0.0,
                        "item_keys": [],
                        "score_channels": {"bm25": False, "dense": False, "graph": False},
                        "limitations": ["Memory /recall failed; no raw database fallback attempted."],
                        "error": type(exc).__name__,
                    }
                )
                consecutive_failures += 1
                total_failures += 1
            else:
                consecutive_failures = 0
                items = data.get("items") or []
                channels = {
                    "bm25": any((item.get("scores") or {}).get("bm25", 0) > 0 for item in items),
                    "dense": any((item.get("scores") or {}).get("dense", 0) > 0 for item in items),
                    "graph": any((item.get("scores") or {}).get("graph", 0) > 0 for item in items),
                }
                rows.append(
                    {
                        "query_id": query_id,
                        **query,
                        "status": "MATCHES" if data.get("found") else "NO_MATCHES",
                        "found": bool(data.get("found")),
                        "confidence": float(data.get("confidence") or 0.0),
                        "item_keys": [str(item.get("_key")) for item in items if item.get("_key")],
                        "score_channels": channels,
                        "limitations": list(data.get("errors") or []),
                        "took_ms": (data.get("meta") or {}).get("took_ms"),
                        "raw_database_fallback": False,
                    }
                )
            if (
                consecutive_failures >= RECALL_CIRCUIT_FAILURE_LIMIT
                or total_failures >= RECALL_CIRCUIT_TOTAL_FAILURE_LIMIT
            ):
                for skip_idx, skipped in enumerate(queries[idx:], start=idx + 1):
                    rows.append(
                        {
                            "query_id": (
                                f"memory-recall-{skip_idx:02d}-"
                                f"{skipped['category']}-{_slug(skipped['target'])}"
                            ),
                            **skipped,
                            "status": "SKIPPED_CIRCUIT_OPEN",
                            "found": False,
                            "confidence": 0.0,
                            "item_keys": [],
                            "score_channels": {"bm25": False, "dense": False, "graph": False},
                            "limitations": [RECALL_CIRCUIT_OPEN_LIMITATION],
                            "error": "recall_circuit_open",
                        }
                    )
                break
    degraded_reasons = sorted(
        {
            reason
            for row in rows
            if row.get("status") not in {"MATCHES", "NO_MATCHES"}
            for reason in row.get("limitations", [])
        }
    )
    return {
        "schema": "monitor_opportunities.governed_memory_recall.v1",
        "memory_url": memory_url,
        "attempted": sum(1 for row in rows if not str(row.get("status", "")).startswith("SKIPPED")),
        "succeeded": sum(1 for row in rows if row["status"] in {"MATCHES", "NO_MATCHES"}),
        "skipped": sum(1 for row in rows if str(row.get("status", "")).startswith("SKIPPED")),
        "circuit_open": any(row.get("status") == "SKIPPED_CIRCUIT_OPEN" for row in rows),
        "degraded": bool(degraded_reasons),
        "degradation_reasons": degraded_reasons,
        "queries": rows,
        "external_effects": False,
    }


def attach_memory_recall_provenance(
    opportunities: list[dict[str, Any]],
    relationship_signals: list[dict[str, Any]],
    recall_receipt: dict[str, Any],
) -> None:
    """Attach governed recall provenance to existing report-visible fields."""

    queries = recall_receipt.get("queries") or []
    by_target: dict[str, list[dict[str, Any]]] = {}
    for row in queries:
        by_target.setdefault(_slug(row.get("target")), []).append(row)
    degraded = bool(recall_receipt.get("degraded"))
    for opportunity in opportunities:
        org = str(opportunity.get("organization") or "").strip()
        matched = by_target.get(_slug(org), [])
        profile = opportunity.setdefault("screening_interface_profile", {})
        observed = profile.setdefault("observed", [])
        unknowns = profile.setdefault("unknowns", ["Memory recall not yet evaluated."])
        if any(row.get("found") for row in matched):
            keys = sorted({key for row in matched for key in row.get("item_keys", [])})
            observed.append(
                "Governed Memory recall found organization context: "
                + ", ".join(keys[:5])
            )
        elif matched:
            unknowns.append("Governed Memory recall found no stored organization context.")
        if degraded:
            unknowns.append("Governed Memory recall degraded; no raw database fallback was attempted.")
    for signal in relationship_signals:
        subject = str(signal.get("subject") or signal.get("organization") or "").strip()
        matched = by_target.get(_slug(subject), [])
        if any(row.get("found") for row in matched):
            signal["memory_recall_found"] = True
            signal["memory_recall_degraded"] = degraded
            refs = [f"memory-recall://{row['query_id']}" for row in matched if row.get("found")]
            signal["evidence_refs"] = list(dict.fromkeys([*(signal.get("evidence_refs") or []), *refs]))
            signal["provenance"] = (
                str(signal.get("provenance") or "")
                + "; governed Memory recall found supporting contact context"
            ).strip("; ")
        elif matched or degraded:
            signal["memory_recall_found"] = False
            signal["memory_recall_degraded"] = True if degraded else False


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
