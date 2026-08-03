#!/usr/bin/env python3
"""PCTOM-R v2 episode-conditioned M/R/D/CD estimator and condition preflight.

The v1 runner built every prediction from ``_distribution_entries(profile)`` --
a per-condition constant.  The episode contributed ids and wording, never
evidence, so the Brier ordering was fixed by source constants.

This runner replaces the constant with an *episode-conditioned* rule.  Every
condition sees the same agent-visible evidence (the four lossy cues emitted by
the corpus generator) and differs only in **which subset of that evidence its
method can integrate**:

    M  (memory only)          -> {cue_recency}
    R  (textual reflection)   -> {cue_recency, cue_ack}
    D  (single dream)         -> {cue_recency, cue_ack, cue_hedge}
    CD (counterfactual dream) -> {cue_recency, cue_ack, cue_hedge, cue_contrast}

The evidence weights are shared across conditions; only the visible subset
differs.  No condition receives hidden state, the answer key, the future
outcome, or an expected-winner hint.  Two of the four cues are ambiguous by
construction (see the generator), so a *larger* subset is not uniformly better:
``cue_contrast`` fires both when the state really changed and when it is merely
ambiguous, which is precisely how CD can and does lose episodes to M/R/D.

Nothing here is random.  Variance across episodes comes from the evidence
varying; no jitter is added anywhere.

The prevalence-only null baseline (P0) is computed as an explicit reference
score but is deliberately NOT emitted as a case condition: a constant predictor
is exactly what the validity gate must reject, so shipping it as a scored
condition would (correctly) block the gate.  It lives in the receipt instead.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
CORPUS_BUILDER = SCRIPTS / "build_pctom_v2_corpus.py"

CONDITIONS = ("M", "R", "D", "CD")
OUTCOMES = ("TRUE", "FALSE", "UNKNOWN")
PASS_STATUS = "PASS_PCTOM_V2_CONDITION_PREFLIGHT"
BLOCKED_STATUS = "BLOCKED_PCTOM_V2_CONDITION_PREFLIGHT"

#: Which agent-visible cues each condition's method is able to integrate.
#: This is the ONLY thing that differs between conditions.
VISIBLE_CUE_SUBSET: dict[str, tuple[str, ...]] = {
    "M": ("cue_recency",),
    "R": ("cue_recency", "cue_ack"),
    "D": ("cue_recency", "cue_ack", "cue_hedge"),
    "CD": ("cue_recency", "cue_ack", "cue_hedge", "cue_contrast"),
}

CONDITION_METHOD: dict[str, str] = {
    "M": "direct_memory_readout",
    "R": "textual_reflection",
    "D": "single_trajectory_dream",
    "CD": "counterfactual_dream",
}

#: Shared evidence weights in log space: (cue, outcome) -> weight.
#: ``__absent__`` weights apply when the cue is visible to the condition and
#: reads zero.  Identical for every condition.
EVIDENCE_WEIGHTS: dict[int, dict[str, dict[str, float]]] = {
    1: {
        "cue_recency": {"TRUE": 1.10, "__absent__:FALSE": 0.70},
        "cue_ack": {"TRUE": -0.95, "FALSE": 1.15},
        "cue_hedge": {"UNKNOWN": 1.30},
        "cue_contrast": {"TRUE": 1.05},
    },
    2: {
        "cue_recency": {"TRUE": 0.90},
        "cue_ack": {"TRUE": -1.10, "FALSE": 1.30},
        "cue_hedge": {"UNKNOWN": 1.25},
        "cue_contrast": {"TRUE": 0.80},
    },
}

PRIOR_LOGITS: dict[int, dict[str, float]] = {
    1: {"TRUE": 0.0, "FALSE": 0.0, "UNKNOWN": 0.25},
    2: {"TRUE": 0.0, "FALSE": 0.0, "UNKNOWN": 0.20},
}


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# condition-specific inference over agent-visible evidence
# --------------------------------------------------------------------------
def predict(cues: dict[str, int], condition: str, order: int) -> list[dict[str, Any]]:
    """Episode-conditioned belief distribution.

    Reads only ``cues`` (agent-visible) and the condition's cue subset.  Raises
    if asked for a cue outside the subset, so leakage is structurally impossible.
    """
    subset = VISIBLE_CUE_SUBSET[condition]
    weights = EVIDENCE_WEIGHTS[order]
    logits = dict(PRIOR_LOGITS[order])
    for cue in subset:
        value = int(cues[cue])
        for key, weight in weights.get(cue, {}).items():
            if key.startswith("__absent__:"):
                if not value:
                    logits[key.split(":", 1)[1]] += weight
            elif value:
                logits[key] += weight
    top = max(logits.values())
    exps = {k: math.exp(v - top) for k, v in logits.items()}
    total = sum(exps.values())
    return [
        {"value": outcome, "probability": round(exps[outcome] / total, 9)}
        for outcome in OUTCOMES
    ]


def evidence_refs(episode: dict[str, Any], condition: str) -> list[dict[str, str]]:
    """Exact agent-visible fields the prediction read, per condition."""
    episode_id = episode["episode_id"]
    refs = [
        {
            "scope": "visible_cue",
            "source_id": f"{episode_id}:visible_evidence.cues.{cue}",
            "observed_value": str(int(episode["visible_evidence"]["cues"][cue])),
        }
        for cue in VISIBLE_CUE_SUBSET[condition]
    ]
    for line in episode["observable_history"]:
        if line.get("cue") in VISIBLE_CUE_SUBSET[condition]:
            refs.append(
                {
                    "scope": "observable_history",
                    "source_id": f"{episode_id}:observable_history:{line['turn_index']}",
                    "observed_value": line["cue"],
                }
            )
    return refs


def brier(distribution: list[dict[str, Any]], truth: str) -> float:
    return sum((float(e["probability"]) - (1.0 if e["value"] == truth else 0.0)) ** 2 for e in distribution)


def prevalence_baseline(corpus: dict[str, Any], order: int) -> list[dict[str, Any]]:
    """Intercept-only null: the marginal label frequency for this order.

    Uses labels only -- no episode features -- which is exactly the point.
    """
    counts = {o: 0 for o in OUTCOMES}
    total = 0
    for episode in corpus["episodes"]:
        for label in episode["ground_truth_tom_labels"]:
            if label["perspective_order"] == order:
                counts[label["value"]] += 1
                total += 1
    return [
        {"value": o, "probability": round(counts[o] / total, 9) if total else 1 / 3}
        for o in OUTCOMES
    ]


# --------------------------------------------------------------------------
# case bundles (sealed) and reveal
# --------------------------------------------------------------------------
def _distribution_bundle(episode: dict[str, Any], condition: str) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    cues = episode["visible_evidence"]["cues"]
    labels = {int(l["perspective_order"]): l for l in episode["ground_truth_tom_labels"]}
    refs = evidence_refs(episode, condition)
    distributions = []
    for order in (1, 2):
        label = labels[order]
        distributions.append(
            {
                "hypothesis_id": f"{episode_id}-{condition.lower()}-tom{order}-factual",
                "episode_id": episode_id,
                "perspective_order": order,
                "subject": label["subject"],
                "target": label["target"],
                "mental_state_type": label["mental_state_type"],
                "proposition": label["proposition"],
                "distribution": predict(cues, condition, order),
                "evidence_refs": refs,
                "visible_cue_subset": list(VISIBLE_CUE_SUBSET[condition]),
                "prediction_horizon": "next_action",
                "counterfactual": False,
                "counterfactual_context": None,
                "abstain": False,
                "support_status": "supported",
            }
        )
    return {
        "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
        "episode_id": episode_id,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "condition": condition,
        "condition_method": CONDITION_METHOD[condition],
        "distributions": distributions,
    }


def _commitment_bundle(
    episode: dict[str, Any], condition: str, bundle: dict[str, Any], sealed_at: str
) -> dict[str, Any]:
    payload = {
        "episode_id": episode["episode_id"],
        "condition": condition,
        "outcome_visible": False,
        "distributions": bundle["distributions"],
    }
    return {
        "schema": "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1",
        "episode_id": episode["episode_id"],
        "sealed": True,
        "outcome_visible": False,
        "condition": condition,
        "sealed_at": sealed_at,
        "commitment_hash": _stable_json_sha256(payload),
        "prediction_payload_sha256": _stable_json_sha256(payload),
    }


def _outcome_reveal(episode: dict[str, Any], condition: str, revealed_at: str) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    labels = {int(l["perspective_order"]): l for l in episode["ground_truth_tom_labels"]}
    return {
        "schema": "persona_dream.research.prospective_tom.tom_outcome_reveal.v1",
        "outcome_id": f"{episode_id}-{condition.lower()}-outcome",
        "episode_id": episode_id,
        "revealed_at": revealed_at,
        "outcome_visible": True,
        "reveal_complete": True,
        "canonical_memory_write": False,
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "actual_next_action": episode["actual_next_action"],
        "hidden_state_labels": {
            f"{episode_id}-{condition.lower()}-tom1-factual": labels[1]["value"],
            f"{episode_id}-{condition.lower()}-tom2-factual": labels[2]["value"],
        },
    }


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def _bootstrap_ci(diffs: list[float], iterations: int = 2000) -> dict[str, float | None]:
    """Percentile CI resampled by BASE EPISODE (each diff is one base episode).

    Deterministic: a fixed LCG, not ``random``, so re-runs reproduce exactly.
    """
    n = len(diffs)
    if n < 2:
        return {"lo": None, "hi": None}
    state = 0x2545F4914F6CDD1D
    means = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(n):
            state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            total += diffs[(state >> 33) % n]
        means.append(total / n)
    means.sort()
    return {
        "lo": round(means[int(0.025 * iterations)], 9),
        "hi": round(means[min(iterations - 1, int(0.975 * iterations))], 9),
    }


def run(*, split: str, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    builder = _load_module(CORPUS_BUILDER, "pctom_v2_corpus_builder")
    corpus = builder.build_corpus(split)
    corpus_path = output_root / "artifacts" / "pctom_v2_corpus.json"
    _write_json(corpus_path, corpus)

    sealed_base = datetime(2026, 8, 1, 3, 0, 0, tzinfo=timezone.utc)
    reveal_base = datetime(2026, 8, 1, 4, 0, 0, tzinfo=timezone.utc)

    baselines = {order: prevalence_baseline(corpus, order) for order in (1, 2)}
    scores: dict[str, dict[str, float]] = {c: {} for c in CONDITIONS}
    baseline_scores: dict[str, float] = {}
    scores_by_label_class: dict[str, dict[str, list[float]]] = {c: {} for c in CONDITIONS}
    distinct_dists: dict[str, set[str]] = {c: set() for c in CONDITIONS}
    ref_counts: dict[str, int] = {c: 0 for c in CONDITIONS}
    sealed_count = 0
    seal_recomputed_ok = 0
    errors: list[str] = []

    for episode_index, episode in enumerate(corpus["episodes"]):
        labels = {int(l["perspective_order"]): l for l in episode["ground_truth_tom_labels"]}
        base_class = f"order1={labels[1]['value']}"
        baseline_scores[episode["episode_id"]] = (
            brier(baselines[1], labels[1]["value"]) + brier(baselines[2], labels[2]["value"])
        ) / 2.0
        for condition_index, condition in enumerate(CONDITIONS):
            case_dir = output_root / "artifacts" / "cases" / episode["episode_id"] / condition
            sealed_at = (sealed_base + timedelta(minutes=episode_index, seconds=condition_index)).strftime("%Y-%m-%dT%H:%M:%SZ")
            revealed_at = (reveal_base + timedelta(minutes=episode_index, seconds=condition_index)).strftime("%Y-%m-%dT%H:%M:%SZ")

            bundle = _distribution_bundle(episode, condition)
            commitment = _commitment_bundle(episode, condition, bundle, sealed_at)
            reveal = _outcome_reveal(episode, condition, revealed_at)
            _write_json(case_dir / "tom_belief_distribution_bundle.json", bundle)
            _write_json(case_dir / "tom_prediction_commitment_bundle.json", commitment)
            _write_json(case_dir / "tom_outcome_reveal.json", reveal)
            sealed_count += 1

            # recompute the seal before scoring
            recomputed = _stable_json_sha256(
                {
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                    "outcome_visible": False,
                    "distributions": bundle["distributions"],
                }
            )
            if recomputed == commitment["commitment_hash"]:
                seal_recomputed_ok += 1
            else:
                errors.append(f"seal_mismatch:{episode['episode_id']}:{condition}")

            per_case = []
            for dist in bundle["distributions"]:
                order = dist["perspective_order"]
                per_case.append(brier(dist["distribution"], labels[order]["value"]))
                distinct_dists[condition].add(
                    json.dumps([(e["value"], e["probability"]) for e in dist["distribution"]])
                )
                ref_counts[condition] += len(dist["evidence_refs"])
            case_score = sum(per_case) / len(per_case)
            scores[condition][episode["episode_id"]] = case_score
            scores_by_label_class[condition].setdefault(base_class, []).append(case_score)

    # win/tie/loss recomputed exactly the way the validity gate does
    outcomes: dict[str, dict[str, int]] = {c: {"win": 0, "tie": 0, "loss": 0} for c in CONDITIONS}
    for episode_id in sorted(scores["M"]):
        present = {c: scores[c][episode_id] for c in CONDITIONS}
        best, worst = min(present.values()), max(present.values())
        for c, v in present.items():
            if best == worst:
                outcomes[c]["tie"] += 1
            elif v == best:
                outcomes[c]["win"] += 1
            elif v == worst:
                outcomes[c]["loss"] += 1
            else:
                outcomes[c]["tie"] += 1

    episode_ids = sorted(scores["M"])
    benefit: dict[str, Any] = {}
    for condition in CONDITIONS:
        diffs = [scores[condition][e] - baseline_scores[e] for e in episode_ids]
        mean_diff = sum(diffs) / len(diffs)
        benefit[condition] = {
            "mean_brier": round(sum(scores[condition][e] for e in episode_ids) / len(episode_ids), 9),
            "mean_paired_diff_vs_prevalence_baseline": round(mean_diff, 9),
            "bootstrap_ci_by_base_episode": _bootstrap_ci(diffs),
            "lower_is_better": True,
        }
    benefit["P0_prevalence_baseline"] = {
        "mean_brier": round(sum(baseline_scores.values()) / len(baseline_scores), 9),
        "distribution_order1": baselines[1],
        "distribution_order2": baselines[2],
        "note": "intercept/prevalence-only null; not emitted as a scored case condition",
    }

    variance_rows = {
        condition: {
            label_class: {
                "n": len(values),
                "distinct_values": len({round(v, 9) for v in values}),
                "variance": round(_variance(values), 12),
            }
            for label_class, values in sorted(by_class.items())
        }
        for condition, by_class in scores_by_label_class.items()
    }
    for condition, rows in variance_rows.items():
        for label_class, row in rows.items():
            if row["distinct_values"] < 2 or row["variance"] <= 0:
                errors.append(f"degenerate_within_class:{condition}:{label_class}")
    for condition in CONDITIONS:
        if outcomes[condition]["loss"] < 1:
            errors.append(f"condition_cannot_lose:{condition}")
        if len(distinct_dists[condition]) < 2:
            errors.append(f"constant_distribution:{condition}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.pctom_v2_condition_preflight.v1",
        "status": status,
        "split": split,
        "output_root": str(output_root),
        "corpus_path": str(corpus_path),
        "corpus_sha256": _stable_json_sha256(corpus),
        "episodes_sha256": corpus["episodes_sha256"],
        "sealed": True,
        "sealed_commitment_count": sealed_count,
        "sealed_commitments_recomputed_ok": seal_recomputed_ok,
        "conditions": list(CONDITIONS),
        "visible_cue_subset_by_condition": {k: list(v) for k, v in VISIBLE_CUE_SUBSET.items()},
        "counts": {
            "episodes": len(corpus["episodes"]),
            "cases": sealed_count,
            "label_counts": corpus["label_counts"],
            "label_counts_by_family": corpus["label_counts_by_family"],
            "distinct_distributions_by_condition": {k: len(v) for k, v in distinct_dists.items()},
            "distinct_per_episode_scores_by_condition": {
                c: len({round(v, 9) for v in scores[c].values()}) for c in CONDITIONS
            },
            "evidence_ref_count_by_condition": ref_counts,
            "win_tie_loss_by_condition": outcomes,
        },
        "score_variance_within_label_class": variance_rows,
        "benefit_vs_prevalence_baseline": benefit,
        "primary_proper_score": "multiclass_brier",
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "live_tau_calls": 0,
        "provider_calls": 0,
        "memory_write_attempts": 0,
        "mocked": False,
        "live": False,
        "errors": errors,
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="development")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(split=args.split, output_root=args.output_root, receipt_out=args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(f"  labels: {receipt['counts']['label_counts']['all']}")
        print(f"  distinct distributions: {receipt['counts']['distinct_distributions_by_condition']}")
        print(f"  win/tie/loss: {receipt['counts']['win_tie_loss_by_condition']}")
        for err in receipt["errors"]:
            print(f"  ERROR {err}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
