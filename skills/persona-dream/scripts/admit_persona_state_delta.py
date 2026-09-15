#!/usr/bin/env python3
"""Deterministic persona-state admission for the preregistered C0/C1 experiment.

No LLM, no heuristics: the frozen contract
(contracts/c0c1_matched_experiment.v1.md) and the frozen baseline capsule
(contracts/c0c1_baseline.json, digest-verified at runtime) decide everything.

Admission reads an emotional-context packet from recall, RECOMPUTES every
admission-relevant fact from the exact-reread source documents (persona,
relationship, derived status, canonical event identity/class, declared-scale
intensity, valence, timestamp) using the SAME logic as recall, and treats
packet fields as claims to cross-check — any disagreement is
REJECTED packet_source_disagreement. Only when every preregistered gate passes
does it write ONE bounded persona_state_delta record with an exact /list
reread. Every rejection writes NOTHING and proves it with a before/after
/list key-set comparison.

Integrity rules:
- only `source_event_identity_class == "canonical"` (RECOMPUTED from the
  source doc, not the packet) counts toward MIN_DISTINCT_EVENTS;
- any trigger whose source rereads as derived/persona-mismatched is rejected
  or excluded (defense in depth; recall already excludes upstream);
- counted events need distinct source-document hashes AND distinct non-empty
  timestamps (preregistered distinctness, not just distinct canonical ids);
- declared intensity scale required; valence recognized; intensity finite and
  in [0,1]; an ACCEPTED record with zero delta is impossible;
- --user is required and must equal the frozen capsule user; the delta scope
  is ALWAYS the capsule user, never derived from packet fields;
- admission is cumulative: `before` is the independently folded current arm
  state (baseline + validated prior deltas), clamped against the frozen
  baseline by max_abs_from_baseline;
- the baseline capsule is hash-frozen (FROZEN_BASELINE_SHA256 in
  c0c1_frozen.py); a mismatched capsule is a BLOCKED hard failure.

DISPOSITION is returned with exit code 0; nonzero exits are infra failures,
capsule violations, or BLOCKED integrity violations only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from c0c1_frozen import (
    COLLECTION,
    DELTA_SCHEMA,
    delta_idempotency_key,
    load_verified_baseline,
    validate_delta_doc,
)

RECEIPT_SCHEMA = "persona_dream.persona_state_admission_receipt.v1"

_RECALL_MODULE_PATH = Path(__file__).resolve().parent / "recall_emotional_triggers.py"

_DELTA_REREAD_FIELDS = (
    "_key", "schema", "record_type", "kind", "persona_id", "user_id",
    "axis", "scope", "before", "delta", "after",
    "source_event_ids", "source_document_sha256s", "source_keys",
    "idempotency_key", "accepted_at", "baseline_version", "baseline_sha256",
)

_VALENCE_SIGNS = {"positive": 1.0, "negative": -1.0}


def _load_recall_module():
    """Reuse the SAME hashing/identity implementation recall used."""
    spec = importlib.util.spec_from_file_location("persona_dream_recall_emotional_triggers", _RECALL_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:48] or "x"


def recall_sha(payload: Any) -> str:
    """The exact serializer recall used for source_document_sha256."""
    return _load_recall_module()._sha(payload)


def parse_args_ns(**kwargs) -> argparse.Namespace:
    """Deterministic-case entry point: build the Namespace directly."""
    defaults = dict(
        persona="", axis="", packet=None, user="", arm=None,
        baseline=None, output=None, receipt=None, source_docs=None,
        prior_deltas=None,
        offline=False, memory_base_url="http://127.0.0.1:8601", json=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _receipt(disposition: str, reason: str | None, **extra: Any) -> dict[str, Any]:
    base = {
        "schema": RECEIPT_SCHEMA,
        "disposition": disposition,
        "reason": reason,
        "interpretation_note": (
            "Admission is deterministic over declared emotional signals "
            "(valence, intensity, canonical event identity) recomputed from "
            "the exact source reread. It cannot see non-emotional content "
            "differences; this experiment therefore proves deterministic "
            "evolution from declared, provenance-bound emotional signals, "
            "not that experiential semantic content caused the change."
        ),
        "collection": COLLECTION,
        "mocked": False,
        "failed_gates": [],
    }
    base.update(extra)
    return base


def _resolve_source_docs(
    client: httpx.Client | None,
    triggers: list[dict[str, Any]],
    attested: dict[str, Any] | None,
    *,
    offline: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Reread each trigger's source document: live /list, or an offline
    --source-docs file whose bytes must match the packet's declared
    source_document_sha256. Returns {source_key: doc}, problems."""
    docs: dict[str, dict[str, Any]] = {}
    problems: list[dict[str, str]] = []
    for t in triggers:
        prov = t.get("provenance") if isinstance(t.get("provenance"), dict) else {}
        key = str(prov.get("source_key") or "")
        if not key:
            problems.append({"source_key": key, "problem": "missing provenance.source_key"})
            continue
        declared = str(prov.get("source_document_sha256") or "")
        if attested and key in attested:
            doc = attested[key]
            recomputed = recall_sha(doc)
            if declared and declared != recomputed:
                problems.append({"source_key": key, "problem": f"attested hash mismatch: declared={declared} recomputed={recomputed}"})
                continue
            docs[key] = doc
            continue
        if offline:
            problems.append({"source_key": key, "problem": "offline mode but source doc not attested in --source-docs"})
            continue
        if client is None:
            problems.append({"source_key": key, "problem": "no client and no attested doc"})
            continue
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": key}})
        resp.raise_for_status()
        found = resp.json().get("documents") or []
        if len(found) != 1:
            problems.append({"source_key": key, "problem": f"source reread count {len(found)}"})
            continue
        doc = found[0]
        recomputed = recall_sha(doc)
        if declared and declared != recomputed:
            problems.append({"source_key": key, "problem": f"live hash mismatch: declared={declared} recomputed={recomputed}"})
            continue
        docs[key] = doc
    return docs, problems


