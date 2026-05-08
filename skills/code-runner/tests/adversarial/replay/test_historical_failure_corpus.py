from __future__ import annotations

import json
from pathlib import Path


CORPUS = Path(__file__).with_name("historical_failure_corpus.json")
REPLAY_ROOT = Path(__file__).resolve().parent

KNOWN_COVERAGE_IDS = {
    "backend_transport_failure",
    "bad_allowlist_preflight",
    "dirty_allowlist_fail_closed",
    "dod_failure_source_invariance",
    "false_green_monolith",
    "no_patch_produced",
    "non_git_cwd_preflight",
    "orchestrate_runner_policy_gate",
    "orchestrate_untracked_baseline_preflight",
    "rollback_matrix",
    "source_apply_failure_rolls_back",
    "source_mutation_blocking",
    "spec_schema_required_fields",
}


def _corpus() -> dict:
    return json.loads(CORPUS.read_text())


def test_historical_failure_corpus_is_complete_and_unique() -> None:
    data = _corpus()
    entries = data["entries"]
    names = [entry["name"] for entry in entries]

    assert data["schema_version"] == 1
    assert len(entries) == 24
    assert len(names) == len(set(names))


def test_every_stored_failure_has_deterministic_coverage() -> None:
    missing = []
    unknown = []
    for entry in _corpus()["entries"]:
        coverage = entry.get("deterministic_coverage") or []
        if not coverage:
            missing.append(entry["name"])
        for coverage_id in coverage:
            if coverage_id not in KNOWN_COVERAGE_IDS and not (REPLAY_ROOT / coverage_id).is_dir():
                unknown.append({"failure": entry["name"], "coverage": coverage_id})

    assert missing == []
    assert unknown == []


def test_live_model_replay_is_not_the_only_coverage_for_any_stored_failure() -> None:
    bad = [
        entry["name"]
        for entry in _corpus()["entries"]
        if entry.get("deterministic_coverage") == ["live_model_replay"]
    ]

    assert bad == []


def test_required_replay_classes_exist() -> None:
    required_replay_dirs = {
        "dirty_allowlist_fail_closed",
        "false_green_monolith",
    }
    missing = sorted(case for case in required_replay_dirs if not (REPLAY_ROOT / case).is_dir())

    assert missing == []
