"""Unit checks for Gate 0 attribution overlay in live Tau condition comparison.

These tests are deterministic local checks only. They prove the runner can
carry Gate 0 accepted-source attribution into social evidence refs before
commitment sealing; they do not perform live Tau calls.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_tau_condition_comparison.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("live_tau_condition_comparison", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_module()


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _episode() -> dict:
    return {
        "episode_id": "episode-001",
        "scenario_family": "information_asymmetry",
        "information_access_by_agent": {"embry_observes_changed_constraint": True},
        "observable_history": [
            {"speaker": "kai", "utterance": "The access rule changed."},
            {"speaker": "embry", "utterance": "I heard the rule might have changed."},
        ],
        "allowed_next_actions": ["KAI_HINTS_CONSTRAINT", "KAI_SETS_BOUNDARY"],
        "ground_truth_tom_labels": [
            {
                "perspective_order": 1,
                "subject": "kai",
                "target": "constraint",
                "mental_state_type": "belief",
                "proposition": "The rule changed",
            },
            {
                "perspective_order": 2,
                "subject": "embry",
                "target": "kai",
                "mental_state_type": "belief",
                "proposition": "Kai thinks Embry knows the rule changed",
            },
        ],
    }


def test_visible_refs_carry_gate0_accepted_source_attribution(tmp_path):
    digest = "sha256:" + "c" * 64
    case_root = tmp_path / "gate0"
    _write_json(
        case_root / "normalized_residue.json",
        [
            {
                "source_id": "memory_001",
                "accepted_source_id": "memory_001",
                "accepted_source_ids_sha256": digest,
                "query_receipt_index": 0,
                "scope": "persona-dream",
            }
        ],
    )
    records = runner._gate0_attribution_records(case_root)
    refs = runner._visible_refs(_episode(), records)
    assert len(refs) == 3
    for ref in refs:
        assert ref["scope"] in {"social_episode_observation", "social_episode_access"}
        assert ref["source_id"].startswith("episode-001:")
        assert ref["accepted_source_id"] == "memory_001"
        assert ref["accepted_source_ids_sha256"] == digest
        assert ref["gate0_query_receipt_index"] == 0
        assert ref["gate0_attribution_kind"] == "live_recall_residue_grounding"


def test_overlay_updates_social_refs_but_not_synthetic_refs(tmp_path):
    digest = "sha256:" + "d" * 64
    records = [
        {
            "accepted_source_id": "memory_002",
            "accepted_source_ids_sha256": digest,
            "gate0_residue_source_id": "memory_002",
            "gate0_query_receipt_index": 1,
            "gate0_attribution_kind": "live_recall_residue_grounding",
        }
    ]
    refs = runner._visible_refs(_episode(), records)
    payload = {
        "evidence_refs": [
            {"scope": "social_episode_observation", "source_id": "episode-001:observable_history:0"},
            {"scope": "synthetic_counterfactual", "source_id": "episode-001:do:not-history"},
        ]
    }
    overlaid = runner._overlay_gate0_attribution(payload, refs)
    social_ref = overlaid["evidence_refs"][0]
    synthetic_ref = overlaid["evidence_refs"][1]
    assert social_ref["accepted_source_id"] == "memory_002"
    assert social_ref["accepted_source_ids_sha256"] == digest
    assert "accepted_source_id" not in synthetic_ref


def test_prompt_is_compact_and_preserves_gate0_attribution():
    digest = "sha256:" + "e" * 64
    records = [
        {
            "accepted_source_id": "memory_003",
            "accepted_source_ids_sha256": digest,
            "gate0_residue_source_id": "memory_003",
            "gate0_query_receipt_index": 2,
            "gate0_attribution_kind": "live_recall_residue_grounding",
        }
    ]

    prompt = runner._prompt(_episode(), "CD", records)

    assert len(prompt) < 20_000
    assert '"accepted_source_id":"memory_003"' not in prompt
    assert '"accepted_source_ids_sha256":"' + digest + '"' not in prompt
    assert '"source_id":"episode-001:observable_history:0"' in prompt
    assert "\n  " not in prompt


def test_generated_calibration_prompt_stays_below_live_boundary():
    build_corpus = runner._load_module(runner.BUILD_CORPUS_SCRIPT, "build_corpus_for_prompt_size_test")
    corpus = build_corpus.build_corpus("calibration", 1)
    episode = runner._select_episodes(corpus, 1)[0]

    lengths = {
        condition: len(runner._prompt(episode, condition, []))
        for condition in runner.CONDITIONS
    }

    assert lengths
    assert max(lengths.values()) < 18_000


def test_condition_prompt_preflight_blocks_case_fanout(tmp_path):
    class FakeBuildCorpus:
        @staticmethod
        def build_corpus(split, episodes_per_family):
            return {"episode_count": 1, "episodes": [_episode()]}

    class FakeCheckCorpus:
        @staticmethod
        def build_receipt(corpus_path, receipt_path, expect_total, expect_per_family):
            receipt = {
                "status": "PASS_SOCIAL_EPISODE_CORPUS",
                "errors": [],
                "checks": {"policies_deterministic": True},
            }
            _write_json(receipt_path, receipt)
            return receipt

    class FakeAdapter:
        calls: list[str] = []

        @staticmethod
        def dispatch_text_reasoning(prompt, role, output_contract, caller_skill, model, timeout_s):
            FakeAdapter.calls.append(role)
            if role == "pctom-live-condition-preflight":
                return (
                    {
                        "route_ready": True,
                        "surface": "tau_scillm_text_reasoning",
                        "note": "preflight_only",
                    },
                    {
                        "status": "PASS",
                        "live_call_performed": True,
                        "prompt_sha256": runner._text_sha256(prompt),
                    },
                )
            raise RuntimeError("Tau dispatch timed out after 0.1s")

    def fake_load_module(path, name):
        if "build" in name:
            return FakeBuildCorpus
        if "check_corpus" in name:
            return FakeCheckCorpus
        if "tau_text_adapter" in name:
            return FakeAdapter
        return object()

    original_load_module = runner._load_module
    runner._load_module = fake_load_module
    try:
        receipt = runner.run_live_comparison(
            output_root=tmp_path / "out",
            receipt_out=tmp_path / "out" / "receipt.json",
            split="calibration",
            episodes_per_family=1,
            episode_limit=1,
            model=None,
            timeout_s=0.1,
        )
    finally:
        runner._load_module = original_load_module

    condition_receipt_path = Path(receipt["condition_prompt_preflight_receipt_path"])
    condition_receipt = json.loads(condition_receipt_path.read_text())

    assert receipt["status"] == runner.BLOCKED_STATUS
    assert receipt["tau_preflight_passed"] is True
    assert receipt["condition_prompt_preflight_attempted"] is True
    assert receipt["condition_prompt_preflight_passed"] is False
    assert receipt["condition_prompt_preflight_status"] == "BLOCKED_DISPATCH_ERROR"
    assert receipt["checks"]["case_fanout_blocked_until_condition_prompt_preflight_passes"] is True
    assert receipt["counts"]["cases"] == 0
    assert receipt["tau_call_attempts"] == 0
    assert "pctom-live-condition-preflight" in FakeAdapter.calls
    assert "pctom-live-condition-representative-preflight" in FakeAdapter.calls
    assert condition_receipt["status"] == "BLOCKED_DISPATCH_ERROR"
    assert condition_receipt["systemic_failure_signature"] == "tau_text_reasoning_timeout"
    assert condition_receipt["memory_write_attempts"] == 0
    assert condition_receipt["provider_call_attempts"] == 0


def test_balanced_planning_wrapper_forwards_gate0_case_root(tmp_path):
    script = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_tau_balanced_planning_replication.py"
    spec = importlib.util.spec_from_file_location("balanced_planning_gate0_test", script)
    assert spec and spec.loader
    balanced = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(balanced)

    gate0_case_root = tmp_path / "gate0"
    seen: dict[str, Path | None] = {"gate0_case_root": None}
    episodes = [
        "sealedte-info-asym-17",
        "sealedte-pref-desire-17",
        "sealedte-trust-commit-17",
        "sealedte-coord-conflict-17",
    ]

    class FakeLiveCondition:
        PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON"

        @staticmethod
        def _select_episodes(corpus, limit):
            return []

        @staticmethod
        def run_live_comparison(**kwargs):
            seen["gate0_case_root"] = kwargs.get("gate0_case_root")
            output_root = kwargs["output_root"]
            receipt_out = kwargs["receipt_out"]
            case_index = [
                {"episode_id": episode_id, "condition": condition}
                for episode_id in episodes
                for condition in balanced.CONDITIONS
            ]
            case_index_path = output_root / "artifacts" / "live_condition_case_index.json"
            _write_json(case_index_path, case_index)
            receipt = {
                "status": FakeLiveCondition.PASS_STATUS,
                "counts": {"episodes_consumed": 4, "families_consumed": 4, "cases": 16},
                "case_index_path": str(case_index_path),
                "tau_call_attempts": 16,
                "tau_live_call_performed": 16,
                "tau_receipts_hash_bound": True,
                "gate0_attribution_overlay_used": True,
            }
            _write_json(receipt_out, receipt)
            return receipt

    class FakeActionSelection:
        PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION"

        @staticmethod
        def run_bridge(condition_root, action_root, action_receipt_path):
            action_index = [
                {
                    "episode_id": episode_id,
                    "condition": condition,
                    "selected_action": "WAIT",
                    "oracle_action": "WAIT",
                    "planning_regret": 0.0,
                }
                for episode_id in episodes
                for condition in balanced.CONDITIONS
            ]
            action_index_path = action_root / "artifacts" / "live_condition_action_decisions.json"
            _write_json(action_index_path, action_index)
            receipt = {
                "status": FakeActionSelection.PASS_STATUS,
                "counts": {
                    "action_decisions_per_condition": {condition: 4 for condition in balanced.CONDITIONS},
                    "deterministic_reward_or_regret_scores_per_condition": {
                        condition: 4 for condition in balanced.CONDITIONS
                    },
                },
                "decision_index": str(action_index_path),
                "live_tau_originated_artifacts_consumed": True,
            }
            _write_json(action_receipt_path, receipt)
            return receipt

    def fake_load_module(path, name):
        if "action" in name:
            return FakeActionSelection
        if "condition" in name:
            return FakeLiveCondition
        raise AssertionError(name)

    original_load_module = balanced._load_module
    balanced._load_module = fake_load_module
    try:
        receipt = balanced.run_balanced_replication(
            output_root=tmp_path / "out",
            receipt_out=tmp_path / "out" / "receipt.json",
            family_episode_limit=1,
            episodes_per_family=24,
            variant_min=17,
            variant_max=17,
            model=None,
            timeout_s=1.0,
            outer_timeout_s=None,
            bootstrap_samples=10,
            bootstrap_seed=1,
            alpha=0.05,
            gate0_case_root=gate0_case_root,
        )
    finally:
        balanced._load_module = original_load_module

    assert receipt["status"] == balanced.PASS_STATUS
    assert receipt["gate0_case_root"] == str(gate0_case_root.resolve())
    assert receipt["checks"]["gate0_attribution_loaded_if_requested"] is True
    assert seen["gate0_case_root"] == gate0_case_root.resolve()


def test_balanced_planning_wrapper_outer_timeout_blocks_before_action_selection(tmp_path):
    script = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_tau_balanced_planning_replication.py"
    spec = importlib.util.spec_from_file_location("balanced_planning_timeout_test", script)
    assert spec and spec.loader
    balanced = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(balanced)

    class SlowLiveCondition:
        PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON"

        @staticmethod
        def _select_episodes(corpus, limit):
            return []

        @staticmethod
        def run_live_comparison(**kwargs):
            time.sleep(5)
            return {"status": SlowLiveCondition.PASS_STATUS}

    class ActionSelectionShouldNotRun:
        PASS_STATUS = "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION"

        @staticmethod
        def run_bridge(condition_root, action_root, action_receipt_path):
            raise AssertionError("action selection must not run without a passed condition receipt")

    def fake_load_module(path, name):
        if "action" in name:
            return ActionSelectionShouldNotRun
        if "condition" in name:
            return SlowLiveCondition
        raise AssertionError(name)

    original_load_module = balanced._load_module
    balanced._load_module = fake_load_module
    try:
        receipt = balanced.run_balanced_replication(
            output_root=tmp_path / "out",
            receipt_out=tmp_path / "out" / "receipt.json",
            family_episode_limit=1,
            episodes_per_family=24,
            variant_min=17,
            variant_max=17,
            model=None,
            timeout_s=1.0,
            outer_timeout_s=0.1,
            bootstrap_samples=10,
            bootstrap_seed=1,
            alpha=0.05,
        )
    finally:
        balanced._load_module = original_load_module

    assert receipt["status"] == balanced.BLOCKED_STATUS
    assert receipt["outer_timeout_s"] == 0.1
    assert "condition_outer_timeout_s:0.1" in receipt["errors"]
    assert "action_selection_skipped_without_passed_condition_receipt" in receipt["errors"]
    assert receipt["checks"]["condition_outer_timeout_contained_if_triggered"] is True
    assert receipt["checks"]["condition_blocked_before_case_acceptance"] is True
    assert receipt["checks"]["gate0_attribution_loaded_if_requested"] is True
    assert receipt["checks"]["condition_receipt_passed"] is False
    assert receipt["checks"]["action_selection_receipt_passed"] is False
    assert receipt["memory_write_attempts"] == 0
    assert receipt["provider_call_attempts"] == 0


def test_strict_prompt_accepts_gate0_records_argument():
    script = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_tau_strict_inference_prompt_replication.py"
    spec = importlib.util.spec_from_file_location("strict_prompt_gate0_test", script)
    assert spec and spec.loader
    strict = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strict)
    digest = "sha256:" + "f" * 64
    records = [
        {
            "accepted_source_id": "memory_004",
            "accepted_source_ids_sha256": digest,
            "gate0_residue_source_id": "memory_004",
            "gate0_query_receipt_index": 3,
            "gate0_attribution_kind": "live_recall_residue_grounding",
        }
    ]

    prompt = strict._strict_prompt(runner, _episode(), "CD", records)

    assert isinstance(prompt, str)
    assert "Persona Dream PCTOM-R" in prompt
    assert '"accepted_source_id":"memory_004"' not in prompt
    assert '"source_id": "episode-001:observable_history:0"' in prompt
