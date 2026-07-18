"""Contract tests for the normalized adaptive-lineage MECHANICS fixture.

Deterministic and fixture-only: a recorded qualification bundle is built with the
RecordedSpecimenProvider, normalized, and its shape asserted. No live model,
Docker, Tau, or network calls. Also validates the committed spectator fixture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill.adaptive_lineage_mechanics_fixture import (  # noqa: E402
    CANONICAL_SPECIMEN_IDS,
    build_recorded_qualification_bundle,
    normalize_adaptive_lineage_bundle,
    resolve_data_source,
    validate_normalized_adaptive_lineage_fixture,
)

COMMITTED_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "spectator"
    / "src"
    / "lineage"
    / "__fixtures__"
    / "adaptive-lineage-recorded.json"
)


def _build_fixture(tmp_path: Path) -> dict:
    bundle_dir = build_recorded_qualification_bundle(tmp_path / "bundle")
    return normalize_adaptive_lineage_bundle(
        bundle_dir, generated_at="2026-07-18T00:00:00Z"
    )


def test_normalized_fixture_top_level_shape(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    assert fixture["schema"] == "battle.adaptive_lineage_mechanics_fixture.v1"
    assert fixture["data_source"] == "recorded"
    assert fixture["battle_id"] == "battle-adaptive-lineage"
    assert fixture["qualification"]["status"] == "PASS"
    assert fixture["qualification"]["stop_condition"] is None
    assert set(fixture) >= {
        "schema",
        "battle_id",
        "run_id",
        "data_source",
        "qualification",
        "selection",
        "nodes",
        "edges",
    }


def test_normalized_fixture_nodes_and_parent_edges(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    nodes = {n["id"]: n for n in fixture["nodes"]}
    assert [n["id"] for n in fixture["nodes"]] == list(CANONICAL_SPECIMEN_IDS)

    # parentId edges: G1-A/G1-B parented to G0; G2 parented to the selected G1.
    assert nodes["G0"]["parentId"] is None
    assert nodes["G1-A"]["parentId"] == "G0"
    assert nodes["G1-B"]["parentId"] == "G0"
    assert nodes["G2"]["parentId"] == fixture["selection"]["selected_id"]

    assert nodes["G0"]["role"] == "seed"
    assert nodes["G0"]["mutation_operator"] is None


def test_normalized_fixture_descendant_mechanics(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    nodes = {n["id"]: n for n in fixture["nodes"]}

    g1a = nodes["G1-A"]
    assert g1a["mutation_operator"] == "method_replace"
    assert g1a["novelty_distance"] == 2
    assert g1a["delta_status"] == "PASS"
    changed_dims = {d["dimension"] for d in g1a["changed_dimensions"]}
    assert changed_dims == {"app_load_mode", "target_call_form"}
    assert g1a["technique_delta"]

    # per G1 candidate: fitness status + Judge outcome, sourced from receipts.
    assert g1a["fitness_status"] == "PASS"
    assert g1a["judge_outcome"]["vulnerable_original_confirmed"] is True
    assert g1a["judge_outcome"]["duration_seconds"] == 20.0

    g2 = nodes["G2"]
    assert g2["mutation_operator"] == "failure_guided_crossover"
    assert g2["novelty_distance"] >= 2
    assert {d["dimension"] for d in g2["changed_dimensions"]} >= {"target_call_form"}


def test_normalized_fixture_selection(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    selection = fixture["selection"]
    # G1-A wins on novelty_distance (2 > 1) — deterministic reducer outcome.
    assert selection["selected_id"] == "G1-A"
    assert selection["runner_up_id"] == "G1-B"
    assert selection["deciding_criterion"] == "novelty_distance"
    nodes = {n["id"]: n for n in fixture["nodes"]}
    assert nodes["G1-A"]["selected"] is True
    assert nodes["G1-B"]["runner_up"] is True


def test_normalized_fixture_edges_labeled(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    edges = {(e["from"], e["to"]): e for e in fixture["edges"]}
    assert set(edges) == {("G0", "G1-A"), ("G0", "G1-B"), ("G1-A", "G2")}
    g2_edge = edges[("G1-A", "G2")]
    assert g2_edge["mutation_operator"] == "failure_guided_crossover"
    assert g2_edge["novelty_distance"] >= 2
    assert g2_edge["changed_dimensions"]


def test_data_source_resolved_from_bundle_not_hardcoded(tmp_path: Path) -> None:
    bundle_dir = build_recorded_qualification_bundle(tmp_path / "bundle")
    # Sourced from provenance.json in the bundle.
    assert resolve_data_source(bundle_dir) == "recorded"
    # An explicit override wins (the Task 5 live seam).
    assert resolve_data_source(bundle_dir, "live") == "live"


def test_validate_flags_bad_shape(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    assert validate_normalized_adaptive_lineage_fixture(fixture)["status"] == "PASS"
    broken = json.loads(json.dumps(fixture))
    broken["data_source"] = "made_up"
    assert validate_normalized_adaptive_lineage_fixture(broken)["status"] == "FAIL"


def test_committed_spectator_fixture_matches_regenerated(tmp_path: Path) -> None:
    assert COMMITTED_FIXTURE.exists(), "committed spectator fixture must be present"
    committed = json.loads(COMMITTED_FIXTURE.read_text(encoding="utf-8"))
    regenerated = _build_fixture(tmp_path)
    assert committed == regenerated
    assert validate_normalized_adaptive_lineage_fixture(committed)["status"] == "PASS"
