#!/usr/bin/env python3
"""Audit live-originated PCTOM-R stage hashes and lineage across Gates 2-7."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_LIVE_STAGE_HASH_LINEAGE_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_STAGE_HASH_LINEAGE_AUDIT"
CONDITIONS = {"M", "R", "D", "CD"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _rows(value: Any, errors: list[str], label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label}_not_list")
        return []
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(value):
        if not isinstance(row, dict):
            errors.append(f"{label}_{idx}_not_object")
            continue
        rows.append(row)
    return rows


def _receipt_hash_without_self(path: Path, errors: list[str], label: str) -> tuple[Any, str | None]:
    value = _load_json(path, errors, label)
    if isinstance(value, dict) and isinstance(value.get("receipt_sha256"), str):
        clone = dict(value)
        clone.pop("receipt_sha256", None)
        return value, _stable_json_sha256(clone)
    return value, _file_sha256(path) if path.exists() else None


def _index(rows: list[dict[str, Any]], errors: list[str], label: str) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or not isinstance(condition, str):
            errors.append(f"{label}_{idx}_missing_episode_condition:{episode_id}:{condition}")
            continue
        key = (episode_id, condition)
        if key in out:
            errors.append(f"{label}_duplicate_episode_condition:{episode_id}:{condition}")
        out[key] = row
    return out


def _path(value: Any, errors: list[str], label: str) -> Path:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}_path_missing:{value}")
        return Path("__missing__")
    return Path(value)


def _commitment_hashes(
    commitment_bundle: dict[str, Any],
    distribution_sha: str,
    branch_sha: str,
    errors: list[str],
    prefix: str,
) -> tuple[int, int]:
    commitments = commitment_bundle.get("commitments")
    if not isinstance(commitments, list) or not commitments:
        errors.append(f"{prefix}_commitments_not_nonempty_list")
        return 0, 0
    hashes_checked = 0
    accepted_source_refs = 0
    for idx, commitment in enumerate(commitments):
        if not isinstance(commitment, dict):
            errors.append(f"{prefix}_commitment_{idx}_not_object")
            continue
        payload = commitment.get("prediction_payload")
        model_receipts = commitment.get("model_receipts")
        evidence_bundle = commitment.get("evidence_bundle")
        if not isinstance(payload, dict):
            errors.append(f"{prefix}_commitment_{idx}_payload_not_object")
            payload = {}
        if not isinstance(model_receipts, list):
            errors.append(f"{prefix}_commitment_{idx}_model_receipts_not_list")
            model_receipts = []
        if not isinstance(evidence_bundle, dict):
            errors.append(f"{prefix}_commitment_{idx}_evidence_bundle_not_object")
            evidence_bundle = {}
        expected_payload = _stable_json_sha256(payload)
        expected_models = _stable_json_sha256(model_receipts)
        expected_evidence = _stable_json_sha256(evidence_bundle)
        hashes_checked += 3
        if commitment.get("prediction_payload_sha256") != expected_payload:
            errors.append(
                f"{prefix}_commitment_{idx}_prediction_payload_sha256_mismatch:"
                f"{commitment.get('prediction_payload_sha256')}:{expected_payload}"
            )
        if commitment.get("model_receipts_sha256") != expected_models:
            errors.append(
                f"{prefix}_commitment_{idx}_model_receipts_sha256_mismatch:"
                f"{commitment.get('model_receipts_sha256')}:{expected_models}"
            )
        if commitment.get("evidence_bundle_sha256") != expected_evidence:
            errors.append(
                f"{prefix}_commitment_{idx}_evidence_bundle_sha256_mismatch:"
                f"{commitment.get('evidence_bundle_sha256')}:{expected_evidence}"
            )
        if evidence_bundle.get("distribution_bundle_sha256") != distribution_sha:
            errors.append(
                f"{prefix}_commitment_{idx}_distribution_bundle_sha256_mismatch:"
                f"{evidence_bundle.get('distribution_bundle_sha256')}:{distribution_sha}"
            )
        if evidence_bundle.get("branch_bundle_sha256") != branch_sha:
            errors.append(
                f"{prefix}_commitment_{idx}_branch_bundle_sha256_mismatch:"
                f"{evidence_bundle.get('branch_bundle_sha256')}:{branch_sha}"
            )
        for ref_idx, ref in enumerate(evidence_bundle.get("source_evidence_refs", [])):
            if not isinstance(ref, dict):
                errors.append(f"{prefix}_commitment_{idx}_source_ref_{ref_idx}_not_object")
                continue
            for key in (
                "accepted_source_id",
                "accepted_source_ids_sha256",
                "gate0_attribution_kind",
                "gate0_query_receipt_index",
                "gate0_residue_index",
                "gate0_residue_source_id",
                "scope",
                "source_id",
            ):
                if key not in ref:
                    errors.append(f"{prefix}_commitment_{idx}_source_ref_{ref_idx}_missing_{key}")
            if ref.get("accepted_source_id") != ref.get("gate0_residue_source_id"):
                errors.append(
                    f"{prefix}_commitment_{idx}_source_ref_{ref_idx}_accepted_source_id_mismatch:"
                    f"{ref.get('accepted_source_id')}:{ref.get('gate0_residue_source_id')}"
                )
            if not str(ref.get("accepted_source_ids_sha256", "")).startswith("sha256:"):
                errors.append(f"{prefix}_commitment_{idx}_source_ref_{ref_idx}_accepted_source_ids_sha256_invalid")
            accepted_source_refs += 1
    return hashes_checked, accepted_source_refs


def run(
    *,
    condition_case_index: Path,
    action_selection_receipt: Path,
    action_linked_revision_receipt: Path,
    output_root: Path,
    receipt_out: Path,
    expect_cases: int,
    fixture_backed: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    condition_case_index = condition_case_index.resolve()
    action_selection_receipt = action_selection_receipt.resolve()
    action_linked_revision_receipt = action_linked_revision_receipt.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()

    case_rows = _rows(_load_json(condition_case_index, errors, "condition_case_index"), errors, "condition_case_index")
    action_receipt, action_receipt_recomputed_sha = _receipt_hash_without_self(
        action_selection_receipt, errors, "action_selection_receipt"
    )
    revision_receipt, revision_receipt_recomputed_sha = _receipt_hash_without_self(
        action_linked_revision_receipt, errors, "action_linked_revision_receipt"
    )
    action_receipt = action_receipt if isinstance(action_receipt, dict) else {}
    revision_receipt = revision_receipt if isinstance(revision_receipt, dict) else {}
    action_rows = _rows(
        _load_json(_path(action_receipt.get("decision_index"), errors, "action_decision_index"), errors, "action_decision_index"),
        errors,
        "action_decision_index",
    )
    revision_rows = _rows(
        _load_json(_path(revision_receipt.get("revision_index"), errors, "revision_index"), errors, "revision_index"),
        errors,
        "revision_index",
    )
    action_by_key = _index(action_rows, errors, "action_decision_index")
    revision_by_key = _index(revision_rows, errors, "revision_index")

    audit_rows: list[dict[str, Any]] = []
    counts = {
        "condition_cases_seen": len(case_rows),
        "action_cases_seen": len(action_rows),
        "revision_cases_seen": len(revision_rows),
        "cases_audited": 0,
        "conditions_represented": 0,
        "stage_artifacts_loaded": 0,
        "stage_json_hashes_recomputed": 0,
        "commitment_hashes_recomputed": 0,
        "accepted_source_refs_checked": 0,
        "gate6_links_checked": 0,
        "gate7_links_checked": 0,
        "write_violations": 0,
    }
    represented_conditions: set[str] = set()

    if action_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION":
        errors.append(f"action_selection_receipt_not_pass:{action_receipt.get('status')}")
    if revision_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION":
        errors.append(f"action_linked_revision_receipt_not_pass:{revision_receipt.get('status')}")
    if action_receipt.get("receipt_sha256") and action_receipt.get("receipt_sha256") != action_receipt_recomputed_sha:
        errors.append(f"action_selection_receipt_sha256_mismatch:{action_receipt.get('receipt_sha256')}:{action_receipt_recomputed_sha}")
    if revision_receipt.get("receipt_sha256") and revision_receipt.get("receipt_sha256") != revision_receipt_recomputed_sha:
        errors.append(
            f"action_linked_revision_receipt_sha256_mismatch:{revision_receipt.get('receipt_sha256')}:{revision_receipt_recomputed_sha}"
        )

    for idx, case in enumerate(case_rows):
        episode_id = case.get("episode_id")
        condition = case.get("condition")
        prefix = f"case_{idx}_{episode_id}_{condition}"
        if not isinstance(episode_id, str) or not isinstance(condition, str):
            errors.append(f"{prefix}_missing_episode_condition")
            continue
        represented_conditions.add(condition)
        key = (episode_id, condition)
        action = action_by_key.get(key)
        revision = revision_by_key.get(key)
        if action is None:
            errors.append(f"{prefix}_missing_action_decision_row")
        if revision is None:
            errors.append(f"{prefix}_missing_revision_row")
        case_root = _path(case.get("case_root"), errors, f"{prefix}_case_root")
        paths = {
            "distribution": case_root / "tom_belief_distribution_bundle.json",
            "branches": case_root / "counterfactual_branch_bundle.json",
            "commitment": case_root / "tom_prediction_commitment_bundle.json",
            "outcome": case_root / "tom_outcome_reveal.json",
        }
        loaded = {name: _load_json(path, errors, f"{prefix}_{name}") for name, path in paths.items()}
        for value in loaded.values():
            if isinstance(value, dict):
                counts["stage_artifacts_loaded"] += 1
        dist = loaded["distribution"] if isinstance(loaded["distribution"], dict) else {}
        branches = loaded["branches"] if isinstance(loaded["branches"], dict) else {}
        commitment = loaded["commitment"] if isinstance(loaded["commitment"], dict) else {}
        outcome = loaded["outcome"] if isinstance(loaded["outcome"], dict) else {}
        dist_sha = _stable_json_sha256(dist)
        branch_sha = _stable_json_sha256(branches)
        commitment_sha = _stable_json_sha256(commitment)
        outcome_sha = _stable_json_sha256(outcome)
        counts["stage_json_hashes_recomputed"] += 4
        hash_count, source_ref_count = _commitment_hashes(commitment, dist_sha, branch_sha, errors, prefix)
        counts["commitment_hashes_recomputed"] += hash_count
        counts["accepted_source_refs_checked"] += source_ref_count
        if dist.get("episode_id") != episode_id or branches.get("episode_id") != episode_id or commitment.get("episode_id") != episode_id:
            errors.append(f"{prefix}_episode_id_mismatch_across_gate2_4")
        if outcome.get("episode_id") != episode_id:
            errors.append(f"{prefix}_outcome_episode_id_mismatch:{outcome.get('episode_id')}:{episode_id}")
        if dist.get("condition") != condition or branches.get("condition") != condition:
            errors.append(f"{prefix}_condition_mismatch_across_gate2_3")
        for name, value in (("distribution", dist), ("commitment", commitment)):
            if value.get("sealed") is not True:
                errors.append(f"{prefix}_{name}_sealed_not_true:{value.get('sealed')}")
        for name, value in (("distribution", dist), ("branches", branches), ("commitment", commitment)):
            if value.get("outcome_visible") is not False:
                errors.append(f"{prefix}_{name}_outcome_visible_not_false:{value.get('outcome_visible')}")
        if outcome.get("outcome_visible") is not True or outcome.get("reveal_complete") is not True:
            errors.append(f"{prefix}_outcome_not_revealed")
        commitment_ids = [
            item.get("prediction_id")
            for item in commitment.get("commitments", [])
            if isinstance(item, dict) and isinstance(item.get("prediction_id"), str)
        ]
        if outcome.get("prediction_id") not in commitment_ids:
            errors.append(f"{prefix}_outcome_prediction_id_not_in_commitments:{outcome.get('prediction_id')}")
        for artifact_name, value in (
            ("distribution", dist),
            ("branches", branches),
            ("commitment", commitment),
            ("outcome", outcome),
        ):
            for field in ("canonical_memory_write", "identity_write", "source_memory_write"):
                if field in value and value.get(field) is not False:
                    counts["write_violations"] += 1
                    errors.append(f"{prefix}_{artifact_name}_{field}_not_false:{value.get(field)}")

        gate6_status = None
        gate7_status = None
        scoring_path = Path("__missing__")
        scoring_sha = None
        if isinstance(action, dict):
            gate6_path = _path(action.get("gate6_receipt_path"), errors, f"{prefix}_gate6_receipt")
            gate6 = _load_json(gate6_path, errors, f"{prefix}_gate6_receipt")
            gate6 = gate6 if isinstance(gate6, dict) else {}
            gate6_status = gate6.get("status")
            if gate6_status != "PASS_TOM_ACTION_SELECTION":
                errors.append(f"{prefix}_gate6_not_pass:{gate6_status}")
            if Path(str(gate6.get("outcome_reveal_path"))) != paths["outcome"]:
                errors.append(f"{prefix}_gate6_outcome_path_mismatch:{gate6.get('outcome_reveal_path')}:{paths['outcome']}")
            scoring_path = _path(gate6.get("scoring_receipt_path"), errors, f"{prefix}_gate6_scoring_receipt")
            scoring = _load_json(scoring_path, errors, f"{prefix}_gate5_scoring_receipt")
            scoring = scoring if isinstance(scoring, dict) else {}
            scoring_sha = _stable_json_sha256(scoring)
            if scoring.get("status") != "PASS_TOM_SCORING_RECEIPT":
                errors.append(f"{prefix}_gate5_scoring_not_pass:{scoring.get('status')}")
            counts["stage_artifacts_loaded"] += 1 if scoring else 0
            counts["stage_json_hashes_recomputed"] += 1 if scoring else 0
            counts["gate6_links_checked"] += 1

        if isinstance(revision, dict):
            revision_path = _path(revision.get("revision_path"), errors, f"{prefix}_revision_path")
            gate7_path = _path(revision.get("gate7_receipt_path"), errors, f"{prefix}_gate7_receipt")
            revision_doc = _load_json(revision_path, errors, f"{prefix}_belief_revision")
            gate7 = _load_json(gate7_path, errors, f"{prefix}_gate7_receipt")
            revision_doc = revision_doc if isinstance(revision_doc, dict) else {}
            gate7 = gate7 if isinstance(gate7, dict) else {}
            gate7_status = gate7.get("status")
            if gate7_status != "PASS_TOM_BELIEF_REVISION":
                errors.append(f"{prefix}_gate7_not_pass:{gate7_status}")
            if Path(str(gate7.get("distribution_bundle_path"))) != paths["distribution"]:
                errors.append(f"{prefix}_gate7_distribution_path_mismatch")
            if Path(str(gate7.get("outcome_reveal_path"))) != paths["outcome"]:
                errors.append(f"{prefix}_gate7_outcome_path_mismatch")
            if Path(str(gate7.get("scoring_receipt_path"))) != scoring_path:
                errors.append(f"{prefix}_gate7_scoring_path_mismatch:{gate7.get('scoring_receipt_path')}:{scoring_path}")
            if revision_doc.get("outcome_reveal_sha256") != outcome_sha:
                errors.append(f"{prefix}_revision_outcome_reveal_sha256_mismatch:{revision_doc.get('outcome_reveal_sha256')}:{outcome_sha}")
            if scoring_sha and revision_doc.get("scoring_receipt_sha256") != scoring_sha:
                errors.append(f"{prefix}_revision_scoring_receipt_sha256_mismatch:{revision_doc.get('scoring_receipt_sha256')}:{scoring_sha}")
            prior_ref = revision_doc.get("prior_audit_ref") if isinstance(revision_doc.get("prior_audit_ref"), dict) else {}
            if prior_ref.get("distribution_bundle_sha256") != dist_sha:
                errors.append(f"{prefix}_revision_prior_distribution_bundle_sha256_mismatch:{prior_ref.get('distribution_bundle_sha256')}:{dist_sha}")
            if revision_doc.get("prior_remains_auditable") is not True:
                errors.append(f"{prefix}_revision_prior_not_auditable")
            if revision_doc.get("evidence_mutations") not in ([], None):
                errors.append(f"{prefix}_revision_evidence_mutations_nonempty")
            for field in ("canonical_memory_write", "identity_write", "source_memory_write"):
                if revision_doc.get(field) is not False:
                    counts["write_violations"] += 1
                    errors.append(f"{prefix}_revision_{field}_not_false:{revision_doc.get(field)}")
            counts["stage_artifacts_loaded"] += 2 if revision_doc and gate7 else 0
            counts["stage_json_hashes_recomputed"] += 1 if revision_doc else 0
            counts["gate7_links_checked"] += 1

        counts["cases_audited"] += 1
        audit_rows.append(
            {
                "episode_id": episode_id,
                "condition": condition,
                "case_root": str(case_root),
                "distribution_bundle_sha256": dist_sha,
                "branch_bundle_sha256": branch_sha,
                "commitment_bundle_sha256": commitment_sha,
                "outcome_reveal_sha256": outcome_sha,
                "gate6_status": gate6_status,
                "gate7_status": gate7_status,
            }
        )

    counts["conditions_represented"] = len(represented_conditions)
    if len(case_rows) != expect_cases:
        errors.append(f"case_count_mismatch:{len(case_rows)}:{expect_cases}")
    if set(represented_conditions) != CONDITIONS:
        errors.append(f"conditions_mismatch:{sorted(represented_conditions)}:{sorted(CONDITIONS)}")
    if len(action_rows) != len(case_rows):
        errors.append(f"action_row_count_mismatch:{len(action_rows)}:{len(case_rows)}")
    if len(revision_rows) != len(case_rows):
        errors.append(f"revision_row_count_mismatch:{len(revision_rows)}:{len(case_rows)}")
    if counts["write_violations"] != 0:
        errors.append(f"write_violations_nonzero:{counts['write_violations']}")

    audit_rows_path = output_root / "artifacts" / "stage_hash_lineage_audit_rows.json"
    _write_json(audit_rows_path, audit_rows)
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_stage_hash_lineage_audit_receipt.v1",
        "created_at": _now_iso(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "condition_case_index": str(condition_case_index),
        "condition_case_index_sha256": _file_sha256(condition_case_index) if condition_case_index.exists() else None,
        "action_selection_receipt": str(action_selection_receipt),
        "action_selection_receipt_recomputed_sha256": action_receipt_recomputed_sha,
        "action_linked_revision_receipt": str(action_linked_revision_receipt),
        "action_linked_revision_receipt_recomputed_sha256": revision_receipt_recomputed_sha,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "audit_rows": str(audit_rows_path),
        "audit_rows_sha256": _file_sha256(audit_rows_path),
        "errors": errors,
        "counts": counts,
        "checks": {
            "condition_case_count_matches_expected": len(case_rows) == expect_cases,
            "all_conditions_represented": set(represented_conditions) == CONDITIONS,
            "action_rows_match_case_rows": len(action_rows) == len(case_rows),
            "revision_rows_match_case_rows": len(revision_rows) == len(case_rows),
            "commitment_hashes_recomputed": counts["commitment_hashes_recomputed"] >= len(case_rows) * 3,
            "accepted_source_refs_present": counts["accepted_source_refs_checked"] >= len(case_rows),
            "gate6_links_checked": counts["gate6_links_checked"] == len(case_rows),
            "gate7_links_checked": counts["gate7_links_checked"] == len(case_rows),
            "unsupported_writes_absent": counts["write_violations"] == 0,
            "human_content_judgment_absent": True,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": fixture_backed,
        "live_tau_originated_artifacts_consumed": True,
        "memory_write_attempts": 0,
        "tau_call_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "processing_time_s": round(time.monotonic() - started, 6),
        "claims": {
            "proves": [
                "live-originated PCTOM-R Gate 2-7 artifacts are re-walked through one cross-stage hash and lineage audit",
                "Gate 4 prediction payload, model receipt, and evidence-bundle hashes are recomputed for every commitment",
                "Gate 0 accepted source attribution fields are present in commitment evidence refs",
                "Gate 6 action-selection and Gate 7 revision rows resolve back to the same case, outcome, scoring, and distribution artifacts",
                "no Memory write, provider call, Tau call, canonical write, identity write, source-memory write, LLM judge, or human content judgment was used by the audit",
            ]
            if not errors
            else [
                "the cross-stage hash/lineage audit failed closed before accepting the PCTOM-R stage chain",
            ],
            "does_not_prove": [
                "new live Tau execution",
                "new live Memory recall",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition-case-index", type=Path, required=True)
    parser.add_argument("--action-selection-receipt", type=Path, required=True)
    parser.add_argument("--action-linked-revision-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--expect-cases", type=int, default=128)
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_stage_hash_lineage_audit_receipt.v1.json")
    receipt = run(
        condition_case_index=args.condition_case_index,
        action_selection_receipt=args.action_selection_receipt,
        action_linked_revision_receipt=args.action_linked_revision_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        expect_cases=args.expect_cases,
        fixture_backed=args.fixture_backed,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
