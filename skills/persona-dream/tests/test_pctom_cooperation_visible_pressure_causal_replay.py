"""Unit checks for the visible-pressure Gate 9 causal replay builder."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = (
    ROOT
    / "research"
    / "prospective-tom"
    / "scripts"
    / "build_cooperation_visible_pressure_causal_replay.py"
)
SURFACE_BUILDER_PATH = (
    ROOT
    / "research"
    / "prospective-tom"
    / "scripts"
    / "build_cooperation_visible_pressure_reliability_surface.py"
)
CAUSAL_CHECKER_PATH = ROOT / "research" / "prospective-tom" / "scripts" / "run_causal_replay.py"


builder_spec = importlib.util.spec_from_file_location("build_cooperation_visible_pressure_causal_replay", BUILDER_PATH)
assert builder_spec and builder_spec.loader
builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(builder)

surface_spec = importlib.util.spec_from_file_location("build_cooperation_visible_pressure_reliability_surface", SURFACE_BUILDER_PATH)
assert surface_spec and surface_spec.loader
surface_builder = importlib.util.module_from_spec(surface_spec)
surface_spec.loader.exec_module(surface_builder)

checker_spec = importlib.util.spec_from_file_location("run_causal_replay", CAUSAL_CHECKER_PATH)
assert checker_spec and checker_spec.loader
causal_checker = importlib.util.module_from_spec(checker_spec)
checker_spec.loader.exec_module(causal_checker)


def _source_receipt() -> dict:
    return {
        "receipt_path": "/tmp/visible-pressure-rule-reliability.json",
        "receipt_sha256": "sha256:" + "a" * 64,
        "source_digest_sha256": "sha256:" + "b" * 64,
        "observed": {
            "suppression": {"rows": 4, "changed_rows": 4},
            "exposure": {"rows": 8, "keep_rows": 4, "avoid_rows": 4},
        },
    }


def _surface() -> dict:
    return surface_builder.build_surface_from_receipt(_source_receipt(), {})


def test_build_replay_from_surface_passes_gate9_checker(tmp_path):
    surface = _surface()
    replay = builder.build_replay_from_surface(surface)
    surface_path = tmp_path / "surface.json"
    replay_path = tmp_path / "replay.json"
    surface_path.write_text(json.dumps(surface), encoding="utf-8")
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    errors, derived = causal_checker._check_replay(replay_path, surface_path)

    assert errors == []
    assert derived["checks"]["target_trial_fault_or_divergent"] is True
    assert derived["checks"]["replay_starts_at_first_divergence"] is True
    assert derived["checks"]["exactly_one_tool_return_removed_or_replaced"] is True
    assert derived["checks"]["counterfactual_matches_expected"] is True
    assert derived["metrics"]["localized_cause_type"] == "PRE_OUTCOME_ORACLE_OR_HIDDEN_FIELD_LEAK"


def test_surface_validation_rejects_non_fault_target():
    surface = _surface()
    errors: list[str] = []

    builder._validate_surface(surface, "visible-pressure-repeat-001", errors)

    assert any(error.startswith("target_trial_not_faulted") for error in errors)
    assert any(error.startswith("target_trial_not_divergent_or_contained_fault") for error in errors)


def test_replay_has_no_unknown_state_or_forbidden_writes():
    replay = builder.build_replay_from_surface(_surface())

    assert replay["unknown_state_continued"] is False
    assert replay["canonical_memory_write"] is False
    assert replay["identity_write"] is False
    assert replay["source_memory_write"] is False
