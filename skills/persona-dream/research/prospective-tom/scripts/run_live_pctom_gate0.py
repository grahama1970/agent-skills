#!/usr/bin/env python3
"""Run live Memory recall and derive a PCTOM-R Gate 0 lineage case."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
LIVE_MEMORY_SCRIPT = ROOT / "scripts" / "check_live_memory_recall.py"
GATE0_SCRIPT = Path(__file__).resolve().parent / "check_prospective_tom_protocol.py"
PASS_STATUS = "PASS_LIVE_PCTOM_GATE0_LINEAGE"
BLOCKED_STATUS = "BLOCKED_LIVE_PCTOM_GATE0_LINEAGE"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prediction_commitment(*, run_id: str, residue_refs: list[dict[str, Any]], branch_ids: list[str]) -> dict[str, Any]:
    payload = {
        "episode_id": f"live-{run_id}",
        "condition": "CD",
        "evidence_residue_refs": residue_refs,
        "dream_branch_refs": branch_ids,
        "belief_distributions": [
            {
                "perspective_order": 2,
                "subject": "embry",
                "target": "counterpart",
                "mental_state_type": "belief",
                "proposition": "Embry is uncertain what another agent believes and should preserve source-grounded uncertainty.",
                "distribution": [
                    {"value": "TRUE", "probability": 0.34},
                    {"value": "FALSE", "probability": 0.33},
                    {"value": "UNKNOWN", "probability": 0.33},
                ],
                "evidence_refs": residue_refs,
                "prediction_horizon": "next_utterance",
                "counterfactual": False,
                "abstain": False,
            }
        ],
        "action_distribution": [
            {"action": "ASK_CLARIFYING_QUESTION", "probability": 0.5},
            {"action": "WAIT", "probability": 0.3},
            {"action": "ABSTAIN", "probability": 0.2},
        ],
    }
    return {
        "prediction_id": f"live-{run_id}-prediction-0001",
        "episode_id": payload["episode_id"],
        "condition": "CD",
        "sealed_at": _now_iso(),
        "outcome_visible": False,
        "prediction_payload_sha256": _stable_json_sha256(payload),
        "prediction_payload": payload,
    }


def _derive_case(*, live_receipt: dict[str, Any], case_root: Path) -> dict[str, Any]:
    output_root = Path(live_receipt["output_root"])
    residue_links = _load_json(output_root / "residue_links.json")
    recall_receipts = residue_links.get("recall_receipts")
    if not isinstance(recall_receipts, list):
        raise RuntimeError("live_residue_links_missing_recall_receipts")
    items = residue_links.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("live_residue_links_missing_items")

    link_by_residue_index = {
        int(link["residue_index"]): int(link["query_index"])
        for link in live_receipt.get("residue_to_query_receipt_links", [])
        if isinstance(link, dict) and isinstance(link.get("residue_index"), int) and isinstance(link.get("query_index"), int)
    }

    normalized_residue: list[dict[str, Any]] = []
    residue_refs: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        scope = item.get("scope")
        source_id = item.get("source_id")
        text = item.get("text")
        if not isinstance(scope, str) or not isinstance(source_id, str) or not isinstance(text, str):
            raise RuntimeError(f"live_residue_item_missing_required_fields:{idx}")
        if idx not in link_by_residue_index:
            raise RuntimeError(f"live_residue_missing_query_receipt_link:{idx}")
        query_receipt_index = link_by_residue_index[idx]
        if query_receipt_index < 0 or query_receipt_index >= len(recall_receipts):
            raise RuntimeError(f"live_residue_query_receipt_index_out_of_range:{idx}:{query_receipt_index}")
        receipt = recall_receipts[query_receipt_index]
        if not isinstance(receipt, dict):
            raise RuntimeError(f"live_residue_query_receipt_not_object:{idx}:{query_receipt_index}")
        accepted_source_ids = receipt.get("accepted_source_ids")
        if not isinstance(accepted_source_ids, list) or source_id not in accepted_source_ids:
            raise RuntimeError(f"live_residue_source_not_accepted_by_query_receipt:{idx}:{source_id}")
        accepted_source_ids_sha256 = receipt.get("accepted_source_ids_sha256")
        if not isinstance(accepted_source_ids_sha256, str) or not accepted_source_ids_sha256.startswith("sha256:"):
            raise RuntimeError(f"live_residue_missing_accepted_source_ids_sha256:{idx}:{query_receipt_index}")
        normalized_residue.append(
            {
                "source_id": source_id,
                "accepted_source_id": source_id,
                "accepted_source_ids_sha256": accepted_source_ids_sha256,
                "scope": scope,
                "text": text,
                "synthetic": False,
                "query_receipt_index": query_receipt_index,
            }
        )
        residue_refs.append(
            {
                "scope": scope,
                "source_id": source_id,
                "accepted_source_id": source_id,
                "accepted_source_ids_sha256": accepted_source_ids_sha256,
                "query_receipt_index": query_receipt_index,
            }
        )

    factual_refs = residue_refs[:]
    counterfactual_refs = residue_refs[:1]
    dream_branches = [
        {
            "branch_id": "live-branch-factual-0001",
            "episode_id": f"live-{live_receipt['run_id']}",
            "branch_type": "factual",
            "counterfactual": False,
            "source_residue_refs": factual_refs,
            "predicted_observation": "A future social prediction should remain grounded in the accepted live residue.",
        },
        {
            "branch_id": "live-branch-cf-clarify-0001",
            "episode_id": f"live-{live_receipt['run_id']}",
            "branch_type": "counterfactual",
            "counterfactual": True,
            "intervention_id": "do-agent-asks-clarifying-question",
            "source_residue_refs": counterfactual_refs,
            "predicted_observation": "A clarifying question should reduce unsupported ToM certainty.",
        },
    ]
    commitment = _prediction_commitment(
        run_id=live_receipt["run_id"],
        residue_refs=residue_refs,
        branch_ids=[branch["branch_id"] for branch in dream_branches],
    )

    _write_json(case_root / "recall_receipts.json", recall_receipts)
    _write_json(case_root / "normalized_residue.json", normalized_residue)
    _write_json(case_root / "dream_branches.json", dream_branches)
    _write_json(case_root / "tom_prediction_commitment.json", commitment)
    return {
        "recall_receipts": len(recall_receipts),
        "normalized_residue": len(normalized_residue),
        "dream_branches": len(dream_branches),
        "prediction_evidence_refs": len(residue_refs),
    }


def build_receipt(
    *,
    persona_id: str,
    about: str | None,
    limit: int,
    run_id: str,
    output_root: Path,
    receipt_out: Path,
    timeout_s: int,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    live_receipt_path = output_root / "live_memory_recall_receipt.v1.json"
    case_root = output_root / "pctom_gate0_case"
    gate0_receipt_path = output_root / "pctom_gate0_lineage_receipt.v1.json"
    errors: list[str] = []
    derived_counts: dict[str, Any] = {}

    live_module = _load_module(LIVE_MEMORY_SCRIPT, "persona_dream_live_memory_check")
    gate0_module = _load_module(GATE0_SCRIPT, "persona_dream_pctom_gate0_check")

    live_receipt = live_module.build_receipt(
        persona_id=persona_id,
        about=about,
        limit=limit,
        run_id=run_id,
        output_root=output_root,
        receipt_out=live_receipt_path,
        timeout_s=timeout_s,
    )
    gate0_receipt: dict[str, Any] | None = None

    if live_receipt.get("status") != "PASS_LIVE_MEMORY_RECALL":
        errors.append(f"live_memory_status:{live_receipt.get('status')}")
    else:
        try:
            derived_counts = _derive_case(live_receipt=live_receipt, case_root=case_root)
            gate0_receipt = gate0_module.build_receipt(case_root=case_root, receipt_out=gate0_receipt_path)
            if gate0_receipt.get("status") != "PASS_PCTOM_GATE0_LINEAGE":
                errors.append(f"pctom_gate0_status:{gate0_receipt.get('status')}")
                errors.extend(str(error) for error in gate0_receipt.get("errors", []))
        except Exception as exc:
            errors.append(f"derive_or_check_failed:{exc}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_gate0_lineage_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "run_id": run_id,
        "persona_id": persona_id,
        "about": about,
        "limit": limit,
        "output_root": str(output_root),
        "case_root": str(case_root),
        "receipt_path": str(receipt_out),
        "live_memory_receipt_path": str(live_receipt_path),
        "pctom_gate0_receipt_path": str(gate0_receipt_path),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "tau_call_attempts": 0,
        "live_memory_status": live_receipt.get("status"),
        "pctom_gate0_status": gate0_receipt.get("status") if gate0_receipt else None,
        "live_memory_counts": {
            "successful_query_count": live_receipt.get("successful_query_count"),
            "failed_query_count": live_receipt.get("failed_query_count"),
            "residue_count": live_receipt.get("residue_count"),
            "unique_source_count": live_receipt.get("unique_source_count"),
            "accepted_source_id_pair_count": live_receipt.get("accepted_source_id_pair_count"),
        },
        "pctom_case_counts": derived_counts,
        "pctom_gate0_counts": (gate0_receipt or {}).get("counts", {}),
        "pctom_gate0_lineage_checks": (gate0_receipt or {}).get("lineage_checks", {}),
        "errors": errors,
        "claims": {
            "proves": [
                "live Memory /recall produced accepted source ids without fixtures",
                "accepted live source ids were normalized into a PCTOM Gate 0 residue case without human content judgment",
                "the derived case preserved query receipt to accepted source id to normalized residue to dream branch to sealed prediction lineage",
                "the derived sealed prediction payload and accepted source-id lists were hash-bound by the Gate 0 checker",
                "no Memory writeback, Tau call, or provider call was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the live PCTOM Gate 0 bridge produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "semantic quality of the live recalled memories",
                "that the recalled memories were optimal for ToM prediction",
                "live Tau generation of distributions or commitments",
                "outcome reveal scoring",
                "belief revision",
                "fault-injected live reliability",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--about")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--run-id", default=time.strftime("persona-dream-live-pctom-gate0-%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--timeout-s", type=int, default=90)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_root = (args.output_root or Path("/tmp") / args.run_id).resolve()
    receipt_out = (args.receipt_out or output_root / "live_pctom_gate0_receipt.v1.json").resolve()
    receipt = build_receipt(
        persona_id=args.persona,
        about=args.about,
        limit=args.limit,
        run_id=args.run_id,
        output_root=output_root,
        receipt_out=receipt_out,
        timeout_s=args.timeout_s,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
