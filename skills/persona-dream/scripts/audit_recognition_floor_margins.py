#!/usr/bin/env python3
"""Deterministic offline audit of persona-dream recognition floor margins.

Report only. This script reads archived
``persona_dream.session_mood_voice_recognition.v1`` receipts and reports, for
every judged render, the duration, similarity to Embry, the fixed
``min_embry_similarity`` threshold, the duration-aware floor, both pass
booleans, the receipt separation, the adversarial scores, and the margin
``similarity_to_embry - duration_aware_floor``.

It changes no recognition threshold, no duration-aware floor, no gate, no ASR
and no answer-invariance semantics. It never writes into the corpus; the only
write is the ``--out`` JSON report.

The audit quantifies the fixed-threshold-pass / duration-floor-fail population
across the corpus and, by default, reproduces the three systemic live-block
margins from ``soak35_structured_recognition_status`` exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "persona_dream.session_mood_voice_recognition.v1"
REPORT_SCHEMA = "persona_dream.recognition_floor_margin_audit.v1"
POLICY_HOLDOUT_SCHEMA = "persona_dream.session_mood_recognition_policy_holdout.v1"
POLICY_HOLDOUT_REPORT_SCHEMA = "persona_dream.session_mood_recognition_policy_holdout_report.v1"
REPO_ROOT = Path(__file__).resolve().parents[3]

# Margins recorded by the live campaign that ended
# BLOCKED_LIVE_CHAIN_RELIABILITY_PILOT. Expressed as
# (campaign, cycle, render_index, similarity, floor, margin).
EXPECTED_SYSTEMIC_BLOCKS: tuple[tuple[str, str, int, float, float, float], ...] = (
    ("soak35_structured_recognition_status", "cycle_001", 1, 0.765845, 0.774093, -0.008248),
    ("soak35_structured_recognition_status", "cycle_013", 1, 0.763900, 0.771094, -0.007194),
    ("soak35_structured_recognition_status", "cycle_021", 2, 0.770638, 0.779838, -0.009200),
)


def _round(value: Any) -> Any:
    return round(value, 6) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def _discover(root: Path) -> list[Path]:
    return sorted(root.rglob("voice_recognition/RECEIPT.json"))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_artifact_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return REPO_ROOT / path


def _campaign_and_cycle(receipt_path: Path, root: Path) -> tuple[str, str]:
    """``<campaign>/<cycle>/voice_recognition/RECEIPT.json`` relative to root."""
    rel = receipt_path.relative_to(root).parts
    cycle = rel[-3] if len(rel) >= 3 else ""
    campaign = rel[-4] if len(rel) >= 4 else root.name
    return campaign, cycle


def audit_receipt(receipt_path: Path, root: Path) -> dict[str, Any]:
    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    campaign, cycle = _campaign_and_cycle(receipt_path, root)
    thresholds = raw.get("preregistered_thresholds") or {}
    fixed_threshold = thresholds.get("min_embry_similarity")
    adversarial = [
        {
            "path": (voice.get("audio") or {}).get("path"),
            "seconds": _round(voice.get("seconds")),
            "similarity_to_embry": _round(voice.get("similarity_to_embry")),
            "below_ceiling": voice.get("below_ceiling"),
        }
        for voice in (raw.get("adversarial_voices") or [])
    ]
    max_adversarial = max(
        (v["similarity_to_embry"] for v in adversarial if isinstance(v["similarity_to_embry"], float)),
        default=None,
    )

    renders: list[dict[str, Any]] = []
    for index, render in enumerate(raw.get("genuine_renders") or [], start=1):
        similarity = render.get("similarity_to_embry")
        floor = render.get("duration_aware_floor")
        judged = render.get("long_enough_to_judge") is True and isinstance(floor, (int, float))
        margin = (
            _round(similarity - floor)
            if judged and isinstance(similarity, (int, float))
            else None
        )
        passes_threshold = render.get("passes_threshold")
        passes_floor = render.get("passes_duration_aware_floor")
        renders.append(
            {
                "campaign": campaign,
                "cycle": cycle,
                "render_index": index,
                "receipt": str(receipt_path.relative_to(root)),
                "audio_path": (render.get("audio") or {}).get("path"),
                "seconds": _round(render.get("seconds")),
                "similarity_to_embry": _round(similarity),
                "fixed_threshold": _round(fixed_threshold),
                "duration_aware_floor": _round(floor),
                "long_enough_to_judge": render.get("long_enough_to_judge"),
                "passes_threshold": passes_threshold,
                "passes_duration_aware_floor": passes_floor,
                "judged": judged,
                "margin_to_duration_aware_floor": margin,
                "fixed_pass_floor_fail": bool(judged and passes_threshold is True and passes_floor is False),
                "separation": _round(raw.get("separation")),
                "max_adversarial_similarity": max_adversarial,
                "adversarial_voices": adversarial,
            }
        )

    return {
        "campaign": campaign,
        "cycle": cycle,
        "receipt": str(receipt_path.relative_to(root)),
        "schema": raw.get("schema"),
        "status": raw.get("status"),
        "failed_gates": raw.get("failed_gates") or [],
        "live": raw.get("live"),
        "mocked": raw.get("mocked"),
        "separation": _round(raw.get("separation")),
        "fixed_threshold": _round(fixed_threshold),
        "min_separation": _round(thresholds.get("min_separation")),
        "max_adversarial_similarity_threshold": _round(thresholds.get("max_adversarial_similarity")),
        "adversarial_voices": adversarial,
        "renders": renders,
    }


def summarize(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    renders = [r for receipt in receipts for r in receipt["renders"]]
    judged = [r for r in renders if r["judged"]]
    fixed_pass_floor_fail = [r for r in judged if r["fixed_pass_floor_fail"]]
    margins = [r["margin_to_duration_aware_floor"] for r in fixed_pass_floor_fail]
    by_campaign: dict[str, dict[str, int]] = {}
    for r in renders:
        bucket = by_campaign.setdefault(
            r["campaign"], {"renders": 0, "judged": 0, "fixed_pass_floor_fail": 0}
        )
        bucket["renders"] += 1
        bucket["judged"] += int(r["judged"])
        bucket["fixed_pass_floor_fail"] += int(r["fixed_pass_floor_fail"])
    return {
        "receipts": len(receipts),
        "renders": len(renders),
        "renders_judged": len(judged),
        "renders_not_long_enough_to_judge": len(renders) - len(judged),
        "renders_failing_fixed_threshold": sum(1 for r in judged if r["passes_threshold"] is False),
        "renders_failing_duration_aware_floor": sum(
            1 for r in judged if r["passes_duration_aware_floor"] is False
        ),
        "fixed_pass_floor_fail": len(fixed_pass_floor_fail),
        "fixed_pass_floor_fail_margin_min": _round(min(margins)) if margins else None,
        "fixed_pass_floor_fail_margin_max": _round(max(margins)) if margins else None,
        "receipts_failing_all_renders_recognized_as_embry": sum(
            1 for receipt in receipts if "all_renders_recognized_as_embry" in receipt["failed_gates"]
        ),
        "by_campaign": dict(sorted(by_campaign.items())),
    }


def verify_systemic_blocks(renders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {(r["campaign"], r["cycle"], r["render_index"]): r for r in renders}
    checks: list[dict[str, Any]] = []
    for campaign, cycle, render_index, similarity, floor, margin in EXPECTED_SYSTEMIC_BLOCKS:
        observed = index.get((campaign, cycle, render_index))
        ok = bool(
            observed
            and observed["similarity_to_embry"] == similarity
            and observed["duration_aware_floor"] == floor
            and observed["margin_to_duration_aware_floor"] == margin
            and observed["passes_threshold"] is True
            and observed["passes_duration_aware_floor"] is False
        )
        checks.append(
            {
                "name": f"{campaign}/{cycle}/render{render_index}",
                "ok": ok,
                "expected": {
                    "similarity_to_embry": similarity,
                    "duration_aware_floor": floor,
                    "margin_to_duration_aware_floor": margin,
                    "passes_threshold": True,
                    "passes_duration_aware_floor": False,
                },
                "observed": (
                    {
                        "similarity_to_embry": observed["similarity_to_embry"],
                        "duration_aware_floor": observed["duration_aware_floor"],
                        "margin_to_duration_aware_floor": observed["margin_to_duration_aware_floor"],
                        "passes_threshold": observed["passes_threshold"],
                        "passes_duration_aware_floor": observed["passes_duration_aware_floor"],
                    }
                    if observed
                    else None
                ),
            }
        )
    return checks


def _holdout_float_check(name: str, expected: Any, observed: Any, errors: list[str]) -> None:
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        if _round(expected) != _round(observed):
            errors.append(f"{name}: expected {expected!r}, observed {observed!r}")
        return
    if expected != observed:
        errors.append(f"{name}: expected {expected!r}, observed {observed!r}")


def _holdout_receipt(root: Path, item: dict[str, Any], errors: list[str]) -> tuple[Path | None, dict[str, Any] | None]:
    receipt = item.get("receipt")
    if not isinstance(receipt, str):
        errors.append("receipt path missing")
        return None, None
    receipt_path = root / receipt
    if not receipt_path.is_file():
        errors.append(f"{receipt}: receipt not found")
        return receipt_path, None
    expected_sha = item.get("receipt_sha256")
    observed_sha = _sha256(receipt_path)
    if expected_sha != observed_sha:
        errors.append(f"{receipt}: receipt_sha256 expected {expected_sha!r}, observed {observed_sha!r}")
    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    if raw.get("schema") != SCHEMA:
        errors.append(f"{receipt}: schema {raw.get('schema')!r} != {SCHEMA!r}")
    return receipt_path, raw


def _audit_holdout_positive(
    root: Path,
    item: dict[str, Any],
    fixed_threshold: float,
    errors: list[str],
) -> dict[str, Any]:
    receipt_path, raw = _holdout_receipt(root, item, errors)
    observed: dict[str, Any] = {
        "label": item.get("label"),
        "receipt": item.get("receipt"),
        "render_index": item.get("render_index"),
    }
    if raw is None or receipt_path is None:
        observed["usable"] = False
        return observed

    render_index = item.get("render_index")
    renders = raw.get("genuine_renders") or []
    if not isinstance(render_index, int) or render_index < 1 or render_index > len(renders):
        errors.append(f"{item.get('receipt')}: render_index {render_index!r} out of range")
        observed["usable"] = False
        return observed

    render = renders[render_index - 1]
    audio = render.get("audio") or {}
    audio_path = _resolve_artifact_path(audio.get("path"))
    observed_audio_sha = _sha256(audio_path) if audio_path and audio_path.is_file() else None
    if item.get("audio_sha256") != audio.get("sha256"):
        errors.append(
            f"{item.get('receipt')}/render{render_index}: embedded audio sha expected "
            f"{item.get('audio_sha256')!r}, observed {audio.get('sha256')!r}"
        )
    if item.get("audio_sha256") != observed_audio_sha:
        errors.append(
            f"{item.get('receipt')}/render{render_index}: file audio sha expected "
            f"{item.get('audio_sha256')!r}, observed {observed_audio_sha!r}"
        )

    for key in ("seconds", "similarity_to_embry", "duration_aware_floor", "separation"):
        observed_value = raw.get("separation") if key == "separation" else render.get(key)
        _holdout_float_check(f"{item.get('receipt')}/render{render_index}/{key}", item.get(key), observed_value, errors)

    similarity = render.get("similarity_to_embry")
    duration_floor = render.get("duration_aware_floor")
    fixed_pass = isinstance(similarity, (int, float)) and similarity >= fixed_threshold
    duration_floor_pass = isinstance(similarity, (int, float)) and isinstance(duration_floor, (int, float)) and similarity >= duration_floor
    observed.update(
        {
            "usable": True,
            "seconds": _round(render.get("seconds")),
            "similarity_to_embry": _round(similarity),
            "duration_aware_floor": _round(duration_floor),
            "fixed_threshold": _round(fixed_threshold),
            "fixed_threshold_pass": fixed_pass,
            "duration_aware_floor_pass": duration_floor_pass,
            "recorded_passes_threshold": render.get("passes_threshold"),
            "recorded_passes_duration_aware_floor": render.get("passes_duration_aware_floor"),
            "separation": _round(raw.get("separation")),
        }
    )
    return observed


def _audit_holdout_adversarial(
    root: Path,
    item: dict[str, Any],
    fixed_threshold: float,
    errors: list[str],
) -> dict[str, Any]:
    receipt_path, raw = _holdout_receipt(root, item, errors)
    observed: dict[str, Any] = {
        "label": item.get("label"),
        "receipt": item.get("receipt"),
        "adversarial_index": item.get("adversarial_index"),
    }
    if raw is None or receipt_path is None:
        observed["usable"] = False
        return observed

    adversarial_index = item.get("adversarial_index")
    voices = raw.get("adversarial_voices") or []
    if not isinstance(adversarial_index, int) or adversarial_index < 1 or adversarial_index > len(voices):
        errors.append(f"{item.get('receipt')}: adversarial_index {adversarial_index!r} out of range")
        observed["usable"] = False
        return observed

    voice = voices[adversarial_index - 1]
    audio = voice.get("audio") or {}
    audio_path = _resolve_artifact_path(audio.get("path"))
    observed_audio_sha = _sha256(audio_path) if audio_path and audio_path.is_file() else None
    if item.get("audio_sha256") != audio.get("sha256"):
        errors.append(
            f"{item.get('receipt')}/adversarial{adversarial_index}: embedded audio sha expected "
            f"{item.get('audio_sha256')!r}, observed {audio.get('sha256')!r}"
        )
    if item.get("audio_sha256") != observed_audio_sha:
        errors.append(
            f"{item.get('receipt')}/adversarial{adversarial_index}: file audio sha expected "
            f"{item.get('audio_sha256')!r}, observed {observed_audio_sha!r}"
        )

    similarity = voice.get("similarity_to_embry")
    _holdout_float_check(
        f"{item.get('receipt')}/adversarial{adversarial_index}/similarity_to_embry",
        item.get("similarity_to_embry"),
        similarity,
        errors,
    )
    fixed_accept = isinstance(similarity, (int, float)) and similarity >= fixed_threshold
    observed.update(
        {
            "usable": True,
            "seconds": _round(voice.get("seconds")),
            "similarity_to_embry": _round(similarity),
            "fixed_threshold": _round(fixed_threshold),
            "fixed_0_75_false_accept": fixed_accept,
            "recorded_below_ceiling": voice.get("below_ceiling"),
        }
    )
    return observed


def audit_policy_holdout(manifest_path: Path, root: Path, out: Path | None = None) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema") != POLICY_HOLDOUT_SCHEMA:
        errors.append(f"manifest schema {manifest.get('schema')!r} != {POLICY_HOLDOUT_SCHEMA!r}")
    policy = manifest.get("policy") or {}
    fixed_threshold = policy.get("fixed_threshold")
    if not isinstance(fixed_threshold, (int, float)):
        errors.append("policy.fixed_threshold must be numeric")
        fixed_threshold = 0.75

    disputed = [
        _audit_holdout_positive(root, item, float(fixed_threshold), errors)
        for item in manifest.get("disputed_positives", [])
    ]
    clear = [
        _audit_holdout_positive(root, item, float(fixed_threshold), errors)
        for item in manifest.get("clear_positives", [])
    ]
    adversarial = [
        _audit_holdout_adversarial(root, item, float(fixed_threshold), errors)
        for item in manifest.get("adversarial_negatives", [])
    ]

    positives = [row for row in disputed + clear if row.get("usable")]
    positive_similarities = [
        row["similarity_to_embry"] for row in positives if isinstance(row.get("similarity_to_embry"), float)
    ]
    adversarial_similarities = [
        row["similarity_to_embry"] for row in adversarial if isinstance(row.get("similarity_to_embry"), float)
    ]
    disputed_fixed_pass = sum(1 for row in disputed if row.get("fixed_threshold_pass") is True)
    clear_fixed_pass = sum(1 for row in clear if row.get("fixed_threshold_pass") is True)
    fixed_adversarial_false_accept = sum(1 for row in adversarial if row.get("fixed_0_75_false_accept") is True)
    duration_aware_false_rejects = sum(1 for row in disputed + clear if row.get("duration_aware_floor_pass") is False)
    min_positive = min(positive_similarities) if positive_similarities else None
    max_adversarial = max(adversarial_similarities) if adversarial_similarities else None
    separation_margin = (
        _round(min_positive - max_adversarial)
        if isinstance(min_positive, float) and isinstance(max_adversarial, float)
        else None
    )
    eligible_fixed = bool(
        not errors
        and disputed
        and clear
        and adversarial
        and disputed_fixed_pass == len(disputed)
        and clear_fixed_pass == len(clear)
        and fixed_adversarial_false_accept == 0
        and isinstance(separation_margin, float)
        and separation_margin > 0
    )
    decision = "ELIGIBLE_FIXED_0_75" if eligible_fixed else "KEEP_DURATION_AWARE_BLOCKED"
    report = {
        "schema": POLICY_HOLDOUT_REPORT_SCHEMA,
        "manifest": str(manifest_path),
        "root": str(root),
        "mocked": False,
        "fixture_backed": True,
        "live_qualified": False,
        "report_only": True,
        "runtime_policy_changed": False,
        "policy": {"fixed_threshold": _round(fixed_threshold)},
        "summary": {
            "decision": decision,
            "disputed_positive_count": len(disputed),
            "clear_positive_count": len(clear),
            "adversarial_negative_count": len(adversarial),
            "disputed_positive_fixed_pass_count": disputed_fixed_pass,
            "clear_positive_fixed_pass_count": clear_fixed_pass,
            "duration_aware_positive_false_reject_count": duration_aware_false_rejects,
            "fixed_0_75_adversarial_false_accept_count": fixed_adversarial_false_accept,
            "min_positive_similarity": _round(min_positive),
            "max_adversarial_similarity": _round(max_adversarial),
            "positive_to_adversarial_separation_margin": separation_margin,
            "errors": errors,
        },
        "disputed_positives": disputed,
        "clear_positives": clear,
        "adversarial_negatives": adversarial,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report_written {out}")

    summary = report["summary"]
    print(json.dumps({"policy_holdout_summary": summary}, sort_keys=True))
    print(f"runtime_policy_changed={str(report['runtime_policy_changed']).lower()}")
    print(f"disputed_positive_count={summary['disputed_positive_count']}")
    print(f"disputed_positive_fixed_pass_count={summary['disputed_positive_fixed_pass_count']}")
    print(f"fixed_0_75_adversarial_false_accept_count={summary['fixed_0_75_adversarial_false_accept_count']}")
    print(f"decision={decision}")
    if errors:
        print("BLOCKED_RECOGNITION_POLICY_HOLDOUT_AUDIT: fixture verification errors", file=sys.stderr)
        return 1
    print("PASS_RECOGNITION_POLICY_HOLDOUT_AUDIT")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1] / "reports/goal_v5/continuity/reliability"
    parser.add_argument("--root", type=Path, default=default_root,
                        help="reliability corpus root to scan (default: %(default)s)")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--report-only", action="store_true",
                        help="explicit no-op flag: this audit is always report-only")
    parser.add_argument("--no-verify-systemic-blocks", action="store_true",
                        help="skip reproducing the three soak35_structured_recognition_status margins")
    parser.add_argument("--policy-holdout", type=Path, default=None,
                        help="run a checksum-pinned recognition policy holdout fixture audit")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"BLOCKED_RECOGNITION_FLOOR_MARGIN_AUDIT: root not found: {root}", file=sys.stderr)
        return 2

    if args.policy_holdout:
        return audit_policy_holdout(args.policy_holdout.resolve(), root, args.out)

    paths = _discover(root)
    if not paths:
        print(f"BLOCKED_RECOGNITION_FLOOR_MARGIN_AUDIT: no recognition receipts under {root}", file=sys.stderr)
        return 2

    receipts: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in paths:
        try:
            audited = audit_receipt(path, root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            skipped.append({"receipt": str(path.relative_to(root)), "reason": f"{type(exc).__name__}: {exc}"})
            continue
        if audited["schema"] != SCHEMA:
            skipped.append({"receipt": audited["receipt"], "reason": f"schema {audited['schema']!r} != {SCHEMA!r}"})
            continue
        receipts.append(audited)

    renders = [r for receipt in receipts for r in receipt["renders"]]
    summary = summarize(receipts)
    checks = [] if args.no_verify_systemic_blocks else verify_systemic_blocks(renders)

    report = {
        "schema": REPORT_SCHEMA,
        "report_only": True,
        "semantics_changed": [],
        "root": str(root),
        "summary": summary,
        "skipped_receipts": skipped,
        "systemic_block_checks": checks,
        "fixed_pass_floor_fail_renders": [r for r in renders if r["fixed_pass_floor_fail"]],
        "receipts": receipts,
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report_written {args.out}")

    print(json.dumps({"summary": summary}, sort_keys=True))
    for row in report["fixed_pass_floor_fail_renders"]:
        print(
            "FIXED_PASS_FLOOR_FAIL "
            f"{row['campaign']}/{row['cycle']}/render{row['render_index']} "
            f"seconds={row['seconds']} similarity={row['similarity_to_embry']} "
            f"fixed_threshold={row['fixed_threshold']} floor={row['duration_aware_floor']} "
            f"margin={row['margin_to_duration_aware_floor']} separation={row['separation']}"
        )
    failed = [c for c in checks if not c["ok"]]
    for check in checks:
        print(("PASS " if check["ok"] else "FAIL ") + "systemic_block_reproduced " + check["name"]
              + ("" if check["ok"] else " :: " + json.dumps(check, sort_keys=True)))
    if failed:
        print("BLOCKED_RECOGNITION_FLOOR_MARGIN_AUDIT: systemic block margins not reproduced", file=sys.stderr)
        return 1

    print("RECOGNITION_FLOOR_MARGIN_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
