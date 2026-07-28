#!/usr/bin/env python3
"""Fail closed when the PCTOM-R measurement path cannot falsify its hypothesis.

Before any live held-out Tau spend (#1008), the estimator must be capable of
producing a CD loss. Measured 2026-07-28 on the committed path, it was not:

- every ground-truth label in ``build_social_episode_corpus.py`` is ``TRUE``
  (8/8, zero FALSE, zero UNKNOWN);
- ``run_condition_comparison.py`` builds each prediction from
  ``_distribution_entries(CONDITION_PROFILES[condition])``, so the probabilities
  depend only on a per-condition constant; the episode contributes ids and
  wording, never evidence.

With a constant label and a constant prediction, the Brier ordering is decided
by source constants before a single model call. That is not a weak result, it is
a degenerate estimator, and no amount of receipt machinery converts it into
evidence.

This gate reports raw counts rather than derived flags, so a reader can see the
degeneracy rather than trust a boolean. It makes no live or paid call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: A condition whose predictions never vary cannot lose for a reason; it can
#: only win or lose by constant. Two distinct distributions is the bare minimum
#: that lets evidence move a prediction.
MIN_DISTINCT_DISTRIBUTIONS = 2

#: Labels must genuinely vary. A single-valued label set makes accuracy a
#: property of the prior, not of inference.
MIN_DISTINCT_LABEL_VALUES = 2

#: If a condition never loses on any episode, the comparison has no power to
#: falsify it.
MIN_LOSSES_PER_CONDITION = 1

#: Tokens that would mean corpus generation inspected the thing it is meant to
#: be judged by. Their presence in the generator is circularity.
CIRCULARITY_TOKENS = (
    "CONDITION_PROFILES",
    "expected_winner",
    "winning_set",
    "cd_wins",
    "condition_receipt",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_labels(corpus: Any) -> list[dict[str, Any]]:
    episodes = corpus.get("episodes") if isinstance(corpus, dict) else corpus
    labels: list[dict[str, Any]] = []
    for episode in episodes or []:
        for label in (
            episode.get("ground_truth_tom_labels")
            or episode.get("ground_truth_labels")
            or episode.get("labels")
            or []
        ):
            row = dict(label)
            row.setdefault("episode_id", episode.get("episode_id"))
            labels.append(row)
    return labels


def _case_root(receipt: Any, receipt_path: Path | None) -> Path | None:
    """Where the per-case bundles live.

    The condition-comparison receipt carries summary metrics only; the actual
    distributions, seals, and reveals are written per episode/condition under
    ``<output_root>/artifacts/cases/<episode>/<condition>/``. Reading only the
    receipt would score the summary and miss the degeneracy entirely.
    """
    if isinstance(receipt, dict):
        root = receipt.get("output_root")
        if root and (Path(root) / "artifacts" / "cases").is_dir():
            return Path(root) / "artifacts" / "cases"
    if receipt_path:
        candidate = receipt_path.parent / "artifacts" / "cases"
        if candidate.is_dir():
            return candidate
    return None


def _iter_case_bundles(case_root: Path) -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    for episode_dir in sorted(case_root.iterdir()):
        if not episode_dir.is_dir():
            continue
        for cond_dir in sorted(episode_dir.iterdir()):
            if cond_dir.is_dir():
                rows.append((episode_dir.name, cond_dir.name, cond_dir))
    return rows


def _iter_predictions(receipt: Any) -> list[dict[str, Any]]:
    """Flatten predictions from a condition-comparison receipt."""
    out: list[dict[str, Any]] = []
    if not isinstance(receipt, dict):
        return out

    def walk(node: Any, condition: str | None) -> None:
        if isinstance(node, dict):
            cond = node.get("condition") or condition
            if "distribution" in node and isinstance(node.get("distribution"), list):
                row = dict(node)
                row["condition"] = cond
                out.append(row)
            for value in node.values():
                walk(value, cond)
        elif isinstance(node, list):
            for item in node:
                walk(item, condition)

    walk(receipt, None)
    return out


def _distribution_key(entries: Any) -> str:
    """Canonical form of a probability vector, for distinctness counting."""
    if isinstance(entries, list):
        pairs = []
        for entry in entries:
            if isinstance(entry, dict):
                outcome = entry.get("outcome") or entry.get("value") or entry.get("label")
                prob = entry.get("probability", entry.get("p"))
                pairs.append((str(outcome), round(float(prob), 6) if prob is not None else None))
        return json.dumps(sorted(pairs))
    return json.dumps(entries, sort_keys=True)


def check_labels(corpus: Any, problems: list[dict[str, Any]]) -> dict[str, Any]:
    labels = _iter_labels(corpus)
    by_order: dict[Any, Counter] = defaultdict(Counter)
    by_family: dict[Any, Counter] = defaultdict(Counter)
    overall: Counter = Counter()
    for label in labels:
        value = str(label.get("truth_value") or label.get("value") or label.get("label") or "")
        order = label.get("perspective_order") or label.get("order")
        family = label.get("mental_state_type") or label.get("family")
        overall[value] += 1
        by_order[order][value] += 1
        by_family[family][value] += 1

    if len(overall) < MIN_DISTINCT_LABEL_VALUES:
        problems.append(
            {
                "rule": "degenerate_ground_truth_labels",
                "detail": f"all {sum(overall.values())} labels take the value(s) "
                f"{sorted(overall)}; accuracy would measure the prior, not inference",
                "counts": dict(overall),
            }
        )
    return {
        "total": sum(overall.values()),
        "by_value": dict(overall),
        "by_order": {str(k): dict(v) for k, v in by_order.items()},
        "by_family": {str(k): dict(v) for k, v in by_family.items()},
        "distinct_values": len(overall),
    }


def load_case_predictions(case_root: Path) -> list[dict[str, Any]]:
    """Every belief distribution, tagged with its episode and condition."""
    rows: list[dict[str, Any]] = []
    for episode, condition, path in _iter_case_bundles(case_root):
        bundle_path = path / "tom_belief_distribution_bundle.json"
        if not bundle_path.is_file():
            continue
        bundle = load_json(bundle_path)
        for dist in bundle.get("distributions") or []:
            row = dict(dist)
            row["condition"] = bundle.get("condition") or condition
            row["episode_id"] = row.get("episode_id") or episode
            row["_sealed"] = bool(bundle.get("sealed"))
            rows.append(row)
    return rows


def brier(distribution: Any, truth: str) -> float | None:
    """Multiclass Brier over the declared outcome space."""
    if not isinstance(distribution, list):
        return None
    total = 0.0
    seen = False
    for entry in distribution:
        if not isinstance(entry, dict):
            continue
        value = str(entry.get("value") or entry.get("outcome") or entry.get("label"))
        prob = entry.get("probability", entry.get("p"))
        if prob is None:
            continue
        seen = True
        target = 1.0 if value == truth else 0.0
        total += (float(prob) - target) ** 2
    return total if seen else None


def check_predictions(receipt: Any, problems: list[dict[str, Any]], preds: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    preds = preds if preds is not None else _iter_predictions(receipt)
    per_condition: dict[str, set[str]] = defaultdict(set)
    refs_per_condition: dict[str, set[str]] = defaultdict(set)
    counts: Counter = Counter()
    for pred in preds:
        cond = str(pred.get("condition") or "unknown")
        counts[cond] += 1
        per_condition[cond].add(_distribution_key(pred.get("distribution")))
        for ref in pred.get("evidence_refs") or []:
            refs_per_condition[cond].add(
                json.dumps(ref, sort_keys=True) if isinstance(ref, dict) else str(ref)
            )

    for cond, keys in sorted(per_condition.items()):
        if len(keys) < MIN_DISTINCT_DISTRIBUTIONS:
            problems.append(
                {
                    "rule": "constant_prediction_distribution",
                    "detail": f"condition {cond!r} emits {len(keys)} distinct distribution(s) "
                    f"across {counts[cond]} predictions; the prediction does not depend on "
                    "episode evidence",
                    "condition": cond,
                }
            )
        if not refs_per_condition.get(cond):
            problems.append(
                {
                    "rule": "no_evidence_refs",
                    "detail": f"condition {cond!r} cites no evidence source for its predictions",
                    "condition": cond,
                }
            )
    return {
        "predictions_by_condition": dict(counts),
        "distinct_distributions_by_condition": {k: len(v) for k, v in per_condition.items()},
        "distinct_evidence_refs_by_condition": {k: len(v) for k, v in refs_per_condition.items()},
    }


def check_scores(
    receipt: Any, problems: list[dict[str, Any]], case_root: Path | None = None
) -> dict[str, Any]:
    """Per-episode score spread and win/tie/loss counts per condition.

    Scores are recomputed here from the sealed distributions and the revealed
    hidden-state labels rather than trusting a summary metric, so a constant
    estimator cannot hide behind an aggregate mean.
    """
    scores: dict[str, dict[str, float]] = defaultdict(dict)

    if case_root:
        for episode, condition, path in _iter_case_bundles(case_root):
            dist_path = path / "tom_belief_distribution_bundle.json"
            reveal_path = path / "tom_outcome_reveal.json"
            if not (dist_path.is_file() and reveal_path.is_file()):
                continue
            bundle = load_json(dist_path)
            reveal = load_json(reveal_path)
            raw = reveal.get("hidden_state_labels") or {}
            # dict keyed by hypothesis_id in the committed shape; tolerate a list
            if isinstance(raw, dict):
                truths = {str(k): str(v) for k, v in raw.items()}
            else:
                truths = {
                    str(lbl.get("hypothesis_id") or lbl.get("label_id")): str(
                        lbl.get("value") or lbl.get("truth_value")
                    )
                    for lbl in raw
                    if isinstance(lbl, dict)
                }
            per_case: list[float] = []
            for dist in bundle.get("distributions") or []:
                if dist.get("counterfactual"):
                    continue
                truth = truths.get(str(dist.get("hypothesis_id")))
                if truth is None and len(set(truths.values())) == 1 and truths:
                    truth = next(iter(truths.values()))
                if truth is None:
                    continue
                value = brier(dist.get("distribution"), truth)
                if value is not None:
                    per_case.append(value)
            if per_case:
                cond = bundle.get("condition") or condition
                scores[str(cond)][str(episode)] = sum(per_case) / len(per_case)

    distinct = {cond: len(set(round(v, 9) for v in per.values())) for cond, per in scores.items()}
    for cond, n in sorted(distinct.items()):
        if n < MIN_DISTINCT_DISTRIBUTIONS:
            problems.append(
                {
                    "rule": "constant_per_episode_score",
                    "detail": f"condition {cond!r} yields {n} distinct per-episode score(s); "
                    "the metric cannot discriminate between episodes",
                    "condition": cond,
                }
            )

    episodes = sorted({ep for per in scores.values() for ep in per})
    outcomes: dict[str, Counter] = {cond: Counter() for cond in scores}
    for ep in episodes:
        present = {c: per[ep] for c, per in scores.items() if ep in per}
        if len(present) < 2:
            continue
        best = min(present.values())  # Brier: lower is better
        worst = max(present.values())
        for cond, value in present.items():
            if value == best and best != worst:
                outcomes[cond]["win"] += 1
            elif value == worst and best != worst:
                outcomes[cond]["loss"] += 1
            else:
                outcomes[cond]["tie"] += 1

    for cond, tally in sorted(outcomes.items()):
        if tally.get("loss", 0) < MIN_LOSSES_PER_CONDITION:
            problems.append(
                {
                    "rule": "condition_cannot_lose",
                    "detail": f"condition {cond!r} never loses on any episode "
                    f"({dict(tally)}); the comparison cannot falsify it",
                    "condition": cond,
                }
            )
    return {
        "distinct_scores_by_condition": distinct,
        "win_tie_loss_by_condition": {k: dict(v) for k, v in outcomes.items()},
        "episodes_scored": len(episodes),
    }


def check_anticircularity(generator: Path | None, problems: list[dict[str, Any]]) -> dict[str, Any]:
    """The corpus generator must not read condition outputs or expected winners."""
    row: dict[str, Any] = {"generator": str(generator) if generator else None, "hits": []}
    if not generator or not generator.is_file():
        problems.append(
            {
                "rule": "generator_not_readable",
                "detail": "corpus generator source not readable; circularity cannot be excluded",
            }
        )
        return row
    text = generator.read_text(encoding="utf-8")
    row["sha256"] = sha256_bytes(text.encode())
    for token in CIRCULARITY_TOKENS:
        if re.search(re.escape(token), text):
            row["hits"].append(token)
            problems.append(
                {
                    "rule": "corpus_generation_inspects_conditions",
                    "detail": f"generator references {token!r}; the corpus may be authored "
                    "around the method expected to win",
                    "offending": token,
                }
            )
    return row


_SEAL_HINT: dict[str, int] = {}


def check_seals(receipt: Any, problems: list[dict[str, Any]]) -> dict[str, Any]:
    """Sealed commitments must be verifiable before the outcome is revealed."""
    seals: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if any(k in node for k in ("commitment_hash", "sealed_hash", "seal_sha256")) or (
                node.get("sealed") is True
            ):
                seals.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(receipt)
    if not seals and _SEAL_HINT.get("count"):
        seals = [{"sealed": True}] * _SEAL_HINT["count"]
    if not seals:
        problems.append(
            {
                "rule": "no_sealed_commitments",
                "detail": "no sealed prediction commitment found; predictions could have been "
                "written after the outcome was known",
            }
        )
    if isinstance(receipt, dict) and receipt.get("llm_judge_used"):
        problems.append(
            {"rule": "llm_judge_used", "detail": "scoring must be deterministic, not LLM-judged"}
        )
    return {"sealed_commitment_count": len(seals)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    corpus = load_json(args.corpus) if args.corpus and args.corpus.is_file() else None
    receipt = (
        load_json(args.condition_receipt)
        if args.condition_receipt and args.condition_receipt.is_file()
        else None
    )
    if corpus is None:
        problems.append({"rule": "corpus_missing", "detail": f"{args.corpus} not readable"})
    if receipt is None:
        problems.append(
            {"rule": "condition_receipt_missing", "detail": f"{args.condition_receipt} not readable"}
        )

    labels = check_labels(corpus, problems) if corpus is not None else {}
    case_root_early = _case_root(receipt, args.condition_receipt)
    case_preds_early = load_case_predictions(case_root_early) if case_root_early else None
    predictions = (
        check_predictions(receipt, problems, case_preds_early) if receipt is not None else {}
    )
    scores = check_scores(receipt, problems, case_root_early) if receipt is not None else {}
    case_root = _case_root(receipt, args.condition_receipt)
    case_preds = load_case_predictions(case_root) if case_root else None
    _SEAL_HINT["count"] = sum(1 for p in (case_preds or []) if p.get("_sealed"))
    circ = check_anticircularity(args.generator, problems)
    seals = check_seals(receipt, problems) if receipt is not None else {}
    if case_preds and not any(p.get("_sealed") for p in case_preds):
        problems.append(
            {"rule": "unsealed_case_bundles", "detail": "case bundles are not marked sealed"}
        )

    out = {
        "schema": "persona_dream.pctom_measurement_validity_v2.v1",
        "created_at": utc_now(),
        "status": "PASS_MEASUREMENT_VALIDITY_V2" if not problems
        else "BLOCKED_MEASUREMENT_VALIDITY_V2",
        "mocked": False,
        "live": False,
        "llm_judge_used": False,
        "inputs": {
            "corpus": str(args.corpus) if args.corpus else None,
            "condition_receipt": str(args.condition_receipt) if args.condition_receipt else None,
            "generator": str(args.generator) if args.generator else None,
        },
        "ground_truth_labels": labels,
        "predictions": predictions,
        "scoring": scores,
        "anticircularity": circ,
        "seals": seals,
        "problems": problems,
        "problem_count": len(problems),
        "claims": {
            "proves": [
                "the measurement path can produce a CD loss and its predictions "
                "depend on episode evidence"
            ]
            if not problems
            else [],
            "does_not_prove": [
                "that counterfactual dreaming helps",
                "that the corpus is representative",
                "anything about live Tau behaviour",
            ],
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--condition-receipt", type=Path)
    parser.add_argument(
        "--generator",
        type=Path,
        default=Path(__file__).resolve().parent / "build_social_episode_corpus.py",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    receipt = run(args)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"measurement validity v2: {receipt['status']}")
        lbl = receipt.get("ground_truth_labels") or {}
        if lbl:
            print(f"  labels: {lbl.get('total')} total, by value {lbl.get('by_value')}")
        pred = receipt.get("predictions") or {}
        if pred:
            print(f"  distinct distributions: {pred.get('distinct_distributions_by_condition')}")
        sc = receipt.get("scoring") or {}
        if sc:
            print(f"  win/tie/loss: {sc.get('win_tie_loss_by_condition')}")
        for row in receipt["problems"]:
            print(f"  {row['rule']}: {row['detail']}")
    return 1 if receipt["problems"] and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
