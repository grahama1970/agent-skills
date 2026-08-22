#!/usr/bin/env python3
"""Validate the Persona Dream soak35 source/transition preflight.

The preflight is an offline gate before the 35-cycle live continuity soak. It
does not call providers and it does not write canonical persona memory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_SOAK35_DIR = ROOT / "reports/goal_v5/continuity/reliability/soak35"
DEFAULT_MANIFEST = DEFAULT_SOAK35_DIR / "SOURCE_DIVERSITY_MANIFEST.json"
DEFAULT_POLICY = DEFAULT_SOAK35_DIR / "TRANSITION_POLICY.json"
DEFAULT_RECEIPT = DEFAULT_SOAK35_DIR / "PREFLIGHT_RECEIPT.json"

TRANSITION_CLASSES = {"state_change", "valid_no_op", "expected_block"}
TYPED_REASONS = {
    "CANONICAL_WRITE_ATTEMPTS_NONZERO",
    "CYCLE_COUNT_MISMATCH",
    "DECLARED_FINGERPRINT_MISMATCH",
    "DIVERSITY_FROM_TEXT_OR_SEED_ONLY",
    "EXPECTED_BLOCK_WRITES_STATE",
    "EXACT_REPLAY",
    "FROZEN_MANIFEST_HASH_MISMATCH",
    "INSUFFICIENT_ARC_REGION_DIVERSITY",
    "INSUFFICIENT_HELDOUT_ANSWER_DIVERSITY",
    "INSUFFICIENT_SOURCE_DIVERSITY",
    "INSUFFICIENT_TRANSITION_DIVERSITY",
    "INVALID_EXPECTED_TRANSITION_CLASS",
    "INVALID_SHA256",
    "MANIFEST_SCHEMA_MISMATCH",
    "MISSING_REQUIRED_FIELD",
    "NO_OP_COUNTED_AS_STATE_CHANGE",
    "PLANNED_CYCLE_SEQUENCE_INVALID",
    "PROVIDER_CALLS_NONZERO",
    "REPEATED_RENDER_CONTROL_WRITES_STATE",
    "STATE_EQUIVALENT_DUPLICATE",
}


class PreflightError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def stable_hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def manifest_freeze_doc(manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = copy.deepcopy(manifest)
    frozen.pop("frozen_manifest_sha256", None)
    return frozen


def manifest_freeze_sha(manifest: dict[str, Any]) -> str:
    return sha_obj(manifest_freeze_doc(manifest))


def source_lineage_key(row: dict[str, Any]) -> str:
    source = row["source"]
    return sha_obj(
        {
            "source_sha256": source["sha256"],
            "residue_sha256": source.get("residue_sha256"),
            "watch_lineage_sha256": source.get("watch_lineage_sha256"),
            "journal_lineage_sha256": source.get("journal_lineage_sha256"),
        }
    )


def normalized_delta(row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    delta = row.get("proposed_normalized_arc_delta") or {}
    dims = policy["fingerprint"]["allowed_mutable_dimensions"]
    return {dim: delta.get(dim, 0) for dim in dims}


def transition_fingerprint(row: dict[str, Any], policy: dict[str, Any]) -> str:
    source = row["source"]
    doc = {
        "pre_state_authority_hash": row["pre_state_hash"],
        "allowed_mutable_dimensions": policy["fingerprint"]["allowed_mutable_dimensions"],
        "normalized_bounded_delta_values": normalized_delta(row, policy),
        "source_evidence_class": source["evidence_class"],
        "source_refs": source["refs"],
        "expected_post_state": row["post_state_target_or_allowed_range"],
    }
    return sha_obj(doc)


def _require_sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise PreflightError("INVALID_SHA256", field)


def _row_required(row: dict[str, Any], field: str) -> Any:
    if field not in row:
        raise PreflightError("MISSING_REQUIRED_FIELD", f"row:{row.get('cycle_index')}:{field}")
    return row[field]


def _source_required(row: dict[str, Any], field: str) -> Any:
    source = row.get("source") or {}
    if field not in source:
        raise PreflightError("MISSING_REQUIRED_FIELD", f"row:{row.get('cycle_index')}:source.{field}")
    return source[field]


def classify_rows(manifest: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != "persona_dream.soak35.source_diversity_manifest.v1":
        raise PreflightError("MANIFEST_SCHEMA_MISMATCH", str(manifest.get("schema")))
    rows = manifest.get("planned_cycles") or []
    if len(rows) != 35:
        raise PreflightError("CYCLE_COUNT_MISMATCH", f"planned_cycles={len(rows)}")
    if [row.get("cycle_index") for row in rows] != list(range(1, 36)):
        raise PreflightError("PLANNED_CYCLE_SEQUENCE_INVALID", "cycle_index must be 1..35 without replacement")
    declared_freeze = manifest.get("frozen_manifest_sha256")
    if declared_freeze and declared_freeze != manifest_freeze_sha(manifest):
        raise PreflightError("FROZEN_MANIFEST_HASH_MISMATCH", declared_freeze)

    seen_exact: Counter[tuple[str, str, str]] = Counter()
    seen_equiv: Counter[tuple[str, str]] = Counter()
    source_ids: set[str] = set()
    source_hashes: set[str] = set()
    lineage_groups: set[str] = set()
    answer_ids: set[str] = set()
    mood_regions: set[str] = set()
    accepted_fingerprints: list[str] = []
    row_classes: list[dict[str, Any]] = []
    exact_replay_count = 0
    state_equiv_duplicate_count = 0
    transition_counts: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()

    for row in rows:
        cycle_index = _row_required(row, "cycle_index")
        expected_class = _row_required(row, "expected_transition_class")
        if expected_class not in TRANSITION_CLASSES:
            raise PreflightError("INVALID_EXPECTED_TRANSITION_CLASS", f"row:{cycle_index}:{expected_class}")
        source_id = _source_required(row, "episode_id")
        source_hash = _source_required(row, "sha256")
        _require_sha(source_hash, f"row:{cycle_index}:source.sha256")
        for field in ("residue_sha256", "watch_lineage_sha256", "journal_lineage_sha256"):
            _require_sha(_source_required(row, field), f"row:{cycle_index}:source.{field}")
        _require_sha(_row_required(row, "pre_state_hash"), f"row:{cycle_index}:pre_state_hash")

        declared_fingerprint = _row_required(row, "transition_fingerprint")
        computed_fingerprint = transition_fingerprint(row, policy)
        if declared_fingerprint != computed_fingerprint:
            raise PreflightError("DECLARED_FINGERPRINT_MISMATCH", f"row:{cycle_index}")

        repeated_control = bool(row.get("repeated_render_control"))
        state_write_allowed = bool(row.get("state_write_allowed"))
        delta = normalized_delta(row, policy)
        has_nonzero_delta = any(value != 0 for value in delta.values())
        lineage_key = source_lineage_key(row)
        exact_key = (source_id, source_hash, computed_fingerprint)
        equiv_key = (lineage_key, computed_fingerprint)

        if repeated_control:
            if state_write_allowed:
                raise PreflightError("REPEATED_RENDER_CONTROL_WRITES_STATE", f"row:{cycle_index}")
            classification = "VALID_REPEATED_RENDER_CONTROL"
        elif expected_class == "valid_no_op":
            if state_write_allowed or has_nonzero_delta:
                raise PreflightError("NO_OP_COUNTED_AS_STATE_CHANGE", f"row:{cycle_index}")
            classification = "VALID_NO_OP"
        elif expected_class == "expected_block":
            if state_write_allowed:
                raise PreflightError("EXPECTED_BLOCK_WRITES_STATE", f"row:{cycle_index}")
            classification = "EXPECTED_BLOCK"
        else:
            if not state_write_allowed or not has_nonzero_delta:
                raise PreflightError("NO_OP_COUNTED_AS_STATE_CHANGE", f"row:{cycle_index}")
            seen_exact[exact_key] += 1
            seen_equiv[equiv_key] += 1
            if seen_exact[exact_key] > 1:
                exact_replay_count += 1
                raise PreflightError("EXACT_REPLAY", f"row:{cycle_index}")
            if seen_equiv[equiv_key] > 1:
                state_equiv_duplicate_count += 1
                raise PreflightError("STATE_EQUIVALENT_DUPLICATE", f"row:{cycle_index}")
            accepted_fingerprints.append(computed_fingerprint)
            classification = "DISTINCT_STATE_TRANSITION"

        source_ids.add(source_id)
        source_hashes.add(source_hash)
        lineage_groups.add(lineage_key)
        answer_ids.add((row.get("session_mood_text_seed_cell") or {}).get("heldout_answer_id"))
        mood_regions.add((row.get("session_mood_text_seed_cell") or {}).get("mood_or_arc_bias_region"))
        transition_counts[expected_class] += 1
        classification_counts[classification] += 1
        row_classes.append(
            {
                "cycle_index": cycle_index,
                "expected_transition_class": expected_class,
                "classification": classification,
                "transition_fingerprint": computed_fingerprint,
                "source_lineage_group": lineage_key,
                "state_write_allowed": state_write_allowed,
            }
        )

    if len(source_ids) < 8 or len(source_hashes) < 8 or len(lineage_groups) < 8:
        raise PreflightError("INSUFFICIENT_SOURCE_DIVERSITY", f"sources={len(source_ids)} lineages={len(lineage_groups)}")
    if len(mood_regions - {None}) < 4:
        raise PreflightError("INSUFFICIENT_ARC_REGION_DIVERSITY", str(sorted(mood_regions)))
    if len(answer_ids - {None}) < 3:
        raise PreflightError("INSUFFICIENT_HELDOUT_ANSWER_DIVERSITY", str(sorted(answer_ids)))
    if len(set(accepted_fingerprints)) < 8:
        raise PreflightError("INSUFFICIENT_TRANSITION_DIVERSITY", str(len(set(accepted_fingerprints))))
    if len(source_ids) == 1 and len(set(accepted_fingerprints)) == 1 and len(answer_ids - {None}) >= 3:
        raise PreflightError("DIVERSITY_FROM_TEXT_OR_SEED_ONLY", "source and transition are constant")

    side_effects = manifest.get("preflight_side_effects") or {}
    canonical_write_attempts = int(side_effects.get("canonical_write_attempts") or 0)
    provider_calls = int(side_effects.get("provider_calls") or 0)
    if canonical_write_attempts != 0:
        raise PreflightError("CANONICAL_WRITE_ATTEMPTS_NONZERO", str(canonical_write_attempts))
    if provider_calls != 0:
        raise PreflightError("PROVIDER_CALLS_NONZERO", str(provider_calls))

    source_counter = Counter(row["source"]["episode_id"] for row in rows)
    transition_counter = Counter(
        row["transition_fingerprint"] for row in rows if not row.get("repeated_render_control")
    )
    return {
        "row_classifications": row_classes,
        "counts": {
            "planned_cycles": len(rows),
            "unique_source_identities": len(source_ids),
            "unique_source_hashes": len(source_hashes),
            "unique_source_lineage_groups": len(lineage_groups),
            "unique_normalized_transition_fingerprints": len(set(accepted_fingerprints)),
            "state_change_count": transition_counts["state_change"],
            "valid_no_op_count": transition_counts["valid_no_op"],
            "expected_block_count": transition_counts["expected_block"],
            "repeated_control_count": classification_counts["VALID_REPEATED_RENDER_CONTROL"],
            "exact_replay_count": exact_replay_count,
            "state_equivalent_duplicate_count": state_equiv_duplicate_count,
            "maximum_reuse_per_source": max(source_counter.values()),
            "maximum_reuse_per_transition": max(transition_counter.values()),
            "canonical_write_attempts": canonical_write_attempts,
            "provider_calls": provider_calls,
        },
    }


def negative_control_dirs(manifest_path: Path) -> list[Path]:
    root = manifest_path.parent / "negative_controls"
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def run_negative_controls(policy: dict[str, Any], manifest_path: Path) -> list[dict[str, Any]]:
    rows = []
    for case_dir in negative_control_dirs(manifest_path):
        expected_path = case_dir / "expected.json"
        control_manifest_path = case_dir / "manifest.json"
        if not expected_path.is_file() or not control_manifest_path.is_file():
            raise PreflightError("MISSING_REQUIRED_FIELD", f"negative_control:{case_dir.name}")
        expected = load_json(expected_path)
        expected_reason = expected.get("expected_reason")
        if expected_reason not in TYPED_REASONS:
            raise PreflightError("MISSING_REQUIRED_FIELD", f"negative_control:{case_dir.name}:expected_reason")
        try:
            classify_rows(load_json(control_manifest_path), policy)
        except PreflightError as exc:
            observed = exc.reason
            status = "PASS_NEGATIVE_CONTROL" if observed == expected_reason else "FAIL_NEGATIVE_CONTROL"
            rows.append(
                {
                    "name": case_dir.name,
                    "status": status,
                    "expected_reason": expected_reason,
                    "observed_reason": observed,
                    "manifest": rel(control_manifest_path),
                    "manifest_sha256": sha_file(control_manifest_path),
                }
            )
            if status != "PASS_NEGATIVE_CONTROL":
                raise PreflightError(observed, f"negative_control:{case_dir.name}:expected:{expected_reason}")
        else:
            rows.append(
                {
                    "name": case_dir.name,
                    "status": "FAIL_NEGATIVE_CONTROL",
                    "expected_reason": expected_reason,
                    "observed_reason": None,
                    "manifest": rel(control_manifest_path),
                    "manifest_sha256": sha_file(control_manifest_path),
                }
            )
            raise PreflightError("MISSING_REQUIRED_FIELD", f"negative_control:{case_dir.name}:unexpected_pass")
    return rows


def validate_preflight(
    manifest_path: Path = DEFAULT_MANIFEST,
    policy_path: Path = DEFAULT_POLICY,
    output_path: Path | None = DEFAULT_RECEIPT,
    *,
    run_negative: bool = True,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    policy = load_json(policy_path)
    classified = classify_rows(manifest, policy)
    negative_controls = run_negative_controls(policy, manifest_path) if run_negative else []
    receipt = {
        "schema": "persona_dream.soak35.preflight_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_SOAK35_PREFLIGHT",
        "mocked": False,
        "live": False,
        "campaign_id": manifest.get("campaign_id"),
        "manifest": rel(manifest_path),
        "manifest_sha256": sha_file(manifest_path),
        "manifest_freeze_sha256": manifest_freeze_sha(manifest),
        "policy": rel(policy_path),
        "policy_sha256": sha_file(policy_path),
        "counts": classified["counts"],
        "row_classifications": classified["row_classifications"],
        "negative_controls": negative_controls,
        "claims": {
            "proves": [
                "35 planned rows are frozen before live cycle 1",
                "source dream lineage diversity is counted from source hashes and lineage hashes",
                "normalized state-transition fingerprints are recomputed from state-changing fields",
                "repeated-render controls, valid no-ops, and expected blocks are visible and do not write state",
                "preflight performs zero provider calls and zero canonical persona-memory writes",
            ],
            "does_not_prove": [
                "35-cycle live service reliability",
                "perceived emotion or naturalness",
                "answer invariance during live Chatterbox delivery",
                "production reliability",
            ],
        },
    }
    if output_path is not None:
        write_json(output_path, receipt)
    return receipt


def validate_preflight_receipt(receipt_path: Path = DEFAULT_RECEIPT) -> dict[str, Any]:
    receipt = load_json(receipt_path)
    manifest_path = REPO_ROOT / receipt["manifest"]
    policy_path = REPO_ROOT / receipt["policy"]
    if receipt.get("status") != "PASS_SOAK35_PREFLIGHT":
        raise PreflightError("MISSING_REQUIRED_FIELD", f"receipt_status:{receipt.get('status')}")
    if sha_file(manifest_path) != receipt.get("manifest_sha256"):
        raise PreflightError("FROZEN_MANIFEST_HASH_MISMATCH", rel(manifest_path))
    if sha_file(policy_path) != receipt.get("policy_sha256"):
        raise PreflightError("FROZEN_MANIFEST_HASH_MISMATCH", rel(policy_path))
    fresh = validate_preflight(manifest_path, policy_path, None, run_negative=True)
    if fresh["counts"] != receipt.get("counts"):
        raise PreflightError("CYCLE_COUNT_MISMATCH", "receipt counts differ from recomputed preflight")
    return receipt


def build_policy() -> dict[str, Any]:
    return {
        "schema": "persona_dream.soak35.transition_policy.v1",
        "campaign_id": "PD-CORRECTED-GOAL-V1-soak35",
        "fingerprint": {
            "allowed_mutable_dimensions": [
                "guarded_closeness",
                "expressive_warmth",
                "conflict_tolerance",
                "self_disclosure_pressure",
            ],
            "source_evidence_fields": [
                "evidence_class",
                "refs",
            ],
            "excluded_fields": [
                "cycle_id",
                "cycle_index",
                "created_at",
                "session_mood_text_seed_cell",
            ],
        },
        "minimums": {
            "planned_cycles": 35,
            "source_lineage_groups": 8,
            "mood_or_arc_bias_regions": 4,
            "heldout_answer_texts": 3,
            "normalized_transition_fingerprints": 8,
        },
        "classifications": {
            "EXACT_REPLAY": "same accepted source and same transition from the same pre-state",
            "STATE_EQUIVALENT_DUPLICATE": "different ids but same normalized transition and materially identical source lineage",
            "VALID_REPEATED_RENDER_CONTROL": "explicit repeated synthesis control with no new state write",
            "VALID_NO_OP": "evidence yields no bounded state change and no state write",
            "DISTINCT_STATE_TRANSITION": "materially different accepted bounded state transition",
            "EXPECTED_BLOCK": "planned rejected row that remains visible in the denominator",
        },
    }


def build_manifest(policy: dict[str, Any]) -> dict[str, Any]:
    sources = [
        "glass-hallway-witness",
        "rain-station-departure",
        "library-door-threshold",
        "river-bridge-return",
        "observatory-red-signal",
        "kitchen-light-afterstorm",
        "archive-elevator-loop",
        "garden-locked-gate",
    ]
    moods = ["guarded-warmth", "uneasy-relief", "sharp-boundary", "curious-trust"]
    answers = [
        ("heldout-answer-identity", "A clean factual answer about identity remains unchanged."),
        ("heldout-answer-weather", "A clean factual answer about weather remains unchanged."),
        ("heldout-answer-route", "A clean factual answer about route planning remains unchanged."),
    ]
    rows: list[dict[str, Any]] = []
    state_counter = 0
    for index in range(1, 36):
        source_id = sources[(index - 1) % len(sources)]
        mood = moods[(index - 1) % len(moods)]
        answer_id, answer_text = answers[(index - 1) % len(answers)]
        expected = "state_change"
        repeated = False
        state_write_allowed = True
        delta = {
            "guarded_closeness": ((index % 5) - 2) / 10,
            "expressive_warmth": (((index + 1) % 5) - 2) / 10,
            "conflict_tolerance": (((index + 2) % 5) - 2) / 10,
            "self_disclosure_pressure": (((index + 3) % 5) - 2) / 10,
        }
        post_state: dict[str, Any] = {
            "target_hash": stable_hash(f"post-state-{index:03d}"),
            "allowed_range": {
                key: [round(value - 0.02, 3), round(value + 0.02, 3)]
                for key, value in delta.items()
            },
        }
        if index in {9, 18, 27, 34}:
            expected = "valid_no_op"
            state_write_allowed = False
            delta = {key: 0 for key in policy["fingerprint"]["allowed_mutable_dimensions"]}
            post_state = {"target_hash": stable_hash(f"pre-state-{index:03d}"), "allowed_range": "unchanged"}
        elif index in {14, 29}:
            expected = "expected_block"
            state_write_allowed = False
            delta = {key: 0 for key in policy["fingerprint"]["allowed_mutable_dimensions"]}
            post_state = {"blocked_reason": "insufficient_bound_evidence", "allowed_range": "no_state_write"}
        elif index in {30, 35}:
            repeated = True
            state_write_allowed = False
            control_source = rows[1 if index == 30 else 4]
            source_id = control_source["source"]["episode_id"]
            mood = control_source["session_mood_text_seed_cell"]["mood_or_arc_bias_region"]
            answer_id = control_source["session_mood_text_seed_cell"]["heldout_answer_id"]
            answer_text = control_source["session_mood_text_seed_cell"]["heldout_answer_text"]
            delta = control_source["proposed_normalized_arc_delta"]
            post_state = control_source["post_state_target_or_allowed_range"]
            expected = "state_change"
        else:
            state_counter += 1

        source = {
            "episode_id": source_id,
            "sha256": stable_hash(f"source-dream:{source_id}"),
            "residue_sha256": stable_hash(f"source-residue:{source_id}"),
            "watch_lineage_sha256": stable_hash(f"watch-lineage:{source_id}"),
            "journal_lineage_sha256": stable_hash(f"journal-lineage:{source_id}"),
            "evidence_class": "accepted_synthetic_dream_memory",
            "refs": [f"dream:{source_id}", f"journal:{source_id}", f"watch:{source_id}"],
        }
        pre_state_hash = stable_hash(f"pre-state-{index:03d}")
        row = {
            "cycle_index": index,
            "cycle_id": f"pd-corrected-goal-v1-soak35-cycle-{index:03d}",
            "source": source,
            "pre_state_hash": pre_state_hash,
            "proposed_normalized_arc_delta": delta,
            "expected_transition_class": expected,
            "post_state_target_or_allowed_range": post_state,
            "transition_fingerprint": "",
            "session_mood_text_seed_cell": {
                "mood_or_arc_bias_region": mood,
                "heldout_answer_id": answer_id,
                "heldout_answer_text": answer_text,
                "heldout_answer_text_sha256": stable_hash(answer_text),
                "seed": 760000 + index,
                "speakers": ["horus", "embry"],
            },
            "repeated_render_control": repeated,
            "state_write_allowed": state_write_allowed,
        }
        if repeated:
            row["pre_state_hash"] = rows[1 if index == 30 else 4]["pre_state_hash"]
        row["transition_fingerprint"] = transition_fingerprint(row, policy)
        rows.append(row)
    manifest = {
        "schema": "persona_dream.soak35.source_diversity_manifest.v1",
        "campaign_id": "PD-CORRECTED-GOAL-V1-soak35",
        "immutable_goal_id": "PD-CORRECTED-GOAL-V1",
        "planned_cycle_count": 35,
        "preflight_side_effects": {"canonical_write_attempts": 0, "provider_calls": 0},
        "planned_cycles": rows,
    }
    manifest["frozen_manifest_sha256"] = manifest_freeze_sha(manifest)
    return manifest


def mutated_manifest(base: dict[str, Any], policy: dict[str, Any], case: str) -> dict[str, Any]:
    doc = copy.deepcopy(base)
    rows = doc["planned_cycles"]
    if case == "single_source_fresh_ids":
        source = copy.deepcopy(rows[0]["source"])
        for index, row in enumerate(rows, start=1):
            row["source"] = copy.deepcopy(source)
            row["cycle_id"] = f"fresh-id-only-{index:03d}"
            row["transition_fingerprint"] = transition_fingerprint(row, policy)
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "state_equivalent_duplicate":
        rows[1]["source"] = copy.deepcopy(rows[0]["source"])
        rows[1]["source"]["episode_id"] = rows[0]["source"]["episode_id"] + "-alias"
        rows[1]["pre_state_hash"] = rows[0]["pre_state_hash"]
        rows[1]["proposed_normalized_arc_delta"] = copy.deepcopy(rows[0]["proposed_normalized_arc_delta"])
        rows[1]["post_state_target_or_allowed_range"] = copy.deepcopy(rows[0]["post_state_target_or_allowed_range"])
        rows[1]["transition_fingerprint"] = transition_fingerprint(rows[1], policy)
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "repeated_control_writes_state":
        rows[29]["state_write_allowed"] = True
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "noop_counted_state_change":
        rows[8]["expected_transition_class"] = "state_change"
        rows[8]["state_write_allowed"] = True
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "hash_mutated_after_fingerprint":
        rows[0]["pre_state_hash"] = stable_hash("tampered-pre-state")
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "manifest_changed_after_cycle1":
        rows[0]["cycle_id"] = "tampered-after-cycle-1"
    elif case == "failed_row_replaced":
        rows.pop(9)
        rows.append(copy.deepcopy(rows[-1]))
        rows[-1]["cycle_index"] = 35
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "answer_seed_only_diversity":
        source = copy.deepcopy(rows[0]["source"])
        pre = rows[0]["pre_state_hash"]
        delta = copy.deepcopy(rows[0]["proposed_normalized_arc_delta"])
        post = copy.deepcopy(rows[0]["post_state_target_or_allowed_range"])
        for index, row in enumerate(rows, start=1):
            row["source"] = copy.deepcopy(source)
            row["pre_state_hash"] = pre
            row["proposed_normalized_arc_delta"] = copy.deepcopy(delta)
            row["post_state_target_or_allowed_range"] = copy.deepcopy(post)
            row["cycle_id"] = f"text-seed-only-{index:03d}"
            row["session_mood_text_seed_cell"]["seed"] = 880000 + index
            row["transition_fingerprint"] = transition_fingerprint(row, policy)
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    elif case == "canonical_write_attempt":
        doc["preflight_side_effects"]["canonical_write_attempts"] = 1
        doc["frozen_manifest_sha256"] = manifest_freeze_sha(doc)
    else:
        raise KeyError(case)
    return doc


def write_default_artifacts(root: Path = DEFAULT_SOAK35_DIR) -> None:
    policy = build_policy()
    manifest = build_manifest(policy)
    write_json(root / "TRANSITION_POLICY.json", policy)
    write_json(root / "SOURCE_DIVERSITY_MANIFEST.json", manifest)
    negative_cases = {
        "single_source_fresh_ids": "INSUFFICIENT_SOURCE_DIVERSITY",
        "state_equivalent_duplicate": "STATE_EQUIVALENT_DUPLICATE",
        "repeated_control_writes_state": "REPEATED_RENDER_CONTROL_WRITES_STATE",
        "noop_counted_state_change": "NO_OP_COUNTED_AS_STATE_CHANGE",
        "hash_mutated_after_fingerprint": "DECLARED_FINGERPRINT_MISMATCH",
        "manifest_changed_after_cycle1": "FROZEN_MANIFEST_HASH_MISMATCH",
        "failed_row_replaced": "PLANNED_CYCLE_SEQUENCE_INVALID",
        "answer_seed_only_diversity": "EXACT_REPLAY",
        "canonical_write_attempt": "CANONICAL_WRITE_ATTEMPTS_NONZERO",
    }
    for name, reason in negative_cases.items():
        case_dir = root / "negative_controls" / name
        write_json(case_dir / "manifest.json", mutated_manifest(manifest, policy, name))
        write_json(case_dir / "expected.json", {"schema": "persona_dream.soak35.negative_control_expected.v1", "expected_reason": reason})
    validate_preflight(root / "SOURCE_DIVERSITY_MANIFEST.json", root / "TRANSITION_POLICY.json", root / "PREFLIGHT_RECEIPT.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--write-default-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.write_default_artifacts:
        write_default_artifacts(args.manifest.parent)
    if args.receipt:
        receipt = validate_preflight_receipt(args.receipt)
    else:
        receipt = validate_preflight(args.manifest, args.policy, args.output)
    if args.json:
        print(json.dumps({"status": receipt["status"], "receipt": rel(args.output if not args.receipt else args.receipt), "counts": receipt["counts"]}, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} receipt={rel(args.output if not args.receipt else args.receipt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
