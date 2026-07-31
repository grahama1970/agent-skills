#!/usr/bin/env python3
"""Publish the v2 blinded listener-study preregistration (#1126) with a design receipt.

The v1 design had two defects that could bias the primary target-emotion
result: one fixed global presentation order for every rater, and an
outcome-dependent exclusion (a rater was dropped when the cheerful adversarial
stimulus was judged as the dream tone — exactly the confusion the study should
measure). v2 fixes both before the first human response is accepted:

- per-rater counterbalanced order from a Williams square over the four
  stimulus ids, assigned deterministically from the rater id (FNV-1a 32-bit
  over ``salt:rater_id``), reproducible by anyone from this file alone;
- an independent content-recall attention check (final word of the spoken
  sentence) that never reads an emotion judgment; primary analysis is
  intention-to-treat, attention exclusion is sensitivity-only;
- v1 artifacts are preserved untouched as historical; v2 responses go to a
  fresh ``responses_v2.jsonl`` so no row is mixed between designs.

The emitted STUDY_DESIGN_RECEIPT_V2.json is the machine-readable proof #1126
requires; it fails closed if any check regresses (fixed order restored,
outcome-based exclusion restored, condition labels leaking into the page, or
v1 human rows present before activation).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"

ORDER_SALT = "persona-dream-blinded-v2"

#: Williams square for four periods: every stimulus appears once per position
#: across the four sequences and every ordered adjacency occurs exactly once.
WILLIAMS_4 = (
    (0, 1, 3, 2),
    (1, 2, 0, 3),
    (2, 3, 1, 0),
    (3, 0, 2, 1),
)

FIXTURE_RATER_IDS = tuple(f"R{idx:02d}" for idx in range(1, 21))


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if not spec or not spec.loader:
        raise RuntimeError(f"could not load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fnv1a32(text: str) -> int:
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def order_for_rater(rater_id: str, stimulus_ids: list[str]) -> list[str]:
    """The single preregistered order rule, shared with the rater page JS."""
    sequence = WILLIAMS_4[fnv1a32(f"{ORDER_SALT}:{rater_id}") % len(WILLIAMS_4)]
    return [stimulus_ids[slot] for slot in sequence]


def build_preregistration_v2(prereg_v1: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    stimulus_ids = [
        str(item["stimulus_id"])
        for item in sorted(prereg_v1.get("presentation_manifest") or [], key=lambda it: int(it.get("slot") or 0))
    ]
    answer_text = str((prereg_v1.get("stimulus_source") or {}).get("answer_text") or "")
    final_word = answer_text.rstrip(".!? ").rsplit(" ", 1)[-1].lower() if answer_text else ""
    fixture_orders = {rid: order_for_rater(rid, stimulus_ids) for rid in FIXTURE_RATER_IDS}
    return {
        "schema": "persona_dream.blinded_listener_study.v2",
        "created_at": utc_now(),
        "status": "BLOCKED_AWAITING_HUMAN_RATERS",
        "mocked": False,
        "live": True,
        "supersedes": {
            "path": "reports/goal_v5/continuity/blinded_listener_study/PREREGISTRATION.json",
            "sha256": sha_file(study_dir / "PREREGISTRATION.json"),
            "note": "v1 is preserved unmodified as a historical artifact; its fixed global order and outcome-dependent exclusion are superseded by this file.",
        },
        "scope_statement": (
            "Four stimuli x 20 raters is a four-WAV feasibility pilot over these exact "
            "preregistered files. It does not validate any tone profile, rendering policy, "
            "or renderer across texts, seeds, or repeated synthesis."
        ),
        "blinding": str(prereg_v1.get("blinding") or ""),
        "presentation": {
            "rule": "per-rater counterbalanced order",
            "williams_square_slots": [list(row) for row in WILLIAMS_4],
            "order_salt": ORDER_SALT,
            "order_hash": "FNV-1a 32-bit over 'salt:rater_id', modulo 4, selecting one Williams sequence",
            "stimulus_ids_in_slot_order": stimulus_ids,
            "fixture_20_rater_orders": fixture_orders,
            "note": "The rater page derives the same order client-side from the typed rater id; no fixed global order exists in v2.",
        },
        "attention_check": {
            "type": "content_recall",
            "field": "attention_final_word",
            "question": "Type the final word of the spoken sentence (same sentence in every clip).",
            "correct_answer": final_word,
            "independence": (
                "The check reads only this field. It never reads target_emotion_choice, "
                "embry_identity, identity_confidence, naturalness, or preference_rank, so it "
                "cannot select raters on the primary outcome."
            ),
        },
        "analysis": {
            "primary": (
                "Intention-to-treat: every valid rater row is included in the primary "
                "analysis regardless of any judgment it contains. Report raw counts per "
                "condition per measure with Wilson 95% intervals. No LLM judge; no "
                "self-rating by the agent."
            ),
            "sensitivity_only": (
                "A separately labeled sensitivity analysis may exclude raters who fail the "
                "independent attention check. It is never the primary result."
            ),
            "retention": "Included and excluded rater ids, exclusion reasons, and both denominators are retained in the analysis receipt.",
        },
        "hypothesis": str((prereg_v1.get("preregistration") or {}).get("hypothesis") or ""),
        "primary_measure": "target-emotion recognition accuracy for the dream condition (intention-to-treat)",
        "measures_in_order": (prereg_v1.get("preregistration") or {}).get("measures_in_order") or [],
        "stopping_rule": "Fixed n=20 raters. No interim analysis, no extension after seeing results. A null or negative result is a valid outcome.",
        "presentation_manifest": prereg_v1.get("presentation_manifest") or [],
        "stimuli": prereg_v1.get("stimuli") or [],
        "stimulus_source": prereg_v1.get("stimulus_source") or {},
        "responses_path": "reports/goal_v5/continuity/blinded_listener_study/responses_v2.jsonl",
        "v1_response_isolation": "v1 responses.jsonl rows (if any ever existed) are never mixed into v2 analysis; v2 reads responses_v2.jsonl only.",
        "claims": {
            "proves": [],
            "does_not_prove": [
                "anything at all until human raters respond",
                "that any embedding score corresponds to perception",
                "any tone profile or renderer policy beyond these four exact WAV files",
            ],
        },
    }


def _synthetic_row(rater_id: str, prereg: dict[str, Any], *, adversarial_as_dream_tone: bool, attention_word: str) -> dict[str, Any]:
    manifest = prereg.get("presentation_manifest") or []
    tone_by_condition = {
        str(stimulus["condition"]): str((stimulus.get("voice_delivery") or {}).get("tone"))
        for stimulus in prereg.get("stimuli") or []
    }
    dream_tone = tone_by_condition.get("dream")
    responses = []
    for idx, item in enumerate(manifest, start=1):
        condition = str(item.get("condition"))
        tone = tone_by_condition.get(condition)
        if condition == "adversarial" and adversarial_as_dream_tone:
            tone = dream_tone
        responses.append(
            {
                "stimulus_id": str(item.get("stimulus_id")),
                "target_emotion_choice": tone,
                "embry_identity": "yes",
                "identity_confidence": 4,
                "naturalness": 4,
                "content_equivalent": "yes",
                "preference_rank": idx,
            }
        )
    return {
        "rater_id": rater_id,
        "created_at": "2026-07-31T00:00:00Z",
        "attention_final_word": attention_word,
        "responses": responses,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = args.study_dir
    validator = _load_module("validate_blinded_listener_study")
    analyzer = _load_module("analyze_blinded_listener_study")

    checks: dict[str, Any] = {}
    failed: list[str] = []

    prereg_v1_path = study_dir / "PREREGISTRATION.json"
    prereg_v1 = json.loads(prereg_v1_path.read_text(encoding="utf-8"))

    # Gate 1 — no v1 human rows may exist before v2 activation.
    v1_rows, _ = validator.load_jsonl(study_dir / "responses.jsonl")
    expected_ids = {
        str(item.get("stimulus_id") or "") for item in prereg_v1.get("presentation_manifest") or []
    }
    tones = {
        str(((s.get("voice_delivery") or {}).get("tone")) or "")
        for s in prereg_v1.get("stimuli") or []
        if (s.get("voice_delivery") or {}).get("tone")
    }
    v1_valid = sum(
        1
        for line_no, row in enumerate(v1_rows, start=1)
        if not validator.validate_response_row(
            row, expected_stimulus_ids=expected_ids, allowed_tones=tones, line_no=line_no
        )
        and row.get("rater_id")
    )
    checks["v1_valid_human_responses"] = v1_valid
    checks["v1_zero_responses_before_activation"] = v1_valid == 0
    if v1_valid != 0:
        failed.append("v1_responses_present_requires_fresh_v2_response_file")

    prereg_v2 = build_preregistration_v2(prereg_v1, study_dir)
    stimulus_ids = prereg_v2["presentation"]["stimulus_ids_in_slot_order"]

    # Gate 2 — the deterministic 20-rater fixture produces >=4 distinct orders.
    fixture_orders = prereg_v2["presentation"]["fixture_20_rater_orders"]
    distinct_orders = {tuple(order) for order in fixture_orders.values()}
    checks["fixture_rater_count"] = len(fixture_orders)
    checks["distinct_counterbalanced_orders"] = len(distinct_orders)
    if len(distinct_orders) < 4:
        failed.append("counterbalanced_orders_insufficient")
    williams_rows = {tuple(stimulus_ids[slot] for slot in row) for row in WILLIAMS_4}
    if not distinct_orders.issubset(williams_rows):
        failed.append("orders_not_from_williams_square")

    # Gate 3 — the rater page exposes only stimulus ids and blinded audio paths.
    page_path = study_dir / "rater_page.html"
    page_text = page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
    conditions = [str(item.get("condition")) for item in prereg_v1.get("presentation_manifest") or []]
    leaks = sorted(
        condition
        for condition in conditions
        if f"stimuli/{condition}.wav" in page_text or f">{condition}<" in page_text
    )
    if "&quot;condition&quot;" in page_text or '"condition"' in page_text:
        leaks.append("condition_key_present")
    checks["rater_page_condition_leaks"] = leaks
    if not page_text:
        failed.append("rater_page_missing")
    if leaks:
        failed.append("condition_labels_leak_into_rater_page")

    # Gate 4 — the primary analyzer keeps a rater who labels the adversarial
    # stimulus as the dream tone (intention-to-treat; no outcome-based exclusion).
    word = prereg_v2["attention_check"]["correct_answer"]
    confused = _synthetic_row("itt_confused", prereg_v2, adversarial_as_dream_tone=True, attention_word=word)
    attentive = _synthetic_row("itt_attentive", prereg_v2, adversarial_as_dream_tone=False, attention_word=word)
    inattentive = _synthetic_row("catch_fail", prereg_v2, adversarial_as_dream_tone=False, attention_word="wrong")
    fixture_rows = [confused, attentive, inattentive]
    analysis = analyzer.summarize_responses_v2(
        fixture_rows, prereg=prereg_v2, valid_row_indexes={1, 2, 3}
    )
    primary = analysis.get("primary") or {}
    included = set(primary.get("included_rater_ids") or [])
    checks["primary_includes_adversarial_confused_rater"] = "itt_confused" in included
    checks["primary_excluded_rater_ids"] = primary.get("excluded_rater_ids")
    if "itt_confused" not in included or primary.get("excluded_rater_ids"):
        failed.append("primary_analysis_excludes_on_outcome")

    # Gate 5 — the attention flag is independent of the primary outcome: it
    # flags the wrong-word rater, and flipping every emotion judgment changes
    # nothing about the flags.
    flags_before = analyzer.attention_flags(fixture_rows, word)
    mutated = json.loads(json.dumps(fixture_rows))
    for row in mutated:
        for response in row["responses"]:
            response["target_emotion_choice"] = "cheerful"
    flags_after = analyzer.attention_flags(mutated, word)
    checks["attention_flags"] = flags_before
    checks["attention_flag_catches_wrong_word"] = flags_before.get("catch_fail") is True
    checks["attention_flag_ignores_emotion_judgments"] = flags_before == flags_after
    if flags_before.get("catch_fail") is not True:
        failed.append("attention_check_does_not_catch")
    if flags_before != flags_after:
        failed.append("attention_check_reads_primary_outcome")

    # Gate 6 — retention: ids, reasons, and both denominators present.
    sensitivity = analysis.get("sensitivity_attention_check_only") or {}
    retention_ok = (
        isinstance(primary.get("included_rater_ids"), list)
        and isinstance(sensitivity.get("excluded_rater_ids"), list)
        and isinstance(sensitivity.get("exclusion_reasons"), dict)
        and isinstance(primary.get("denominator"), int)
        and isinstance(sensitivity.get("denominator"), int)
    )
    checks["retention_fields_present"] = retention_ok
    checks["primary_denominator"] = primary.get("denominator")
    checks["sensitivity_denominator"] = sensitivity.get("denominator")
    if not retention_ok:
        failed.append("retention_fields_missing")

    status = "PASS_BLINDED_LISTENER_STUDY_DESIGN_V2" if not failed else "BLOCKED_BLINDED_LISTENER_STUDY_DESIGN_V2"

    prereg_out = study_dir / "PREREGISTRATION_V2.json"
    if status.startswith("PASS") and not args.dry_run:
        prereg_out.write_text(json.dumps(prereg_v2, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        responses_v2 = study_dir / "responses_v2.jsonl"
        if not responses_v2.exists():
            responses_v2.write_text("", encoding="utf-8")

    receipt = {
        "schema": "persona_dream.blinded_listener_study_design_receipt.v2",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": False,
        "issue": "grahama1970/agent-skills#1126",
        "blocks": "grahama1970/agent-skills#1058 human collection until this receipt is PASS",
        "study_dir": rel(study_dir),
        "preregistration_v2": rel(prereg_out),
        "preregistration_v2_sha256": sha_file(prereg_out) if prereg_out.is_file() else None,
        "preregistration_v1_preserved": {
            "path": rel(prereg_v1_path),
            "sha256": sha_file(prereg_v1_path),
        },
        "checks": checks,
        "failed_gates": failed,
        "claims": {
            "proves": [
                "per-rater counterbalanced orders exist and are reproducible from the preregistration alone",
                "the primary analysis is intention-to-treat and cannot exclude on target_emotion_choice",
                "the attention check is independent of every emotion judgment",
                "no v1 human response is mixed into the v2 design",
            ]
            if status.startswith("PASS")
            else [],
            "does_not_prove": [
                "perceived emotion, Embry identity, or naturalness",
                "anything about human raters until responses_v2.jsonl fills",
                "any tone profile or renderer policy beyond the four preregistered WAVs",
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
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "STUDY_DESIGN_RECEIPT_V2.json")
    parser.add_argument("--dry-run", action="store_true", help="Run all checks without writing PREREGISTRATION_V2.json.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": rel(args.out) if args.out else None,
        "checks": receipt["checks"],
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
