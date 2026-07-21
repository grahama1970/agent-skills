"""Unit checks for Gate 0 attribution overlay in live Tau condition comparison.

These tests are deterministic local checks only. They prove the runner can
carry Gate 0 accepted-source attribution into social evidence refs before
commitment sealing; they do not perform live Tau calls.
"""

from __future__ import annotations

import importlib.util
import json
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
