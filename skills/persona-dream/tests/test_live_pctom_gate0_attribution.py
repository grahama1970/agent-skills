"""Unit checks for live PCTOM Gate 0 attribution propagation.

These tests use local synthetic receipts only. They prove the live Gate 0 case
deriver carries accepted source ids and source-id digests into prediction
evidence refs; they do not call live Memory.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_pctom_gate0.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("live_pctom_gate0", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate0 = _load_module()


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_derive_case_carries_accepted_source_attribution_into_prediction_refs(tmp_path):
    output_root = tmp_path / "live"
    case_root = tmp_path / "case"
    digest = gate0._stable_json_sha256(["memory_001"])
    _write_json(
        output_root / "residue_links.json",
        {
            "recall_receipts": [
                {
                    "query": "What should Embry preserve?",
                    "scope": "persona-dream",
                    "status": "ok",
                    "accepted_source_ids": ["memory_001"],
                    "accepted_source_ids_sha256": digest,
                }
            ],
            "items": [
                {
                    "scope": "persona-dream",
                    "source_id": "memory_001",
                    "text": "Embry should preserve uncertainty instead of inventing certainty.",
                    "synthetic": False,
                }
            ],
        },
    )
    counts = gate0._derive_case(
        live_receipt={
            "run_id": "unit-live-gate0",
            "output_root": str(output_root),
            "residue_to_query_receipt_links": [{"residue_index": 0, "query_index": 0}],
        },
        case_root=case_root,
    )
    commitment = json.loads((case_root / "tom_prediction_commitment.json").read_text(encoding="utf-8"))
    residue = json.loads((case_root / "normalized_residue.json").read_text(encoding="utf-8"))
    evidence_ref = commitment["prediction_payload"]["belief_distributions"][0]["evidence_refs"][0]
    assert counts["prediction_evidence_refs"] == 1
    assert residue[0]["accepted_source_id"] == "memory_001"
    assert residue[0]["accepted_source_ids_sha256"] == digest
    assert evidence_ref["accepted_source_id"] == "memory_001"
    assert evidence_ref["accepted_source_ids_sha256"] == digest
    assert evidence_ref["query_receipt_index"] == 0
