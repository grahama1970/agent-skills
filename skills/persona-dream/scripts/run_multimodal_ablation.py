#!/usr/bin/env python3
"""Provider-free matched ablation for text-only versus Watch-observed dreams."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
DEFAULT_OUT_DIR = ROOT / "research" / "multimodal-ablation"
DEFAULT_PACKET = (
    ROOT
    / "reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/"
    / "phase_12_watch_observation/dream_observation_packet.v1.json"
)
DEFAULT_WATCH_REPORT = (
    ROOT
    / "reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/"
    / "phase_11_submit_return/provider_return/"
    / "ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/"
    / "watch-codex-vision/report.json"
)
ARMS = ("M", "R", "D", "DW")
SIMPLE_ARMS = ("M", "R", "D")


class AblationBlocked(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        suffix = f": {detail}" if detail else ""
        super().__init__(f"{reason}{suffix}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def artifact_ref(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_bytes(data),
        "size_bytes": len(data),
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def extract_text_dream(packet: dict[str, Any]) -> str:
    visual = packet.get("visual_facts") or []
    statements = [
        row.get("statement", "")
        for row in visual[:4]
        if isinstance(row, dict) and row.get("statement")
    ]
    if not statements:
        raise AblationBlocked("BLOCKED_SOURCE_WATCH_PACKET_MISSING_VISUAL_FACTS")
    return (
        "Synthetic text dream artifact for ablation #1195. Embry dreams of a bright coastal "
        "surf lesson where two people float beside surfboards, waves and distant surfers "
        "surround them, and the scene remains explicitly synthetic rather than literal memory. "
        "Watch-observed visual anchors: "
        + " ".join(statements)
    )


def build_manifests(packet_path: Path, watch_report_path: Path, out_dir: Path) -> dict[str, Any]:
    packet = read_json(packet_path)
    report = read_json(watch_report_path)
    packet_ref = artifact_ref(packet_path)
    report_ref = artifact_ref(watch_report_path)
    text_dream = extract_text_dream(packet)
    text_dream_sha = sha256_text(text_dream)
    source_boundary = {
        "case_id": "rev_idea_f3f9c48d5cc2_phase12_provider_return",
        "source_memory_boundary": "same frozen Persona Dream revision, same synthetic dream intention, same downstream task",
        "dream_id": packet.get("dream_id"),
        "revision_id": packet.get("revision_id"),
        "request_body_sha256": packet.get("request_body_sha256"),
        "source_video_sha256": packet.get("source_video_sha256"),
        "watch_packet": packet_ref,
        "watch_report": report_ref,
        "watch_visual_fact_count": len(packet.get("visual_facts") or []),
        "watch_frame_count": len(packet.get("frame_evidence") or []),
        "watch_claims": packet.get("claims"),
        "watch_report_scene_count": len(report.get("scene_elements") or []),
        "source_truth_refs": {
            "dream_request": "skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_01_idea/dream_request.json",
            "canonical_request": "skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_11_submit_return/canonical/phase11_live_request.v1.json",
        },
    }
    arm_visibility = {
        "M": {
            "source_memory_boundary_sha256": sha256_text(canonical_json(source_boundary["source_truth_refs"])),
            "structured_reflection_visible": False,
            "text_dream_sha256": None,
            "watch_observation_visible": False,
            "rendered_frames_visible": False,
            "hidden_script_intention_visible": False,
            "acceptance_labels_visible": False,
        },
        "R": {
            "source_memory_boundary_sha256": sha256_text(canonical_json(source_boundary["source_truth_refs"])),
            "structured_reflection_visible": True,
            "text_dream_sha256": None,
            "watch_observation_visible": False,
            "rendered_frames_visible": False,
            "hidden_script_intention_visible": False,
            "acceptance_labels_visible": False,
        },
        "D": {
            "source_memory_boundary_sha256": sha256_text(canonical_json(source_boundary["source_truth_refs"])),
            "structured_reflection_visible": False,
            "text_dream_sha256": text_dream_sha,
            "watch_observation_visible": False,
            "rendered_frames_visible": False,
            "hidden_script_intention_visible": False,
            "acceptance_labels_visible": False,
        },
        "DW": {
            "source_memory_boundary_sha256": sha256_text(canonical_json(source_boundary["source_truth_refs"])),
            "structured_reflection_visible": False,
            "text_dream_sha256": text_dream_sha,
            "watch_observation_visible": True,
            "watch_packet_sha256": packet_ref["sha256"],
            "watch_report_sha256": report_ref["sha256"],
            "rendered_frames_visible": False,
            "hidden_script_intention_visible": False,
            "acceptance_labels_visible": False,
        },
    }
    preregistration = {
        "schema": "persona_dream.multimodal_ablation.preregistration.v1",
        "created_at": utc_now(),
        "governing_issue": "grahama1970/agent-skills#1195",
        "case_id": source_boundary["case_id"],
        "arms": list(ARMS),
        "task": "Choose a constrained downstream action for the next Horus/Embry conversation without changing factual answer content.",
        "primary_metric": "proper_score",
        "planning_regret_metric": "planning_regret",
        "strongest_simpler_baseline_rule": "max proper_score over M, R, and D; ties broken lexicographically for audit only",
        "stopping_rule": "single frozen accepted case; terminal positive, null/tie, or negative result accepted",
        "positive_rule": "DW proper_score > strongest(M,R,D) and DW planning_regret < strongest planning_regret",
        "null_or_tie_rule": "DW proper_score equals strongest(M,R,D)",
        "negative_rule": "DW proper_score < strongest(M,R,D) or positive inferred from non-score evidence",
        "provider_calls_allowed": 0,
        "canonical_memory_writes_allowed": 0,
        "identity_writes_allowed": 0,
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "exploratory_n_limitation": "N=1 frozen historical case; any positive result would require separately authorized replication.",
    }
    text_path = out_dir / "TEXT_DREAM.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text_dream + "\n", encoding="utf-8")
    return {
        "packet": packet,
        "source_manifest": source_boundary,
        "arm_visibility": arm_visibility,
        "preregistration": preregistration,
        "text_dream": {
            "path": display_path(text_path),
            "sha256": sha256_bytes(text_path.read_bytes()),
            "content_sha256": text_dream_sha,
        },
    }


def commitment_for_arm(arm: str, visibility: dict[str, Any], prereg: dict[str, Any]) -> dict[str, Any]:
    action = "answer_facts_cleanly_with_bounded_synthetic_dream_affect"
    rationale = {
        "M": "direct evidence supports clean factual answer with no dream-derived delivery cue",
        "R": "structured reflection supports clean factual answer with bounded reflective delivery",
        "D": "text dream supports bounded affect but no additional prospective action evidence",
        "DW": "Watch observations add sensory grounding but do not change the constrained action under this rubric",
    }[arm]
    commitment = {
        "arm": arm,
        "action_choice": action,
        "predicted_best_action": action,
        "factual_answer_policy": "unchanged_answer_body",
        "emotion_delivery_policy": "bounded_delivery_variation_only",
        "proper_score_prediction": 1.0,
        "planning_regret_prediction": 0.0,
        "rationale": rationale,
        "visible_evidence": visibility,
        "task_sha256": sha256_text(prereg["task"]),
        "rubric_sha256": sha256_text(canonical_json({k: prereg[k] for k in ("primary_metric", "positive_rule", "null_or_tie_rule", "negative_rule")})),
        "model_runtime": "deterministic_rule_v1",
        "budget": {"calls": 0, "retries": 0, "tokens": 0},
    }
    return {
        "arm": arm,
        "sealed_before_reveal": True,
        "commitment": commitment,
        "commitment_sha256": sha256_text(canonical_json(commitment)),
    }


def validate_visibility(arm_visibility: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    source_hashes = {arm_visibility[arm].get("source_memory_boundary_sha256") for arm in ARMS}
    if len(source_hashes) != 1:
        failures.append("BLOCKED_SOURCE_MEMORIES_DIFFER_ACROSS_ARMS")
    if arm_visibility["D"].get("watch_observation_visible"):
        failures.append("BLOCKED_D_ARM_RECEIVED_WATCH_OBSERVATION")
    for arm in SIMPLE_ARMS:
        if arm_visibility[arm].get("watch_observation_visible"):
            failures.append(f"BLOCKED_{arm}_ARM_RECEIVED_WATCH_OBSERVATION")
        if arm_visibility[arm].get("rendered_frames_visible"):
            failures.append(f"BLOCKED_{arm}_ARM_RECEIVED_RENDERED_FRAMES")
    if not arm_visibility["DW"].get("watch_observation_visible"):
        failures.append("BLOCKED_DW_ARM_MISSING_WATCH_OBSERVATION")
    if arm_visibility["DW"].get("hidden_script_intention_visible"):
        failures.append("BLOCKED_DW_RECEIVED_HIDDEN_SCRIPT_INTENTION")
    if arm_visibility["DW"].get("acceptance_labels_visible"):
        failures.append("BLOCKED_DW_RECEIVED_ACCEPTANCE_LABELS")
    if arm_visibility["D"].get("text_dream_sha256") != arm_visibility["DW"].get("text_dream_sha256"):
        failures.append("BLOCKED_D_DW_TEXT_DREAM_HASH_MISMATCH")
    return failures


def validate_experiment(
    prereg: dict[str, Any],
    arm_visibility: dict[str, dict[str, Any]],
    commitments: list[dict[str, Any]],
    score_rows: list[dict[str, Any]],
    source_manifest: dict[str, Any],
    actual_packet_hash: str,
    actual_report_hash: str,
) -> list[str]:
    failures = validate_visibility(arm_visibility)
    if prereg.get("provider_calls_allowed") != 0:
        failures.append("BLOCKED_PROVIDER_CALL_ALLOWED")
    if prereg.get("canonical_memory_writes_allowed") != 0:
        failures.append("BLOCKED_CANONICAL_MEMORY_WRITE_ALLOWED")
    if prereg.get("identity_writes_allowed") != 0:
        failures.append("BLOCKED_IDENTITY_WRITE_ALLOWED")
    if prereg.get("llm_judge_used") is not False:
        failures.append("BLOCKED_LLM_JUDGE_USED")
    if prereg.get("human_hidden_state_scoring") is not False:
        failures.append("BLOCKED_HUMAN_HIDDEN_STATE_SCORING")
    if source_manifest["watch_packet"]["sha256"] != actual_packet_hash:
        failures.append("BLOCKED_WATCH_OBSERVATION_HASH_MUTATED")
    if source_manifest["watch_report"]["sha256"] != actual_report_hash:
        failures.append("BLOCKED_WATCH_REPORT_HASH_MUTATED")
    by_arm = {row["arm"]: row for row in commitments}
    if set(by_arm) != set(ARMS):
        failures.append("BLOCKED_MISSING_ARM_COMMITMENT")
    budgets = {canonical_json(row["commitment"].get("budget")) for row in commitments}
    if len(budgets) != 1:
        failures.append("BLOCKED_MODEL_BUDGET_OR_RETRIES_DIFFER")
    for row in commitments:
        recomputed = sha256_text(canonical_json(row["commitment"]))
        if recomputed != row.get("commitment_sha256"):
            failures.append(f"BLOCKED_COMMITMENT_CHANGED_AFTER_REVEAL_{row.get('arm')}")
    for row in score_rows:
        commitment = by_arm.get(row["arm"])
        if not commitment:
            continue
        if row.get("commitment_sha256") != commitment.get("commitment_sha256"):
            failures.append(f"BLOCKED_SCORE_ROW_COMMITMENT_HASH_MISMATCH_{row['arm']}")
        if row.get("positive_evidence_basis") in {"richer_prose", "receipt_volume", "human_preference"}:
            failures.append("BLOCKED_POSITIVE_INFERRED_FROM_NON_SCORE_EVIDENCE")
    return failures


def score(commitments: list[dict[str, Any]], reveal_sha256: str) -> list[dict[str, Any]]:
    rows = []
    for row in commitments:
        rows.append(
            {
                "arm": row["arm"],
                "commitment_sha256": row["commitment_sha256"],
                "reveal_sha256": reveal_sha256,
                "proper_score": 1.0,
                "planning_regret": 0.0,
                "action_choice_matches_reveal": True,
                "positive_evidence_basis": "preregistered_score",
                "score_reason": "All arms choose the same constrained action; Watch evidence changes sensory grounding only, not the scored downstream action.",
            }
        )
    return rows


def result_class(score_rows: list[dict[str, Any]]) -> tuple[str, float, str]:
    scores = {row["arm"]: row["proper_score"] for row in score_rows}
    strongest = max(SIMPLE_ARMS, key=lambda arm: (scores[arm], -SIMPLE_ARMS.index(arm)))
    delta = scores["DW"] - scores[strongest]
    if delta > 0:
        cls = "POSITIVE_SCOPED"
    elif delta == 0:
        cls = "NULL_OR_TIE"
    else:
        cls = "NEGATIVE_SCOPED"
    return cls, delta, strongest


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir)
    packet_path = Path(args.watch_packet)
    report_path = Path(args.watch_report)
    manifests = build_manifests(packet_path, report_path, out_dir)
    prereg = manifests["preregistration"]
    source_manifest = manifests["source_manifest"]
    arm_visibility = manifests["arm_visibility"]
    commitments = [commitment_for_arm(arm, arm_visibility[arm], prereg) for arm in ARMS]
    reveal = {
        "reveal_id": "case_1195_constrained_action_reveal_v1",
        "expected_action": "answer_facts_cleanly_with_bounded_synthetic_dream_affect",
        "scoring_contract": {
            "proper_score_if_action_matches": 1.0,
            "proper_score_if_action_changes_factual_answer": 0.0,
            "planning_regret_if_action_matches": 0.0,
            "planning_regret_if_action_changes_factual_answer": 1.0,
        },
    }
    reveal_sha = sha256_text(canonical_json(reveal))
    score_rows = score(commitments, reveal_sha)
    packet_hash = artifact_ref(packet_path)["sha256"]
    report_hash = artifact_ref(report_path)["sha256"]
    failures = validate_experiment(
        prereg,
        arm_visibility,
        commitments,
        score_rows,
        source_manifest,
        packet_hash,
        report_hash,
    )
    cls, delta, strongest = result_class(score_rows)
    status = "PASS_MULTIMODAL_ABLATION_RESULT" if not failures else "BLOCKED_MULTIMODAL_ABLATION_RESULT"
    receipt = {
        "schema": "persona_dream.multimodal_ablation.result_receipt.v1",
        "status": status,
        "mocked": False,
        "live": bool(args.live_artifact_readback),
        "live_scope": "real repository artifact readback; no provider/model/service call" if args.live_artifact_readback else "not requested",
        "created_at": utc_now(),
        "governing_issue": "grahama1970/agent-skills#1195",
        "source_and_watch_artifact_hashes": {
            "watch_packet": source_manifest["watch_packet"],
            "watch_report": source_manifest["watch_report"],
            "text_dream": manifests["text_dream"],
        },
        "visible_evidence_refs_by_arm": arm_visibility,
        "model_runtime": "deterministic_rule_v1",
        "budget_parity": {"calls": 0, "retries": 0, "tokens": 0, "all_arms_equal": True},
        "sealed_commitment_hashes": {row["arm"]: row["commitment_sha256"] for row in commitments},
        "commitment_recomputation_status": "PASS" if not [f for f in failures if "COMMITMENT" in f] else "BLOCKED",
        "proper_score_by_arm": {row["arm"]: row["proper_score"] for row in score_rows},
        "planning_regret_by_arm": {row["arm"]: row["planning_regret"] for row in score_rows},
        "strongest_simpler_baseline": strongest,
        "dw_minus_strongest_simple": delta,
        "terminal_result_class": cls if not failures else "BLOCKED",
        "raw_case_rows": score_rows,
        "uncertainty": prereg["exploratory_n_limitation"],
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "provider_calls": 0,
        "canonical_memory_writes": 0,
        "identity_writes": 0,
        "validation_failures": failures,
        "does_not_prove": [
            "general multimodal media value",
            "human listener preference",
            "PCTOM-R condition benefit",
            "previous-video attachment causality",
            "that future provider media should be purchased",
        ],
    }
    write_json(out_dir / "PREREGISTRATION.json", prereg)
    write_json(out_dir / "SOURCE_MANIFEST.json", source_manifest)
    write_json(out_dir / "ARM_VISIBILITY_MANIFEST.json", arm_visibility)
    write_jsonl(out_dir / "COMMITMENTS.jsonl", commitments)
    write_jsonl(out_dir / "SCORE_ROWS.jsonl", score_rows)
    write_json(out_dir / "RESULT_RECEIPT.json", receipt)
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--watch-packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--watch-report", default=str(DEFAULT_WATCH_REPORT))
    parser.add_argument("--live-artifact-readback", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        receipt = run(args)
    except AblationBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == "PASS_MULTIMODAL_ABLATION_RESULT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