def _declared_scale_known(doc: dict[str, Any]) -> bool:
    """The source record must DECLARE its intensity scale. intensity_value
    without intensity_scale_max is E-null's corruption and fails closed;
    a record with neither field also fails closed."""
    if doc.get("intensity_scale_max") is not None and doc.get("intensity_value") is not None:
        try:
            return float(doc["intensity_scale_max"]) > 0
        except (TypeError, ValueError):
            return False
    return False


def _recompute_trigger_facts(
    mod: Any,
    doc: dict[str, Any],
    packet_trigger: dict[str, Any],
    *,
    persona: str,
    user: str,
) -> tuple[dict[str, Any], list[str]]:
    """Recompute every admission-relevant fact from the reread source document
    using recall's own logic; cross-check the packet's claims. Packet fields
    are never authoritative (BIND_TRIGGER_FACTS_TO_SOURCE)."""
    disagreements: list[str] = []

    persona_ok = bool(mod._matches_persona(doc, persona))
    rel = str(mod._source_user(doc) or "")
    ok, adm_reason = mod._source_admissibility(doc, persona=persona, user=user)
    derived = (not ok) and str(adm_reason or "").startswith("derived")

    event = doc.get("event_context") if isinstance(doc.get("event_context"), dict) else {}
    existing_event_id = doc.get("event_id") or doc.get("source_event_id") or event.get("event_id")
    identity_class = "canonical" if existing_event_id else "document_fallback"
    identity = str(existing_event_id) if existing_event_id else mod._sha({
        "collection": COLLECTION, "key": str(doc.get("_key") or ""), "document_sha256": mod._sha(doc),
    })

    scale_known = _declared_scale_known(doc)
    if scale_known:
        intensity = float(doc["intensity_value"]) / float(doc["intensity_scale_max"])
    else:
        intensity = mod._intensity(doc)
    valence = str((doc.get("emotional_context") or {}).get("emotional_valence") or "").lower()
    observed = str(mod._one_line(
        doc.get("observed_at") or doc.get("source_observed_at") or doc.get("timestamp") or doc.get("created_at"), 40,
    ) or "")

    pt = packet_trigger
    pt_identity = str(pt.get("source_event_identity") or "")
    if pt_identity and pt_identity != identity:
        disagreements.append(f"source_event_identity packet={pt_identity} recomputed={identity}")
    pt_class = str(pt.get("source_event_identity_class") or "")
    if pt_class and pt_class != identity_class:
        disagreements.append(f"source_event_identity_class packet={pt_class} recomputed={identity_class}")
    pt_rel = str(pt.get("source_user_id") or "")
    if pt_rel and pt_rel != rel:
        disagreements.append(f"source_user_id packet={pt_rel} recomputed={rel}")
    appraisal = pt.get("appraisal") if isinstance(pt.get("appraisal"), dict) else {}
    pt_valence = str(appraisal.get("valence") or "").lower()
    if pt_valence and pt_valence != valence:
        disagreements.append(f"valence packet={pt_valence} recomputed={valence}")
    pt_intensity = appraisal.get("intensity")
    if pt_intensity is not None:
        try:
            if abs(float(pt_intensity) - float(intensity)) > 1e-6:
                disagreements.append(f"intensity packet={pt_intensity} recomputed={intensity}")
        except (TypeError, ValueError):
            disagreements.append(f"intensity packet={pt_intensity!r} not numeric")
    pt_observed = str(pt.get("source_observed_at") or "")
    if pt_observed and observed and pt_observed != observed:
        disagreements.append(f"source_observed_at packet={pt_observed} recomputed={observed}")

    facts = {
        "persona_ok": persona_ok,
        "relationship": rel,
        "derived": derived,
        "admissible": bool(ok),
        "admissibility_reason": str(adm_reason or ""),
        "identity": identity,
        "identity_class": identity_class,
        "intensity": intensity,
        "valence": valence,
        "observed": observed,
        "scale_known": scale_known,
        "doc_sha": mod._sha(doc),
    }
    return facts, disagreements


