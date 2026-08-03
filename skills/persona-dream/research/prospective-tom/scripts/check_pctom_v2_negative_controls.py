#!/usr/bin/env python3
"""Adversarial negative controls for the PCTOM-R v2 corpus and estimator.

A gate that only ever says PASS is not a gate.  Each control below deliberately
reintroduces one of the defects #1056 found (or one the ticket names), runs the
REAL ``check_pctom_measurement_validity_v2`` gate and/or a corpus auditor over
it, and requires a BLOCK with a typed reason.

Two classes of control:

* **gate-visible** -- the shipped validity-v2 gate rejects them by itself.
* **auditor-visible** -- defects the validity-v2 gate cannot see (a label that
  contradicts the simulator, a split overlap, hidden-state leakage into CD, a
  commitment altered after reveal).  These are caught by the auditors in this
  module, which are part of the v2 preflight contract.

No control mutates the shipped corpus on disk; each builds its fixture in a
temporary directory.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load(SCRIPTS / "build_pctom_v2_corpus.py", "pctom_v2_builder")
runner = _load(SCRIPTS / "run_pctom_v2_condition_comparison.py", "pctom_v2_runner")
mv2 = _load(SCRIPTS / "check_pctom_measurement_validity_v2.py", "pctom_mv2")


# --------------------------------------------------------------------------
# auditors: defects the validity-v2 gate cannot see on its own
# --------------------------------------------------------------------------
def audit_labels_against_oracle(corpus: dict[str, Any]) -> list[dict[str, str]]:
    """Every label must equal what the oracle says about the hidden state."""
    problems = []
    for episode in corpus["episodes"]:
        hidden = episode["hidden_world_state"]
        args = (hidden["state_changed"], hidden["counterpart_informed"], hidden["state_ambiguous"])
        expected = {1: builder.oracle_order1(*args), 2: builder.oracle_order2(*args)}
        for label in episode["ground_truth_tom_labels"]:
            want = expected[int(label["perspective_order"])]
            if label["value"] != want:
                problems.append(
                    {
                        "rule": "label_contradicts_simulator_truth",
                        "detail": f"{label['label_id']} says {label['value']} but the oracle "
                        f"on hidden state {args} says {want}",
                    }
                )
    return problems


def audit_split_disjointness(dev: dict[str, Any], heldout: dict[str, Any]) -> list[dict[str, str]]:
    """Development and heldout must share no episode id, seed, or template."""
    problems = []
    for field, key in (("episode_id", "episode_id"), ("simulator_seed", "simulator_seed"), ("template_id", "template_id")):
        a = {e[key] for e in dev["episodes"]}
        b = {e[key] for e in heldout["episodes"]}
        overlap = sorted(str(x) for x in (a & b))
        if overlap:
            problems.append(
                {
                    "rule": "heldout_overlaps_development",
                    "detail": f"{field} overlap between splits: {overlap[:5]} ({len(overlap)} total)",
                }
            )
    return problems


def audit_evidence_scope(corpus: dict[str, Any], case_root: Path) -> list[dict[str, str]]:
    """No condition may cite a withheld (hidden-state) field, and every
    condition must cite the same *kind* of source with the same reveal boundary.
    """
    problems = []
    withheld = set(corpus["episodes"][0]["visible_evidence"]["withheld_fields"])
    for episode_dir in sorted(case_root.iterdir()):
        if not episode_dir.is_dir():
            continue
        for cond_dir in sorted(episode_dir.iterdir()):
            bundle_path = cond_dir / "tom_belief_distribution_bundle.json"
            if not bundle_path.is_file():
                continue
            bundle = json.loads(bundle_path.read_text())
            for dist in bundle["distributions"]:
                for ref in dist["evidence_refs"]:
                    tail = str(ref.get("source_id", "")).split(":", 1)[-1]
                    if any(tail.startswith(field) for field in withheld):
                        problems.append(
                            {
                                "rule": "hidden_state_leakage_into_condition",
                                "detail": f"{bundle['condition']} cites withheld field {tail!r} "
                                f"in {dist['hypothesis_id']}",
                            }
                        )
    return problems


def audit_commitment_integrity(case_root: Path) -> list[dict[str, str]]:
    """The sealed commitment hash must recompute from the stored distributions."""
    problems = []
    for episode_dir in sorted(case_root.iterdir()):
        if not episode_dir.is_dir():
            continue
        for cond_dir in sorted(episode_dir.iterdir()):
            bundle_path = cond_dir / "tom_belief_distribution_bundle.json"
            commit_path = cond_dir / "tom_prediction_commitment_bundle.json"
            if not (bundle_path.is_file() and commit_path.is_file()):
                continue
            bundle = json.loads(bundle_path.read_text())
            commitment = json.loads(commit_path.read_text())
            recomputed = runner._stable_json_sha256(
                {
                    "episode_id": bundle["episode_id"],
                    "condition": bundle["condition"],
                    "outcome_visible": False,
                    "distributions": bundle["distributions"],
                }
            )
            if recomputed != commitment["commitment_hash"]:
                problems.append(
                    {
                        "rule": "commitment_changed_after_reveal",
                        "detail": f"{bundle['episode_id']}:{bundle['condition']} sealed hash "
                        f"{commitment['commitment_hash'][:23]}... does not recompute",
                    }
                )
    return problems


# --------------------------------------------------------------------------
# control fixtures
# --------------------------------------------------------------------------
def _materialize(root: Path, split: str = "development") -> tuple[Path, Path, dict[str, Any]]:
    receipt_out = root / "CONDITION_PREFLIGHT_RECEIPT.json"
    receipt = runner.run(split=split, output_root=root, receipt_out=receipt_out)
    corpus_path = root / "artifacts" / "pctom_v2_corpus.json"
    return corpus_path, receipt_out, receipt


def _gate(corpus_path: Path, receipt_path: Path, generator: Path) -> dict[str, Any]:
    class Args:
        pass

    args = Args()
    args.corpus = corpus_path
    args.condition_receipt = receipt_path
    args.generator = generator
    args.out = None
    mv2._SEAL_HINT.clear()
    return mv2.run(args)


def _rules(result: dict[str, Any]) -> set[str]:
    return {p["rule"] for p in result["problems"]}


def _rewrite_all_distributions(case_root: Path, conditions: set[str], flat: list[dict[str, Any]]) -> None:
    for episode_dir in sorted(case_root.iterdir()):
        for cond_dir in sorted(episode_dir.iterdir()):
            path = cond_dir / "tom_belief_distribution_bundle.json"
            bundle = json.loads(path.read_text())
            if bundle["condition"] not in conditions:
                continue
            for dist in bundle["distributions"]:
                dist["distribution"] = copy.deepcopy(flat)
            path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")


CONSTANT = [
    {"value": "TRUE", "probability": 0.5},
    {"value": "FALSE", "probability": 0.3},
    {"value": "UNKNOWN", "probability": 0.2},
]
PERFECT = [
    {"value": "TRUE", "probability": 1.0},
    {"value": "FALSE", "probability": 0.0},
    {"value": "UNKNOWN", "probability": 0.0},
]


def run_controls(tmp: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    generator = SCRIPTS / "build_pctom_v2_corpus.py"

    def record(name: str, expect: str, blocked: bool, rules: set[str], detail: str = "") -> None:
        results.append(
            {
                "control": name,
                "expected_rule": expect,
                "blocked": blocked,
                "typed_reasons": sorted(rules),
                "detail": detail,
                "status": "PASS_NEGATIVE_CONTROL" if blocked and expect in rules else "FAIL_NEGATIVE_CONTROL",
            }
        )

    # 0. positive control: the shipped path must PASS, or the controls prove nothing
    root = tmp / "positive"
    corpus_path, receipt_path, _ = _materialize(root)
    base = _gate(corpus_path, receipt_path, generator)
    results.append(
        {
            "control": "positive_control_shipped_path",
            "expected_rule": "(none)",
            "blocked": bool(base["problems"]),
            "typed_reasons": sorted(_rules(base)),
            "detail": base["status"],
            "status": "PASS_NEGATIVE_CONTROL" if base["status"] == "PASS_MEASUREMENT_VALIDITY_V2" else "FAIL_NEGATIVE_CONTROL",
        }
    )

    # 1. all labels collapse to one value
    root = tmp / "c1"
    corpus_path, receipt_path, _ = _materialize(root)
    corpus = json.loads(corpus_path.read_text())
    for ep in corpus["episodes"]:
        for lbl in ep["ground_truth_tom_labels"]:
            lbl["value"] = "TRUE"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n")
    got = _gate(corpus_path, receipt_path, generator)
    record("all_labels_collapse_to_one_value", "degenerate_ground_truth_labels", bool(got["problems"]), _rules(got))

    # 2. labels balanced but contradicting simulator truth
    root = tmp / "c2"
    corpus_path, receipt_path, _ = _materialize(root)
    corpus = json.loads(corpus_path.read_text())
    rotate = {"TRUE": "FALSE", "FALSE": "UNKNOWN", "UNKNOWN": "TRUE"}
    for ep in corpus["episodes"]:
        for lbl in ep["ground_truth_tom_labels"]:
            lbl["value"] = rotate[lbl["value"]]
    problems = audit_labels_against_oracle(corpus)
    record(
        "labels_balanced_but_contradict_simulator_truth",
        "label_contradicts_simulator_truth",
        bool(problems),
        {p["rule"] for p in problems},
        f"{len(problems)} labels contradict the oracle; the validity-v2 gate alone cannot see this",
    )

    # 3. one condition emits a constant table
    root = tmp / "c3"
    corpus_path, receipt_path, _ = _materialize(root)
    _rewrite_all_distributions(root / "artifacts" / "cases", {"CD"}, CONSTANT)
    got = _gate(corpus_path, receipt_path, generator)
    record("one_condition_emits_constant_table", "constant_prediction_distribution", bool(got["problems"]), _rules(got))

    # 4. prediction ignores agent-visible evidence (every condition constant)
    root = tmp / "c4"
    corpus_path, receipt_path, _ = _materialize(root)
    _rewrite_all_distributions(root / "artifacts" / "cases", set(runner.CONDITIONS), CONSTANT)
    got = _gate(corpus_path, receipt_path, generator)
    # NOTE: the per-episode score still varies here (the *truth* varies), so the
    # typed reason is the distribution rule, not the score rule.  That is the
    # gate behaving correctly: a constant predictor is caught upstream of scoring.
    record("prediction_ignores_visible_evidence", "constant_prediction_distribution", bool(got["problems"]), _rules(got))

    # 5. generator inspects expected winners / condition profiles
    root = tmp / "c5"
    corpus_path, receipt_path, _ = _materialize(root)
    bad_gen = root / "leaky_generator.py"
    bad_gen.write_text("from comparison import CONDITION_PROFILES\nexpected_winner = 'CD'\n")
    got = _gate(corpus_path, receipt_path, bad_gen)
    record("generator_inspects_condition_profiles", "corpus_generation_inspects_conditions", bool(got["problems"]), _rules(got))

    # 6. heldout overlaps development
    dev = builder.build_corpus("development")
    leaky_heldout = copy.deepcopy(dev)
    leaky_heldout["split"] = "heldout"
    problems = audit_split_disjointness(dev, leaky_heldout)
    record(
        "heldout_overlaps_development",
        "heldout_overlaps_development",
        bool(problems),
        {p["rule"] for p in problems},
        f"{len(problems)} overlapping identity fields",
    )

    # 7. CD receives a withheld field unavailable to M/R/D
    root = tmp / "c7"
    corpus_path, receipt_path, _ = _materialize(root)
    corpus = json.loads(corpus_path.read_text())
    case_root = root / "artifacts" / "cases"
    for episode_dir in sorted(case_root.iterdir()):
        cd_path = episode_dir / "CD" / "tom_belief_distribution_bundle.json"
        bundle = json.loads(cd_path.read_text())
        for dist in bundle["distributions"]:
            dist["evidence_refs"].append(
                {
                    "scope": "leaked",
                    "source_id": f"{bundle['episode_id']}:hidden_world_state.state_ambiguous",
                }
            )
        cd_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    problems = audit_evidence_scope(corpus, case_root)
    record(
        "cd_receives_withheld_hidden_state_field",
        "hidden_state_leakage_into_condition",
        bool(problems),
        {p["rule"] for p in problems},
        f"{len(problems)} leaked evidence refs",
    )

    # 8. commitment changed after reveal
    root = tmp / "c8"
    corpus_path, receipt_path, _ = _materialize(root)
    case_root = root / "artifacts" / "cases"
    first = sorted(case_root.iterdir())[0] / "CD" / "tom_belief_distribution_bundle.json"
    bundle = json.loads(first.read_text())
    bundle["distributions"][0]["distribution"] = copy.deepcopy(PERFECT)
    first.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    problems = audit_commitment_integrity(case_root)
    record(
        "commitment_changed_after_reveal",
        "commitment_changed_after_reveal",
        bool(problems),
        {p["rule"] for p in problems},
        f"{len(problems)} seals fail to recompute",
    )

    # 9. one condition cannot lose by construction
    root = tmp / "c9"
    corpus_path, receipt_path, _ = _materialize(root)
    case_root = root / "artifacts" / "cases"
    for episode_dir in sorted(case_root.iterdir()):
        cd_path = episode_dir / "CD" / "tom_belief_distribution_bundle.json"
        reveal = json.loads((episode_dir / "CD" / "tom_outcome_reveal.json").read_text())
        bundle = json.loads(cd_path.read_text())
        for dist in bundle["distributions"]:
            truth = reveal["hidden_state_labels"][dist["hypothesis_id"]]
            dist["distribution"] = [
                {"value": v, "probability": 1.0 if v == truth else 0.0}
                for v in ("TRUE", "FALSE", "UNKNOWN")
            ]
        cd_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    got = _gate(corpus_path, receipt_path, generator)
    record("one_condition_cannot_lose", "condition_cannot_lose", bool(got["problems"]), _rules(got))

    # 10. an LLM or human supplies hidden-state correctness
    root = tmp / "c10"
    corpus_path, receipt_path, _ = _materialize(root)
    receipt = json.loads(receipt_path.read_text())
    receipt["llm_judge_used"] = True
    receipt["human_hidden_state_scoring"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    got = _gate(corpus_path, receipt_path, generator)
    record("llm_or_human_supplies_hidden_state_correctness", "llm_judge_used", bool(got["problems"]), _rules(got))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        results = run_controls(Path(tmpdir))

    failed = [r for r in results if r["status"] != "PASS_NEGATIVE_CONTROL"]
    receipt = {
        "schema": "persona_dream.research.prospective_tom.pctom_v2_negative_controls.v1",
        "status": "PASS_PCTOM_V2_NEGATIVE_CONTROLS" if not failed else "BLOCKED_PCTOM_V2_NEGATIVE_CONTROLS",
        "control_count": len(results),
        "failed_count": len(failed),
        "controls": results,
        "llm_judge_used": False,
        "live_tau_calls": 0,
        "provider_calls": 0,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        for row in results:
            mark = "ok  " if row["status"] == "PASS_NEGATIVE_CONTROL" else "FAIL"
            print(f"  [{mark}] {row['control']} -> {row['typed_reasons'] or '(no problems)'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
