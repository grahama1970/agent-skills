from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .common import SCHEMA_VALIDATION, digest_object, json_sidecar, load_json, write_json


def _head(value: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return None


def stage_candidate(candidate_path: Path, validation_path: Path) -> tuple[int, dict[str, Any]]:
    candidate = load_json(candidate_path)
    validation = load_json(validation_path)
    receipt_path = json_sidecar(candidate_path, ".stage-receipt.json")
    receipt: dict[str, Any] = {
        "schema_version": "project_dream_stage_receipt.v1",
        "status": "blocked",
        "project_id": candidate.get("project_id"),
        "run_id": candidate.get("run_id"),
        "candidate_path": str(candidate_path),
        "validation_path": str(validation_path),
        "candidate_digest": digest_object(candidate),
        "validation_digest": digest_object(validation),
        "shadow_only": True,
        "active_head_unchanged": False,
        "errors": [],
    }
    if validation.get("schema_version") != SCHEMA_VALIDATION or validation.get("status") != "accepted":
        receipt["errors"].append("validation receipt is not accepted")
        write_json(receipt_path, receipt)
        return 1, receipt

    memory_run = os.environ.get("PROJECT_DREAM_MEMORY_RUN") or str(Path(__file__).resolve().parents[2] / "memory" / "run.sh")
    cmd = [memory_run, "project-memory", "stage", "--packet", str(candidate_path), "--json"]
    receipt["memory_command"] = cmd
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    except OSError as exc:
        receipt["errors"].append(f"memory wrapper unavailable: {exc}")
        write_json(receipt_path, receipt)
        return 1, receipt

    receipt["memory_exit_status"] = proc.returncode
    receipt["memory_stdout"] = proc.stdout[-4000:]
    receipt["memory_stderr"] = proc.stderr[-4000:]
    if proc.returncode != 0:
        receipt["errors"].append("memory project-memory stage rejected or is unavailable")
        write_json(receipt_path, receipt)
        return 1, receipt

    try:
        memory = load_json_from_text(proc.stdout)
    except ValueError as exc:
        receipt["errors"].append(str(exc))
        write_json(receipt_path, receipt)
        return 1, receipt

    before = _head(memory, "active_head_before", "head_before")
    after = _head(memory, "active_head_after", "head_after")
    receipt["memory_response"] = memory
    receipt["active_head_before"] = before
    receipt["active_head_after"] = after
    receipt["active_head_unchanged"] = before == after
    if not receipt["active_head_unchanged"]:
        receipt["errors"].append("active head changed during shadow staging")
    else:
        receipt["status"] = "staged"
    write_json(receipt_path, receipt)
    return (0 if receipt["status"] == "staged" else 1), receipt


def load_json_from_text(text: str) -> dict[str, Any]:
    import json

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("memory wrapper did not emit JSON")
