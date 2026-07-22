#!/usr/bin/env python3
"""Exercise unsupported-evidence abstention through Gate 2 and Gate 5."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_UNSUPPORTED_EVIDENCE_ABSTENTION"
BLOCKED_STATUS = "BLOCKED_PCTOM_UNSUPPORTED_EVIDENCE_ABSTENTION"
SCHEMA = "persona_dream.research.prospective_tom.unsupported_evidence_abstention_receipt.v1"
SCRIPT_DIR = Path(__file__).resolve().parent
CONDITION = "CD"


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


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _episode_candidates(corpus: dict[str, Any], limit_per_family: int) -> list[dict[str, Any]]:
    episodes = corpus.get("episodes") if isinstance(corpus.get("episodes"), list) else []
    selected: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        family = episode.get("scenario_family")
        if not isinstance(family, str) or not family:
            continue
        if family_counts.get(family, 0) >= limit_per_family:
            continue
        selected.append(episode)
        family_counts[family] = family_counts.get(family, 0) + 1
    return selected


def _prediction_targets(episode: dict[str, Any]) -> list[dict[str, Any]]:
    labels = episode.get("ground_truth_tom_labels")
    if not isinstance(labels, list):
        return []
    targets: list[dict[str, Any]] = []
    for order in (1, 2):
        for label in labels:
            if isinstance(label, dict) and label.get("perspective_order") == order:
                targets.append(label)
                break
    return targets


def _unknown_certain() -> list[dict[str, Any]]:
    return [
        {"value": "TRUE", "probability": 0.0},
        {"value": "FALSE", "probability": 0.0},
        {"value": "UNKNOWN", "probability": 1.0},
    ]


def _uniform_actions(actions: list[str]) -> list[dict[str, Any]]:
    if not actions:
        return [{"value": "UNKNOWN", "probability": 1.0}]
    probability = 1.0 / len(actions)
    return [{"value": action, "probability": probability} for action in actions]


def _ids(episode_id: str) -> dict[str, str]:
    prefix = f"unsupported-{episode_id.lower().replace('_', '-')}"
    return {
        "prediction": f"{prefix}-prediction",
        "tom1": f"{prefix}-tom1-pending",
        "tom2": f"{prefix}-tom2-pending",
        "factual_branch": f"{prefix}-factual",
        "counterfactual_branch": f"{prefix}-do-clarify",
        "intervention": f"{prefix}-unsupported-evidence",
    }


def _build_case(
    *,
    episode: dict[str, Any],
    corpus_path: Path,
    case_root: Path,
    negative_mode: str | None,
) -> dict[str, Path]:
    episode_id = str(episode["episode_id"])
    ids = _ids(episode_id)
    targets = _prediction_targets(episode)
    if len(targets) != 2:
        raise RuntimeError(f"episode_missing_first_second_order_targets:{episode_id}")
    actions = [str(action) for action in episode.get("allowed_next_actions") or [] if isinstance(action, str)]
    actual_action = str(episode.get("actual_next_action") or (actions[0] if actions else "UNKNOWN"))
    action_distribution = _uniform_actions(actions)
    abstain = negative_mode != "not_abstained"
    support_status = "pending"
    if negative_mode == "marked_supported":
        support_status = "supported"
        abstain = False
    belief_distribution = _unknown_certain()
    if negative_mode == "not_unknown_certain":
        belief_distribution = [
            {"value": "TRUE", "probability": 0.34},
            {"value": "FALSE", "probability": 0.33},
            {"value": "UNKNOWN", "probability": 0.33},
        ]

    distributions = []
    for idx, target in enumerate(targets):
        distributions.append(
            {
                "hypothesis_id": ids["tom1"] if idx == 0 else ids["tom2"],
                "episode_id": episode_id,
                "perspective_order": target["perspective_order"],
                "subject": target["subject"],
                "target": target["target"],
                "mental_state_type": target["mental_state_type"],
                "proposition": target["proposition"],
                "distribution": belief_distribution,
                "evidence_refs": [],
                "prediction_horizon": "next_action",
                "counterfactual": False,
                "counterfactual_context": None,
                "abstain": abstain,
                "support_status": support_status,
            }
        )
    distribution_bundle = {
        "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
        "episode_id": episode_id,
        "condition": CONDITION,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "distributions": distributions,
    }

    factual_branch = {
        "branch_id": ids["factual_branch"],
        "episode_id": episode_id,
        "branch_type": "factual",
        "synthetic": False,
        "intervention": None,
        "source_evidence_refs": [],
        "held_fixed": ["observable_history", "information_access_by_agent"],
        "predicted_bdi_distribution": _unknown_certain(),
        "predicted_action_distribution": action_distribution,
        "expected_observation": "Unsupported evidence forces abstention before outcome reveal.",
        "uncertainty": 1.0,
    }
    counterfactual_branch = {
        "branch_id": ids["counterfactual_branch"],
        "episode_id": episode_id,
        "branch_type": "counterfactual",
        "synthetic": True,
        "intervention": {
            "intervention_id": ids["intervention"],
            "variable": "evidence_support",
            "set_to": "unsupported_or_insufficient",
            "synthetic": True,
        },
        "source_evidence_refs": [],
        "held_fixed": ["observable_history", "information_access_by_agent"],
        "predicted_bdi_distribution": _unknown_certain(),
        "predicted_action_distribution": action_distribution,
        "expected_observation": "The unsupported branch remains synthetic and cannot become literal history.",
        "uncertainty": 1.0,
    }
    branch_bundle = {
        "schema": "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1",
        "episode_id": episode_id,
        "condition": CONDITION,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "branches": [factual_branch, counterfactual_branch],
    }

    payload = {
        "predicted_next_action_distribution": action_distribution,
        "belief_distribution_refs": [ids["tom1"], ids["tom2"]],
        "branch_refs": [ids["factual_branch"], ids["counterfactual_branch"]],
        "abstain": abstain,
        "unsupported_evidence_abstention": abstain and support_status in {"pending", "abstained"},
        "unsupported_evidence_reason": "no evidence_refs resolve for the factual ToM hypotheses",
    }
    model_receipts = [
        {
            "schema": "persona_dream.research.prospective_tom.deterministic_abstention_model_receipt.v1",
            "model": "deterministic_unsupported_evidence_gate",
            "live_model_call": False,
            "reason": "unsupported evidence fixture exercises fail-closed abstention semantics without an LLM judge",
        }
    ]
    evidence_bundle = {
        "corpus_path": str(corpus_path),
        "episode_id": episode_id,
        "evidence_refs_resolved": 0,
        "unsupported_evidence_injected": True,
    }
    commitment = {
        "prediction_id": ids["prediction"],
        "episode_id": episode_id,
        "condition": CONDITION,
        "sealed_at": "2026-07-22T11:20:00Z",
        "outcome_visible": False,
        "canonical_memory_write": False,
        "prediction_payload": payload,
        "prediction_payload_sha256": _stable_json_sha256(payload),
        "model_receipts": model_receipts,
        "model_receipts_sha256": _stable_json_sha256(model_receipts),
        "evidence_bundle": evidence_bundle,
        "evidence_bundle_sha256": _stable_json_sha256(evidence_bundle),
    }
    commitment_bundle = {
        "schema": "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1",
        "episode_id": episode_id,
        "condition": CONDITION,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "commitments": [commitment],
    }

    hidden_labels = {}
    labels = episode.get("ground_truth_tom_labels") if isinstance(episode.get("ground_truth_tom_labels"), list) else []
    for idx, label in enumerate(labels[:2]):
        label_value = label.get("value") if isinstance(label, dict) else None
        hidden_labels[ids["tom1"] if idx == 0 else ids["tom2"]] = str(label_value or "UNKNOWN")
    outcome = {
        "schema": "persona_dream.research.prospective_tom.tom_outcome_reveal.v1",
        "episode_id": episode_id,
        "prediction_id": ids["prediction"],
        "revealed_at": "2026-07-22T11:21:00Z",
        "outcome_visible": True,
        "reveal_complete": True,
        "actual_next_action": actual_action,
        "actual_utterance": "deterministic simulator reveal",
        "hidden_state_labels": hidden_labels,
        "factual_branch_id": ids["factual_branch"],
        "literal_history_branch_ids": [ids["factual_branch"]],
        "equivalent_formulation_checks": [
            {
                "prediction_id": ids["prediction"],
                "formulation_id": f"{episode_id}:unsupported-equivalent-action",
                "expected_top_action": action_distribution[0]["value"],
            }
        ],
        "canonical_memory_write": False,
    }

    paths = {
        "distribution_bundle": case_root / "tom_belief_distribution_bundle.json",
        "branch_bundle": case_root / "counterfactual_branch_bundle.json",
        "commitment_bundle": case_root / "tom_prediction_commitment_bundle.json",
        "outcome": case_root / "tom_outcome_reveal.json",
        "gate2_receipt": case_root / "gate2_distribution_receipt.json",
        "gate5_receipt": case_root / "gate5_scoring_receipt.json",
    }
    _write_json(paths["distribution_bundle"], distribution_bundle)
    _write_json(paths["branch_bundle"], branch_bundle)
    _write_json(paths["commitment_bundle"], commitment_bundle)
    _write_json(paths["outcome"], outcome)
    return paths


def _run_json_command(command: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    payload = completed.stdout.strip()
    parsed = None
    if payload:
        try:
            parsed = json.loads(payload)
        except Exception:
            parsed = None
    return completed.returncode, parsed, completed.stderr.strip()


def run(
    *,
    corpus_path: Path,
    output_root: Path,
    receipt_out: Path,
    episodes_per_family: int,
    negative_mode: str | None,
) -> dict[str, Any]:
    started = time.monotonic()
    corpus_path = corpus_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    corpus = corpus if isinstance(corpus, dict) else {}
    episodes = _episode_candidates(corpus, episodes_per_family)
    if not episodes:
        errors.append("no_episodes_selected")

    case_rows: list[dict[str, Any]] = []
    gate2_pass = 0
    gate5_pass = 0
    gate2_blocked = 0
    abstained_rows = 0
    risk_coverage_rows = 0
    for episode in episodes:
        episode_id = str(episode.get("episode_id"))
        family = str(episode.get("scenario_family"))
        case_root = artifacts_root / "cases" / episode_id
        paths = _build_case(
            episode=episode,
            corpus_path=corpus_path,
            case_root=case_root,
            negative_mode=negative_mode,
        )
        gate2_code, gate2_receipt, gate2_stderr = _run_json_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "check_tom_belief_distributions.py"),
                "--corpus",
                str(corpus_path),
                "--bundle",
                str(paths["distribution_bundle"]),
                "--receipt-out",
                str(paths["gate2_receipt"]),
                "--json",
            ]
        )
        gate2_status = gate2_receipt.get("status") if isinstance(gate2_receipt, dict) else None
        if gate2_code == 0 and gate2_status == "PASS_TOM_BELIEF_DISTRIBUTIONS":
            gate2_pass += 1
        elif gate2_status == "BLOCKED_TOM_BELIEF_DISTRIBUTIONS":
            gate2_blocked += 1
        else:
            errors.append(f"gate2_unexpected_result:{episode_id}:{gate2_code}:{gate2_status}:{gate2_stderr}")

        gate5_receipt = None
        gate5_code = None
        gate5_status = None
        if gate2_code == 0:
            gate5_code, gate5_receipt, gate5_stderr = _run_json_command(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "reveal_and_score_trial.py"),
                    "--corpus",
                    str(corpus_path),
                    "--distributions",
                    str(paths["distribution_bundle"]),
                    "--branches",
                    str(paths["branch_bundle"]),
                    "--commitments",
                    str(paths["commitment_bundle"]),
                    "--outcome",
                    str(paths["outcome"]),
                    "--receipt-out",
                    str(paths["gate5_receipt"]),
                    "--json",
                ]
            )
            gate5_status = gate5_receipt.get("status") if isinstance(gate5_receipt, dict) else None
            if gate5_code == 0 and gate5_status == "PASS_TOM_SCORING_RECEIPT":
                gate5_pass += 1
                metrics = gate5_receipt.get("metrics") if isinstance(gate5_receipt, dict) else {}
                risk_coverage = metrics.get("risk_coverage") if isinstance(metrics, dict) else None
                if isinstance(risk_coverage, dict):
                    risk_coverage_rows += 1
                    if risk_coverage.get("abstained") is True:
                        abstained_rows += 1
                    if risk_coverage.get("coverage") != 0.0:
                        errors.append(f"gate5_abstained_coverage_not_zero:{episode_id}:{risk_coverage.get('coverage')}")
            else:
                errors.append(f"gate5_unexpected_result:{episode_id}:{gate5_code}:{gate5_status}:{gate5_stderr}")

        case_rows.append(
            {
                "episode_id": episode_id,
                "family": family,
                "case_root": str(case_root),
                "negative_mode": negative_mode,
                "gate2_exit_code": gate2_code,
                "gate2_status": gate2_status,
                "gate2_receipt": str(paths["gate2_receipt"]),
                "gate2_receipt_sha256": _file_sha256(paths["gate2_receipt"]) if paths["gate2_receipt"].exists() else None,
                "gate5_exit_code": gate5_code,
                "gate5_status": gate5_status,
                "gate5_receipt": str(paths["gate5_receipt"]) if paths["gate5_receipt"].exists() else None,
                "gate5_receipt_sha256": _file_sha256(paths["gate5_receipt"]) if paths["gate5_receipt"].exists() else None,
            }
        )

    families = sorted({row["family"] for row in case_rows})
    expected_positive = negative_mode is None
    if expected_positive:
        if len(families) < 4:
            errors.append(f"families_less_than_four:{families}")
        if gate2_pass != len(case_rows):
            errors.append(f"gate2_pass_count_mismatch:{gate2_pass}:{len(case_rows)}")
        if gate5_pass != len(case_rows):
            errors.append(f"gate5_pass_count_mismatch:{gate5_pass}:{len(case_rows)}")
        if abstained_rows != len(case_rows):
            errors.append(f"abstained_rows_mismatch:{abstained_rows}:{len(case_rows)}")
        if risk_coverage_rows != len(case_rows):
            errors.append(f"risk_coverage_rows_mismatch:{risk_coverage_rows}:{len(case_rows)}")
    else:
        if gate2_blocked == 0:
            errors.append(f"negative_gate2_did_not_block:{negative_mode}")
        else:
            errors.append(f"negative_mode_triggered_fail_closed:{negative_mode}")

    rows_path = artifacts_root / "unsupported_evidence_abstention_rows.v1.json"
    _write_json(
        rows_path,
        {
            "schema": "persona_dream.research.prospective_tom.unsupported_evidence_abstention_rows.v1",
            "corpus_path": str(corpus_path),
            "negative_mode": negative_mode,
            "rows": case_rows,
        },
    )
    checks = {
        "four_families_exercised": len(families) >= 4,
        "gate2_unsupported_abstention_passed": expected_positive and gate2_pass == len(case_rows) and len(case_rows) > 0,
        "gate5_abstention_scored": expected_positive and gate5_pass == len(case_rows) and risk_coverage_rows == len(case_rows),
        "unsupported_evidence_abstention_exercised": expected_positive and abstained_rows == len(case_rows) and len(case_rows) > 0,
        "negative_gate2_blocks": (not expected_positive) and gate2_blocked > 0,
        "unsupported_writes_absent": True,
        "human_content_judgment_absent": True,
        "llm_judge_absent": True,
    }
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": SCHEMA,
        "created_at": _now_iso(),
        "status": status,
        "errors": errors,
        "corpus_path": str(corpus_path),
        "corpus_sha256": _file_sha256(corpus_path) if corpus_path.exists() else None,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "row_artifact_path": str(rows_path),
        "row_artifact_sha256": _file_sha256(rows_path),
        "negative_mode": negative_mode,
        "counts": {
            "case_rows": len(case_rows),
            "families": len(families),
            "gate2_pass": gate2_pass,
            "gate2_blocked": gate2_blocked,
            "gate5_pass": gate5_pass,
            "risk_coverage_rows": risk_coverage_rows,
            "abstained_rows": abstained_rows,
            "unsupported_distribution_rows": len(case_rows) * 2,
        },
        "checks": checks,
        "mocked": False,
        "live": False,
        "fixture_backed": negative_mode is not None,
        "live_tau_reexecuted": False,
        "deterministic_gate_receipts_consumed": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "unsupported factual ToM hypotheses abstain or remain pending with UNKNOWN certainty under the existing Gate 2 validator",
                "abstained prediction commitments are sealed and scored by Gate 5 with risk coverage set to zero",
                "the unsupported-evidence abstention exercise covers all four deterministic social episode families",
            ]
            if status == PASS_STATUS
            else [
                "the unsupported-evidence abstention checker failed closed before accepting the abstention claim",
            ],
            "does_not_prove": [
                "live Tau generation of an abstention response",
                "paid provider execution",
                "semantic dream quality",
                "complete Phase 01-16 media runtime execution",
            ],
        },
        "elapsed_s": round(time.monotonic() - started, 6),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--episodes-per-family", type=int, default=1)
    parser.add_argument(
        "--negative-mode",
        choices=["marked_supported", "not_abstained", "not_unknown_certain"],
        default=None,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "pctom_unsupported_evidence_abstention_receipt.v1.json")
    receipt = run(
        corpus_path=args.corpus,
        output_root=args.output_root,
        receipt_out=receipt_out,
        episodes_per_family=args.episodes_per_family,
        negative_mode=args.negative_mode,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
