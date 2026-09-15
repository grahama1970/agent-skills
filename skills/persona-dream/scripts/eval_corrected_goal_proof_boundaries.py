#!/usr/bin/env python3
"""Retained corrected-goal proof-boundary eval: fail-closed artifact checks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from adjudicate_corrected_goal import adjudicate  # noqa: E402
import append_conversation  # noqa: E402


RETAINED = Path("/mnt/storage12tb/skills/persona-dream/outputs/eval-full-cycle-20260907T135011Z")
ZERO = "sha256:" + "0" * 64


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha_file(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sha_text(text: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 80)


def manifest(identity_sha: str) -> dict[str, Any]:
    return {
        "schema": "persona_dream.corrected_goal_manifest.v1",
        "proof_id": "PD-CORRECTED-GOAL-PROOF-BOUNDARY-EVAL",
        "answer_capsule": {
            "answer_body": "Keep synthetic dreams marked as synthetic.",
            "answer_body_sha256": sha_text("Keep synthetic dreams marked as synthetic."),
            "protected_tokens": [],
        },
        "identity": {"identity_core_digest": identity_sha},
        "conditions": [
            {"condition_id": "C0_STRUCTURED_REFLECTION", "conflict_id": None, "session_mood": {"intensity": 0.1}},
            {"condition_id": "C1_DREAM_JOURNAL", "conflict_id": "conflict", "session_arc": []},
        ],
        "claims": {
            "one_passing_pair_proves": "no positive pair is proven by this eval; it proves fail-closed admission only",
            "does_not_prove": "fresh provider readiness, human emotional value, visual identity correctness, or production readiness",
        },
    }


def tau_receipt() -> dict[str, Any]:
    return {
        "tau_receipt_schema": "tau.persona_dream.scillm_text_reasoning_receipt.v1",
        "status": "PASS",
        "live_call_performed": True,
        "http_status": 200,
        "model": "fixture-model",
        "route": "tau:persona-dream-text-reasoning",
        "prompt_sha256": sha_text("prompt"),
        "output_contract_sha256": sha_text("contract"),
    }


def stage_synthetic(
    root: Path,
    *,
    gate_live: bool = False,
    provider_count: Any = None,
    include_tau: bool = True,
) -> tuple[Path, Path]:
    run = root / "proof"
    manifest_path = root / "manifest.json"
    run.mkdir(parents=True, exist_ok=True)

    identity_path = run / "identity" / "identity_reference.bin"
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_bytes(b"independent identity reference bytes\n")
    identity_sha = sha_file(identity_path)
    write_json(manifest_path, manifest(identity_sha))
    shutil.copyfile(manifest_path, run / "manifest.json")

    metrics_path = run / "chatterbox_delivery.metrics.json"
    write_json(metrics_path, {
        "schema": "persona_dream.corrected_goal_chatterbox_delivery_metrics.v1",
        "live": gate_live,
        "mocked": False,
        "observed_effect_channels": ["tempo"],
        "control": {},
        "treatment": {},
    })
    gates = (
        ("answer_invariance.json", "persona_dream.answer_invariance_validation.v1", "PASS_ANSWER_INVARIANCE"),
        ("emotional_carryover.json", "persona_dream.emotion_lineage_validation.v1", "PASS_EMOTION_LINEAGE"),
        ("chatterbox_delivery.json", "persona_dream.chatterbox_delivery_validation.v1", "PASS_CHATTERBOX_DELIVERY"),
    )
    for name, schema, status in gates:
        receipt = {"schema": schema, "status": status, "live": gate_live, "mocked": False}
        if name == "chatterbox_delivery.json":
            receipt["chatterbox_delivery_metrics_sha256"] = sha_file(metrics_path)
        write_json(run / name, receipt)

    source = run / "source_memory"
    write_json(source / "residue_links.json", {"schema": "persona_dream.residue_links.v1", "idea_id": "eval", "items": []})
    write_json(source / "day_context.json", {"day": "eval", "persona": "embry", "items": [], "receipt": {}, "status": "PASS"})
    source_binding = {
        "residue_links_sha256": sha_file(source / "residue_links.json"),
        "day_context_sha256": sha_file(source / "day_context.json"),
    }
    identity = {"artifact_path": "../identity/identity_reference.bin", "artifact_sha256": identity_sha, "identity_core_digest": identity_sha}

    for side in ("control", "treatment"):
        side_dir = run / side
        side_dir.mkdir(parents=True, exist_ok=True)
        write_json(side_dir / "session_mood.json", {
            "schema": "persona_dream.corrected_goal_session_mood.v1",
            "conflict_id": None if side == "control" else "conflict",
            "source_memory": source_binding,
            "identity": identity,
        })
        journal = side_dir / "journal_spoken.txt"
        journal.write_text("journal spoken bytes\n", encoding="utf-8")
        write_wav(side_dir / "horus.wav")
        write_wav(side_dir / "embry.wav")
        answer = "Keep synthetic dreams marked as synthetic."
        rows = [
            {"schema": "persona_dream.conversation_turn.v1", "role": "horus", "speaker": "horus", "text": "Question", "journal_spoken_sha256": sha_file(journal), "created_at": "2026-09-15T00:00:00Z", "audio": "horus.wav", "audio_sha256": sha_file(side_dir / "horus.wav")},
            {"schema": "persona_dream.conversation_turn.v1", "role": "embry", "speaker": "embry", "text": answer, "answer_body": answer, "answer_body_sha256": sha_text(answer), "journal_spoken_sha256": sha_file(journal), "created_at": "2026-09-15T00:00:01Z", "audio": "embry.wav", "audio_sha256": sha_file(side_dir / "embry.wav")},
        ]
        write_jsonl(side_dir / "conversation.jsonl", rows)
        receipt: dict[str, Any] = {
            "schema": "persona_dream.dynamic_conversation_receipt.v1",
            "status": "PASS_DYNAMIC_CONVERSATION",
            "live": gate_live,
            "mocked": False,
            "run_dir": str(side_dir),
            "turn_count": 2,
            "turn_pairs": [{
                "pair": 1,
                "horus": {"audio": "horus.wav", "audio_sha256": sha_file(side_dir / "horus.wav"), "audio_bytes": (side_dir / "horus.wav").stat().st_size, "append_read_back": True, **({"tau_receipt": tau_receipt()} if include_tau else {})},
                "embry": {"audio": "embry.wav", "audio_sha256": sha_file(side_dir / "embry.wav"), "audio_bytes": (side_dir / "embry.wav").stat().st_size, "append_read_back": True},
            }],
        }
        if provider_count is not None:
            receipt["provider_call_attempts"] = provider_count
        write_json(side_dir / "dynamic_conversation_receipt.v1.json", receipt)
    return manifest_path, run


def retained_case(root: Path) -> dict[str, Any]:
    case_root = root / "retained-unproven"
    manifest_path, run = stage_synthetic(case_root, gate_live=True, provider_count=1)
    if RETAINED.is_dir():
        shutil.copyfile(RETAINED / "residue_links.json", run / "source_memory" / "residue_links.json")
        if (RETAINED / "day_context.json").is_file():
            shutil.copyfile(RETAINED / "day_context.json", run / "source_memory" / "day_context.json")
        for side in ("control", "treatment"):
            dst = run / side
            for name in ("dynamic_conversation_receipt.v1.json", "conversation.jsonl", "journal_spoken.txt"):
                shutil.copyfile(RETAINED / name, dst / name)
            receipt = json.loads((dst / "dynamic_conversation_receipt.v1.json").read_text(encoding="utf-8"))
            for pair in receipt.get("turn_pairs") or []:
                for role in ("horus", "embry"):
                    audio = ((pair.get(role) or {}).get("audio"))
                    if audio:
                        shutil.copyfile(RETAINED / audio, dst / audio)
        for side in ("control", "treatment"):
            mood_path = run / side / "session_mood.json"
            mood = json.loads(mood_path.read_text(encoding="utf-8"))
            mood["source_memory"] = {
                "residue_links_sha256": sha_file(run / "source_memory" / "residue_links.json"),
                "day_context_sha256": sha_file(run / "source_memory" / "day_context.json"),
            }
            mood.pop("identity", None)
            write_json(mood_path, mood)
    code, receipt = adjudicate(manifest_path, run, run / "corrected_goal_receipt.json", fail_closed=True)
    failures = receipt.get("failures", [])
    return {
        "name": "retained-current-artifacts-fail-closed-unproven",
        "exit_code": code,
        "status": receipt.get("status"),
        "ok": receipt.get("status") == "BLOCKED_CORRECTED_GOAL_PAIRED_PROOF" and any("identity" in item for item in failures),
        "failures": failures,
        "evidence_class": "retained_real_world_artifact_backed_fail_closed",
    }


def append_corrected_goal_contract_case(root: Path) -> dict[str, Any]:
    case_root = root / "append-corrected-goal-contract"
    run = case_root / "run"
    run.mkdir(parents=True, exist_ok=True)
    (run / "journal_spoken.txt").write_text("journal spoken bytes\n", encoding="utf-8")
    write_wav(run / "embry.wav")
    answer = "Keep synthetic dreams marked as synthetic."
    prefix = "I feel careful saying this."
    suffix = "I can let the feeling stay in my voice."
    text = append_conversation.corrected_goal_text(prefix, answer, suffix)
    base = {
        "run_dir": run,
        "role": "embry",
        "text": text,
        "tone": "neutral_warm",
        "audio": run / "embry.wav",
        "chatterbox_utterance_text": text,
        "tts_render_text": text,
        "emotional_utterance_tags": None,
        "chatterbox_pause_plan": None,
        "answer_body": answer,
        "answer_body_sha256": sha_text(answer),
        "emotional_prefix": prefix,
        "emotional_suffix": suffix,
        "factual_claims_in_emotional_frame": "0",
        "contradiction_count": "0",
        "unsupported_fact_count": "0",
        "created_at": "2026-09-15T00:00:00Z",
        "out": None,
        "json": True,
    }
    good = append_conversation.run(argparse.Namespace(**base))
    mismatch = append_conversation.run(argparse.Namespace(**{**base, "text": f"{text} {answer}"}))
    bad_hash = append_conversation.run(argparse.Namespace(**{**base, "answer_body_sha256": ZERO}))
    ok = (
        good.get("status") == "PASS_CONVERSATION_APPENDED"
        and (good.get("appended") or {}).get("answer_body") == answer
        and "answer_body_not_exactly_once" in mismatch.get("failed_gates", [])
        and "answer_body_sha256_mismatch" in bad_hash.get("failed_gates", [])
    )
    return {
        "name": "append-corrected-goal-answer-contract",
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "good_status": good.get("status"),
        "mismatch_failures": mismatch.get("failed_gates", []),
        "bad_hash_failures": bad_hash.get("failed_gates", []),
    }


def run_case(
    name: str,
    mutate: Callable[[Path, Path], None],
    expected: str,
    root: Path,
    *,
    gate_live: bool = True,
    provider_count: Any = None,
    include_tau: bool = True,
) -> dict[str, Any]:
    case_root = root / name
    manifest_path, run = stage_synthetic(case_root, gate_live=gate_live, provider_count=provider_count, include_tau=include_tau)
    mutate(manifest_path, run)
    code, receipt = adjudicate(manifest_path, run, run / "corrected_goal_receipt.json", fail_closed=True)
    failures = receipt.get("failures", [])
    ok = receipt.get("status") == "BLOCKED_CORRECTED_GOAL_PAIRED_PROOF" and any(expected in item for item in failures)
    return {"name": name, "exit_code": code, "ok": ok, "status": receipt.get("status"), "expected": expected, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="persona-dream-corrected-goal-proof-") as tmp:
        tmp_path = Path(tmp)
        noop = lambda manifest_path, run: None
        cases = [
            run_case("synthetic-internal-coverage-blocks-not-live", noop, "gate_live_not_true", tmp_path, gate_live=False),
            run_case("gate-schema-mismatch", lambda _m, run: _set(run / "answer_invariance.json", ["schema"], "wrong.schema.v1"), "gate_schema_mismatch", tmp_path),
            run_case("gate-mocked-true", lambda _m, run: _set(run / "answer_invariance.json", ["mocked"], True), "gate_mocked_not_false", tmp_path),
            run_case("synthetic-provider-count-one-without-tau", noop, "dynamic_conversation_tau_receipt_missing_or_invalid", tmp_path, gate_live=True, provider_count=1, include_tau=False),
            run_case("synthetic-provider-count-true-without-tau", noop, "dynamic_conversation_provider_count_not_integer", tmp_path, gate_live=True, provider_count=True, include_tau=False),
            run_case("tau-model-non-string", lambda _m, run: _set_first_tau(run / "control" / "dynamic_conversation_receipt.v1.json", "model", 1), "invalid_model", tmp_path),
            run_case("tau-route-wrong", lambda _m, run: _set_first_tau(run / "control" / "dynamic_conversation_receipt.v1.json", "route", "tau:wrong"), "invalid_route", tmp_path),
            run_case("tau-route-non-string", lambda _m, run: _set_first_tau(run / "control" / "dynamic_conversation_receipt.v1.json", "route", 1), "invalid_route", tmp_path),
            run_case("source-memory-digest-missing", lambda _m, run: _drop(run / "control" / "session_mood.json", ["source_memory", "residue_links_sha256"]), "source_memory_digest_missing", tmp_path),
            run_case("source-memory-digest-mismatch", lambda _m, run: _set(run / "control" / "session_mood.json", ["source_memory", "residue_links_sha256"], ZERO), "source_memory_digest_mismatch", tmp_path),
            run_case("identity-artifact-digest-missing", lambda _m, run: _drop(run / "control" / "session_mood.json", ["identity", "artifact_sha256"]), "identity_artifact_digest_missing", tmp_path),
            run_case("identity-artifact-digest-mismatch", lambda _m, run: _set(run / "control" / "session_mood.json", ["identity", "artifact_sha256"], ZERO), "identity_artifact_digest_mismatch", tmp_path),
            run_case("manifest-identity-digest-missing", lambda m, _run: _drop(m, ["identity", "identity_core_digest"]), "manifest_identity_core_digest_missing", tmp_path),
            run_case("manifest-identity-digest-mismatch", lambda m, _run: _set(m, ["identity", "identity_core_digest"], ZERO), "manifest_identity_core_digest_mismatch", tmp_path),
            run_case("dynamic-conversation-receipt-missing", lambda _m, run: (run / "control" / "dynamic_conversation_receipt.v1.json").unlink(), "dynamic_conversation_receipt_missing", tmp_path),
            run_case("dynamic-conversation-receipt-fixture-scripted", lambda _m, run: _set(run / "control" / "dynamic_conversation_receipt.v1.json", ["mocked"], True), "dynamic_conversation_fixture_scripted", tmp_path),
            run_case("aligned-embry-answer-missing", lambda _m, run: _rewrite_no_embry(run / "control" / "conversation.jsonl"), "aligned_embry_answer_missing", tmp_path),
            run_case("chatterbox-delivery-metrics-missing", lambda _m, run: (run / "chatterbox_delivery.metrics.json").unlink(), "chatterbox_delivery_metrics_missing", tmp_path),
            run_case("chatterbox-delivery-metrics-digest-missing", lambda _m, run: _drop(run / "chatterbox_delivery.json", ["chatterbox_delivery_metrics_sha256"]), "chatterbox_delivery_metrics_digest_missing", tmp_path),
            run_case("chatterbox-delivery-metrics-digest-mismatch", lambda _m, run: _set(run / "chatterbox_delivery.json", ["chatterbox_delivery_metrics_sha256"], ZERO), "chatterbox_delivery_metrics_digest_mismatch", tmp_path),
            append_corrected_goal_contract_case(tmp_path),
            retained_case(tmp_path),
        ]

    status = "PASS" if all(case.get("ok") for case in cases) else "FAIL"
    report = {
        "schema": "persona_dream.corrected_goal_proof_boundaries_eval.v1",
        "status": status,
        "cases": cases,
        "provider_call_attempts": 0,
        "readiness_awarded": {"webgpt": False, "webkimi": False, "kling": False, "real_world_positive": False},
        "proof_boundary": {
            "live": False,
            "mocked": False,
            "fixture_backed": True,
            "fault_injected": True,
            "retained_artifact_backed": RETAINED.is_dir(),
            "positive_pair_proven": False,
            "does_not_prove": "fresh Memory query, provider availability, browser readiness, Kling/media generation, human perceptual review, canonical identity availability, a complete retained positive proof, or cryptographic unforgeability against a malicious filesystem writer",
        },
    }
    write_json(args.output, report)
    if status == "PASS":
        print("CORRECTED_GOAL_PROOF_BOUNDARIES_OK")
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1


def _drop(path: Path, keys: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data
    for key in keys[:-1]:
        target = target[key]
    target.pop(keys[-1], None)
    write_json(path, data)


def _set(path: Path, keys: list[str], value: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    write_json(path, data)


def _rewrite_no_embry(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row.get("role") == "embry":
            row["role"] = "assistant"
            row["speaker"] = "assistant"
    write_jsonl(path, rows)


def _set_first_tau(path: Path, field: str, value: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["turn_pairs"][0]["horus"]["tau_receipt"][field] = value
    write_json(path, data)


if __name__ == "__main__":
    sys.exit(main())