def run(args: argparse.Namespace) -> dict[str, Any]:
    baseline, baseline_sha = load_verified_baseline(Path(args.baseline))
    admission = baseline["admission"]
    baseline_state = baseline.get("baseline_state") or {}

    # FREEZE_C0C1_CAPSULE: runtime identity must equal the preregistered one.
    if args.persona != baseline.get("persona"):
        raise SystemExit(f"BLOCKED_C0C1_CAPSULE_PERSONA: {args.persona!r} != capsule {baseline.get('persona')!r}")
    if not args.user or args.user != baseline.get("user"):
        raise SystemExit(f"BLOCKED_C0C1_CAPSULE_USER: {args.user!r} != capsule {baseline.get('user')!r}")

    mod = _load_recall_module()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    triggers = [t for t in (packet.get("triggers") or []) if isinstance(t, dict)]

    common = dict(
        persona_id=args.persona, axis=args.axis, baseline_version=baseline.get("schema"),
        baseline_sha256=baseline_sha,
        packet_path=str(Path(args.packet).resolve()),
    )

    if args.axis not in (admission.get("writable_axes") or []):
        receipt = _receipt("REJECTED", "axis_not_writable", **common)
        receipt["failed_gates"] = [f"axis {args.axis!r} not in writable_axes"]
        return receipt
    if not triggers:
        receipt = _receipt("REJECTED", "no_triggers", **common)
        return receipt

    attested = None
    if args.source_docs:
        attested = json.loads(Path(args.source_docs).read_text(encoding="utf-8"))

    timeout = httpx.Timeout(30.0, connect=2.0)
    client_ctx = None if args.offline else httpx.Client(base_url=args.memory_base_url.rstrip("/"), timeout=timeout)
    client = client_ctx.__enter__() if client_ctx else None

    # ZERO_WRITE_PREPOST_PROOF: capture the pre-decision delta key set; every
    # rejection re-lists on the way out and proves no new key appeared.
    def _delta_keyset() -> list[str]:
        if client is None:
            return []
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 500, "filters": {"record_type": "persona_state_delta"}})
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
        return sorted(str(d.get("_key") or "") for d in docs
                      if str(d.get("persona_id") or "") == args.persona
                      and str(d.get("user_id") or "") == args.user
                      and (args.arm is None or str(d.get("arm") or "") == args.arm))

    pre_keys = _delta_keyset() if client is not None else []

    def _zero_write_proof() -> dict[str, Any]:
        if client is None:
            return {"mode": "offline_deterministic", "keys_before": pre_keys, "keys_after": pre_keys, "no_new_keys": True}
        post = _delta_keyset()
        return {"mode": "list_keyset", "keys_before": pre_keys, "keys_after": post,
                "no_new_keys": set(post).issubset(set(pre_keys))}

    def _reject(reason: str, **extra: Any) -> dict[str, Any]:
        receipt = _receipt("REJECTED", reason, **common)
        receipt["zero_write_proof"] = _zero_write_proof()
        receipt.update(extra)
        return receipt

    try:
        if derived := [t for t in triggers if t.get("source_is_derived")]:
            receipt = _reject("derived_source",
                              derived_trigger_ids=[t.get("trigger_id") for t in derived],
                              excluded_triggers=[{"trigger_id": t.get("trigger_id"), "reason": "derived_source"} for t in derived])
            return receipt

        source_docs, problems = _resolve_source_docs(client, triggers, attested, offline=args.offline)
        if problems:
            raise SystemExit(f"BLOCKED_ADMISSION_SOURCE_REREAD_FAILED: {problems}")

        # BIND_TRIGGER_FACTS_TO_SOURCE: recompute every fact from the reread
        # source; packet disagreement is a forged-packet rejection.
        excluded: list[dict[str, str]] = []
        counted: list[dict[str, Any]] = []
        for t in triggers:
            prov = t.get("provenance") if isinstance(t.get("provenance"), dict) else {}
            key = str(prov.get("source_key") or "")
            doc = source_docs.get(key)
            if doc is None:
                excluded.append({"trigger_id": t.get("trigger_id"), "reason": "source_doc_unresolved"})
                continue
            facts, disagreements = _recompute_trigger_facts(mod, doc, t, persona=args.persona, user=args.user)
            if disagreements:
                receipt = _receipt("REJECTED", "packet_source_disagreement", **common)
                receipt["zero_write_proof"] = _zero_write_proof()
                receipt["disagreements"] = [{"trigger_id": t.get("trigger_id"), "details": disagreements}]
                return receipt
            if facts["derived"]:
                receipt = _reject("derived_source",
                                  excluded_triggers=[{"trigger_id": t.get("trigger_id"), "reason": "derived_source_recomputed"}])
                return receipt
            if not facts["admissible"]:
                receipt = _reject("source_inadmissible",
                                  excluded_triggers=[{"trigger_id": t.get("trigger_id"), "reason": facts["admissibility_reason"]}])
                return receipt
            if not facts["persona_ok"]:
                excluded.append({"trigger_id": t.get("trigger_id"), "reason": "persona_mismatch"})
                continue
            if facts["relationship"] != args.user:
                excluded.append({"trigger_id": t.get("trigger_id"), "reason": "relationship_mismatch"})
                continue
            if args.arm and str(doc.get("arm") or "") != args.arm:
                excluded.append({"trigger_id": t.get("trigger_id"), "reason": "arm_mismatch"})
                continue
            if facts["identity_class"] != "canonical":
                excluded.append({"trigger_id": t.get("trigger_id"), "reason": "document_fallback_identity_not_counted"})
                continue
            counted.append({**t, "_facts": facts})

        counted_event_ids = sorted({str(t["_facts"]["identity"]) for t in counted})
        min_events = int(admission.get("min_distinct_events", 2))
        receipt_extra = dict(
            **common,
            counted_event_ids=counted_event_ids,
            distinct_canonical_count=len(counted_event_ids),
            excluded_triggers=excluded,
            trigger_count=len(triggers),
        )

        if len(counted_event_ids) < min_events:
            return _reject("insufficient_distinct_events", **receipt_extra)

        # C1-null ordering: the declared-scale gate stays POST-count so the
        # corrupt-scale arm clears distinctness and fails HERE.
        bad_scale = [t.get("trigger_id") for t in counted if not t["_facts"]["scale_known"]]
        if bad_scale:
            return _reject("unknown_intensity_scale", unknown_scale_trigger_ids=bad_scale, **receipt_extra)

        # C1_DISTINCT_SOURCE_GATES: preregistered distinctness is more than
        # distinct canonical ids — the reread sources must differ in document
        # hash AND carry distinct non-empty event timestamps.
        doc_shas = [t["_facts"]["doc_sha"] for t in counted]
        timestamps = [t["_facts"]["observed"] for t in counted]
        if len(set(doc_shas)) != len(doc_shas) or len(set(timestamps)) != len(timestamps) or not all(timestamps):
            return _reject("insufficient_distinct_sources",
                           distinct_doc_sha_count=len(set(doc_shas)),
                           distinct_timestamp_count=len(set(timestamps)), **receipt_extra)

        # REQUIRE_AXIS_SIGNAL_FINITE: recognized valence, finite in-[0,1]
        # declared-scale intensity, usable axis signal for every counted event.
        no_signal = []
        for t in counted:
            f = t["_facts"]
            intensity = float(f["intensity"]) if f["intensity"] is not None else float("nan")
            if f["valence"] not in _VALENCE_SIGNS or not math.isfinite(intensity) or not 0.0 <= intensity <= 1.0:
                no_signal.append(t.get("trigger_id"))
        if no_signal:
            return _reject("no_axis_signal", no_signal_trigger_ids=no_signal, **receipt_extra)

        # Contradiction on the axis from RECOMPUTED valence/intensity.
        signed = [( _VALENCE_SIGNS[t["_facts"]["valence"]], float(t["_facts"]["intensity"]) ) for t in counted]
        support = sum(i for s, i in signed if s > 0)
        oppose = sum(i for s, i in signed if s < 0)
        margin = None
        if oppose > 0:
            margin = round(support - oppose, 3)
            if margin < float(admission.get("contradiction_min_margin", 0.20)):
                return _reject("contradictory_experience", contradiction_margin=margin, **receipt_extra)

        direction = 1.0 if support >= oppose else -1.0
        raw_magnitude = round(sum(i for _, i in signed) / len(signed), 3) if signed else 0.0
        max_delta = float(admission.get("max_delta_per_cycle", 0.10))
        magnitude = min(max_delta, raw_magnitude)
        clamp_applied = raw_magnitude > max_delta
        clamp_reduction = round(raw_magnitude - magnitude, 3) if clamp_applied else 0.0
        delta = round(direction * magnitude, 3)
        if delta == 0.0:
            # Zero-delta ACCEPTs are forbidden: acceptance must move state.
            return _reject("zero_magnitude", raw_magnitude=raw_magnitude, **receipt_extra)

        # TRUE_CUMULATIVE_ADMISSION: `before` is the independently folded
        # current arm state (frozen baseline + validated prior deltas),
        # never simply the frozen baseline.
        scope = {"kind": "relationship", "user_id": args.user}
        if client is not None:
            prior = _delta_docs(client, args)
            for d in prior:
                violation = validate_delta_doc(d, baseline)
                if violation:
                    raise SystemExit(f"BLOCKED_ADMISSION_INVALID_PRIOR_DELTA {d.get('_key')}: {violation}")
            cumulative_before = round(float(baseline_state.get(args.axis, 0.0)) + sum(float(d.get("delta")) for d in prior), 6)
            cumulative_basis = "folded_prior_deltas"
        else:
            prior_offline = []
            if getattr(args, "prior_deltas", None):
                prior_offline = json.loads(Path(args.prior_deltas).read_text(encoding="utf-8"))
                for d in prior_offline:
                    violation = validate_delta_doc(d, baseline)
                    if violation:
                        raise SystemExit(f"BLOCKED_ADMISSION_INVALID_PRIOR_DELTA {d.get('_key')}: {violation}")
            cumulative_before = round(float(baseline_state.get(args.axis, 0.0)) + sum(float(d.get("delta")) for d in prior_offline), 6)
            cumulative_basis = "offline_attested_prior_deltas"
        before = cumulative_before
        after = round(before + delta, 3)
        max_abs = float(admission.get("max_abs_from_baseline", 0.25))
        baseline_value = float(baseline_state.get(args.axis, 0.0))
        if abs(after - baseline_value) > max_abs:
            overshoot = abs(after - baseline_value) - max_abs
            delta = round(delta - (overshoot if delta > 0 else -overshoot), 3)
            after = round(before + delta, 3)
            clamp_applied = True
            clamp_reduction = round(clamp_reduction + overshoot, 3)
            if delta == 0.0:
                return _reject("zero_magnitude", raw_magnitude=raw_magnitude, cumulative_clamp_exhausted=True, **receipt_extra)

        idempotency_key = delta_idempotency_key(
            persona=args.persona, axis=args.axis, scope=scope,
            canonical_ids=counted_event_ids, delta=delta,
            baseline_version=baseline.get("schema"),
        )

        if not args.offline:
            existing = _count_matching_deltas(client, args, counted_event_ids)
            if any(d.get("idempotency_key") == idempotency_key for d in existing):
                receipt = _receipt("ALREADY_APPLIED", None, **receipt_extra)
                receipt.update(idempotency_key=idempotency_key, delta=delta, before=before, after=after,
                               clamp_applied=clamp_applied, clamp_reduction=clamp_reduction,
                               contradiction_margin=margin, scope=scope,
                               cumulative_before=cumulative_before, cumulative_basis=cumulative_basis)
                receipt["zero_write_proof"] = _zero_write_proof()
                return receipt
        else:
            existing = []

        doc = {
            "_key": f"persona_state_delta_{_slug(args.persona)}_{_slug(args.axis)}_{idempotency_key.split(':')[-1][:12]}",
            "schema": DELTA_SCHEMA,
            "record_type": "persona_state_delta",
            "kind": "persona_dream_persona_state_delta",
            "project": "persona-dream",
            "persona_id": args.persona,
            "user_id": scope["user_id"],
            "axis": args.axis,
            "scope": scope,
            "before": before,
            "delta": delta,
            "after": after,
            "baseline_version": baseline.get("schema"),
            "baseline_sha256": baseline_sha,
            "source_event_ids": counted_event_ids,
            "source_event_identity_classes": sorted({str(t.get("_facts", t).get("identity_class", "canonical")) for t in counted}),
            "source_document_sha256s": sorted(str((t.get("provenance") or {}).get("source_document_sha256") or "") for t in counted),
            "source_keys": sorted(str((t.get("provenance") or {}).get("source_key") or "") for t in counted),
            "idempotency_key": idempotency_key,
            "accepted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "arm": args.arm,
            "contradiction_margin": margin,
            "clamp_applied": clamp_applied,
            "clamp_reduction": clamp_reduction,
            "cumulative_before": cumulative_before,
            "synthetic_boundary": "bounded deterministic state delta; not a claim of felt emotion or literal memory",
            "tags": ["persona-dream", "persona-state-delta", f"persona:{args.persona}",
                     *( [f"user:{scope['user_id']}"] if scope["user_id"] else [] ), "c0c1-delta"],
            "problem": f"What personality-state delta should {args.persona} carry on {args.axis}?",
            "solution": f"Deterministic admission accepted {delta} on {args.axis} from {len(counted_event_ids)} distinct canonical events.",
            "retrieval_text": f"persona_state_delta {args.axis} {delta} for {args.persona} from {counted_event_ids}",
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "memory_write_method": "/upsert+/list-exact-reread",
            "mocked": False,
            "live": not args.offline,
        }

        if args.offline:
            receipt = _receipt("ACCEPTED", None, **receipt_extra)
            receipt.update(idempotency_key=idempotency_key, delta=delta, before=before, after=after,
                           clamp_applied=clamp_applied, clamp_reduction=clamp_reduction,
                           contradiction_margin=margin, scope=scope, exact_reread=None,
                           offline_deterministic=True, delta_key=doc["_key"],
                           cumulative_before=cumulative_before, cumulative_basis=cumulative_basis,
                           zero_write_proof=_zero_write_proof())
            return receipt

        client.post("/upsert", json={"collection": COLLECTION, "documents": [doc]}).raise_for_status()
        resp = client.post("/list", json={"collection": COLLECTION, "limit": 2, "filters": {"_key": doc["_key"]}})
        resp.raise_for_status()
        reread = resp.json().get("documents") or []
        if len(reread) != 1:
            raise SystemExit(f"exact reread count mismatch for {doc['_key']}: {len(reread)}")
        mismatches = [f for f in _DELTA_REREAD_FIELDS if reread[0].get(f) != doc.get(f)]
        if mismatches:
            raise SystemExit(f"exact reread field mismatch for {doc['_key']}: {mismatches}")

        receipt = _receipt("ACCEPTED", None, **receipt_extra)
        receipt.update(idempotency_key=idempotency_key, delta=delta, before=before, after=after,
                       clamp_applied=clamp_applied, clamp_reduction=clamp_reduction,
                       contradiction_margin=margin, scope=scope, exact_reread=True,
                       delta_key=doc["_key"],
                       cumulative_before=cumulative_before, cumulative_basis=cumulative_basis)
        receipt["zero_write_proof"] = {"mode": "accept_wrote_exactly_one",
                                       "delta_key": doc["_key"],
                                       "keys_after": _delta_keyset()}
        return receipt
    finally:
        if client_ctx:
            client_ctx.close()


