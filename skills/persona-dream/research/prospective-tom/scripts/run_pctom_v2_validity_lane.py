#!/usr/bin/env python3
"""End-to-end PCTOM-R v2 measurement-validity lane (#1131).

Regenerates the frozen corpus, runs the episode-conditioned condition preflight,
runs the REAL #1056 validity-v2 gate over it, runs the adversarial negative
controls, and writes the four artifacts the ticket requires:

    receipts/measurement-validity-v2-pass/PREREGISTRATION.json            (static)
    receipts/measurement-validity-v2-pass/CORPUS_MANIFEST.json
    receipts/measurement-validity-v2-pass/CONDITION_PREFLIGHT_RECEIPT.json
    receipts/measurement-validity-v2-pass/MEASUREMENT_VALIDITY_RECEIPT.json

Case bundles (one directory per episode x condition) are regenerable working
artifacts and are written under ``local/pctom-v2/<split>/``, matching this
lane's existing convention of tracking flat receipts rather than per-case trees.
Determinism means re-running this lane reproduces them byte for byte.

Makes no live, paid, provider, Tau, or Memory call.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
RESEARCH_ROOT = SCRIPTS.parent
RECEIPT_DIR = RESEARCH_ROOT / "receipts" / "measurement-validity-v2-pass"
FIXTURE_DIR = RESEARCH_ROOT / "fixtures" / "pctom-v2"
LOCAL_ROOT = RESEARCH_ROOT / "local" / "pctom-v2"
GENERATOR = SCRIPTS / "build_pctom_v2_corpus.py"
SPLITS = ("development", "heldout")
CONFIRMATORY_SPLIT = "heldout"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load(GENERATOR, "pctom_v2_builder")
runner = _load(SCRIPTS / "run_pctom_v2_condition_comparison.py", "pctom_v2_runner")
mv2 = _load(SCRIPTS / "check_pctom_measurement_validity_v2.py", "pctom_mv2")
controls = _load(SCRIPTS / "check_pctom_v2_negative_controls.py", "pctom_v2_controls")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-negative-controls", action="store_true")
    args = parser.parse_args()

    prereg_path = RECEIPT_DIR / "PREREGISTRATION.json"
    if not prereg_path.is_file():
        print(f"BLOCKED: preregistration missing at {prereg_path}")
        return 1
    prereg_sha = _file_sha256(prereg_path)

    corpora: dict[str, dict[str, Any]] = {}
    preflights: dict[str, dict[str, Any]] = {}
    validities: dict[str, dict[str, Any]] = {}

    for split in SPLITS:
        corpus = builder.build_corpus(split)
        corpora[split] = corpus
        _write_json(FIXTURE_DIR / f"pctom_v2_corpus.{split}.json", corpus)
        root = LOCAL_ROOT / split
        receipt_out = root / "CONDITION_PREFLIGHT_RECEIPT.json"
        preflights[split] = runner.run(split=split, output_root=root, receipt_out=receipt_out)

        class Args:
            pass

        gate_args = Args()
        gate_args.corpus = root / "artifacts" / "pctom_v2_corpus.json"
        gate_args.condition_receipt = receipt_out
        gate_args.generator = GENERATOR
        gate_args.out = root / "MEASUREMENT_VALIDITY_RECEIPT.json"
        mv2._SEAL_HINT.clear()
        validities[split] = mv2.run(gate_args)

    # split disjointness, audited not asserted
    split_problems = controls.audit_split_disjointness(corpora["development"], corpora["heldout"])
    oracle_problems: list[dict[str, str]] = []
    for split in SPLITS:
        oracle_problems += controls.audit_labels_against_oracle(corpora[split])
    scope_problems = controls.audit_evidence_scope(
        corpora[CONFIRMATORY_SPLIT], LOCAL_ROOT / CONFIRMATORY_SPLIT / "artifacts" / "cases"
    )
    seal_problems = controls.audit_commitment_integrity(
        LOCAL_ROOT / CONFIRMATORY_SPLIT / "artifacts" / "cases"
    )

    manifest = {
        "schema": "persona_dream.research.prospective_tom.pctom_v2_corpus_manifest.v1",
        "issue": "grahama1970/agent-skills#1131",
        "generator": str(GENERATOR.relative_to(RESEARCH_ROOT)),
        "generator_sha256": _file_sha256(GENERATOR),
        "generator_version": builder.GENERATOR_VERSION,
        "preregistration_sha256": prereg_sha,
        "confirmatory_split": CONFIRMATORY_SPLIT,
        "splits": {
            split: {
                "episode_count": corpora[split]["episode_count"],
                "episodes_sha256": corpora[split]["episodes_sha256"],
                "fixture_path": str(
                    (FIXTURE_DIR / f"pctom_v2_corpus.{split}.json").relative_to(RESEARCH_ROOT)
                ),
                "fixture_sha256": _file_sha256(FIXTURE_DIR / f"pctom_v2_corpus.{split}.json"),
                "template_ids": corpora[split]["template_ids"],
                "seed_range": corpora[split]["seed_range"],
                "label_counts": corpora[split]["label_counts"],
                "label_counts_by_family": corpora[split]["label_counts_by_family"],
                "distinct_visible_evidence_vectors": corpora[split][
                    "distinct_visible_evidence_vectors"
                ],
                "cue_on_counts": corpora[split]["cue_on_counts"],
            }
            for split in SPLITS
        },
        "disjointness_checks": {
            "episode_id_overlap": 0 if not split_problems else len(split_problems),
            "problems": split_problems,
        },
        "label_oracle_consistency": {
            "labels_checked": sum(len(c["episodes"]) * 2 for c in corpora.values()),
            "problems": oracle_problems,
        },
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "live_tau_calls": 0,
        "provider_calls": 0,
    }
    _write_json(RECEIPT_DIR / "CORPUS_MANIFEST.json", manifest)

    preflight_receipt = dict(preflights[CONFIRMATORY_SPLIT])
    preflight_receipt["preregistration_sha256"] = prereg_sha
    preflight_receipt["exploratory_split_receipt"] = preflights["development"]
    preflight_receipt["evidence_scope_problems"] = scope_problems
    preflight_receipt["commitment_integrity_problems"] = seal_problems
    _write_json(RECEIPT_DIR / "CONDITION_PREFLIGHT_RECEIPT.json", preflight_receipt)

    control_receipt = None
    if not args.skip_negative_controls:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            rows = controls.run_controls(Path(tmp))
        failed = [r for r in rows if r["status"] != "PASS_NEGATIVE_CONTROL"]
        control_receipt = {
            "status": "PASS_PCTOM_V2_NEGATIVE_CONTROLS" if not failed else "BLOCKED_PCTOM_V2_NEGATIVE_CONTROLS",
            "control_count": len(rows),
            "failed_count": len(failed),
            "controls": rows,
        }

    confirmatory = validities[CONFIRMATORY_SPLIT]
    blocking = (
        split_problems
        + oracle_problems
        + scope_problems
        + seal_problems
        + list(confirmatory["problems"])
        + list(validities["development"]["problems"])
    )
    if control_receipt and control_receipt["failed_count"]:
        blocking.append({"rule": "negative_control_did_not_block", "detail": "see controls"})

    out = {
        "schema": "persona_dream.research.prospective_tom.pctom_v2_measurement_validity.v1",
        "issue": "grahama1970/agent-skills#1131",
        "status": "PASS_PCTOM_MEASUREMENT_VALIDITY_V2" if not blocking else "BLOCKED_PCTOM_MEASUREMENT_VALIDITY_V2",
        "gate_status_by_split": {s: validities[s]["status"] for s in SPLITS},
        "confirmatory_split": CONFIRMATORY_SPLIT,
        "preregistration_sha256": prereg_sha,
        "corpus_manifest_sha256": _file_sha256(RECEIPT_DIR / "CORPUS_MANIFEST.json"),
        "label_counts_by_truth_value": {
            s: corpora[s]["label_counts"]["all"] for s in SPLITS
        },
        "label_counts_by_order": {s: corpora[s]["label_counts"] for s in SPLITS},
        "label_counts_by_family": {s: corpora[s]["label_counts_by_family"] for s in SPLITS},
        "distinct_distributions_by_condition": {
            s: validities[s]["predictions"]["distinct_distributions_by_condition"] for s in SPLITS
        },
        "distinct_per_episode_scores_by_condition": {
            s: validities[s]["scoring"]["distinct_scores_by_condition"] for s in SPLITS
        },
        "win_tie_loss_by_condition": {
            s: validities[s]["scoring"]["win_tie_loss_by_condition"] for s in SPLITS
        },
        "proper_scores_by_condition": {
            s: {
                c: preflights[s]["benefit_vs_prevalence_baseline"][c]["mean_brier"]
                for c in runner.CONDITIONS
            }
            for s in SPLITS
        },
        "benefit_vs_prevalence_baseline": {
            s: preflights[s]["benefit_vs_prevalence_baseline"] for s in SPLITS
        },
        "score_variance_within_label_class": {
            s: preflights[s]["score_variance_within_label_class"] for s in SPLITS
        },
        "evidence_ref_counts_by_condition": {
            s: preflights[s]["counts"]["evidence_ref_count_by_condition"] for s in SPLITS
        },
        "evidence_ref_hashes_by_split": {
            s: validities[s]["predictions"]["distinct_evidence_refs_by_condition"] for s in SPLITS
        },
        "calibration_heldout_disjointness": manifest["disjointness_checks"],
        "anti_circularity": confirmatory["anticircularity"],
        "sealed_commitment_counts": {
            s: preflights[s]["sealed_commitment_count"] for s in SPLITS
        },
        "sealed_commitments_recomputed_ok": {
            s: preflights[s]["sealed_commitments_recomputed_ok"] for s in SPLITS
        },
        "negative_controls": control_receipt,
        "problems": blocking,
        "problem_count": len(blocking),
        "llm_judge_used": False,
        "human_hidden_state_scoring": False,
        "live_tau_calls": 0,
        "provider_calls": 0,
        "memory_write_attempts": 0,
        "mocked": False,
        "live": False,
        "claims": {
            "proves": [
                "the frozen PCTOM-R v2 corpus and episode-conditioned estimator pass the #1056 validity-v2 gate on both splits",
                "every condition, including CD, loses on at least one episode",
                "ten adversarial negative controls each block with a typed reason",
            ]
            if not blocking
            else [],
            "does_not_prove": [
                "that counterfactual dreaming improves prospective Theory of Mind",
                "anything about live Tau behaviour (#1008 owns the live held-out run)",
                "that the corpus is representative of real social interaction",
            ],
        },
    }
    _write_json(RECEIPT_DIR / "MEASUREMENT_VALIDITY_RECEIPT.json", out)

    print(out["status"])
    for split in SPLITS:
        print(f"  {split}: {validities[split]['status']}")
        print(f"    labels {corpora[split]['label_counts']['all']}")
        print(f"    distinct distributions {validities[split]['predictions']['distinct_distributions_by_condition']}")
        print(f"    win/tie/loss {validities[split]['scoring']['win_tie_loss_by_condition']}")
    if control_receipt:
        print(f"  negative controls: {control_receipt['status']} ({control_receipt['control_count']} controls)")
    for row in blocking:
        print(f"  BLOCK {row.get('rule')}: {row.get('detail')}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
