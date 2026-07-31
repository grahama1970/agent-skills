#!/usr/bin/env python3
"""Analyze Persona Dream blinded listener responses after human collection.

This script is deliberately stricter than the stimulus validator. The validator
can say the bundle is ready for raters; this analyzer cannot pass until there
are enough valid human response rows and a separate signed human interpretation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"
DEFAULT_REQUIRED_RATERS = 20


def _load_validator():
    path = ROOT / "scripts" / "validate_blinded_listener_study.py"
    spec = importlib.util.spec_from_file_location("validate_blinded_listener_study", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"could not load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def yes(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "yes")


def wilson_interval(successes: int, n: int, z: float = 1.96) -> dict[str, Any]:
    if n <= 0:
        return {
            "method": "Wilson score interval, 95%",
            "successes": successes,
            "n": n,
            "proportion": None,
            "lower": None,
            "upper": None,
        }
    phat = successes / n
    denom = 1 + (z * z) / n
    centre = phat + (z * z) / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + (z * z) / (4 * n)) / n)
    return {
        "method": "Wilson score interval, 95%",
        "successes": successes,
        "n": n,
        "proportion": round(phat, 6),
        "lower": round((centre - margin) / denom, 6),
        "upper": round((centre + margin) / denom, 6),
    }


def validate_signed_interpretation(path: Path, *, receipt_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, ["signed_human_interpretation_missing"]
    try:
        doc = load_json(path)
    except Exception as exc:  # noqa: BLE001 - malformed signatures must fail closed
        return None, [f"signed_human_interpretation_invalid_json:{type(exc).__name__}"]
    errors: list[str] = []
    if doc.get("schema") != "persona_dream.blinded_listener_study_signed_interpretation.v1":
        errors.append("signed_human_interpretation_invalid:schema")
    for field in ("signed_by", "signed_at", "interpretation"):
        if not isinstance(doc.get(field), str) or not doc[field].strip():
            errors.append(f"signed_human_interpretation_invalid:{field}")
    acknowledgements = doc.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        errors.append("signed_human_interpretation_invalid:acknowledgements")
    else:
        for field in ("human_raters_only", "no_llm_judge", "no_agent_self_rating", "raw_counts_reviewed"):
            if acknowledgements.get(field) is not True:
                errors.append(f"signed_human_interpretation_invalid:acknowledgement:{field}")
    expected_receipt_sha = doc.get("analysis_receipt_sha256")
    if expected_receipt_sha not in (None, "", sha_file(receipt_path) if receipt_path.is_file() else None):
        errors.append("signed_human_interpretation_invalid:analysis_receipt_sha256_mismatch")
    return doc, errors


def response_by_stimulus(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("stimulus_id")): item for item in row.get("responses", []) if isinstance(item, dict)}


def summarize_responses(
    rows: list[dict[str, Any]],
    *,
    prereg: dict[str, Any],
    valid_row_indexes: set[int],
) -> dict[str, Any]:
    manifest_by_id = {
        str(item["stimulus_id"]): str(item["condition"])
        for item in prereg.get("presentation_manifest") or []
        if item.get("stimulus_id") and item.get("condition")
    }
    tone_by_condition = {
        str(stimulus["condition"]): str((stimulus.get("voice_delivery") or {}).get("tone"))
        for stimulus in prereg.get("stimuli") or []
        if stimulus.get("condition")
    }
    stimulus_by_condition = {condition: sid for sid, condition in manifest_by_id.items()}
    dream_condition = "dream"
    dream_tone = tone_by_condition.get(dream_condition)
    adversarial_stimulus = stimulus_by_condition.get("adversarial")

    included_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if idx not in valid_row_indexes:
            continue
        by_stimulus = response_by_stimulus(row)
        adversarial = by_stimulus.get(str(adversarial_stimulus))
        inattentive = bool(
            adversarial
            and dream_tone
            and adversarial.get("target_emotion_choice", adversarial.get("target_emotion")) == dream_tone
        )
        target = excluded_rows if inattentive else included_rows
        target.append(row)

    condition_rows: dict[str, list[dict[str, Any]]] = {condition: [] for condition in tone_by_condition}
    for row in included_rows:
        by_stimulus = response_by_stimulus(row)
        for stimulus_id, condition in manifest_by_id.items():
            response = by_stimulus.get(stimulus_id)
            if response:
                condition_rows.setdefault(condition, []).append(response)

    by_condition: dict[str, Any] = {}
    for condition, responses in sorted(condition_rows.items()):
        expected_tone = tone_by_condition.get(condition)
        n = len(responses)
        target_success = sum(
            1
            for response in responses
            if response.get("target_emotion_choice", response.get("target_emotion")) == expected_tone
        )
        identity_yes = sum(1 for response in responses if yes(response.get("embry_identity")))
        content_yes = sum(1 for response in responses if yes(response.get("content_equivalent")))
        identity_confidence = [
            response["identity_confidence"]
            for response in responses
            if isinstance(response.get("identity_confidence"), int) and not isinstance(response.get("identity_confidence"), bool)
        ]
        naturalness = [
            response["naturalness"]
            for response in responses
            if isinstance(response.get("naturalness"), int) and not isinstance(response.get("naturalness"), bool)
        ]
        preference_ranks = [
            response["preference_rank"]
            for response in responses
            if isinstance(response.get("preference_rank"), int) and not isinstance(response.get("preference_rank"), bool)
        ]
        by_condition[condition] = {
            "n": n,
            "expected_tone": expected_tone,
            "target_emotion_recognition": wilson_interval(target_success, n),
            "embry_identity_yes": wilson_interval(identity_yes, n),
            "content_equivalent_yes": wilson_interval(content_yes, n),
            "identity_confidence_mean": round(sum(identity_confidence) / len(identity_confidence), 6)
            if identity_confidence
            else None,
            "naturalness_mean": round(sum(naturalness) / len(naturalness), 6) if naturalness else None,
            "preference_rank_counts": {
                str(rank): preference_ranks.count(rank) for rank in sorted(set(preference_ranks))
            },
        }

    return {
        "valid_human_raters": len({str(row.get("rater_id")) for row in rows if row.get("rater_id")}),
        "included_human_raters": len({str(row.get("rater_id")) for row in included_rows if row.get("rater_id")}),
        "excluded_by_preregistered_attention_rule": [
            str(row.get("rater_id")) for row in excluded_rows if row.get("rater_id")
        ],
        "attention_rule": (
            "Exclude a rater only if the adversarial condition is judged as the target emotion of the dream condition."
        ),
        "by_condition": by_condition,
        "primary_measure": {
            "condition": "dream",
            "measure": "target_emotion_recognition",
            "result": by_condition.get("dream", {}).get("target_emotion_recognition"),
        },
    }


#: v2 (#1126): the primary analysis is intention-to-treat. The only permitted
#: rater flag is an attention check that never reads an emotion judgment.
ATTENTION_FIELD = "attention_final_word"


def attention_flags(rows: list[dict[str, Any]], expected_word: str) -> dict[str, bool]:
    """True means the rater failed the independent content-recall check.

    Reads ONLY ``attention_final_word``. Emotion, identity, naturalness, and
    preference judgments must never influence this flag; #1126 exists because
    the v1 rule excluded raters on the primary outcome itself.
    """
    expected = expected_word.strip().lower().strip(".,!?")
    flags: dict[str, bool] = {}
    for row in rows:
        rater_id = str(row.get("rater_id") or "")
        if not rater_id:
            continue
        answer = str(row.get(ATTENTION_FIELD) or "").strip().lower().strip(".,!?")
        flags[rater_id] = answer != expected
    return flags


def summarize_responses_v2(
    rows: list[dict[str, Any]],
    *,
    prereg: dict[str, Any],
    valid_row_indexes: set[int],
) -> dict[str, Any]:
    """v2 analysis: every valid rater is in the primary denominator.

    The v1 adversarial-tone exclusion was outcome-dependent selection — a rater
    who hears the cheerful adversarial file as the dream tone is evidence the
    affect channel is weak, not a discardable row. Attention-check exclusion is
    reported as a separately labeled sensitivity analysis only.
    """
    expected_word = str(
        ((prereg.get("attention_check") or {}).get("correct_answer")) or ""
    )
    valid_rows = [row for idx, row in enumerate(rows, start=1) if idx in valid_row_indexes]
    flags = attention_flags(valid_rows, expected_word) if expected_word else {}
    failed_ids = sorted(rid for rid, failed in flags.items() if failed)

    primary_rows = valid_rows
    sensitivity_rows = [row for row in valid_rows if not flags.get(str(row.get("rater_id") or ""), False)]
    primary_conditions = _itt_conditions(primary_rows, prereg)
    sensitivity_conditions = _itt_conditions(sensitivity_rows, prereg)
    return {
        "analysis_policy": "intention_to_treat_primary_v2",
        "valid_human_raters": len({str(row.get("rater_id")) for row in valid_rows if row.get("rater_id")}),
        "primary": {
            "label": "PRIMARY intention-to-treat: all valid raters included; no outcome-based exclusion",
            "included_rater_ids": sorted(
                {str(row.get("rater_id")) for row in primary_rows if row.get("rater_id")}
            ),
            "excluded_rater_ids": [],
            "denominator": len({str(row.get("rater_id")) for row in primary_rows if row.get("rater_id")}),
            "by_condition": primary_conditions,
            "primary_measure": {
                "condition": "dream",
                "measure": "target_emotion_recognition",
                "result": primary_conditions.get("dream", {}).get("target_emotion_recognition"),
            },
        },
        "sensitivity_attention_check_only": {
            "label": "SENSITIVITY ONLY: attention-check failures excluded; never the primary result",
            "attention_check_field": ATTENTION_FIELD,
            "expected_answer_normalized": expected_word.strip().lower().strip(".,!?"),
            "excluded_rater_ids": failed_ids,
            "exclusion_reasons": {rid: "attention_check_failed" for rid in failed_ids},
            "denominator": len({str(row.get("rater_id")) for row in sensitivity_rows if row.get("rater_id")}),
            "by_condition": sensitivity_conditions,
        },
    }


def _itt_conditions(rows: list[dict[str, Any]], prereg: dict[str, Any]) -> dict[str, Any]:
    """Per-condition summaries over the given rows with no exclusions."""
    manifest_by_id = {
        str(item["stimulus_id"]): str(item["condition"])
        for item in prereg.get("presentation_manifest") or []
        if item.get("stimulus_id") and item.get("condition")
    }
    tone_by_condition = {
        str(stimulus["condition"]): str((stimulus.get("voice_delivery") or {}).get("tone"))
        for stimulus in prereg.get("stimuli") or []
        if stimulus.get("condition")
    }
    condition_rows: dict[str, list[dict[str, Any]]] = {condition: [] for condition in tone_by_condition}
    for row in rows:
        by_stimulus = response_by_stimulus(row)
        for stimulus_id, condition in manifest_by_id.items():
            response = by_stimulus.get(stimulus_id)
            if response:
                condition_rows.setdefault(condition, []).append(response)
    by_condition: dict[str, Any] = {}
    for condition, responses in sorted(condition_rows.items()):
        expected_tone = tone_by_condition.get(condition)
        n = len(responses)
        target_success = sum(
            1
            for response in responses
            if response.get("target_emotion_choice", response.get("target_emotion")) == expected_tone
        )
        identity_yes = sum(1 for response in responses if yes(response.get("embry_identity")))
        by_condition[condition] = {
            "n": n,
            "expected_tone": expected_tone,
            "target_emotion_recognition": wilson_interval(target_success, n),
            "embry_identity_yes": wilson_interval(identity_yes, n),
        }
    return by_condition


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = args.study_dir
    prereg_v2_path = study_dir / "PREREGISTRATION_V2.json"
    v2_mode = prereg_v2_path.is_file()
    prereg_path = prereg_v2_path if v2_mode else study_dir / "PREREGISTRATION.json"
    responses_path = study_dir / ("responses_v2.jsonl" if v2_mode else "responses.jsonl")
    stimulus_validation_path = study_dir / "STIMULUS_VALIDATION_RECEIPT.json"
    signed_path = args.signed_interpretation or (study_dir / "SIGNED_INTERPRETATION.json")
    failed_gates: list[str] = []

    prereg = load_json(prereg_path) if prereg_path.is_file() else {}
    if not prereg:
        failed_gates.append("preregistration_exists")

    stimulus_validation = load_json(stimulus_validation_path) if stimulus_validation_path.is_file() else {}
    if not stimulus_validation_path.is_file():
        failed_gates.append("stimulus_validation_receipt_exists")
    elif not str(stimulus_validation.get("status") or "").startswith("PASS_"):
        failed_gates.append("stimulus_validation_receipt_pass")

    responses, jsonl_errors = validator.load_jsonl(responses_path)
    failed_gates.extend(jsonl_errors)
    expected_stimulus_ids = {
        str(item.get("stimulus_id") or "")
        for item in prereg.get("presentation_manifest") or []
        if item.get("stimulus_id")
    }
    allowed_tones = {
        str(((stimulus.get("voice_delivery") or {}).get("tone")) or "")
        for stimulus in prereg.get("stimuli") or []
        if ((stimulus.get("voice_delivery") or {}).get("tone"))
    }
    response_summary = validator.validate_responses(
        responses,
        args.required_raters,
        expected_stimulus_ids=expected_stimulus_ids,
        allowed_tones=allowed_tones,
    )
    failed_gates.extend(response_summary["response_errors"])
    if not response_summary["enough_human_responses"]:
        failed_gates.append("human_responses_complete")
    if response_summary["duplicate_rater_ids"]:
        failed_gates.append("rater_ids_unique")

    valid_row_indexes: set[int] = set()
    for line_no, row in enumerate(responses, start=1):
        row_errors = validator.validate_response_row(
            row,
            expected_stimulus_ids=expected_stimulus_ids,
            allowed_tones=allowed_tones,
            line_no=line_no,
        )
        if not row_errors and row.get("rater_id"):
            valid_row_indexes.add(line_no)

    if v2_mode:
        response_analysis = summarize_responses_v2(
            responses, prereg=prereg, valid_row_indexes=valid_row_indexes
        )
    else:
        response_analysis = summarize_responses(responses, prereg=prereg, valid_row_indexes=valid_row_indexes)
    signed_doc, signed_errors = validate_signed_interpretation(signed_path, receipt_path=args.out)
    failed_gates.extend(signed_errors)

    status = "PASS_BLINDED_LISTENER_STUDY_ANALYSIS" if not failed_gates else "BLOCKED_BLINDED_LISTENER_STUDY_ANALYSIS"
    receipt = {
        "schema": "persona_dream.blinded_listener_study_analysis.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": False,
        "study_dir": rel(study_dir),
        "design_version": "v2" if v2_mode else "v1",
        "preregistration": artifact(prereg_path),
        "stimulus_validation_receipt": artifact(stimulus_validation_path),
        "responses": artifact(responses_path),
        "signed_human_interpretation": artifact(signed_path),
        "response_summary": response_summary,
        "response_analysis": response_analysis,
        "signed_interpretation_summary": {
            "present": signed_doc is not None,
            "signed_by": signed_doc.get("signed_by") if signed_doc else None,
            "signed_at": signed_doc.get("signed_at") if signed_doc else None,
        },
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "raw blinded-listener counts were computed from enough valid append-only human response rows",
                "the analysis is accompanied by a separate signed human interpretation",
            ]
            if status.startswith("PASS_")
            else [],
            "does_not_prove": [
                "general voice identity across long sessions",
                "emotion perception beyond this preregistered stimulus set",
                "PCTOM-R planning benefit",
                "SPARTA production conversation-service consumption",
                "Persona Dream immutable-goal completion by itself",
            ],
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "RECEIPT.json")
    parser.add_argument("--signed-interpretation", type=Path, default=None)
    parser.add_argument("--required-raters", type=int, default=DEFAULT_REQUIRED_RATERS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": rel(args.out),
        "responses": receipt["response_summary"],
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
