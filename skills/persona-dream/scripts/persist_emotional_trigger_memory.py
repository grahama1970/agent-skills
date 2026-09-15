#!/usr/bin/env python3
"""Persist persona_dream.emotional_trigger.v1 records to Memory and reread them.

This is the write boundary for Persona Dream's emotional-context packets. A
successful /upsert response is not accepted as proof; every written trigger is
reread by exact _key through /list and checked field-by-field.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

COLLECTION = "persona_memory"
SCHEMA = "persona_dream.emotional_trigger.v1"
RECEIPT_SCHEMA = "persona_dream.emotional_trigger_memory_receipt.v1"
EXACT_FIELDS = (
    "_key",
    "schema",
    "persona_id",
    "user_id",
    "trigger_text",
    "empathy",
    "speech_delivery",
    "source_event_ids",
    "source_types",
    "provenance",
    "source_document_sha256",
    "relationship_context",
    "appraisal",
    "emotion_delta",
    "safe_response_constraint",
    "source_event_identity",
    "source_event_identity_class",
    "source_record_type",
    "source_kind",
    "source_user_id",
    "source_observed_at",
    "source_event_at",
    "recency_known",
    "source_is_derived",
)

_RECALL_MODULE_PATH = Path(__file__).resolve().parent / "recall_emotional_triggers.py"


def _load_recall_module():
    """Load the sibling recall module so persistence reuses the SAME hashing,
    relationship, and admissibility implementations recall used — the write
    boundary must not re-derive those rules independently."""
    spec = importlib.util.spec_from_file_location("persona_dream_recall_emotional_triggers", _RECALL_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:64] or "trigger"


def _sha(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _read_context(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"context must be a JSON object: {path}")
    return payload


def _one_line(text: str, limit: int = 360) -> str:
    return " ".join(str(text or "").split())[:limit].rstrip()


def _doc_for(trigger: dict[str, Any], *, persona: str, user: str, run_id: str, context_sha: str) -> dict[str, Any]:
    # SOURCE_RELATIONSHIP_IS_AUTHORITY: the trigger's source-bound relationship,
    # not the CLI --user value, is what gets persisted. args.user is only a
    # request filter (gated upstream); it never relabels the source.
    effective_user = str(trigger.get("source_user_id") or "") or str(user or "")
    trigger_id = str(trigger.get("trigger_id") or _slug(trigger.get("trigger_text"))).strip()
    key = f"persona_dream_emotional_trigger_{_slug(run_id)}_{_slug(trigger_id)}"
    empathy = trigger.get("empathy") if isinstance(trigger.get("empathy"), dict) else {}
    speech = trigger.get("speech_delivery") if isinstance(trigger.get("speech_delivery"), dict) else {}
    trigger_text = _one_line(trigger.get("trigger_text"))
    relationship = _one_line(trigger.get("relationship_context"))
    retrieval = " ".join(
        p for p in [
            f"Emotional trigger for {persona} responding to {effective_user or 'the speaker'}: {trigger_text}.",
            f"Relationship context: {relationship}." if relationship else "",
            f"Empathy confidence: {empathy.get('confidence')}." if empathy else "",
            f"Empathy gap: {_one_line(empathy.get('gap'))}." if empathy.get("gap") else "",
            f"Safe response: {_one_line(empathy.get('safe_response_constraint') or trigger.get('safe_response_constraint'))}." if (empathy.get("safe_response_constraint") or trigger.get("safe_response_constraint")) else "",
            f"Speech delivery: {_one_line(json.dumps(speech, sort_keys=True))}." if speech else "",
            f"Dream seed: {_one_line(trigger.get('dream_seed'))}." if trigger.get("dream_seed") else "",
        ] if p
    )
    tags = ["persona-dream", "emotional-trigger", f"persona:{persona}", f"run:{run_id}"]
    if effective_user:
        tags.append(f"user:{effective_user}")
    return {
        "_key": key,
        "schema": SCHEMA,
        "kind": "persona_dream_emotional_trigger",
        "record_type": "emotional_trigger",
        "project": "persona-dream",
        "persona_id": persona,
        "user_id": effective_user,
        "run_id": run_id,
        "trigger_id": trigger_id,
        "trigger_text": trigger_text,
        "relationship_context": relationship,
        "source_document_sha256": str((trigger.get("provenance") if isinstance(trigger.get("provenance"), dict) else {}).get("source_document_sha256") or ""),
        "source_event_ids": trigger.get("source_event_ids") or [],
        "source_types": trigger.get("source_types") or [],
        "source_event_identity": str(trigger.get("source_event_identity") or ""),
        "source_event_identity_class": str(trigger.get("source_event_identity_class") or ""),
        "source_record_type": str(trigger.get("source_record_type") or ""),
        "source_kind": str(trigger.get("source_kind") or ""),
        "source_user_id": str(trigger.get("source_user_id") or ""),
        "source_observed_at": str(trigger.get("source_observed_at") or ""),
        "source_event_at": str(trigger.get("source_event_at") or ""),
        "recency_known": bool(trigger.get("recency_known")),
        "source_is_derived": bool(trigger.get("source_is_derived")),
        "appraisal": trigger.get("appraisal") if isinstance(trigger.get("appraisal"), dict) else {},
        "emotion_delta": trigger.get("emotion_delta") if isinstance(trigger.get("emotion_delta"), dict) else {},
        "empathy": empathy,
        "speech_delivery": speech,
        "dream_seed": _one_line(trigger.get("dream_seed")),
        "safe_response_constraint": _one_line(empathy.get("safe_response_constraint") or trigger.get("safe_response_constraint")),
        "provenance": {
            **(trigger.get("provenance") if isinstance(trigger.get("provenance"), dict) else {}),
            "synthetic_boundary": "tone/empathy context, not a claim that the triggering event happened inside Embry's life",
            "context_sha256": context_sha,
        },
        "scope": "persona-dream/emotional-triggers",
        "tags": tags,
        "problem": (
            f"What emotional trigger should shape {persona}'s speech delivery for {effective_user}?"
            if effective_user else
            f"What emotional trigger should shape {persona}'s speech delivery?"
        ),
        "solution": retrieval,
        "retrieval_text": retrieval,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "memory_write_method": "/upsert+/list-exact-reread",
        "mocked": False,
        "live": True,
    }


def _write_and_reread(client: httpx.Client, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client.post("/upsert", json={"collection": COLLECTION, "documents": docs}).raise_for_status()
    results: list[dict[str, Any]] = []
    for doc in docs:
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": doc["_key"]}})
        resp.raise_for_status()
        body = resp.json()
        reread = body.get("documents") or []
        if len(reread) != 1:
            raise SystemExit(f"exact reread count mismatch for {doc['_key']}: {len(reread)}")
        got = reread[0]
        mismatches = [field for field in EXACT_FIELDS if got.get(field) != doc.get(field)]
        if mismatches:
            raise SystemExit(f"exact reread field mismatch for {doc['_key']}: {mismatches}")
        results.append({"_key": doc["_key"], "exact_reread": True, "semantic_sync_state": got.get("semantic_sync_state")})
    return results


def _reverify_sources(client: httpx.Client, triggers: list[dict[str, Any]], *, persona: str, recall_mod) -> list[dict[str, Any]]:
    """PERSIST_SOURCE_REVERIFY: the packet's claims about its source are not
    trusted. Before writing, reread each source document by exact _key,
    recompute its hash with the SAME serializer recall used, and re-verify
    persona, relationship, and admissibility. A forged packet fails here."""
    results = []
    for t in triggers:
        prov = t.get("provenance") if isinstance(t.get("provenance"), dict) else {}
        source_key = str(prov.get("source_key") or "")
        if not source_key:
            raise SystemExit("BLOCKED_TRIGGER_SOURCE_REVERIFY_FAILED: trigger packet missing provenance.source_key")
        collection = str(prov.get("source_collection") or COLLECTION)
        resp = client.post("/list", json={"collection": collection, "limit": 2, "filters": {"_key": source_key}})
        resp.raise_for_status()
        src_docs = resp.json().get("documents") or []
        if len(src_docs) != 1:
            raise SystemExit(f"BLOCKED_TRIGGER_SOURCE_REVERIFY_FAILED: source reread count {len(src_docs)} for {source_key}")
        src = src_docs[0]
        recomputed = recall_mod._sha(src)
        declared = str(prov.get("source_document_sha256") or "")
        if declared and declared != recomputed:
            raise SystemExit(f"BLOCKED_TRIGGER_SOURCE_REVERIFY_FAILED: source hash mismatch for {source_key}: declared={declared} recomputed={recomputed}")
        trigger_user = str(t.get("source_user_id") or "")
        source_user = recall_mod._source_user(src)
        if trigger_user and source_user != trigger_user:
            raise SystemExit(f"BLOCKED_TRIGGER_SOURCE_REVERIFY_FAILED: relationship mismatch for {source_key}: source={source_user!r} trigger={trigger_user!r}")
        admissible, reason = recall_mod._source_admissibility(src, persona=persona, user=(trigger_user or None))
        if not admissible:
            raise SystemExit(f"BLOCKED_TRIGGER_SOURCE_REVERIFY_FAILED: source no longer admissible ({reason}) for {source_key}")
        results.append({"source_key": source_key, "source_collection": collection, "recomputed_document_sha256": recomputed, "exact_reread": True})
    return results


def run(args: argparse.Namespace) -> dict[str, Any]:
    context_path = args.context or (args.run_dir / "emotional_context.json")
    context = _read_context(context_path)
    triggers = context.get("triggers") if isinstance(context.get("triggers"), list) else []
    triggers = [t for t in triggers if isinstance(t, dict)]
    if not triggers:
        return {
            "schema": RECEIPT_SCHEMA,
            "status": "BLOCKED_NO_EMOTIONAL_TRIGGERS",
            "collection": COLLECTION,
            "context_path": str(context_path),
            "failed_gates": ["no triggers[] in emotional context"],
            "mocked": False,
            "live": False,
        }
    context_sha = _sha(context)
    # SOURCE_RELATIONSHIP_IS_AUTHORITY: --user is a request filter; every
    # trigger must carry a source-bound relationship that matches it exactly.
    for t in triggers:
        pid = str(t.get("source_user_id") or "")
        if args.user:
            if not pid:
                raise SystemExit("BLOCKED_TRIGGER_RELATIONSHIP_UNPROVEN")
            if pid != args.user:
                raise SystemExit("BLOCKED_TRIGGER_RELATIONSHIP_MISMATCH")
    recall_mod = _load_recall_module()
    timeout = httpx.Timeout(30.0, connect=2.0)
    with httpx.Client(base_url=args.memory_base_url.rstrip("/"), timeout=timeout) as client:
        source_rereads = _reverify_sources(client, triggers, persona=args.persona, recall_mod=recall_mod)
        docs = [_doc_for(t, persona=args.persona, user=args.user, run_id=args.run_id, context_sha=context_sha) for t in triggers]
        rereads = _write_and_reread(client, docs)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS_EMOTIONAL_TRIGGER_MEMORY_REREAD",
        "collection": COLLECTION,
        "context_path": str(context_path),
        "context_sha256": context_sha,
        "persona_id": args.persona,
        "user_id": args.user,
        "persisted_user_ids": sorted({str(d["user_id"]) for d in docs}),
        "source_rereads": source_rereads,
        "run_id": args.run_id,
        "trigger_count": len(docs),
        "memory_keys": [d["_key"] for d in docs],
        "exact_rereads": rereads,
        "exact_fields": list(EXACT_FIELDS),
        "mocked": False,
        "live": True,
        "failed_gates": [],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=Path.cwd())
    ap.add_argument("--context", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--persona", default="embry")
    ap.add_argument("--user", default="", help="Optional relationship filter: every trigger's source_user_id must equal this. Never the authority for the persisted relationship.")
    ap.add_argument("--run-id", default=f"manual-{int(time.time())}")
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipt = run(args)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} triggers={receipt.get('trigger_count', 0)}")
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
