#!/usr/bin/env python3
"""Agent prescreen for Persona Dream Chatterbox listening stimuli.

This is the gate before human listener collection. It signs off only technical
and acoustic fitness: hashes, ASR, Chatterbox ops receipts, caller misuse scan,
and analyzer proxy quality. It never claims human-perceived emotion or identity.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
SCHEMA = "persona_dream.agent_listening_signoff.v1"
TAG_WORDS = {"laugh", "chuckle", "sigh", "gasp", "whispering", "cough", "groan", "sniff", "shush"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def analyzer_path(analyzer_dir: Path, stimulus_id: str, condition: str) -> Path:
    preferred = analyzer_dir / f"{stimulus_id}_{condition}.json"
    if preferred.is_file():
        return preferred
    matches = sorted(analyzer_dir.glob(f"{stimulus_id}_*.json"))
    return matches[0] if matches else preferred


def isolated_words(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return set(cleaned.split())


def ops_gate(name: str, path: Path, expected_status_prefix: str) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "path": rel(path), "ok": False, "failed_gates": []}
    if not path.is_file():
        row["failed_gates"].append("ops_receipt_missing")
        return row
    data = load_json(path)
    row.update({
        "schema": data.get("schema"),
        "status": data.get("status"),
        "receipt_ok": data.get("ok"),
        "live": data.get("live"),
        "mocked": data.get("mocked"),
        "failures": data.get("failures") or [],
    })
    if not str(data.get("status") or "").startswith(expected_status_prefix):
        row["failed_gates"].append("ops_status_not_pass")
    if data.get("ok") is not True:
        row["failed_gates"].append("ops_ok_not_true")
    if data.get("failures"):
        row["failed_gates"].append("ops_failures_present")
    row["ok"] = not row["failed_gates"]
    return row


def run(args: argparse.Namespace) -> dict[str, Any]:
    validation = load_json(args.validation_receipt)
    failed_gates: list[str] = []

    ops = [
        ops_gate("doctor", args.ops_doctor, "PASS_CHATTERBOX_DOCTOR"),
        ops_gate("health", args.ops_health, "PASS_CHATTERBOX_HEALTH"),
        ops_gate("render_smoke", args.ops_render_smoke, "PASS_CHATTERBOX_RENDER_SMOKE"),
        ops_gate("assess", args.ops_assess, "PASS_CHATTERBOX_USAGE_ASSESSMENT"),
    ]
    for row in ops:
        if not row["ok"]:
            failed_gates.append(f"ops_gate_failed:{row['name']}")

    validation_failed = list(validation.get("failed_gates") or [])
    unexpected_validation_failures = [gate for gate in validation_failed if gate != "human_responses_complete"]
    if unexpected_validation_failures:
        failed_gates.append("validation_has_unexpected_failed_gates")
    if validation.get("status") != "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS":
        failed_gates.append("validation_not_ready_for_human_raters")

    stimulus_rows: list[dict[str, Any]] = []
    for stimulus in validation.get("stimuli") or []:
        condition = str(stimulus.get("condition") or "")
        stimulus_id = str(stimulus.get("stimulus_id") or "")
        row_failed: list[str] = []
        audio = stimulus.get("audio") or {}
        asr = stimulus.get("asr") or {}
        if not stimulus_id:
            row_failed.append("stimulus_id_missing")
        if audio.get("exists") is not True or not audio.get("sha256") or not audio.get("bytes"):
            row_failed.append("audio_hash_or_bytes_missing")
        if stimulus.get("hash_match") is not True or stimulus.get("bytes_match") is not True:
            row_failed.append("stimulus_hash_or_bytes_mismatch")
        if asr.get("ok") is not True or asr.get("wer") != 0.0:
            row_failed.append("asr_not_exact")
        transcript_words = isolated_words(str(asr.get("transcript") or ""))
        spoken_tag_words = sorted(TAG_WORDS & transcript_words)
        if spoken_tag_words:
            row_failed.append("literal_chatterbox_tag_spoken")
        if not isinstance(stimulus.get("voice_delivery"), dict) or not stimulus.get("voice_delivery"):
            row_failed.append("voice_delivery_missing")

        apath = analyzer_path(args.analyzer_dir, stimulus_id, condition)
        analyzer: dict[str, Any] = {}
        if not apath.is_file():
            row_failed.append("analyzer_receipt_missing")
        else:
            analyzer = load_json(apath)
            if analyzer.get("schema") != "analyze_chatterbox_emotions.voice_eval.v1":
                row_failed.append("analyzer_schema_wrong")
            if analyzer.get("status") != "PASS_VOICE_EVAL" or analyzer.get("verdict") != "pass":
                row_failed.append("analyzer_not_pass")
            if analyzer.get("failed_gates"):
                row_failed.append("analyzer_failed_gates_present")

        stimulus_rows.append({
            "stimulus_id": stimulus_id,
            "condition": condition,
            "status": "PASS_AGENT_LISTENING_SIGNOFF" if not row_failed else "BLOCKED_AGENT_LISTENING_SIGNOFF",
            "audio": audio,
            "voice_delivery": stimulus.get("voice_delivery"),
            "asr": {"ok": asr.get("ok"), "wer": asr.get("wer"), "transcript_sha256_present": bool(asr.get("transcript"))},
            "spoken_tag_words": spoken_tag_words,
            "analyzer_receipt": rel(apath),
            "analyzer_status": analyzer.get("status"),
            "analyzer_score": analyzer.get("overall_score"),
            "failed_gates": row_failed,
        })
        failed_gates.extend(f"stimulus_gate_failed:{stimulus_id}:{gate}" for gate in row_failed)

    status = "PASS_AGENT_LISTENING_SIGNOFF" if not failed_gates else "BLOCKED_AGENT_LISTENING_SIGNOFF"
    receipt = {
        "schema": SCHEMA,
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": True,
        "validation_receipt": rel(args.validation_receipt),
        "analyzer_dir": rel(args.analyzer_dir),
        "ops_receipts": ops,
        "stimuli": stimulus_rows,
        "stimulus_count": len(stimulus_rows),
        "passed_stimulus_count": sum(1 for row in stimulus_rows if row["status"] == "PASS_AGENT_LISTENING_SIGNOFF"),
        "human_collection_permitted": status == "PASS_AGENT_LISTENING_SIGNOFF",
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "agent prescreen found the listening stimuli technically fit for human collection",
                "Chatterbox ops receipts passed for service health, live smoke, and caller usage assessment",
                "stimulus audio hashes, bytes, ASR, and analyzer proxy receipts passed",
            ] if status == "PASS_AGENT_LISTENING_SIGNOFF" else [],
            "does_not_prove": [
                "human-perceived emotion",
                "human listener recognition of Embry",
                "naturalness preference",
                "that the listener study has enough human responses or a signed interpretation",
            ],
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-receipt", type=Path, required=True)
    parser.add_argument("--ops-doctor", type=Path, required=True)
    parser.add_argument("--ops-health", type=Path, required=True)
    parser.add_argument("--ops-render-smoke", type=Path, required=True)
    parser.add_argument("--ops-assess", type=Path, required=True)
    parser.add_argument("--analyzer-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": str(args.out),
        "stimulus_count": receipt["stimulus_count"],
        "passed_stimulus_count": receipt["passed_stimulus_count"],
        "human_collection_permitted": receipt["human_collection_permitted"],
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
