"""Deterministic hardening tests for the Persona Dream continuity ledger."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger_mod = _load("continuity_ledger")


def _delta(**extra):
    d = {
        "before": "Distance is a reliable way to retain myself.",
        "now": "Professionalism can hide wanting to be understood.",
        "because": "dream cycle held witness and capture in tension",
        "still_true": "I resist closeness that assumes access to me.",
        "open_tension": "I do not know whether witness is intrusion.",
        "possible_expression": "careful warmth under a boundary",
    }
    d.update(extra)
    return d


@pytest.fixture()
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "CONTINUITY_DIR", tmp_path)
    return tmp_path


def test_embry_legacy_schema_normalizes_without_losing_provenance(isolated_ledger):
    core = ledger_mod.founding_core("embry")
    legacy = {
        "schema": ledger_mod.LEGACY_EMBRY_SCHEMA,
        "identity_core": core,
        "arc_state": {
            "current_self_claims": ["Distance is a reliable way to retain myself."],
            "active_tensions": ["I want someone to notice what I refuse to show."],
            "earned_permissions": [],
            "contested_beliefs": [],
            "unresolved_questions": ["Is being known the same as being interpreted?"],
            "recurring_avoidances": ["direct relational confrontation"],
            "recent_arc_deltas": [],
        },
        "provenance": {"source_journal_ids": ["cycle_a"], "source_dream_ids": ["cycle_a"],
                       "relevant_canon_event_ids": [], "identity_core_version": 1},
        "epoch": 0,
        "core_amendment_log": [],
        "identity_core_sha256": ledger_mod._sha(core),
    }
    ledger_mod.ledger_path("embry").write_text(json.dumps(legacy, indent=2) + "\n")

    got = ledger_mod.read_ledger("embry")

    assert got["schema"] == ledger_mod.SCHEMA
    assert got["persona_id"] == "embry"
    assert got["provenance"]["source_journal_ids"] == ["cycle_a"]
    assert got["provenance"]["normalized_from_schema"] == ledger_mod.LEGACY_EMBRY_SCHEMA


def test_append_requires_expected_epoch(isolated_ledger):
    ledger_mod.init_ledger("embry")

    with pytest.raises(ValueError, match="BLOCKED_STALE_LEDGER_EPOCH"):
        ledger_mod.append_arc_delta("embry", _delta(), dream_id="cycle_a")


def test_stale_epoch_blocks_after_first_append(isolated_ledger):
    ledger_mod.init_ledger("embry")
    ledger_mod.append_arc_delta("embry", _delta(), dream_id="cycle_a",
                                expected_epoch=0)

    with pytest.raises(ValueError, match="BLOCKED_STALE_LEDGER_EPOCH"):
        ledger_mod.append_arc_delta("embry", _delta(now="A later shift"),
                                    dream_id="cycle_b", expected_epoch=0)


def test_duplicate_dream_cycle_replay_blocks_and_does_not_append(isolated_ledger):
    ledger_mod.init_ledger("embry")
    first = ledger_mod.append_arc_delta("embry", _delta(), dream_id="cycle_a",
                                        journal_id="journal_a", expected_epoch=0)
    assert first["epoch"] == 1
    assert len(first["arc_state"]["recent_arc_deltas"]) == 1

    with pytest.raises(ValueError, match="BLOCKED_DUPLICATE_CYCLE_REPLAY"):
        ledger_mod.append_arc_delta("embry", _delta(now="Replay should not append"),
                                    dream_id="cycle_a", journal_id="journal_a",
                                    expected_epoch=1)

    reread = ledger_mod.read_ledger("embry")
    assert reread["epoch"] == 1
    assert len(reread["arc_state"]["recent_arc_deltas"]) == 1


def test_identity_core_hash_mismatch_blocks_before_append(isolated_ledger):
    ledger = ledger_mod.init_ledger("embry")
    ledger["identity_core"]["durable_rule"] = "mutated into a different core"
    ledger_mod.ledger_path("embry").write_text(json.dumps(ledger, indent=2) + "\n")

    with pytest.raises(ValueError, match="BLOCKED_CORE_MUTATED"):
        ledger_mod.append_arc_delta("embry", _delta(), dream_id="cycle_a",
                                    expected_epoch=0)


def test_arc_delta_cannot_smuggle_identity_core_update(isolated_ledger):
    ledger_mod.init_ledger("embry")

    with pytest.raises(ValueError, match="BLOCKED_ARC_DELTA_INVALID"):
        ledger_mod.append_arc_delta(
            "embry",
            _delta(identity_core={"durable_rule": "replace the core"}),
            dream_id="cycle_a",
            expected_epoch=0,
        )


def test_one_cycle_appends_exactly_one_delta_with_idempotency_key(isolated_ledger):
    ledger_mod.init_ledger("embry")

    got = ledger_mod.append_arc_delta("embry", _delta(), dream_id="cycle_a",
                                      journal_id="journal_a", expected_epoch=0)

    deltas = got["arc_state"]["recent_arc_deltas"]
    assert len(deltas) == 1
    assert deltas[0]["source_epoch"] == 0
    assert deltas[0]["idempotency_key"].startswith("dream_cycle:")
    assert got["provenance"]["arc_delta_idempotency_keys"] == [
        deltas[0]["idempotency_key"]
    ]
