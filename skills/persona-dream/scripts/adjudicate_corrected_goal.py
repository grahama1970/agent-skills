#!/usr/bin/env python3
"""Admit corrected-goal paired proofs only when artifact bytes bind the claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_ROOT = [
    "manifest.json",
    "answer_invariance.json",
    "emotional_carryover.json",
    "chatterbox_delivery.json",
]
GATE_CONTRACTS = {
    "answer_invariance": {
        "path": "answer_invariance.json",
        "schema": "persona_dream.answer_invariance_validation.v1",
        "status": "PASS_ANSWER_INVARIANCE",
    },
    "emotional_carryover": {
        "path": "emotional_carryover.json",
        "schema": "persona_dream.emotion_lineage_validation.v1",
        "status": "PASS_EMOTION_LINEAGE",
    },
    "chatterbox_delivery": {
        "path": "chatterbox_delivery.json",
        "schema": "persona_dream.chatterbox_delivery_validation.v1",
        "status": "PASS_CHATTERBOX_DELIVERY",
    },
}
SOURCE_MEMORY_FILES = {
    "residue_links_sha256": "residue_links.json",
    "day_context_sha256": "day_context.json",
}
DYNAMIC_RECEIPT = "dynamic_conversation_receipt.v1.json"
DYNAMIC_TRANSCRIPT = "conversation.jsonl"
JOURNAL_SPOKEN = "journal_spoken.txt"
CHATTERBOX_METRICS = "chatterbox_delivery.metrics.json"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TAU_RECEIPT_SCHEMA = "tau.persona_dream.scillm_text_reasoning_receipt.v1"


def _sha_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"line_{line_no}_not_object")
            rows.append(row)
    return rows


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _resolve_inside(base: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    raw = Path(ref)
    path = raw if raw.is_absolute() else base / raw
    if not _is_relative_to(path, base):
        return None
    return path


def _condition_identity(mood: dict[str, Any]) -> dict[str, Any]:
    identity = mood.get("identity")
    if isinstance(identity, dict):
        return identity
    return {
        "artifact_path": mood.get("identity_artifact_path"),
        "artifact_sha256": mood.get("identity_artifact_sha256"),
        "identity_core_digest": mood.get("identity_core_digest"),
    }


def _validate_source_memory(
    run_root: Path,
    control: dict[str, Any],
    treatment: dict[str, Any],
    failures: list[str],
    artifacts: dict[str, str],
) -> dict[str, str]:
    source_dir = run_root / "source_memory"
    expected: dict[str, str] = {}
    for key, name in SOURCE_MEMORY_FILES.items():
        path = source_dir / name
        if not path.is_file():
            failures.append(f"source_memory_artifact_missing:{name}")
            continue
        digest = _sha_file(path)
        expected[key] = digest
        artifacts[f"source_memory/{name}"] = digest
        try:
            data = _load_json(path)
        except Exception as exc:  # noqa: BLE001 - validator reports fail-closed cause.
            failures.append(f"source_memory_artifact_invalid:{name}:{exc}")
            continue
        if name == "residue_links.json":
            if data.get("schema") != "persona_dream.residue_links.v1" or not isinstance(data.get("items"), list):
                failures.append("source_memory_artifact_invalid:residue_links.json")
        else:
            for field in ("day", "persona", "items", "receipt", "status"):
                if field not in data:
                    failures.append(f"source_memory_artifact_invalid:day_context.json:missing_{field}")

    for side, mood in (("control", control), ("treatment", treatment)):
        binding = mood.get("source_memory") if isinstance(mood.get("source_memory"), dict) else {}
        for key, digest in expected.items():
            observed = binding.get(key)
            if not observed:
                failures.append(f"{side}:source_memory_digest_missing:{key}")
            elif observed != digest:
                failures.append(f"{side}:source_memory_digest_mismatch:{key}")
    if expected:
        c_binding = control.get("source_memory") if isinstance(control.get("source_memory"), dict) else {}
        t_binding = treatment.get("source_memory") if isinstance(treatment.get("source_memory"), dict) else {}
        for key in SOURCE_MEMORY_FILES:
            if c_binding.get(key) and t_binding.get(key) and c_binding.get(key) != t_binding.get(key):
                failures.append(f"source_memory_digest_unequal:{key}")
    return expected


def _resolve_identity_path(run_root: Path, side_dir: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    raw = Path(ref)
    candidates = [raw] if raw.is_absolute() else [side_dir / raw, run_root / raw]
    for path in candidates:
        if _is_relative_to(path, run_root):
            return path
    return None


def _validate_identity(
    manifest: dict[str, Any],
    run_root: Path,
    control: dict[str, Any],
    treatment: dict[str, Any],
    failures: list[str],
    artifacts: dict[str, str],
) -> None:
    manifest_identity = (manifest.get("identity") or {}).get("identity_core_digest")
    if not manifest_identity:
        failures.append("manifest_identity_core_digest_missing")
    seen: dict[str, list[str]] = {"artifact_sha256": [], "identity_core_digest": []}
    seen_actual: list[str] = []
    for side, mood in (("control", control), ("treatment", treatment)):
        side_dir = run_root / side
        identity = _condition_identity(mood)
        artifact_path = identity.get("artifact_path")
        artifact_sha = identity.get("artifact_sha256")
        core_digest = identity.get("identity_core_digest")
        if not artifact_path:
            failures.append(f"{side}:identity_artifact_path_missing")
        if not artifact_sha:
            failures.append(f"{side}:identity_artifact_digest_missing")
        if not core_digest:
            failures.append(f"{side}:identity_core_digest_missing")
        if not (artifact_path and artifact_sha and core_digest):
            continue
        path = _resolve_identity_path(run_root, side_dir, artifact_path)
        if path is None or not path.is_file():
            failures.append(f"{side}:identity_artifact_missing")
            continue
        actual = _sha_file(path)
        seen_actual.append(actual)
        artifacts[f"{side}/{Path(str(artifact_path)).as_posix()}"] = actual
        if artifact_sha != actual:
            failures.append(f"{side}:identity_artifact_digest_mismatch")
        if core_digest != actual:
            failures.append(f"{side}:identity_core_digest_unverified")
        if manifest_identity and manifest_identity != actual:
            failures.append(f"{side}:manifest_identity_core_digest_mismatch")
        seen["artifact_sha256"].append(str(artifact_sha))
        seen["identity_core_digest"].append(str(core_digest))
    for key, values in seen.items():
        if len(values) == 2 and values[0] != values[1]:
            failures.append(f"identity_{key}_unequal")
    if len(seen_actual) == 2 and seen_actual[0] != seen_actual[1]:
        failures.append("identity_artifact_bytes_unequal")


def _int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST_RE.match(value) is not None


def _validate_audio(
    base: Path,
    ref: Any,
    digest: Any,
    byte_count: Any,
    failures: list[str],
    label: str,
    artifacts: dict[str, str],
) -> None:
    path = _resolve_inside(base, ref)
    if path is None or not path.is_file():
        failures.append(f"{label}:audio_missing")
        return
    data = path.read_bytes()
    artifacts[f"{base.name}/{Path(str(ref)).as_posix()}"] = _sha_bytes(data)
    if not (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"):
        failures.append(f"{label}:audio_not_wave")
    if digest != _sha_bytes(data):
        failures.append(f"{label}:audio_sha256_mismatch")
    if byte_count is not None:
        if not _int_not_bool(byte_count):
            failures.append(f"{label}:audio_bytes_not_integer")
        elif byte_count != len(data):
            failures.append(f"{label}:audio_bytes_mismatch")


def _validate_tau_receipt(side: str, pair_no: Any, tau: Any, failures: list[str]) -> bool:
    label = f"{side}:tau_receipt:pair_{pair_no}"
    if not isinstance(tau, dict):
        failures.append(f"{label}:missing")
        return False
    checks = {
        "tau_receipt_schema": tau.get("tau_receipt_schema") == TAU_RECEIPT_SCHEMA,
        "status": tau.get("status") == "PASS",
        "live_call_performed": tau.get("live_call_performed") is True,
        "http_status": tau.get("http_status") == 200,
        "model": isinstance(tau.get("model"), str) and bool(tau.get("model", "").strip()),
        "route": tau.get("route") == "tau:persona-dream-text-reasoning",
        "prompt_sha256": _valid_digest(tau.get("prompt_sha256")),
        "output_contract_sha256": _valid_digest(tau.get("output_contract_sha256")),
    }
    failed = [key for key, ok in checks.items() if not ok]
    for key in failed:
        failures.append(f"{label}:invalid_{key}")
    return not failed


def _validate_dynamic_condition(run_root: Path, side: str, failures: list[str], artifacts: dict[str, str]) -> dict[str, Any]:
    side_dir = run_root / side
    receipt_path = side_dir / DYNAMIC_RECEIPT
    transcript_path = side_dir / DYNAMIC_TRANSCRIPT
    journal_path = side_dir / JOURNAL_SPOKEN
    evidence: dict[str, Any] = {}
    if not receipt_path.is_file():
        failures.append(f"{side}:dynamic_conversation_receipt_missing")
        return evidence
    if not transcript_path.is_file():
        failures.append(f"{side}:dynamic_conversation_transcript_missing")
        return evidence
    if not journal_path.is_file():
        failures.append(f"{side}:journal_spoken_missing")
        return evidence

    receipt_digest = _sha_file(receipt_path)
    transcript_digest = _sha_file(transcript_path)
    journal_digest = _sha_file(journal_path)
    artifacts[f"{side}/{DYNAMIC_RECEIPT}"] = receipt_digest
    artifacts[f"{side}/{DYNAMIC_TRANSCRIPT}"] = transcript_digest
    artifacts[f"{side}/{JOURNAL_SPOKEN}"] = journal_digest
    evidence.update({
        "dynamic_conversation_receipt_sha256": receipt_digest,
        "conversation_jsonl_sha256": transcript_digest,
        "journal_spoken_sha256": journal_digest,
    })

    try:
        receipt = _load_json(receipt_path)
        rows = _read_jsonl(transcript_path)
    except Exception as exc:  # noqa: BLE001 - fail closed with the parse cause.
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:{exc}")
        return evidence

    if receipt.get("schema") != "persona_dream.dynamic_conversation_receipt.v1":
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:schema")
    if receipt.get("status") != "PASS_DYNAMIC_CONVERSATION":
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:status")
    if receipt.get("live") is not True or receipt.get("mocked") is not False:
        failures.append(f"{side}:dynamic_conversation_fixture_scripted")
    for provider_count_key in ("actual_provider_call_attempts", "provider_call_attempts"):
        if isinstance(receipt.get(provider_count_key), bool):
            failures.append(f"{side}:dynamic_conversation_provider_count_not_integer:{provider_count_key}")

    pairs = receipt.get("turn_pairs")
    if not isinstance(pairs, list) or not pairs:
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:turn_pairs")
        pairs = []
    pair_numbers = [pair.get("pair") for pair in pairs if isinstance(pair, dict)]
    if pair_numbers != list(range(1, len(pair_numbers) + 1)):
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:pair_order")
    if len(set(pair_numbers)) != len(pair_numbers):
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:pair_duplicate")
    if receipt.get("turn_count") != 2 * len(pairs):
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:turn_count")

    base_lines = receipt.get("transcript_base_lines")
    total_lines = receipt.get("transcript_total_lines")
    if (base_lines is None) != (total_lines is None):
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_line_fields")
    expected_rows = (int(base_lines) if base_lines is not None else 0) + int(receipt.get("turn_count") or 0)
    if len(rows) != expected_rows:
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_row_count")
    if base_lines is not None and int(total_lines) != int(base_lines) + int(receipt.get("turn_count") or 0):
        failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_total_lines")

    transcript_audio_hashes = {row.get("audio_sha256") for row in rows if row.get("audio_sha256")}
    embry_texts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if row.get("schema") != "persona_dream.conversation_turn.v1":
            failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_schema:{idx}")
        for field in ("role", "text", "journal_spoken_sha256", "created_at"):
            if not row.get(field):
                failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_missing_{field}:{idx}")
        if str(row.get("role") or row.get("speaker") or "").lower() == "embry":
            if row.get("text"):
                embry_texts.append(str(row["text"]))
        if row.get("journal_spoken_sha256") != journal_digest:
            failures.append(f"{side}:artifact_lineage_hash_mismatch:journal_spoken_sha256:{idx}")
        if row.get("audio") or row.get("audio_sha256"):
            if not (row.get("audio") and row.get("audio_sha256")):
                failures.append(f"{side}:dynamic_conversation_receipt_invalid:transcript_audio_binding:{idx}")
            else:
                _validate_audio(side_dir, row.get("audio"), row.get("audio_sha256"), None, failures, f"{side}:transcript:{idx}", artifacts)
    evidence["embry_answer_count"] = len(embry_texts)
    evidence["embry_answer_sha256"] = [_sha_bytes(text.encode("utf-8")) for text in embry_texts]

    validated_tau_receipts = 0
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        horus_turn = pair.get("horus") if isinstance(pair.get("horus"), dict) else {}
        if _validate_tau_receipt(side, pair.get("pair"), horus_turn.get("tau_receipt"), failures):
            validated_tau_receipts += 1
        for role in ("horus", "embry"):
            turn = pair.get(role) if isinstance(pair.get(role), dict) else {}
            for field in ("audio", "audio_sha256", "audio_bytes", "append_read_back"):
                if field not in turn:
                    failures.append(f"{side}:dynamic_conversation_receipt_invalid:{role}_{field}_missing")
            if turn.get("audio_sha256") not in transcript_audio_hashes:
                failures.append(f"{side}:dynamic_conversation_receipt_invalid:{role}_audio_not_in_transcript")
            if turn.get("append_read_back") is not True:
                failures.append(f"{side}:dynamic_conversation_receipt_invalid:{role}_append_read_back")
            if turn.get("audio") and turn.get("audio_sha256"):
                label = f"{side}:receipt:{role}:pair_{pair.get('pair')}"
                _validate_audio(side_dir, turn.get("audio"), turn.get("audio_sha256"), turn.get("audio_bytes"), failures, label, artifacts)
    evidence["validated_tau_receipt_count"] = validated_tau_receipts
    if pairs and validated_tau_receipts != len(pairs):
        failures.append(f"{side}:dynamic_conversation_tau_receipt_missing_or_invalid")
    return evidence


def _validate_chatterbox_metrics(run_root: Path, failures: list[str], artifacts: dict[str, str]) -> None:
    path = run_root / CHATTERBOX_METRICS
    if not path.is_file():
        failures.append("chatterbox_delivery_metrics_missing")
        return
    artifacts[CHATTERBOX_METRICS] = _sha_file(path)
    try:
        data = _load_json(path)
    except Exception as exc:  # noqa: BLE001 - fail closed with the parse cause.
        failures.append(f"chatterbox_delivery_metrics_invalid:{exc}")
        return
    if data.get("schema") != "persona_dream.corrected_goal_chatterbox_delivery_metrics.v1":
        failures.append("chatterbox_delivery_metrics_schema_mismatch")
    if data.get("live") is not True:
        failures.append("chatterbox_delivery_metrics_live_not_true")
    if data.get("mocked") is not False:
        failures.append("chatterbox_delivery_metrics_mocked_not_false")


def validate_boundary_artifacts(manifest: dict[str, Any], run_root: Path) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    failures: list[str] = []
    artifacts: dict[str, str] = {}
    evidence: dict[str, Any] = {"control": {}, "treatment": {}, "source_memory": {}}

    if not run_root.exists():
        return ["run_root_missing"], artifacts, evidence

    for rel in REQUIRED_ROOT:
        path = run_root / rel
        if path.exists():
            artifacts[rel] = _sha_file(path)
        else:
            failures.append(f"missing_root_artifact:{rel}")
    _validate_chatterbox_metrics(run_root, failures, artifacts)

    moods: dict[str, dict[str, Any]] = {}
    for side in ("control", "treatment"):
        side_dir = run_root / side
        if not side_dir.exists():
            failures.append(f"missing_condition_dir:{side}")
            moods[side] = {}
            continue
        mood_path = side_dir / "session_mood.json"
        if not mood_path.is_file():
            failures.append(f"{side}:session_mood_missing")
            moods[side] = {}
        else:
            artifacts[f"{side}/session_mood.json"] = _sha_file(mood_path)
            moods[side] = _load_json(mood_path)
        evidence[side].update(_validate_dynamic_condition(run_root, side, failures, artifacts))

    evidence["observed_provider_call_count"] = int(evidence["control"].get("validated_tau_receipt_count") or 0) + int(evidence["treatment"].get("validated_tau_receipt_count") or 0)

    control_count = int(evidence["control"].get("embry_answer_count") or 0)
    treatment_count = int(evidence["treatment"].get("embry_answer_count") or 0)
    if control_count < 1 or treatment_count < 1:
        failures.append("aligned_embry_answer_missing")
    elif control_count != treatment_count:
        failures.append("aligned_embry_answer_count_mismatch")

    evidence["source_memory"] = _validate_source_memory(run_root, moods.get("control", {}), moods.get("treatment", {}), failures, artifacts)
    _validate_identity(manifest, run_root, moods.get("control", {}), moods.get("treatment", {}), failures, artifacts)
    return failures, artifacts, evidence


def _validate_gate(gate: str, path: Path, failures: list[str]) -> tuple[str, bool, bool]:
    contract = GATE_CONTRACTS[gate]
    data = _load_json(path)
    status = str(data.get("status"))
    if data.get("schema") != contract["schema"]:
        failures.append(f"gate_schema_mismatch:{gate}:{data.get('schema')}")
    if status != contract["status"]:
        failures.append(f"gate_not_pass:{gate}:{status}")
    if data.get("live") is not True:
        failures.append(f"gate_live_not_true:{gate}")
    if data.get("mocked") is not False:
        failures.append(f"gate_mocked_not_false:{gate}")
    if gate == "chatterbox_delivery":
        observed = data.get("chatterbox_delivery_metrics_sha256")
        metrics_path = path.parent / CHATTERBOX_METRICS
        if not observed:
            failures.append("chatterbox_delivery_metrics_digest_missing")
        elif not metrics_path.is_file() or observed != _sha_file(metrics_path):
            failures.append("chatterbox_delivery_metrics_digest_mismatch")
    return status, data.get("live") is True, data.get("mocked") is True


def adjudicate(manifest_path: Path, run_root: Path, out_path: Path, *, fail_closed: bool = False) -> tuple[int, dict[str, Any]]:
    failures: list[str] = []
    manifest = _load_json(manifest_path)
    manifest_digest = _sha_file(manifest_path)
    boundary_failures, artifacts, evidence = validate_boundary_artifacts(manifest, run_root)
    failures.extend(boundary_failures)

    gate_statuses: dict[str, str] = {}
    live_values: list[bool] = []
    mocked_values: list[bool] = []
    if run_root.exists():
        for gate, contract in GATE_CONTRACTS.items():
            path = run_root / contract["path"]
            if not path.exists():
                continue
            status, live, mocked = _validate_gate(gate, path, failures)
            gate_statuses[gate] = status
            live_values.append(live)
            mocked_values.append(mocked)

    if len(live_values) != len(GATE_CONTRACTS) or not all(live_values):
        failures.append("live_true_missing")
    if any(mocked_values):
        failures.append("mocked_true_forbidden")

    status = "PASS_CORRECTED_GOAL_PAIRED_PROOF" if not failures else "BLOCKED_CORRECTED_GOAL_PAIRED_PROOF"
    receipt = {
        "schema": "persona_dream.corrected_goal_receipt.v1",
        "proof_id": manifest.get("proof_id"),
        "status": status,
        "mocked": bool(any(mocked_values)),
        "live": bool(live_values and all(live_values) and not failures),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_digest,
        "run_root": str(run_root),
        "artifacts": artifacts,
        "boundary_evidence": evidence,
        "gate_statuses": gate_statuses,
        "failures": failures,
        "claims": manifest.get("claims"),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return (0 if not failures else (2 if fail_closed else 1)), receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fail-closed", action="store_true")
    args = parser.parse_args()

    code, receipt = adjudicate(Path(args.manifest), Path(args.run_root), Path(args.out), fail_closed=args.fail_closed)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