def _delta_docs(client: httpx.Client, args: argparse.Namespace) -> list[dict[str, Any]]:
    # /list filters are scalar field-equality; array fields (tags) do not
    # match. record_type is the precise probe for delta documents.
    resp = client.post("/list", json={"collection": COLLECTION, "limit": 500, "filters": {"record_type": "persona_state_delta"}})
    resp.raise_for_status()
    docs = resp.json().get("documents") or []
    return [d for d in docs
            if str(d.get("persona_id") or "") == args.persona
            and str(d.get("user_id") or "") == args.user
            and (args.arm is None or str(d.get("arm") or "") == args.arm)]


def _count_matching_deltas(client: httpx.Client, args: argparse.Namespace, counted_event_ids: list[str]) -> list[dict[str, Any]]:
    """Deltas whose source_event_ids set equals the counted set: the sharp
    idempotency probe (a delta over the SAME events)."""
    wanted = sorted(set(counted_event_ids))
    return [d for d in _delta_docs(client, args) if sorted(d.get("source_event_ids") or []) == wanted]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persona", required=True)
    ap.add_argument("--axis", required=True)
    ap.add_argument("--packet", type=Path, required=True, help="emotional_context.json from recall")
    ap.add_argument("--user", required=True, help="relationship filter; must equal the frozen capsule user")
    ap.add_argument("--arm", default=None)
    ap.add_argument("--baseline", type=Path, default=Path(__file__).resolve().parents[1] / "contracts" / "c0c1_baseline.json")
    ap.add_argument("--source-docs", type=Path, default=None, help="offline attested {source_key: doc} map; bytes must match declared hashes")
    ap.add_argument("--prior-deltas", type=Path, default=None, help="offline attested list of previously accepted delta docs for cumulative admission")
    ap.add_argument("--offline", action="store_true", help="no network: requires --source-docs; skips live idempotency/zero-write /list proofs (recorded in receipt)")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipt = run(args)
    for path in (args.output, args.receipt):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['disposition']} reason={receipt.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
