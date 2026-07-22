#!/usr/bin/env python3
"""Check that PCTOM-R goal clauses are backed by concrete local receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_GOAL_COVERAGE"
BLOCKED_STATUS = "BLOCKED_PCTOM_GOAL_COVERAGE"
SCHEMA = "persona_dream.research.prospective_tom.goal_coverage_receipt.v1"

REQUIRED_COVERAGE_IDS = {
    "gate0_provenance_bound_recall_residue",
    "gate1_deterministic_hidden_state_social_episodes",
    "gate2_valid_tom_distributions",
    "gate3_counterfactual_branches_synthetic",
    "gate4_sealed_prediction_commitments",
    "gate5_deterministic_scoring",
    "gate6_action_selection_planning",
    "gate7_non_destructive_belief_revision",
    "gate8_fault_containment",
    "gate9_causal_replay",
    "cross_stage_hash_lineage",
    "autonomous_no_human_judgment",
    "memory_retention_and_recall",
    "negative_fixtures_fail_closed",
}

POSITIVE_STATUS_PREFIXES = ("PASS_",)
NEGATIVE_STATUS_PREFIXES = ("BLOCKED_",)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    if not path.is_file():
        errors.append(f"{label}_not_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _as_list(value: Any, errors: list[str], label: str) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label}_not_list")
        return []
    return value


def _status_matches(status: Any, kind: str) -> bool:
    if not isinstance(status, str):
        return False
    if kind == "positive":
        return status.startswith(POSITIVE_STATUS_PREFIXES)
    if kind == "negative":
        return status.startswith(NEGATIVE_STATUS_PREFIXES)
    return False


def _counter(receipt: dict[str, Any], *names: str) -> int:
    total = 0
    for name in names:
        value = receipt.get(name)
        if isinstance(value, bool):
            total += int(value)
        elif isinstance(value, int):
            total += value
    return total


def _validate_evidence(
    coverage_id: str,
    item_index: int,
    item: dict[str, Any],
    manifest_dir: Path,
    errors: list[str],
) -> dict[str, Any] | None:
    kind = item.get("kind", "positive")
    if kind not in {"positive", "negative"}:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_kind_invalid:{kind}")
        kind = "positive"
    raw_path = item.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_path_missing")
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = (manifest_dir / path).resolve()
    receipt = _load_json(path, errors, f"coverage_{coverage_id}_receipt_{item_index}")
    if not isinstance(receipt, dict):
        return None
    file_sha256 = _file_sha256(path)

    status = receipt.get("status")
    if not _status_matches(status, kind):
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_status_mismatch:{kind}:{status}")

    if item.get("require_mocked_false", True) and receipt.get("mocked") is not False:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_mocked_not_false:{receipt.get('mocked')}")

    if kind == "positive" and item.get("allow_fixture_backed", False) is not True and receipt.get("fixture_backed") is True:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_positive_fixture_backed_true")

    if item.get("require_no_llm_judge_true", True) and receipt.get("llm_judge_used") is True:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_llm_judge_used_true")

    if item.get("require_no_human_content_judgment_true", True) and receipt.get("human_content_judgment_required") is True:
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_human_content_judgment_required_true")

    if item.get("require_receipt_sha256", True):
        sha = receipt.get("receipt_sha256")
        expected_file_sha256 = item.get("expected_file_sha256")
        if isinstance(sha, str) and sha.startswith("sha256:"):
            pass
        elif isinstance(expected_file_sha256, str) and expected_file_sha256.startswith("sha256:"):
            if file_sha256 != expected_file_sha256:
                errors.append(
                    f"coverage_{coverage_id}_evidence_{item_index}_expected_file_sha256_mismatch:"
                    f"{file_sha256}:{expected_file_sha256}"
                )
        else:
            errors.append(f"coverage_{coverage_id}_evidence_{item_index}_receipt_sha256_missing")

    forbidden_write_count = _counter(
        receipt,
        "actual_provider_call_attempts",
        "provider_calls",
        "provider_call_count",
        "canonical_memory_writes",
        "identity_writes",
        "source_memory_writes",
        "canonical_write_violations",
        "identity_write_violations",
        "source_memory_write_violations",
    )
    if item.get("require_no_provider_or_canonical_writes", True) and forbidden_write_count:
        errors.append(
            f"coverage_{coverage_id}_evidence_{item_index}_provider_or_canonical_write_counter_nonzero:"
            f"{forbidden_write_count}"
        )

    required_errors = item.get("required_error_needles", [])
    if required_errors is None:
        required_errors = []
    if not isinstance(required_errors, list):
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_required_error_needles_not_list")
        required_errors = []
    receipt_errors = "\n".join(str(error) for error in receipt.get("errors", []))
    matched_errors = [needle for needle in required_errors if isinstance(needle, str) and needle in receipt_errors]
    for needle in required_errors:
        if not isinstance(needle, str):
            errors.append(f"coverage_{coverage_id}_evidence_{item_index}_required_error_needle_not_string")
        elif needle not in receipt_errors:
            errors.append(f"coverage_{coverage_id}_evidence_{item_index}_required_error_missing:{needle}")

    required_counts = item.get("required_counts", {})
    if required_counts is None:
        required_counts = {}
    if not isinstance(required_counts, dict):
        errors.append(f"coverage_{coverage_id}_evidence_{item_index}_required_counts_not_object")
        required_counts = {}
    count_matches: dict[str, Any] = {}
    receipt_counts = receipt.get("counts", {})
    for key, expected in required_counts.items():
        actual = receipt_counts.get(key) if isinstance(receipt_counts, dict) else None
        count_matches[key] = {"expected": expected, "actual": actual, "matched": actual == expected}
        if actual != expected:
            errors.append(f"coverage_{coverage_id}_evidence_{item_index}_count_mismatch:{key}:{actual}:{expected}")

    return {
        "coverage_id": coverage_id,
        "kind": kind,
        "path": str(path),
        "status": status,
        "schema": receipt.get("schema"),
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "fixture_backed": receipt.get("fixture_backed"),
        "human_content_judgment_required": receipt.get("human_content_judgment_required"),
        "llm_judge_used": receipt.get("llm_judge_used"),
        "file_sha256": file_sha256,
        "expected_file_sha256": item.get("expected_file_sha256"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "required_error_needles": required_errors,
        "matched_error_needles": matched_errors,
        "required_count_matches": count_matches,
    }


def run(*, manifest_path: Path, output_root: Path, receipt_out: Path, fixture_backed: bool) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    manifest_path = manifest_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    manifest = _load_json(manifest_path, errors, "manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    coverage_items = _as_list(manifest.get("coverage"), errors, "manifest_coverage")

    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    evidence_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    positive_evidence = 0
    negative_evidence = 0
    live_positive_evidence = 0

    for index, raw_item in enumerate(coverage_items):
        if not isinstance(raw_item, dict):
            errors.append(f"coverage_{index}_not_object")
            continue
        coverage_id = raw_item.get("coverage_id")
        if not isinstance(coverage_id, str) or not coverage_id:
            errors.append(f"coverage_{index}_id_missing")
            continue
        if coverage_id in seen_ids:
            duplicate_ids.append(coverage_id)
            errors.append(f"coverage_duplicate_id:{coverage_id}")
        seen_ids.add(coverage_id)
        evidence = _as_list(raw_item.get("evidence"), errors, f"coverage_{coverage_id}_evidence")
        if not evidence:
            errors.append(f"coverage_{coverage_id}_evidence_empty")
        row = {
            "coverage_id": coverage_id,
            "description": raw_item.get("description"),
            "evidence_count": len(evidence),
            "positive_evidence": 0,
            "negative_evidence": 0,
            "live_positive_evidence": 0,
        }
        for item_index, evidence_item in enumerate(evidence):
            if not isinstance(evidence_item, dict):
                errors.append(f"coverage_{coverage_id}_evidence_{item_index}_not_object")
                continue
            evidence_row = _validate_evidence(coverage_id, item_index, evidence_item, manifest_path.parent, errors)
            if evidence_row is None:
                continue
            evidence_rows.append(evidence_row)
            if evidence_row["kind"] == "positive":
                row["positive_evidence"] += 1
                positive_evidence += 1
                if evidence_row.get("live") is True:
                    row["live_positive_evidence"] += 1
                    live_positive_evidence += 1
            elif evidence_row["kind"] == "negative":
                row["negative_evidence"] += 1
                negative_evidence += 1
        if raw_item.get("require_negative", False) and row["negative_evidence"] == 0:
            errors.append(f"coverage_{coverage_id}_missing_required_negative")
        if raw_item.get("require_live_positive", False) and row["live_positive_evidence"] == 0:
            errors.append(f"coverage_{coverage_id}_missing_required_live_positive")
        if row["positive_evidence"] == 0:
            errors.append(f"coverage_{coverage_id}_missing_positive_evidence")
        coverage_rows.append(row)

    missing_ids = sorted(REQUIRED_COVERAGE_IDS - seen_ids)
    unexpected_ids = sorted(seen_ids - REQUIRED_COVERAGE_IDS)
    for coverage_id in missing_ids:
        errors.append(f"missing_required_coverage_id:{coverage_id}")
    for coverage_id in unexpected_ids:
        errors.append(f"unexpected_coverage_id:{coverage_id}")

    counts = {
        "required_coverage_ids": len(REQUIRED_COVERAGE_IDS),
        "coverage_ids_seen": len(seen_ids),
        "coverage_ids_missing": len(missing_ids),
        "coverage_ids_unexpected": len(unexpected_ids),
        "duplicate_coverage_ids": len(duplicate_ids),
        "evidence_receipts_seen": len(evidence_rows),
        "positive_evidence_receipts": positive_evidence,
        "negative_evidence_receipts": negative_evidence,
        "live_positive_evidence_receipts": live_positive_evidence,
    }

    receipt = {
        "schema": SCHEMA,
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "generated_at": _now_iso(),
        "mocked": False,
        "live": False,
        "fixture_backed": fixture_backed,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _file_sha256(manifest_path) if manifest_path.exists() else None,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "required_coverage_ids": sorted(REQUIRED_COVERAGE_IDS),
        "missing_coverage_ids": missing_ids,
        "unexpected_coverage_ids": unexpected_ids,
        "coverage": coverage_rows,
        "evidence": evidence_rows,
        "counts": counts,
        "errors": errors,
        "claims": {
            "proves": [
                "the current PCTOM-R evidence bundle names concrete receipts for every active goal clause",
                "positive evidence receipts have PASS status and required hashes",
                "negative fixture evidence named in the manifest fails closed with expected BLOCKED status",
            ],
            "does_not_prove": [
                "semantic dream quality",
                "paid provider execution",
                "future receipts not added to the manifest",
                "complete Phase 01-16 media runtime execution",
            ],
        },
        "elapsed_s": round(time.monotonic() - started, 6),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(
        manifest_path=Path(args.manifest),
        output_root=Path(args.output_root),
        receipt_out=Path(args.receipt_out),
        fixture_backed=args.fixture_backed,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
