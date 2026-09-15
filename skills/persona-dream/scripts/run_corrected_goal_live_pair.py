#!/usr/bin/env python3
"""Build a corrected-goal proof from already-produced artifact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MEMORY_FILES = ("residue_links.json", "day_context.json")
DYNAMIC_RECEIPT = "dynamic_conversation_receipt.v1.json"
DYNAMIC_TRANSCRIPT = "conversation.jsonl"
JOURNAL_SPOKEN = "journal_spoken.txt"
CHATTERBOX_METRICS = "chatterbox_delivery.metrics.json"


def sha_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def sha_text(text: str) -> str:
    return sha_bytes(text.encode("utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def condition_manifest(manifest: dict[str, Any], condition_id: str) -> dict[str, Any]:
    for condition in manifest.get("conditions", []):
        if condition.get("condition_id") == condition_id:
            return condition
    raise KeyError(condition_id)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _resolve_source_ref(base: Path, ref: Any) -> Path:
    if not isinstance(ref, str) or not ref:
        raise ValueError("audio_ref_missing")
    raw = Path(ref)
    path = raw if raw.is_absolute() else base / raw
    if not _is_relative_to(path, base):
        raise ValueError(f"audio_ref_outside_condition:{ref}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _copy_dynamic_condition(*, side: str, receipt: Path, transcript: Path, journal: Path, dst: Path) -> dict[str, str]:
    source_base = transcript.parent.resolve()
    receipt_data = _load_json(receipt)
    _copy_file(receipt, dst / DYNAMIC_RECEIPT)
    _copy_file(journal, dst / JOURNAL_SPOKEN)

    audio_refs: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("role") and not row.get("speaker"):
                row["speaker"] = row["role"]
            if str(row.get("role") or row.get("speaker") or "").lower() == "embry" and row.get("text"):
                row.setdefault("answer_body", row["text"])
                row.setdefault("answer_body_sha256", sha_text(str(row["answer_body"])))
            normalized_rows.append(row)
            if row.get("audio"):
                audio_refs.add(str(row["audio"]))
    for pair in receipt_data.get("turn_pairs") or []:
        if not isinstance(pair, dict):
            continue
        for role in ("horus", "embry"):
            turn = pair.get(role) if isinstance(pair.get(role), dict) else {}
            if turn.get("audio"):
                audio_refs.add(str(turn["audio"]))

    (dst / DYNAMIC_TRANSCRIPT).write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in normalized_rows),
        encoding="utf-8",
    )

    copied_audio: set[str] = set()
    for ref in sorted(audio_refs):
        src = _resolve_source_ref(source_base, ref)
        target = dst / Path(ref)
        _copy_file(src, target)
        copied_audio.add(ref)

    return {
        "dynamic_conversation_receipt_sha256": sha_file(dst / DYNAMIC_RECEIPT),
        "conversation_jsonl_sha256": sha_file(dst / DYNAMIC_TRANSCRIPT),
        "journal_spoken_sha256": sha_file(dst / JOURNAL_SPOKEN),
        "copied_audio_count": str(len(copied_audio)),
    }


def _run_validator(args: list[str], out_path: Path) -> int:
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    if proc.stdout:
        out_path.write_text(proc.stdout, encoding="utf-8")
        try:
            data = json.loads(proc.stdout)
            write_json(out_path, data)
        except json.JSONDecodeError:
            pass
    else:
        write_json(out_path, {
            "schema": "persona_dream.corrected_goal_validator_subprocess.v1",
            "status": "FAIL_VALIDATOR_NO_STDOUT",
            "args": args,
            "returncode": proc.returncode,
            "stderr_tail": proc.stderr[-500:],
            "mocked": False,
            "live": False,
        })
    return proc.returncode


def _required(args: argparse.Namespace) -> dict[str, bool]:
    return {
        "manifest": args.manifest.is_file(),
        "source_run": args.source_run.is_dir(),
        "source_residue_links": (args.source_run / "residue_links.json").is_file(),
        "source_day_context": (args.source_run / "day_context.json").is_file(),
        "identity_artifact": args.identity_artifact.is_file(),
        "chatterbox_delivery_metrics": args.chatterbox_delivery_metrics.is_file(),
        "control_dynamic_receipt": args.control_dynamic_receipt.is_file(),
        "control_conversation": args.control_conversation.is_file(),
        "control_journal_spoken": args.control_journal_spoken.is_file(),
        "treatment_dynamic_receipt": args.treatment_dynamic_receipt.is_file(),
        "treatment_conversation": args.treatment_conversation.is_file(),
        "treatment_journal_spoken": args.treatment_journal_spoken.is_file(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--identity-artifact", required=True, type=Path)
    parser.add_argument("--chatterbox-delivery-metrics", required=True, type=Path)
    parser.add_argument("--control-dynamic-receipt", required=True, type=Path)
    parser.add_argument("--control-conversation", required=True, type=Path)
    parser.add_argument("--control-journal-spoken", required=True, type=Path)
    parser.add_argument("--treatment-dynamic-receipt", required=True, type=Path)
    parser.add_argument("--treatment-conversation", required=True, type=Path)
    parser.add_argument("--treatment-journal-spoken", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    args.manifest = args.manifest.resolve()
    args.source_run = args.source_run.resolve()
    args.identity_artifact = args.identity_artifact.resolve()
    args.chatterbox_delivery_metrics = args.chatterbox_delivery_metrics.resolve()
    args.control_dynamic_receipt = args.control_dynamic_receipt.resolve()
    args.control_conversation = args.control_conversation.resolve()
    args.control_journal_spoken = args.control_journal_spoken.resolve()
    args.treatment_dynamic_receipt = args.treatment_dynamic_receipt.resolve()
    args.treatment_conversation = args.treatment_conversation.resolve()
    args.treatment_journal_spoken = args.treatment_journal_spoken.resolve()
    args.out = args.out.resolve()

    required_inputs = _required(args)
    if args.preflight_only:
        receipt = {
            "schema": "persona_dream.corrected_goal_live_pair_preflight.v1",
            "status": "PASS_CORRECTED_GOAL_LIVE_PAIR_PREFLIGHT" if all(required_inputs.values()) else "BLOCKED_CORRECTED_GOAL_LIVE_PAIR_PREFLIGHT",
            "required_inputs_present": required_inputs,
            "mocked": False,
            "live": False,
        }
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["status"].startswith("PASS_") else 2
    if not all(required_inputs.values()):
        write_json(args.out / "corrected_goal_receipt.json", {
            "schema": "persona_dream.corrected_goal_receipt.v1",
            "status": "BLOCKED_CORRECTED_GOAL_PAIRED_PROOF",
            "failures": [key for key, ok in required_inputs.items() if not ok],
            "mocked": False,
            "live": False,
        })
        return 2

    manifest = _load_json(args.manifest)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.manifest, out / "manifest.json")

    source_dir = out / "source_memory"
    source_binding: dict[str, str] = {}
    for name in SOURCE_MEMORY_FILES:
        _copy_file(args.source_run / name, source_dir / name)
    source_binding["residue_links_sha256"] = sha_file(source_dir / "residue_links.json")
    source_binding["day_context_sha256"] = sha_file(source_dir / "day_context.json")

    identity_dir = out / "identity"
    identity_target = identity_dir / args.identity_artifact.name
    _copy_file(args.identity_artifact, identity_target)
    identity_sha = sha_file(identity_target)
    manifest_identity = (manifest.get("identity") or {}).get("identity_core_digest")
    identity_binding = {
        "artifact_path": f"../identity/{identity_target.name}",
        "artifact_sha256": identity_sha,
        "identity_core_digest": manifest_identity or identity_sha,
    }
    _copy_file(args.chatterbox_delivery_metrics, out / CHATTERBOX_METRICS)

    control_condition = condition_manifest(manifest, "C0_STRUCTURED_REFLECTION")
    treatment_condition = condition_manifest(manifest, "C1_DREAM_JOURNAL")
    control = out / "control"
    treatment = out / "treatment"
    control.mkdir(exist_ok=True)
    treatment.mkdir(exist_ok=True)

    dynamic_evidence = {
        "control": _copy_dynamic_condition(
            side="control",
            receipt=args.control_dynamic_receipt,
            transcript=args.control_conversation,
            journal=args.control_journal_spoken,
            dst=control,
        ),
        "treatment": _copy_dynamic_condition(
            side="treatment",
            receipt=args.treatment_dynamic_receipt,
            transcript=args.treatment_conversation,
            journal=args.treatment_journal_spoken,
            dst=treatment,
        ),
    }

    write_json(control / "reflection_packet.json", {
        "schema": "persona_dream.structured_reflection_packet.v1",
        "condition_id": "C0_STRUCTURED_REFLECTION",
        "source_run": str(args.source_run),
        "answer_capsule": manifest["answer_capsule"],
        "conflict_id": None,
        "source_memory": source_binding,
        "identity": identity_binding,
        "boundary": "control imports existing dynamic-conversation artifacts; it does not synthesize dialogue",
    })
    write_json(control / "session_mood.json", {
        "schema": "persona_dream.corrected_goal_session_mood.v1",
        "condition_id": "C0_STRUCTURED_REFLECTION",
        "conflict_id": None,
        "session_mood_event_id": "control_reflection_mood_v1",
        "source_memory": source_binding,
        "identity": identity_binding,
        **control_condition["session_mood"],
    })
    write_json(treatment / "dream_residue.json", {
        "schema": "persona_dream.corrected_goal_residue.v1",
        "source_run": str(args.source_run),
        "source_memory": source_binding,
        "identity": identity_binding,
    })
    write_json(treatment / "journal.json", {
        "schema": "persona_dream.corrected_goal_journal.v1",
        "source_run": str(args.source_run),
        "source_memory": source_binding,
        "identity": identity_binding,
        "conflict": treatment_condition["conflict_id"],
        "synthetic_boundary": "imported proof preserves synthetic provenance and does not add facts",
    })
    write_json(treatment / "session_mood.json", {
        "schema": "persona_dream.corrected_goal_session_mood.v1",
        "condition_id": "C1_DREAM_JOURNAL",
        "conflict_id": treatment_condition["conflict_id"],
        "session_mood_event_id": "treatment_dream_journal_mood_v1",
        "source_memory": source_binding,
        "identity": identity_binding,
        "arc": treatment_condition["session_arc"],
    })
    write_json(treatment / "emotion_lineage.json", {
        "schema": "persona_dream.corrected_goal_emotion_lineage.v1",
        "dream_residue_sha256": sha_file(treatment / "dream_residue.json"),
        "dream_packet_sha256": source_binding["residue_links_sha256"],
        "journal_sha256": sha_file(treatment / "journal.json"),
        "conflict_id": treatment_condition["conflict_id"],
        "session_mood_event_id": "treatment_dream_journal_mood_v1",
        "horus_challenge_turn_id": "imported_dynamic_pair_2_horus",
        "embry_emotional_frame_turn_id": "imported_dynamic_pair_2_embry",
        "chatterbox_render_request_sha256": dynamic_evidence["treatment"]["dynamic_conversation_receipt_sha256"],
        "audio_sha256": dynamic_evidence["treatment"]["conversation_jsonl_sha256"],
        "source_memory": source_binding,
        "identity": identity_binding,
        "mocked": False,
        "live": True,
    })
    write_json(out / "proof_boundary_import.json", {
        "schema": "persona_dream.corrected_goal_import_boundary.v1",
        "status": "IMPORTED_ARTIFACTS_UNADJUDICATED",
        "source_memory": source_binding,
        "identity": identity_binding,
        "dynamic_conversation": dynamic_evidence,
        "provider_call_attempts": 0,
        "boundary": "offline retained-artifact import; no dialogue, receipt rows, transcript rows, or audio were generated by this runner",
        "mocked": False,
        "live": False,
    })

    validator_results = {
        "answer_invariance": _run_validator([
            str(ROOT / "scripts" / "validate_answer_invariance.py"),
            "--manifest", str(args.manifest),
            "--control", str(control / DYNAMIC_TRANSCRIPT),
            "--treatment", str(treatment / DYNAMIC_TRANSCRIPT),
            "--require-exact-answer-body",
            "--live-artifacts",
        ], out / "answer_invariance.json"),
        "emotional_carryover": _run_validator([
            str(ROOT / "scripts" / "validate_emotion_lineage.py"),
            "--manifest", str(args.manifest),
            "--run-root", str(out),
            "--require-control-null-conflict",
            "--require-treatment-complete-chain",
            "--forbid-durable-identity-mutation",
            "--live-artifacts",
        ], out / "emotional_carryover.json"),
        "chatterbox_delivery": _run_validator([
            str(ROOT / "scripts" / "validate_chatterbox_delivery.py"),
            "--manifest", str(args.manifest),
            "--run-root", str(out),
            "--reuse-issue24-gates",
            "--reuse-issue25-gates",
            "--forbid-literal-tag-words",
            "--live-artifacts",
        ], out / "chatterbox_delivery.validation.json"),
    }
    if (out / "chatterbox_delivery.validation.json").is_file():
        write_json(out / "chatterbox_delivery.json", _load_json(out / "chatterbox_delivery.validation.json"))
    write_json(out / "validator_results.json", validator_results)
    _run_validator([
        str(ROOT / "scripts" / "adjudicate_corrected_goal.py"),
        "--manifest", str(args.manifest),
        "--run-root", str(out),
        "--out", str(out / "corrected_goal_receipt.json"),
        "--fail-closed",
    ], out / "corrected_goal_receipt.stdout.json")

    receipt = _load_json(out / "corrected_goal_receipt.json")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "PASS_CORRECTED_GOAL_PAIRED_PROOF" else 2


if __name__ == "__main__":
    sys.exit(main())
