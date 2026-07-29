#!/usr/bin/env python3
"""Validate the Persona Dream blinded listener-study bundle.

This is a bundle/readiness validator, not a substitute for human listener
responses. It verifies preregistered stimulus hashes, optionally transcribes the
stimuli through a live OpenAI-compatible ASR endpoint, and reports whether the
append-only response file has enough human responses for analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"
DEFAULT_ASR_BASE_URL = "http://127.0.0.1:9000"
DEFAULT_REQUIRED_RATERS = 20


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


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return rows, [f"responses_missing:{rel(path)}"]
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"responses_jsonl_invalid:{line_no}:{exc}")
    return rows, errors


def resolve_bundle_path(raw: str | None) -> Path:
    if not isinstance(raw, str) or not raw:
        return Path("")
    path = Path(raw)
    if path.is_absolute():
        return path
    if raw.startswith("reports/"):
        return ROOT / raw
    return REPO_ROOT / raw


def normalize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip().split()


def word_error_rate(expected: str, actual: str) -> float:
    ref = normalize(expected)
    hyp = normalize(actual)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, token in enumerate(ref, start=1):
        cur = [i]
        for j, other in enumerate(hyp, start=1):
            cost = 0 if token == other else 1
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return round(prev[-1] / len(ref), 6)


def multipart_form_data(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----persona-dream-listener-study"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
        b"Content-Type: audio/wav\r\n\r\n",
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def transcribe(base_url: str, api_key: str, audio: Path) -> str:
    body, content_type = multipart_form_data(
        {"model": "whisper-1", "response_format": "json", "language": "en"},
        "file",
        audio,
    )
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data.get("text") or "").strip()


def validate_responses(rows: list[dict[str, Any]], required: int) -> dict[str, Any]:
    rater_ids = [str(row.get("rater_id") or "") for row in rows]
    unique_raters = sorted({rid for rid in rater_ids if rid})
    return {
        "response_count": len(rows),
        "unique_rater_count": len(unique_raters),
        "required_raters": required,
        "enough_human_responses": len(unique_raters) >= required,
        "duplicate_rater_ids": sorted({rid for rid in unique_raters if rater_ids.count(rid) > 1}),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = args.study_dir
    prereg_path = study_dir / "PREREGISTRATION.json"
    responses_path = study_dir / "responses.jsonl"
    failed_gates: list[str] = []
    if not prereg_path.is_file():
        failed_gates.append("preregistration_exists")
        prereg = {}
    else:
        prereg = load_json(prereg_path)

    expected_text = ((prereg.get("stimulus_source") or {}).get("answer_text") or "")
    stimulus_rows: list[dict[str, Any]] = []
    for stimulus in prereg.get("stimuli") or []:
        audio_rel = stimulus.get("audio")
        audio = resolve_bundle_path(audio_rel)
        row = {
            "condition": stimulus.get("condition"),
            "stimulus_id": next(
                (
                    item.get("stimulus_id")
                    for item in prereg.get("presentation_manifest") or []
                    if item.get("condition") == stimulus.get("condition")
                ),
                None,
            ),
            "audio": artifact(audio),
            "expected_sha256": stimulus.get("sha256"),
            "expected_bytes": stimulus.get("bytes"),
            "hash_match": audio.is_file() and sha_file(audio) == stimulus.get("sha256"),
            "bytes_match": audio.is_file() and audio.stat().st_size == stimulus.get("bytes"),
            "engine": stimulus.get("engine"),
            "voice_delivery": stimulus.get("voice_delivery"),
        }
        if not row["hash_match"]:
            failed_gates.append(f"stimulus_hash_match:{stimulus.get('condition')}")
        if not row["bytes_match"]:
            failed_gates.append(f"stimulus_bytes_match:{stimulus.get('condition')}")
        if args.asr and audio.is_file():
            try:
                transcript = transcribe(args.asr_base_url, args.asr_api_key, audio)
                wer = word_error_rate(expected_text, transcript)
                row["asr"] = {
                    "mocked": False,
                    "live": True,
                    "base_url": args.asr_base_url,
                    "transcript": transcript,
                    "wer": wer,
                    "ok": wer <= args.max_wer,
                }
                if wer > args.max_wer:
                    failed_gates.append(f"stimulus_asr_wer:{stimulus.get('condition')}")
            except Exception as exc:  # noqa: BLE001 - ASR must fail closed
                row["asr"] = {"mocked": False, "live": True, "error": f"{type(exc).__name__}: {exc}"}
                failed_gates.append(f"stimulus_asr_available:{stimulus.get('condition')}")
        stimulus_rows.append(row)

    responses, response_errors = load_jsonl(responses_path)
    failed_gates.extend(response_errors)
    response_summary = validate_responses(responses, args.required_raters)
    if not response_summary["enough_human_responses"]:
        failed_gates.append("human_responses_complete")
    if response_summary["duplicate_rater_ids"]:
        failed_gates.append("rater_ids_unique")

    stimuli_ready = all(row["hash_match"] and row["bytes_match"] for row in stimulus_rows)
    asr_ready = all((row.get("asr") or {}).get("ok") is True for row in stimulus_rows) if args.asr else None
    status = (
        "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS"
        if stimuli_ready and (asr_ready is not False) and not response_summary["enough_human_responses"]
        else "PASS_BLINDED_LISTENER_STUDY_RESPONSES_PRESENT"
        if stimuli_ready and response_summary["enough_human_responses"] and not failed_gates
        else "BLOCKED_BLINDED_LISTENER_STUDY"
    )
    receipt = {
        "schema": "persona_dream.blinded_listener_study_validation.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": bool(args.asr),
        "study_dir": rel(study_dir),
        "preregistration": artifact(prereg_path),
        "responses": artifact(responses_path),
        "stimuli": stimulus_rows,
        "responses_summary": response_summary,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "preregistered stimulus files exist and match their exact hashes",
                "stimulus content ASR is within the configured WER limit",
            ] if status == "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS" and args.asr else [
                "preregistered stimulus files exist and match their exact hashes",
            ] if stimuli_ready else [],
            "does_not_prove": [
                "target emotion is perceived by humans",
                "human listener recognition of Embry",
                "naturalness",
                "the study result, until append-only human responses and signed interpretation exist",
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
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "STIMULUS_VALIDATION_RECEIPT.json")
    parser.add_argument("--required-raters", type=int, default=DEFAULT_REQUIRED_RATERS)
    parser.add_argument("--asr", action="store_true")
    parser.add_argument("--asr-base-url", default=DEFAULT_ASR_BASE_URL)
    parser.add_argument("--asr-api-key", default=os.getenv("WHISPER_API_KEY", "none"))
    parser.add_argument("--max-wer", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "receipt": rel(args.out),
        "stimuli": {
            "count": len(receipt["stimuli"]),
            "hash_match": sum(1 for row in receipt["stimuli"] if row["hash_match"]),
        },
        "responses_summary": receipt["responses_summary"],
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
