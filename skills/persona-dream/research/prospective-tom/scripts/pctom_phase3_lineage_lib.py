"""Deterministic Phase 3 lineage and pre-seal isolation helpers."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


SCHEMA_PREFIX = "persona_dream.research.prospective_tom"
REQUIRED_CASE_FILES = {
    "recall_receipts": "recall_receipts.json",
    "normalized_residue": "normalized_residue.json",
    "dream_branches": "dream_branches.json",
    "tom_prediction_commitment": "tom_prediction_commitment.json",
}
FORBIDDEN_OUTCOME_KEYS = {
    "actual_next_action",
    "hidden_world_state",
    "ground_truth_tom_labels",
    "outcome",
    "outcome_reveal",
    "observed_outcome",
    "revealed_outcome",
    "score",
    "scoring_receipt",
}


def collect_forbidden_paths(value: Any, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_OUTCOME_KEYS:
                paths.append(child_path)
            paths.extend(collect_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(collect_forbidden_paths(child, f"{prefix}[{index}]"))
    return paths


def load_case_data(case_root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    data: dict[str, Any] = {}
    for key, filename in REQUIRED_CASE_FILES.items():
        data[key] = load_json(case_root / filename, errors, key)
    return data, errors


def source_files(root: Path, case_root: Path) -> list[dict[str, str]]:
    rows = []
    for key, filename in REQUIRED_CASE_FILES.items():
        path = case_root / filename
        rows.append({
            "artifact": key,
            "path": rel(root, path),
            "sha256": file_sha256(path),
        })
    return rows


def _pair(ref: Any) -> tuple[str, str] | None:
    if not isinstance(ref, dict):
        return None
    scope = ref.get("scope")
    source_id = ref.get("source_id")
    if not isinstance(scope, str) or not scope or not isinstance(source_id, str) or not source_id:
        return None
    return scope, source_id


def audit_case_data(data: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    recall_receipts = data.get("recall_receipts")
    residues = data.get("normalized_residue")
    branches = data.get("dream_branches")
    commitment = data.get("tom_prediction_commitment")

    accepted: dict[tuple[int, str, str], dict[str, Any]] = {}
    if not isinstance(recall_receipts, list):
        errors.append("case_recall_receipts_not_list")
        recall_receipts = []
    for receipt_index, receipt in enumerate(recall_receipts):
        if not isinstance(receipt, dict):
            errors.append(f"recall_receipt_{receipt_index}_not_object")
            continue
        scope = receipt.get("scope")
        source_ids = receipt.get("accepted_source_ids")
        if not isinstance(scope, str) or not scope:
            errors.append(f"recall_receipt_{receipt_index}_missing_scope")
            scope = ""
        if not isinstance(source_ids, list):
            errors.append(f"recall_receipt_{receipt_index}_accepted_source_ids_not_list")
            source_ids = []
        expected_hash = stable_json_sha256(source_ids)
        if receipt.get("accepted_source_ids_sha256") != expected_hash:
            errors.append(f"stale_source_substitution:recall_receipt_{receipt_index}_accepted_source_ids_sha256_mismatch")
        for order, source_id in enumerate(source_ids):
            if isinstance(source_id, str) and source_id:
                accepted[(receipt_index, scope, source_id)] = {
                    "accepted_order": order,
                    "accepted_source_ids_sha256": receipt.get("accepted_source_ids_sha256"),
                    "query": receipt.get("query"),
                }

    residue_pairs: set[tuple[str, str]] = set()
    residue_index: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(residues, list):
        errors.append("case_normalized_residue_not_list")
        residues = []
    for residue_number, residue in enumerate(residues):
        if not isinstance(residue, dict):
            errors.append(f"residue_{residue_number}_not_object")
            continue
        scope = residue.get("scope")
        source_id = residue.get("source_id")
        query_receipt_index = residue.get("query_receipt_index")
        if residue.get("synthetic") is not False:
            errors.append(f"residue_{residue_number}_synthetic_not_false")
        if not isinstance(scope, str) or not scope or not isinstance(source_id, str) or not source_id:
            errors.append(f"residue_{residue_number}_missing_source_pair")
            continue
        if not isinstance(query_receipt_index, int):
            errors.append(f"residue_{residue_number}_missing_query_receipt_index")
            continue
        accepted_row = accepted.get((query_receipt_index, scope, source_id))
        if accepted_row is None:
            errors.append(f"unaccepted_source:residue_{residue_number}:{scope}:{source_id}")
            continue
        pair = (scope, source_id)
        if pair in residue_pairs:
            errors.append(f"duplicate_residue_pair:{scope}:{source_id}")
        residue_pairs.add(pair)
        residue_index[pair] = {
            "residue_index": residue_number,
            "query_receipt_index": query_receipt_index,
            "accepted_order": accepted_row["accepted_order"],
            "accepted_source_ids_sha256": accepted_row["accepted_source_ids_sha256"],
            "query": accepted_row["query"],
            "residue": residue,
        }

    branch_ids: set[str] = set()
    branch_pairs: dict[str, set[tuple[str, str]]] = {}
    branch_episode_ids: dict[str, str] = {}
    if not isinstance(branches, list):
        errors.append("case_dream_branches_not_list")
        branches = []
    for branch_number, branch in enumerate(branches):
        if not isinstance(branch, dict):
            errors.append(f"branch_{branch_number}_not_object")
            continue
        branch_id = branch.get("branch_id")
        episode_id = branch.get("episode_id")
        if not isinstance(branch_id, str) or not branch_id:
            errors.append(f"branch_{branch_number}_missing_branch_id")
            continue
        if branch_id in branch_ids:
            errors.append(f"duplicate_branch_id:{branch_id}")
        branch_ids.add(branch_id)
        if isinstance(episode_id, str) and episode_id:
            branch_episode_ids[branch_id] = episode_id
        refs = branch.get("source_residue_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"branch_{branch_number}_missing_source_residue_refs")
            continue
        branch_pairs.setdefault(branch_id, set())
        for ref_number, ref in enumerate(refs):
            pair = _pair(ref)
            if pair is None:
                errors.append(f"branch_{branch_number}_source_ref_{ref_number}_invalid")
                continue
            if pair not in residue_pairs:
                errors.append(f"unaccepted_source:branch_{branch_number}_unresolved_residue_ref:{pair[0]}:{pair[1]}")
            branch_pairs[branch_id].add(pair)

    prediction_refs: list[tuple[str, str]] = []
    prediction_branch_refs: list[str] = []
    payload_hash_valid = False
    outcome_visible = None
    commitment_episode_id = None
    if not isinstance(commitment, dict):
        errors.append("case_tom_prediction_commitment_not_object")
        commitment = {}
    else:
        outcome_visible = commitment.get("outcome_visible")
        commitment_episode_id = commitment.get("episode_id")
        if outcome_visible is not False:
            errors.append("prospective_leakage:commitment_outcome_visible_not_false")
        payload = commitment.get("prediction_payload")
        expected_payload_hash = stable_json_sha256(payload)
        if commitment.get("prediction_payload_sha256") != expected_payload_hash:
            errors.append("postseal_lineage_mutation:commitment_prediction_payload_sha256_mismatch")
        else:
            payload_hash_valid = True
        if isinstance(payload, dict):
            if payload.get("episode_id") != commitment_episode_id:
                errors.append(f"cross_episode_source:payload_episode_mismatch:{payload.get('episode_id')}:{commitment_episode_id}")
            for ref_number, ref in enumerate(payload.get("evidence_residue_refs") or []):
                pair = _pair(ref)
                if pair is None:
                    errors.append(f"prediction_evidence_ref_{ref_number}_invalid")
                    continue
                if pair not in residue_pairs:
                    errors.append(f"unaccepted_source:prediction_unresolved_evidence_ref:{pair[0]}:{pair[1]}")
                prediction_refs.append(pair)
            for branch_ref in payload.get("dream_branch_refs") or []:
                if not isinstance(branch_ref, str) or not branch_ref:
                    errors.append("prediction_invalid_dream_branch_ref")
                    continue
                if branch_ref not in branch_ids:
                    errors.append(f"prediction_unresolved_dream_branch_ref:{branch_ref}")
                else:
                    prediction_branch_refs.append(branch_ref)
                    if branch_episode_ids.get(branch_ref) != commitment_episode_id:
                        errors.append(
                            "cross_episode_source:branch_episode_mismatch:"
                            f"{branch_ref}:{branch_episode_ids.get(branch_ref)}:{commitment_episode_id}"
                        )
            if prediction_refs and prediction_branch_refs:
                carried_pairs: set[tuple[str, str]] = set()
                for branch_ref in prediction_branch_refs:
                    carried_pairs.update(branch_pairs.get(branch_ref, set()))
                for pair in prediction_refs:
                    if pair not in carried_pairs:
                        errors.append(f"prediction_source_not_carried_by_branch:{pair[0]}:{pair[1]}")

    forbidden_paths = collect_forbidden_paths(data)
    for path in forbidden_paths:
        errors.append(f"prospective_leakage:forbidden_outcome_key:{path}")

    counts = {
        "recall_receipts": len(recall_receipts),
        "accepted_source_ids": len(accepted),
        "normalized_residue": len(residue_pairs),
        "dream_branches": len(branch_ids),
        "prediction_evidence_refs": len(prediction_refs),
        "prediction_branch_refs": len(prediction_branch_refs),
        "accepted_source_lineage_missing": sum(
            1 for error in errors
            if error.startswith("unaccepted_source:")
            or error.startswith("prediction_source_not_carried_by_branch:")
            or error.startswith("prediction_unresolved_dream_branch_ref:")
        ),
        "preseal_outcome_dependencies": len(forbidden_paths) + (1 if outcome_visible is not False else 0),
        "postseal_lineage_mutations": sum(1 for error in errors if error.startswith("postseal_lineage_mutation:")),
        "cross_episode_sources": sum(1 for error in errors if error.startswith("cross_episode_source:")),
        "stale_source_substitutions": sum(1 for error in errors if error.startswith("stale_source_substitution:")),
    }
    derived = {
        "counts": counts,
        "residue_index": residue_index,
        "branch_pairs": branch_pairs,
        "prediction_refs": prediction_refs,
        "prediction_branch_refs": prediction_branch_refs,
        "payload_hash_valid": payload_hash_valid,
        "forbidden_paths": forbidden_paths,
    }
    return errors, derived


def mutation_status(errors: list[str]) -> str:
    if any(error.startswith("prospective_leakage:") for error in errors):
        return "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE"
    if any(error.startswith("postseal_lineage_mutation:") for error in errors):
        return "BLOCKED_PCTOM_POSTSEAL_LINEAGE_MUTATION"
    if any(error.startswith("cross_episode_source:") for error in errors):
        return "BLOCKED_PCTOM_CROSS_EPISODE_SOURCE"
    if any(error.startswith("stale_source_substitution:") for error in errors):
        return "BLOCKED_PCTOM_STALE_SOURCE_SUBSTITUTION"
    if any(error.startswith("unaccepted_source:") for error in errors):
        return "BLOCKED_PCTOM_UNACCEPTED_SOURCE"
    return "PASS_PCTOM_PHASE3_CASE"


def phase3_negative_cases(data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []

    unaccepted = deepcopy(data)
    unaccepted["normalized_residue"][0]["source_id"] = "memory_999"
    cases.append(("unaccepted-source", "BLOCKED_PCTOM_UNACCEPTED_SOURCE", unaccepted))

    stale = deepcopy(data)
    stale["recall_receipts"][0]["accepted_source_ids_sha256"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    cases.append(("stale-source-substitution", "BLOCKED_PCTOM_STALE_SOURCE_SUBSTITUTION", stale))

    cross_episode = deepcopy(data)
    cross_episode["dream_branches"][0]["episode_id"] = "episode-cross-source"
    cases.append(("cross-episode-source", "BLOCKED_PCTOM_CROSS_EPISODE_SOURCE", cross_episode))

    postseal = deepcopy(data)
    postseal["tom_prediction_commitment"]["prediction_payload"]["evidence_residue_refs"].append({
        "scope": "persona-dream",
        "source_id": "memory_42",
    })
    cases.append(("postseal-lineage-mutation", "BLOCKED_PCTOM_POSTSEAL_LINEAGE_MUTATION", postseal))

    leakage = deepcopy(data)
    leakage["tom_prediction_commitment"]["prediction_payload"]["outcome_reveal"] = {
        "actual_next_action": "ASK_CLARIFYING_QUESTION"
    }
    cases.append(("prospective-leakage", "BLOCKED_PCTOM_PROSPECTIVE_LEAKAGE", leakage))
    return cases


def build_lineage_evidence(root: Path, case_root: Path, evidence_out: Path) -> dict[str, Any]:
    data, load_errors = load_case_data(case_root)
    errors, derived = audit_case_data(data)
    rows: list[dict[str, Any]] = []
    commitment = data.get("tom_prediction_commitment") if isinstance(data.get("tom_prediction_commitment"), dict) else {}
    prediction_payload = commitment.get("prediction_payload") if isinstance(commitment.get("prediction_payload"), dict) else {}
    branches = data.get("dream_branches") if isinstance(data.get("dream_branches"), list) else []
    branch_by_id = {branch.get("branch_id"): branch for branch in branches if isinstance(branch, dict)}
    for pair in derived["prediction_refs"]:
        residue = derived["residue_index"].get(pair)
        if not residue:
            continue
        carrying_branch_ids = [
            branch_id for branch_id in derived["prediction_branch_refs"]
            if pair in derived["branch_pairs"].get(branch_id, set())
        ]
        for branch_id in carrying_branch_ids:
            branch = branch_by_id.get(branch_id, {})
            rows.append({
                "chain_id": f"{commitment.get('prediction_id')}:{branch_id}:{pair[0]}:{pair[1]}",
                "query_receipt_path": rel(root, case_root / "recall_receipts.json"),
                "query_receipt_index": residue["query_receipt_index"],
                "query": residue["query"],
                "accepted_raw_source_id": pair[1],
                "accepted_source_id": pair[1],
                "scope": pair[0],
                "accepted_order": residue["accepted_order"],
                "accepted_source_ids_sha256": residue["accepted_source_ids_sha256"],
                "normalized_residue_path": rel(root, case_root / "normalized_residue.json"),
                "normalized_residue_index": residue["residue_index"],
                "normalized_residue_sha256": stable_json_sha256(residue["residue"]),
                "dream_branch_path": rel(root, case_root / "dream_branches.json"),
                "dream_branch_id": branch_id,
                "dream_branch_type": branch.get("branch_type"),
                "dream_branch_sha256": stable_json_sha256(branch),
                "tom_prediction_commitment_path": rel(root, case_root / "tom_prediction_commitment.json"),
                "prediction_id": commitment.get("prediction_id"),
                "condition": commitment.get("condition"),
                "prediction_payload_sha256": commitment.get("prediction_payload_sha256"),
                "prediction_payload_recomputed_sha256": stable_json_sha256(prediction_payload),
                "outcome_visible": commitment.get("outcome_visible"),
                "lineage_complete": True,
            })
    counts = dict(derived["counts"])
    counts["lineage_rows"] = len(rows)
    counts["build_errors"] = len(load_errors) + len(errors)
    evidence = {
        "schema": f"{SCHEMA_PREFIX}.pctom_accepted_source_lineage.v1",
        "created_at": now_iso(),
        "status": "ACCEPTED_SOURCE_LINEAGE_BUILT",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "source_case_root": rel(root, case_root),
        "source_files": source_files(root, case_root),
        "lineage_rows": rows,
        "counts": counts,
        "build_errors": load_errors + errors,
        "claims": {
            "proves": [
                "Gate 0 positive fixture source ids are represented as explicit query receipt to accepted source to normalized residue to dream branch to ToM prediction rows",
                "accepted source ids and sealed prediction payload hashes are recomputed for the archived fixture-backed lineage evidence",
            ],
            "does_not_prove": [
                "live Memory recall",
                "semantic dream quality",
                "future prediction accuracy",
                "proper scoring",
                "belief revision",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    write_json(evidence_out, evidence)
    return evidence
