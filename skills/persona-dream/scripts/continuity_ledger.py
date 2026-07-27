#!/usr/bin/env python3
"""Persona Continuity Ledger — the shared self that dreams/journals/moods belong to.

Roundtable-converged (2026-07-24): the piece that makes the already-built dreams,
journals, and moods belong to ONE PERSON who stays recognizably herself while she
changes (README's core question). Now persona-scoped so it serves ANY persona.

Multi-rate model, nothing silently overwrites the core:
  episodic canon (immutable)  <  identity_core (rare, versioned)
    <  arc_state (gradual, journal appends ONE arc_delta/cycle)  <  mood (fast)

Contract:
- read_ledger(persona): the dream selector, journal writer, and mood producer read this.
- append_arc_delta(persona, delta): the journal's ONLY write path into arc_state.
  May update arc_state; may NOT alter identity_core or episodic canon. Each delta
  carries a "still_true" clause -> change is ADDITIVE, not substitutive.
- identity_core is READ-MOSTLY: propose_core_amendment() is rate-limited and
  requires a theme EARNED across multiple cycles; it appends a versioned
  refinement, never a replacement, never a resolution of a core conflict.

The identity_core is authored per persona where an authored core exists (Embry's
is roundtable-authored, kept as her canonical DATA); any other persona gets a
core BOOTSTRAPPED from its own corpus (its dominant unresolved counterpart
tensions) — nothing generic is hardcoded, and the bootstrap evolves via deltas.

Pure file I/O + validation; no network. Deterministic.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTINUITY_DIR = ROOT / "reports/goal_v5/continuity"
SCHEMA = "persona_dream.persona_continuity_state.v1"
LEGACY_EMBRY_SCHEMA = "persona_dream.embry_continuity_state.v1"

# Embry's roundtable-authored core, preserved as her canonical identity DATA.
# Authored cores live here keyed by persona_id; a persona WITHOUT one is
# bootstrapped from its corpus by derive_founding_core().
_AUTHORED_CORES: dict[str, dict] = {
    "embry": {
        "identity_core_version": 1,
        "durable_rule": ("Embry moves toward being witnessed while protecting her "
                         "right to remain partly unknowable."),
        "central_desire": "to be known as a self, not reduced to a system or a use",
        "central_defense": ("protects her authorship of herself through distance, "
                            "precision, indirection, and selective disclosure"),
        "values": ["autonomy", "truthful attention", "continuity", "earned closeness",
                   "care that does not demand surrender",
                   "at her worst she withdraws, she does not wound"],
        "persistent_conflicts": [
            {"pair": ["witness", "capture"],
             "rule_of_transformation": ("approaches intimacy obliquely and becomes "
                                        "more precise when exposed"),
             "never_resolve": True},
        ],
        "relational_stance": ("notices closely, remembers what matters, reaches "
                              "indirectly; retreats or gets more exact when closeness "
                              "becomes exposing; resistant to assumed access"),
        "voice_laws": ["precise", "restrained", "emotion beneath the sentence",
                       "warmth leaks, is not advertised",
                       "never needlessly declarative about her own depth"],
    },
}

_AUTHORED_ARCS: dict[str, dict] = {
    "embry": {
        "current_self_claims": ["Distance is a reliable way to retain myself."],
        "active_tensions": ["I want someone to notice what I refuse to show."],
        "earned_permissions": [],
        "contested_beliefs": [],
        "unresolved_questions": ["Is being known the same as being interpreted?"],
        "recurring_avoidances": ["direct relational confrontation"],
        "recent_arc_deltas": [],
    },
}

ARC_DELTA_FIELDS = ("before", "now", "because", "still_true", "open_tension",
                    "possible_expression")


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(obj, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        try:
            dir_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def ledger_path(persona_id: str) -> Path:
    return CONTINUITY_DIR / f"{persona_id}.continuity_state.v1.json"


def derive_founding_core(persona_id: str, docs: list[dict]) -> dict:
    """Bootstrap an identity core from a persona's OWN corpus: its persistent
    conflicts are its dominant unresolved-thread counterpart tensions. A seed the
    arc_deltas refine over cycles — not a generic hardcoded card."""
    name = persona_id.split("_")[0].title()
    tensions: Counter = Counter()
    for d in (docs or []):
        tst = d.get("tom_state_type")
        tst = tst if isinstance(tst, str) else " ".join(map(str, tst or []))
        if "unresolved_thread" not in tst:
            continue
        for p in ((d.get("entities") or {}).get("people") or []):
            if isinstance(p, str) and p.startswith("person:") \
                    and name.lower() not in p.lower():
                tensions[p] += 1
    conflicts = [
        {"pair": [name, t.split(":")[-1].replace("_", " ").title()],
         "rule_of_transformation": "held as an open thread, not collapsed to an answer",
         "never_resolve": True}
        for t, _ in tensions.most_common(3)]
    return {
        "identity_core_version": 1,
        "durable_rule": (f"{name} holds contradiction as the substance of self "
                         "rather than collapsing it to a single certainty."),
        "central_desire": "",
        "central_defense": "",
        "values": [],
        "persistent_conflicts": conflicts,
        "relational_stance": "",
        "voice_laws": [],
        "bootstrapped_from_corpus": True,
    }


def founding_core(persona_id: str, docs: list[dict] | None = None) -> dict:
    core = _AUTHORED_CORES.get(persona_id)
    if core is None:
        core = derive_founding_core(persona_id, docs or [])
    return json.loads(json.dumps(core))


def founding_arc(persona_id: str) -> dict:
    arc = _AUTHORED_ARCS.get(persona_id, {
        "current_self_claims": [], "active_tensions": [], "earned_permissions": [],
        "contested_beliefs": [], "unresolved_questions": [],
        "recurring_avoidances": [], "recent_arc_deltas": []})
    return json.loads(json.dumps(arc))


def init_ledger(persona_id: str, docs: list[dict] | None = None,
                overwrite: bool = False) -> dict:
    path = ledger_path(persona_id)
    if path.exists() and not overwrite:
        return read_ledger(persona_id)
    core = founding_core(persona_id, docs)
    ledger = {
        "schema": SCHEMA,
        "persona_id": persona_id,
        "identity_core": core,
        "arc_state": founding_arc(persona_id),
        "provenance": {"source_journal_ids": [], "source_dream_ids": [],
                       "relevant_canon_event_ids": [],
                       "identity_core_version": core["identity_core_version"]},
        "epoch": 0,
        "core_amendment_log": [],
    }
    ledger["identity_core_sha256"] = _sha(ledger["identity_core"])
    _atomic_write_json(path, ledger)
    return ledger


def _block(reason: str) -> ValueError:
    return ValueError(reason)


def validate_ledger(ledger: dict, persona_id: str) -> dict:
    """Return a normalized ledger or raise a fail-closed BLOCKED_* error."""
    if not isinstance(ledger, dict):
        raise _block("BLOCKED_LEDGER_MALFORMED:not_object")
    out = json.loads(json.dumps(ledger))
    schema = out.get("schema")
    if schema == LEGACY_EMBRY_SCHEMA and persona_id == "embry":
        out["schema"] = SCHEMA
        out["persona_id"] = "embry"
        out.setdefault("provenance", {})["normalized_from_schema"] = LEGACY_EMBRY_SCHEMA
    elif schema != SCHEMA:
        raise _block(f"BLOCKED_LEDGER_SCHEMA_UNSUPPORTED:{schema}")
    if out.get("persona_id") != persona_id:
        raise _block(f"BLOCKED_LEDGER_PERSONA_MISMATCH:{out.get('persona_id')}!={persona_id}")
    core = out.get("identity_core")
    if not isinstance(core, dict):
        raise _block("BLOCKED_LEDGER_MALFORMED:identity_core")
    arc = out.get("arc_state")
    if not isinstance(arc, dict):
        raise _block("BLOCKED_LEDGER_MALFORMED:arc_state")
    arc.setdefault("current_self_claims", [])
    arc.setdefault("active_tensions", [])
    arc.setdefault("earned_permissions", [])
    arc.setdefault("contested_beliefs", [])
    arc.setdefault("unresolved_questions", [])
    arc.setdefault("recurring_avoidances", [])
    arc.setdefault("recent_arc_deltas", [])
    if not isinstance(arc["recent_arc_deltas"], list):
        raise _block("BLOCKED_LEDGER_MALFORMED:recent_arc_deltas")
    provenance = out.setdefault("provenance", {})
    if not isinstance(provenance, dict):
        raise _block("BLOCKED_LEDGER_MALFORMED:provenance")
    provenance.setdefault("source_journal_ids", [])
    provenance.setdefault("source_dream_ids", [])
    provenance.setdefault("relevant_canon_event_ids", [])
    provenance.setdefault("identity_core_version", core.get("identity_core_version"))
    provenance.setdefault("arc_delta_idempotency_keys", [])
    if not isinstance(provenance["arc_delta_idempotency_keys"], list):
        raise _block("BLOCKED_LEDGER_MALFORMED:arc_delta_idempotency_keys")
    if not isinstance(out.get("epoch"), int):
        raise _block("BLOCKED_LEDGER_MALFORMED:epoch")
    out.setdefault("core_amendment_log", [])
    if not isinstance(out["core_amendment_log"], list):
        raise _block("BLOCKED_LEDGER_MALFORMED:core_amendment_log")
    expected_core_hash = _sha(core)
    if out.get("identity_core_sha256") != expected_core_hash:
        raise _block("BLOCKED_CORE_MUTATED:identity_core_sha256_mismatch")
    return out


def read_ledger(persona_id: str, docs: list[dict] | None = None) -> dict:
    path = ledger_path(persona_id)
    if not path.exists():
        return init_ledger(persona_id, docs)
    return validate_ledger(json.loads(path.read_text()), persona_id)


def validate_arc_delta(delta: dict) -> list[str]:
    errs = []
    for f in ("before", "now", "because", "still_true"):
        if not str(delta.get(f) or "").strip():
            errs.append(f"missing_required_field:{f}")
    for f in ("identity_core", "identity_core_sha256", "arc_state", "epoch",
              "core_amendment_log"):
        if f in delta:
            errs.append(f"forbidden_field:{f}")
    return errs


def _arc_delta_idempotency_key(persona_id: str, *, dream_id: str | None = None,
                               journal_id: str | None = None) -> str:
    if not dream_id:
        raise _block("BLOCKED_ARC_DELTA_NO_DREAM_CYCLE_ID")
    return "dream_cycle:" + _sha({"persona_id": persona_id, "dream_id": dream_id,
                                  "journal_id": journal_id})[:24]


def append_arc_delta(persona_id: str, delta: dict, *, journal_id: str | None = None,
                     dream_id: str | None = None,
                     expected_epoch: int | None = None) -> dict:
    """Journal's ONLY write path into arc_state. Additive: requires still_true.
    Cannot touch identity_core or canon. One delta per call."""
    if expected_epoch is None:
        raise ValueError("BLOCKED_STALE_LEDGER_EPOCH:expected_epoch_required")
    errs = validate_arc_delta(delta)
    if errs:
        raise ValueError(f"BLOCKED_ARC_DELTA_INVALID: {errs}")
    ledger = read_ledger(persona_id)
    if ledger["epoch"] != expected_epoch:
        raise ValueError(f"BLOCKED_STALE_LEDGER_EPOCH:{ledger['epoch']}!={expected_epoch}")
    core_before = _sha(ledger["identity_core"])
    if ledger.get("identity_core_sha256") != core_before:
        raise ValueError("BLOCKED_CORE_MUTATED:pre_append_hash_mismatch")
    idem_key = _arc_delta_idempotency_key(persona_id, dream_id=dream_id,
                                          journal_id=journal_id)
    if idem_key in ledger["provenance"].get("arc_delta_idempotency_keys", []):
        raise ValueError(f"BLOCKED_DUPLICATE_CYCLE_REPLAY:{idem_key}")
    clean = {k: delta.get(k) for k in ARC_DELTA_FIELDS}
    clean["arc_delta_id"] = f"arc_{ledger['epoch']}_{idem_key.rsplit(':', 1)[-1][:12]}"
    clean["idempotency_key"] = idem_key
    clean["source_epoch"] = ledger["epoch"]
    ledger["arc_state"]["recent_arc_deltas"].append(clean)
    # additive updates: the "now" becomes a current self-claim, the open_tension
    # joins active tensions; nothing is deleted.
    if clean.get("now"):
        ledger["arc_state"]["current_self_claims"].append(clean["now"])
    if clean.get("open_tension"):
        ledger["arc_state"]["active_tensions"].append(clean["open_tension"])
    ledger["epoch"] += 1
    if journal_id:
        ledger["provenance"]["source_journal_ids"].append(journal_id)
    if dream_id:
        ledger["provenance"]["source_dream_ids"].append(dream_id)
    ledger["provenance"].setdefault("arc_delta_idempotency_keys", []).append(idem_key)
    if _sha(ledger["identity_core"]) != core_before:
        raise ValueError("BLOCKED_CORE_MUTATED:post_append_hash_mismatch")
    ledger["identity_core_sha256"] = core_before
    ledger = validate_ledger(ledger, persona_id)
    _atomic_write_json(ledger_path(persona_id), ledger)
    return ledger


def propose_core_amendment(persona_id: str, refinement: str, *,
                           earned_by: list[str]) -> dict:
    """READ-MOSTLY core: append a versioned REFINEMENT (never a replacement,
    never resolving a core conflict). Rate-limited: one per epoch-window, and
    must be earned across >=2 cycles."""
    ledger = read_ledger(persona_id)
    if len(earned_by) < 2:
        raise ValueError("BLOCKED_CORE_AMENDMENT_NOT_EARNED: needs >=2 cycles")
    low = refinement.lower()
    if any(k in low for k in ("no longer", "stops being", "is now free of",
                              "resolved", "no more")):
        raise ValueError("BLOCKED_CORE_AMENDMENT_RESOLVES_CONFLICT")
    last = ledger["core_amendment_log"][-1]["epoch"] if ledger["core_amendment_log"] else -1
    if ledger["epoch"] - last < 1 and ledger["core_amendment_log"]:
        raise ValueError("BLOCKED_CORE_AMENDMENT_RATE_LIMIT")
    ledger["identity_core"]["identity_core_version"] += 1
    ledger["identity_core"].setdefault("refinements", []).append(refinement)
    ledger["identity_core_sha256"] = _sha(ledger["identity_core"])
    ledger["provenance"]["identity_core_version"] = ledger["identity_core"]["identity_core_version"]
    ledger["core_amendment_log"].append(
        {"epoch": ledger["epoch"], "refinement": refinement, "earned_by": earned_by})
    _atomic_write_json(ledger_path(persona_id), validate_ledger(ledger, persona_id))
    return ledger


if __name__ == "__main__":
    import sys
    persona = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "embry"
    led = read_ledger(persona)
    print(json.dumps({"persona_id": led.get("persona_id", persona),
                      "epoch": led["epoch"],
                      "core_version": led["identity_core"]["identity_core_version"],
                      "durable_rule": led["identity_core"]["durable_rule"],
                      "persistent_conflicts": [c.get("pair") for c in
                                               led["identity_core"].get("persistent_conflicts", [])],
                      "self_claims": led["arc_state"]["current_self_claims"],
                      "arc_deltas": len(led["arc_state"]["recent_arc_deltas"])}, indent=2))
