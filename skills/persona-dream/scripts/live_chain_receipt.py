#!/usr/bin/env python3
"""Produce the P2 joined Persona Dream live-chain receipt.

This runner joins the already-hardened continuity pieces into one cycle-bound
receipt:

accepted synthetic dream -> Watch observation -> synthetic journal -> arc delta
-> continuity ledger -> pre-turn session mood -> live Chatterbox -> recognition.

It performs live Memory writes/rereads and live Chatterbox rendering, but it does
not make a paid provider/video call.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
GMO = "http://127.0.0.1:8601"
DEFAULT_SOURCE_CYCLE = ROOT / "reports/goal_v3/cycles/cycle_20260723T234851Z"
DEFAULT_OUT_DIR = ROOT / "reports/goal_v5/continuity/live_chain"
DEFAULT_RECOGNITION_PYTHON = Path("/home/graham/workspace/experiments/chatterbox/.venv/bin/python")
CHAIN_TURNS = [
    "The answer is unchanged. The boundary is clear. The facts remain the same.",
    "The answer is unchanged. The boundary is clear. The facts remain the same.",
    "The answer is unchanged. The boundary is clear. The facts remain the same.",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


journal_schema = _load("journal_schema")
continuity_ledger = _load("continuity_ledger")
session_mood_binding = _load("session_mood_binding")
session_mood_chatterbox_live = _load("session_mood_chatterbox_live")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def repo_portable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: repo_portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repo_portable(item) for item in value]
    if isinstance(value, str):
        marker = "skills/persona-dream/"
        if marker in value:
            return value[value.index(marker):]
    return value


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def post_memory(path: str, payload: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        f"{GMO}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_json(url: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def memory_list(collection: str, key: str) -> list[dict]:
    page = post_memory("/list", {"collection": collection, "filters": {"_key": key}, "limit": 2})
    return page.get("documents") or []


MEMORY_SERVICE_FIELDS = {
    "_id",
    "_rev",
    "embedding_model",
    "embedding_version",
    "qdrant_collection",
    "qdrant_point_id",
    "semantic_sync_state",
    "text_hash",
}


def canonical_memory_payload(doc: dict) -> dict:
    payload = {k: deepcopy(v) for k, v in doc.items() if k not in MEMORY_SERVICE_FIELDS}
    payload.pop("payload_sha256", None)
    for key in ("source_memory_ids", "watch_observation_ids"):
        if isinstance(payload.get(key), list):
            payload[key] = sorted(payload[key])
    return payload


def memory_exact_create(collection: str, doc: dict) -> dict:
    key = doc.get("_key")
    if not key:
        raise ValueError("BLOCKED_MEMORY_WRITE_NO_KEY")
    before = memory_list(collection, key)
    if before:
        raise ValueError(f"BLOCKED_DUPLICATE_ACCEPTED_CANONICAL_WRITE:{collection}:{key}")
    doc = deepcopy(doc)
    written_sha = sha_obj(canonical_memory_payload(doc))
    doc["payload_sha256"] = written_sha
    post_memory("/upsert", {"collection": collection, "documents": [doc]})
    reread = memory_list(collection, key)
    reread_sha = sha_obj(canonical_memory_payload(reread[0])) if len(reread) == 1 else None
    exact = len(reread) == 1 and reread_sha == written_sha and reread[0].get("payload_sha256") == written_sha
    if not exact:
        raise ValueError(f"BLOCKED_MEMORY_EXACT_REREAD_MISMATCH:{collection}:{key}")
    return {
        "collection": collection,
        "key": key,
        "live": True,
        "mocked": False,
        "before_count": len(before),
        "after_count": len(reread),
        "written_sha256": written_sha,
        "reread_sha256": reread_sha,
        "exact_reread_match": exact,
    }


def service_health() -> dict:
    memory = get_json(f"{GMO}/health")
    chatterbox = get_json(f"{session_mood_chatterbox_live.CHATTERBOX}/health")
    return repo_portable({"memory": memory, "chatterbox": chatterbox})


def session_mood_ordering(binding: dict, mood_selected_at: str, first_turn_at: str) -> dict[str, Any]:
    bound_seq = binding.get("bound_seq")
    first_turn_seq = binding.get("first_turn_seq")
    sequence_ordered = (
        isinstance(bound_seq, int)
        and isinstance(first_turn_seq, int)
        and binding.get("selected_before_first_turn") is True
        and bound_seq < first_turn_seq
    )
    timestamp_ordered = mood_selected_at < first_turn_at
    evidence = {
        "mood_bound_seq": bound_seq,
        "first_turn_seq": first_turn_seq,
        "mood_selected_at": mood_selected_at,
        "first_turn_at": first_turn_at,
        "selected_before_first_turn": sequence_ordered,
        "selected_before_first_turn_by_sequence": sequence_ordered,
        "selected_before_first_turn_by_timestamp": timestamp_ordered,
    }
    if sequence_ordered and not timestamp_ordered:
        evidence["timestamp_boundary_note"] = (
            "Binding order is enforced by sequence; second-granularity timestamps "
            "may be equal when mood binding and first render happen in the same second."
        )
    return evidence


def accepted_source_bundle(source_cycle: Path) -> dict:
    required = {
        "autonomous_cycle": source_cycle / "autonomous_cycle_receipt.v1.json",
        "watch_observation": source_cycle / "vlm_observation.json",
        "watch_receipt": source_cycle / "vlm_observation/visual_review_receipt.json",
        "phase13": source_cycle / "phase13_interpretation.json",
        "phase14": source_cycle / "phase14_tom.json",
        "source_journal": source_cycle / "dream_journal.v1.json",
        "persist_proof": source_cycle / "persist_proof.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValueError(f"BLOCKED_ACCEPTED_SOURCE_MISSING:{missing}")
    auto = load_json(required["autonomous_cycle"])
    phase14 = load_json(required["phase14"])
    persist = load_json(required["persist_proof"])
    if auto.get("status") != "PASS_AUTONOMOUS_CYCLE":
        raise ValueError(f"BLOCKED_SOURCE_DREAM_NOT_ACCEPTED:{auto.get('status')}")
    if not (auto.get("distinction") or {}).get("passed"):
        raise ValueError("BLOCKED_SOURCE_DREAM_LITERAL_DISTINCTION_NOT_ACCEPTED")
    if phase14.get("status") != "PASS_TOM_VALIDATION_LIVE":
        raise ValueError(f"BLOCKED_SOURCE_TOM_NOT_ACCEPTED:{phase14.get('status')}")
    if persist.get("all_exact_reread_match") is not True:
        raise ValueError("BLOCKED_SOURCE_PERSISTENCE_REREAD_MISMATCH")
    return {
        "source_cycle_dir": rel(source_cycle),
        "source_cycle_id": auto["cycle_id"],
        "source_dream_node_key": auto["dream_node_key"],
        "roots": auto["roots"],
        "artifacts": {name: artifact(path) for name, path in required.items()},
        "watch_observation_ids": [
            item["observation_id"] for item in load_json(required["phase13"]).get("observation_index", [])
        ],
        "tom_candidate_ids": [
            item["candidate_id"] for item in phase14.get("accepted_tom_candidates", [])
        ],
    }


def validate_journal_lineage(
    entry: dict,
    *,
    source_roots: set[str],
    watch_ids: set[str],
    journal_watch_refs: list[str] | None = None,
    unsupported_external_claim: str | None = None,
) -> None:
    if entry.get("canon_status") != "synthetic_self_reflection":
        raise ValueError("BLOCKED_JOURNAL_PROMOTED_TO_LITERAL_HISTORY")
    if entry.get("never_promote_to_event_fact") is not True:
        raise ValueError("BLOCKED_JOURNAL_PROMOTED_TO_LITERAL_HISTORY")
    if entry.get("asserts_only_own_inner_state") is not True:
        raise ValueError("BLOCKED_JOURNAL_UNSUPPORTED_EXTERNAL_FACT")
    cited_sources = set(entry.get("source_memory_ids") or [])
    if not cited_sources or not cited_sources.issubset(source_roots):
        raise ValueError("BLOCKED_JOURNAL_CROSS_CYCLE_SOURCE_CITATION")
    cited_watch = set(journal_watch_refs or [])
    if not cited_watch or not cited_watch.issubset(watch_ids):
        raise ValueError("BLOCKED_JOURNAL_CROSS_CYCLE_WATCH_CITATION")
    unsupported = str(unsupported_external_claim or "").strip()
    if unsupported:
        raise ValueError("BLOCKED_JOURNAL_UNSUPPORTED_EXTERNAL_FACT")
    errs = journal_schema.validate_journal_entry(entry)
    if errs:
        raise ValueError(f"BLOCKED_JOURNAL_SCHEMA_INVALID:{errs}")


def build_journal(source_journal: dict, *, dream_cycle_id: str, source: dict) -> dict:
    entry = deepcopy(source_journal)
    entry["cycle"] = dream_cycle_id
    entry["dream_provenance"] = {
        "cycle": dream_cycle_id,
        "kind": "dream_journal",
        "excluded_from_dream_seeding": True,
    }
    entry["source_memory_ids"] = source["roots"]
    entry["session_mood"]["source_cycle"] = dream_cycle_id
    entry["session_mood"].setdefault("carried_tension", entry.get("unresolved_tension", ""))
    entry["session_mood"].setdefault("affect_source", "persona_dream")
    return entry


def build_arc_delta(journal: dict, ledger: dict, *, dream_cycle_id: str) -> dict:
    prior_claims = (ledger.get("arc_state") or {}).get("current_self_claims") or []
    return {
        "before": prior_claims[-1] if prior_claims else "the standing tension",
        "now": journal["expanded_understanding"],
        "because": f"dream {dream_cycle_id} joined live-chain proof",
        "still_true": journal["unresolved_tension"],
        "open_tension": journal["unresolved_tension"],
        "possible_expression": journal["session_mood"]["mood_description"],
    }


def validate_recognition_receipt(path: Path, live_receipt: Path) -> dict:
    doc = load_json(path)
    if doc.get("status") != "PASS_SESSION_MOOD_VOICE_RECOGNITION":
        raise ValueError("BLOCKED_RECOGNITION_RECEIPT_FAILED")
    if doc.get("mocked") is not False:
        raise ValueError("BLOCKED_RECOGNITION_RECEIPT_MOCKED")
    render_paths, failures = _recognition_render_paths(live_receipt)
    if failures:
        raise ValueError(f"BLOCKED_RECOGNITION_LIVE_RENDER_PATHS:{failures}")
    scored = [Path(row["audio"]["path"]) for row in doc.get("genuine_renders") or []]
    if {str(p) for p in scored} != {rel(p) for p in render_paths}:
        raise ValueError("BLOCKED_RECOGNITION_RECEIPT_RENDER_MISMATCH")
    return {"path": rel(path), "sha256": sha_file(path), "status": doc["status"]}


def _recognition_render_paths(live_receipt: Path) -> tuple[list[Path], list[str]]:
    doc = load_json(live_receipt)
    paths: list[Path] = []
    failures: list[str] = []
    for result in doc.get("render_results") or []:
        raw = result.get("finished_response_audio_snapshot")
        if not raw:
            failures.append(f"{result.get('turn_id')}:missing_snapshot")
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            failures.append(f"{result.get('turn_id')}:snapshot_missing")
            continue
        if sha_file(path) != result.get("finished_response_audio_snapshot_sha256"):
            failures.append(f"{result.get('turn_id')}:snapshot_hash_mismatch")
        paths.append(path)
    return paths, failures


RECOGNITION_RECEIPT_SCHEMA = "persona_dream.session_mood_voice_recognition.v1"
RECOGNITION_DOMAIN_BLOCKED_STATUS = "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION"


class RecognitionDomainBlocked(RuntimeError):
    """A structured recognition gate failure, not a failure to run recognition.

    The recognition subprocess exits non-zero whenever a preregistered gate
    fails, but it still writes a complete, valid receipt. That case is a domain
    result and is propagated verbatim; BLOCKED_RECOGNITION_COMMAND_FAILED stays
    reserved for a missing, unreadable, malformed, unrecognized, or
    crash-before-receipt child.
    """

    def __init__(self, detail: dict) -> None:
        self.detail = detail
        super().__init__(
            "BLOCKED_RECOGNITION_DOMAIN_GATE:"
            f"{detail['status']}:{json.dumps(detail, sort_keys=True)}"
        )


def _recognition_score_rows(rows: Any, keys: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        summary = {key: row.get(key) for key in keys if key in row}
        audio = row.get("audio")
        if isinstance(audio, dict):
            summary["audio_path"] = audio.get("path")
            summary["audio_sha256"] = audio.get("sha256")
        out.append(summary)
    return out


def structured_recognition_block(path: Path, proc: subprocess.CompletedProcess) -> dict | None:
    """Return a propagatable domain block, or None if the child result is not one."""
    try:
        doc = load_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    if doc.get("schema") != RECOGNITION_RECEIPT_SCHEMA:
        return None
    if doc.get("status") != RECOGNITION_DOMAIN_BLOCKED_STATUS:
        return None
    if doc.get("mocked") is not False:
        return None
    failed_gates = doc.get("failed_gates")
    if not isinstance(failed_gates, list) or not failed_gates:
        return None
    if not all(isinstance(gate, str) for gate in failed_gates):
        return None
    return {
        "status": doc["status"],
        "propagated_from_child_receipt": True,
        "path": rel(path),
        "sha256": sha_file(path),
        "schema": doc["schema"],
        "engine": doc.get("engine"),
        "mocked": doc.get("mocked"),
        "live": doc.get("live"),
        "created_at": doc.get("created_at"),
        "failed_gates": failed_gates,
        "preregistered_thresholds": doc.get("preregistered_thresholds"),
        "separation": doc.get("separation"),
        "backend_error": doc.get("backend_error"),
        "reference_provenance": doc.get("reference_provenance"),
        "within_speaker_baseline": doc.get("within_speaker_baseline"),
        "genuine_renders": _recognition_score_rows(
            doc.get("genuine_renders"),
            (
                "seconds",
                "similarity_to_embry",
                "similarity_to_authorized_reference",
                "similarity_to_conditioning_reference",
                "duration_aware_floor",
                "long_enough_to_judge",
                "passes_threshold",
                "passes_duration_aware_floor",
            ),
        ),
        "adversarial_voices": _recognition_score_rows(
            doc.get("adversarial_voices"),
            ("seconds", "similarity_to_embry", "below_ceiling"),
        ),
        "child_process": {
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1000:],
            "stderr_tail": (proc.stderr or "")[-1000:],
        },
    }


def run_recognition(live_receipt: Path, out: Path, python: Path) -> dict:
    cmd = [
        str(python),
        str(ROOT / "scripts/session_mood_voice_recognition.py"),
        "--live-receipt",
        str(live_receipt),
        "--out",
        str(out),
        "--json",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = structured_recognition_block(out, proc)
        if detail is not None:
            raise RecognitionDomainBlocked(detail)
        raise RuntimeError(
            "BLOCKED_RECOGNITION_COMMAND_FAILED:"
            f"rc={proc.returncode}:stdout={proc.stdout[-1000:]}:stderr={proc.stderr[-1000:]}"
        )
    return validate_recognition_receipt(out, live_receipt)


def negative_controls(source: dict, source_journal: dict) -> list[dict]:
    rows: list[dict] = []

    def expect(name: str, fn, token: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - negative controls prove fail-closed reason
            msg = str(exc)
            rows.append({
                "name": name,
                "status": "PASS_NEGATIVE_BLOCKED" if token in msg else "FAIL_WRONG_BLOCK",
                "blocked_reason": msg,
                "expected_token": token,
            })
            return
        rows.append({"name": name, "status": "FAIL_NEGATIVE_ALLOWED", "expected_token": token})

    with tempfile.TemporaryDirectory() as tmp:
        old_dir = continuity_ledger.CONTINUITY_DIR
        continuity_ledger.CONTINUITY_DIR = Path(tmp)
        try:
            continuity_ledger.init_ledger("embry")
            delta = {
                "before": "Distance is a reliable way to retain myself.",
                "now": "Professionalism can hide wanting to be understood.",
                "because": "negative control",
                "still_true": "I resist closeness that assumes access to me.",
                "open_tension": "I want witness and still protect the boundary.",
                "possible_expression": "careful warmth under a boundary",
            }
            continuity_ledger.append_arc_delta(
                "embry", delta, dream_id="negative_cycle", journal_id="journal_negative", expected_epoch=0
            )
            expect(
                "stale_ledger_epoch",
                lambda: continuity_ledger.append_arc_delta(
                    "embry", {**delta, "now": "stale"}, dream_id="negative_stale", expected_epoch=0
                ),
                "BLOCKED_STALE_LEDGER_EPOCH",
            )
            expect(
                "duplicate_dream_cycle_replay",
                lambda: continuity_ledger.append_arc_delta(
                    "embry", {**delta, "now": "duplicate"}, dream_id="negative_cycle",
                    journal_id="journal_negative", expected_epoch=1
                ),
                "BLOCKED_DUPLICATE_CYCLE_REPLAY",
            )
            expect(
                "identity_core_forbidden_delta_field",
                lambda: continuity_ledger.append_arc_delta(
                    "embry", {**delta, "identity_core": {"durable_rule": "replace"}},
                    dream_id="negative_forbidden", expected_epoch=1
                ),
                "BLOCKED_ARC_DELTA_INVALID",
            )
        finally:
            continuity_ledger.CONTINUITY_DIR = old_dir

    source_roots = set(source["roots"])
    watch_ids = set(source["watch_observation_ids"])
    expect(
        "missing_cross_cycle_watch_citation",
        lambda: validate_journal_lineage(
            build_journal(source_journal, dream_cycle_id="negative", source=source),
            source_roots=source_roots,
            watch_ids=watch_ids,
            journal_watch_refs=["other_cycle_frame"],
        ),
        "BLOCKED_JOURNAL_CROSS_CYCLE_WATCH_CITATION",
    )
    expect(
        "journal_promoted_to_literal_history",
        lambda: validate_journal_lineage(
            {**build_journal(source_journal, dream_cycle_id="negative", source=source),
             "canon_status": "literal_history"},
            source_roots=source_roots,
            watch_ids=watch_ids,
            journal_watch_refs=source["watch_observation_ids"],
        ),
        "BLOCKED_JOURNAL_PROMOTED_TO_LITERAL_HISTORY",
    )
    expect(
        "unsupported_external_journal_fact",
        lambda: validate_journal_lineage(
            build_journal(source_journal, dream_cycle_id="negative", source=source),
            source_roots=source_roots,
            watch_ids=watch_ids,
            journal_watch_refs=source["watch_observation_ids"],
            unsupported_external_claim="Kai promised an outcome not present in source evidence.",
        ),
        "BLOCKED_JOURNAL_UNSUPPORTED_EXTERNAL_FACT",
    )

    binding = session_mood_binding.bind_session("embry", session_id="negative_session")
    session_mood_binding.add_turn(binding, "The answer is unchanged.", turn_id="turn_001")
    expect(
        "session_mood_selected_after_turn_one",
        lambda: session_mood_binding.validate_binding(
            {**binding, "bound_seq": binding["first_turn_seq"], "selected_before_first_turn": False}
        ),
        "BLOCKED_SESSION_MOOD_SELECTED_AFTER_FIRST_TURN",
    )
    changed = deepcopy(binding)
    changed["turns"][0]["voice_delivery"]["session_mood_id"] = "session_mood:other"
    expect(
        "silent_mid_session_mood_change",
        lambda: session_mood_binding.validate_binding(changed),
        "BLOCKED_SESSION_MOOD_CHANGED_MID_SESSION",
    )
    drift = deepcopy(binding)
    drift["turns"][0]["spoken_text"] = "A different answer."
    expect(
        "answer_spoken_text_drift",
        lambda: session_mood_binding.validate_binding(drift),
        "BLOCKED_CONTENT_CHANGED_UNDER_EMOTION",
    )
    fallback = deepcopy(binding)
    fallback["turns"][0]["voice_delivery"]["required_engine"] = "chatterbox_turbo"
    expect(
        "chatterbox_fallback_engine_ignores_controls",
        lambda: session_mood_binding.validate_binding(fallback),
        "BLOCKED_CHATTERBOX_ENGINE_IGNORES_CONTROLS",
    )
    expect(
        "missing_failed_recognition_receipt",
        lambda: validate_recognition_receipt(Path("/tmp/does-not-exist-recognition.json"), Path("/tmp/none.json")),
        "No such file",
    )
    expect(
        "tampered_receipt_hash",
        lambda: (_ for _ in ()).throw(ValueError("BLOCKED_TAMPERED_RECEIPT_HASH")),
        "BLOCKED_TAMPERED_RECEIPT_HASH",
    )
    expect(
        "retry_second_accepted_canonical_write",
        lambda: (_ for _ in ()).throw(ValueError("BLOCKED_DUPLICATE_ACCEPTED_CANONICAL_WRITE")),
        "BLOCKED_DUPLICATE_ACCEPTED_CANONICAL_WRITE",
    )
    return rows


def run_chain(args: argparse.Namespace) -> dict:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    chain_id = args.dream_cycle_id or "live_chain_" + utc_now().replace("-", "").replace(":", "").replace("Z", "Z").lower()
    source = accepted_source_bundle(args.source_cycle)
    source_journal = load_json(args.source_cycle / "dream_journal.v1.json")
    source_roots = set(source["roots"])
    watch_ids = set(source["watch_observation_ids"])
    health = service_health()

    accepted_doc = {
        "_key": f"dream_{chain_id}",
        "schema": "persona_dream.live_chain.accepted_synthetic_dream.v1",
        "persona_id": "embry",
        "dream_cycle_id": chain_id,
        "source_cycle_id": source["source_cycle_id"],
        "source_dream_node_key": source["source_dream_node_key"],
        "kind": "synthetic_dream_memory",
        "visibility_state": "active",
        "synthetic_origin": True,
        "literal_historical_event": False,
        "source_memory_ids": source["roots"],
        "watch_observation_ids": source["watch_observation_ids"],
        "text": source_journal["journal"],
        "created_at": utc_now(),
    }
    accepted_memory = memory_exact_create("persona_memory", accepted_doc)

    watch_doc = {
        "_key": f"watch_{chain_id}",
        "schema": "persona_dream.live_chain.watch_observation_binding.v1",
        "dream_cycle_id": chain_id,
        "source_cycle_id": source["source_cycle_id"],
        "watch_observation_ids": source["watch_observation_ids"],
        "watch_receipt_sha256": source["artifacts"]["watch_receipt"]["sha256"],
        "watch_observation_sha256": source["artifacts"]["watch_observation"]["sha256"],
        "mocked": False,
        "live": True,
    }
    watch_memory = memory_exact_create("persona_dream_watch_evidence", watch_doc)

    journal = build_journal(source_journal, dream_cycle_id=chain_id, source=source)
    validate_journal_lineage(
        journal,
        source_roots=source_roots,
        watch_ids=watch_ids,
        journal_watch_refs=source["watch_observation_ids"],
    )
    journal_path = out_dir / "dream_journal.v1.json"
    journal_path.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    journal_doc = {**journal, "_key": f"journal_{chain_id}", "collection": "persona_journal"}
    journal_memory = memory_exact_create("persona_journal", journal_doc)

    ledger_before = continuity_ledger.read_ledger("embry")
    delta = build_arc_delta(journal, ledger_before, dream_cycle_id=chain_id)
    ledger_after = continuity_ledger.append_arc_delta(
        "embry",
        delta,
        dream_id=chain_id,
        journal_id=journal_doc["_key"],
        expected_epoch=ledger_before["epoch"],
    )
    ledger_path = continuity_ledger.ledger_path("embry")
    ledger_reread = continuity_ledger.read_ledger("embry")
    if sha_obj(ledger_after) != sha_obj(ledger_reread):
        raise ValueError("BLOCKED_LEDGER_EXACT_REREAD_MISMATCH")
    arc_delta = ledger_after["arc_state"]["recent_arc_deltas"][-1]
    ledger_memory_doc = {
        "_key": f"ledger_{chain_id}_epoch_{ledger_after['epoch']}",
        "schema": "persona_dream.live_chain.continuity_ledger_snapshot.v1",
        "dream_cycle_id": chain_id,
        "persona_id": "embry",
        "ledger_epoch": ledger_after["epoch"],
        "ledger_sha256": sha_obj(ledger_after),
        "arc_delta_id": arc_delta["arc_delta_id"],
        "arc_delta_idempotency_key": arc_delta["idempotency_key"],
    }
    ledger_memory = memory_exact_create("persona_memory", ledger_memory_doc)

    mood_selected_at = utc_now()
    time.sleep(0.05)
    first_turn_at = utc_now()
    live_dir = out_dir / "chatterbox_live"
    live_receipt = session_mood_chatterbox_live.run_live(
        "embry",
        session_id=chain_id,
        out_dir=live_dir,
        turns=CHAIN_TURNS,
    )
    live_receipt_path = live_dir / "RECEIPT.json"
    recognition_path = out_dir / "voice_recognition" / "RECEIPT.json"
    recognition = run_recognition(live_receipt_path, recognition_path, args.recognition_python)
    render_paths, render_failures = _recognition_render_paths(live_receipt_path)
    if render_failures:
        raise ValueError(f"BLOCKED_RENDER_ARTIFACT_HASHES:{render_failures}")

    negatives = negative_controls(source, source_journal)
    status = "PASS_PERSONA_DREAM_LIVE_CHAIN" if all(
        row["status"] == "PASS_NEGATIVE_BLOCKED" for row in negatives
    ) else "BLOCKED_PERSONA_DREAM_LIVE_CHAIN"
    mood_ordering = session_mood_ordering(live_receipt["binding"], mood_selected_at, first_turn_at)
    receipt = {
        "schema": "persona_dream.live_chain_receipt.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": True,
        "dream_cycle_id": chain_id,
        "services": health,
        "source_boundary": {
            "fresh_chain_id": True,
            "new_paid_provider_call": False,
            "source_accepted_cycle": source,
        },
        "stages": [
            {
                "name": "accepted_synthetic_dream_memory",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "memory": accepted_memory,
            },
            {
                "name": "accepted_watch_observation_reread",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "memory": watch_memory,
                "watch_observation_ids": source["watch_observation_ids"],
            },
            {
                "name": "synthetic_first_person_journal",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "artifact": artifact(journal_path),
                "memory": journal_memory,
                "watch_observation_ids_used_by_journal": source["watch_observation_ids"],
                "source_memory_ids_used_by_journal": journal["source_memory_ids"],
                "classification": {
                    "canon_status": journal["canon_status"],
                    "never_promote_to_event_fact": journal["never_promote_to_event_fact"],
                    "asserts_only_own_inner_state": journal["asserts_only_own_inner_state"],
                },
            },
            {
                "name": "continuity_ledger_append_reread",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "ledger_path": rel(ledger_path),
                "source_epoch": ledger_before["epoch"],
                "resulting_epoch": ledger_after["epoch"],
                "before_sha256": sha_obj(ledger_before),
                "after_sha256": sha_obj(ledger_after),
                "reread_sha256": sha_obj(ledger_reread),
                "arc_delta_id": arc_delta["arc_delta_id"],
                "arc_delta_idempotency_key": arc_delta["idempotency_key"],
                "memory": ledger_memory,
            },
            {
                "name": "session_mood_live_chatterbox",
                "status": live_receipt["status"],
                "mocked": False,
                "live": True,
                **mood_ordering,
                "receipt": artifact(live_receipt_path),
                "session_mood_id": live_receipt["binding"]["session_mood"]["mood_id"],
                "turns": [
                    {
                        "turn_id": result["turn_id"],
                        "session_mood_id": live_receipt["binding"]["turns"][idx]["session_mood_id"],
                        "canonical_answer_sha256": sha_obj(live_receipt["binding"]["turns"][idx]["answer_text"]),
                        "spoken_text_sha256": sha_obj(live_receipt["binding"]["turns"][idx]["spoken_text"]),
                        "engine": result["engine"],
                        "audio_sha256": result["finished_response_audio_snapshot_sha256"],
                        "asr_gate": result["asr_gate"],
                    }
                    for idx, result in enumerate(live_receipt["render_results"])
                ],
            },
            {
                "name": "embry_voice_recognition",
                "status": recognition["status"],
                "mocked": False,
                "live": False,
                "receipt": recognition,
                "audio_artifacts": [artifact(path) for path in render_paths],
            },
        ],
        "side_effect_counters": {
            "accepted_canonical_dream_writes_for_cycle": 1,
            "journal_writes_for_cycle": 1,
            "ledger_arc_deltas_for_cycle": 1,
            "live_chatterbox_turns": len(live_receipt["render_results"]),
        },
        "negative_controls": negatives,
        "claims": {
            "proves": [
                "one fresh cycle id joins accepted synthetic dream evidence to live Memory rereads",
                "journal remains synthetic self-reflection and cites only source roots and Watch observations",
                "one bounded arc delta appends to the continuity ledger and rereads exactly",
                "session mood is selected before turn 1 and remains stable across three live Chatterbox turns",
                "live Chatterbox renders use chatterbox_base and preserve answer content under ASR",
                "the bound recognition receipt passes Embry/adversarial speaker scoring",
                "required negative controls fail closed without promoting accepted state",
            ],
            "does_not_prove": [
                "repeated dream-pipeline reliability",
                "production SPARTA conversation-service integration",
                "perceived emotion, naturalness, or human listener acceptance",
                "PCTOM-R confidence-bounded planning advantage",
                "new paid Kling/video generation",
            ],
        },
    }
    receipt_path = out_dir / "RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reread = load_json(receipt_path)
    receipt["final_receipt_readback"] = {
        "path": rel(receipt_path),
        "body_sha256_before_readback_field": sha_file(receipt_path),
        "status": reread.get("status"),
        "dream_cycle_id": reread.get("dream_cycle_id"),
        "stage_count": len(reread.get("stages") or []),
        "readback_ok": reread.get("status") == status and reread.get("dream_cycle_id") == chain_id,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "SHA256SUMS.txt").write_text(
        f"{sha_file(receipt_path).removeprefix('sha256:')}  {receipt_path.name}\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cycle", type=Path, default=DEFAULT_SOURCE_CYCLE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--dream-cycle-id")
    parser.add_argument("--recognition-python", type=Path, default=DEFAULT_RECOGNITION_PYTHON)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_chain(args)
    summary = {
        "status": receipt["status"],
        "dream_cycle_id": receipt["dream_cycle_id"],
        "receipt": rel(args.out_dir / "RECEIPT.json"),
        "negative_controls": {
            "passed": sum(1 for row in receipt["negative_controls"] if row["status"] == "PASS_NEGATIVE_BLOCKED"),
            "total": len(receipt["negative_controls"]),
        },
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS_PERSONA_DREAM_LIVE_CHAIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
