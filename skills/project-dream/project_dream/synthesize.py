from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .common import (
    SCHEMA_CANDIDATE,
    digest_object,
    json_sidecar,
    load_json,
    provider_from_model,
    sha256_file,
    sha256_text,
    write_json,
)
from .validate_candidate import validate_candidate, validate_packet

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "consolidate_project_memory.v1.md"


def _load_command_spec(path: Path | None) -> dict[str, Any]:
    if path:
        spec = load_json(path)
    else:
        raw = os.environ.get("PROJECT_DREAM_OPENCODE_COMMAND")
        if not raw:
            raise ValueError("missing --command-spec or PROJECT_DREAM_OPENCODE_COMMAND")
        spec = json.loads(raw)
    if not isinstance(spec.get("argv"), list) or not all(isinstance(x, str) and x for x in spec["argv"]):
        raise ValueError("command spec must contain non-empty argv string list")
    if any(any(ch in part for ch in "\n\r") for part in spec["argv"]):
        raise ValueError("command spec argv cannot contain newlines")
    return spec


def _extract_json(raw: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == SCHEMA_CANDIDATE:
            return obj
    raise ValueError("no project_dream_candidate.v1 JSON object found in worker output")


def _render_prompt(packet: dict[str, Any], model: str) -> tuple[str, str]:
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{MODEL_ID}}", model).replace("{{PACKET_JSON}}", json.dumps(packet, sort_keys=True, indent=2))
    return prompt, sha256_text(prompt_template)


def _cache_key(packet_digest: str, model: str, prompt_sha: str, spec: dict[str, Any]) -> str:
    return sha256_text(json.dumps({"packet_digest": packet_digest, "model": model, "prompt_sha256": prompt_sha, "argv": spec["argv"]}, sort_keys=True))


def _copy_cached(cache_dir: Path, key: str, output: Path) -> dict[str, Any] | None:
    hit_dir = cache_dir / key
    candidate = hit_dir / "candidate.json"
    receipt = hit_dir / "synthesis-receipt.json"
    if not candidate.exists() or not receipt.exists():
        return None
    cached_receipt = load_json(receipt)
    if cached_receipt.get("cache_key") != key or cached_receipt.get("raw_output_sha256") != sha256_file(hit_dir / "raw-output.txt"):
        return None
    shutil.copyfile(candidate, output)
    out_receipt = dict(cached_receipt, cache_hit=True, output_path=str(output))
    write_json(json_sidecar(output, ".synthesis-receipt.json"), out_receipt)
    return out_receipt


def synthesize(packet_path: Path, model: str, output: Path, command_spec_path: Path | None = None, cache_dir: Path | None = None) -> tuple[int, dict[str, Any]]:
    if not model or "/" not in model:
        raise ValueError("--model must be an explicit resolved provider/model id")
    packet = load_json(packet_path)
    packet_errors = validate_packet(packet)
    if packet_errors:
        raise ValueError("invalid packet: " + "; ".join(packet_errors))
    packet_digest = digest_object(packet)
    prompt, prompt_sha = _render_prompt(packet, model)
    spec = _load_command_spec(command_spec_path)
    key = _cache_key(packet_digest, model, prompt_sha, spec)
    if cache_dir:
        cached = _copy_cached(cache_dir, key, output)
        if cached:
            return 0, cached

    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="project-dream-worker-") as tmp:
        workdir = Path(tmp)
        packet_dir = workdir / "packet"
        packet_dir.mkdir()
        sandbox_packet = packet_dir / packet_path.name
        shutil.copyfile(packet_path, sandbox_packet)
        sandbox_output = workdir / "candidate.json"
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
        env.update({
            "PROJECT_DREAM_PACKET_DIR": str(packet_dir),
            "PROJECT_DREAM_PACKET": str(sandbox_packet),
            "PROJECT_DREAM_OUTPUT": str(sandbox_output),
            "PROJECT_DREAM_MODEL": model,
            "PROJECT_DREAM_RUN_ID": str(packet.get("run_id")),
            "PROJECT_DREAM_EXCLUDE_FROM_LEARNING": "true",
            "NO_COLOR": "1",
        })
        proc = subprocess.run(
            spec["argv"],
            cwd=workdir,
            env=env,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(spec.get("timeout_seconds", 120)),
            check=False,
        )
        duration_ms = round((time.monotonic() - start) * 1000, 3)
        raw = sandbox_output.read_text(encoding="utf-8") if sandbox_output.exists() else proc.stdout

    raw_path = json_sidecar(output, ".raw-output.txt")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw, encoding="utf-8")
    receipt = {
        "schema_version": "project_dream_synthesis_receipt.v1",
        "status": "blocked",
        "project_id": packet.get("project_id"),
        "run_id": packet.get("run_id"),
        "provider": provider_from_model(model),
        "model": model,
        "prompt_sha256": prompt_sha,
        "packet_digest": packet_digest,
        "input_digest": packet.get("input_digest"),
        "duration_ms": duration_ms,
        "exit_status": proc.returncode,
        "raw_output_sha256": sha256_file(raw_path),
        "raw_output_path": str(raw_path),
        "output_path": str(output),
        "cache_key": key,
        "cache_hit": False,
        "exclude_from_learning": True,
        "telemetry": {"tokens": None, "cost": None},
        "errors": [],
    }
    try:
        candidate = _extract_json(raw)
        validation = validate_candidate(packet, candidate)
        if validation["status"] != "accepted":
            receipt["errors"] = validation["errors"]
            return 1, receipt
        write_json(output, candidate)
        receipt["status"] = "accepted"
        receipt["candidate_digest"] = digest_object(candidate)
        if cache_dir:
            hit_dir = cache_dir / key
            hit_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output, hit_dir / "candidate.json")
            shutil.copyfile(raw_path, hit_dir / "raw-output.txt")
            write_json(hit_dir / "synthesis-receipt.json", receipt)
        return 0, receipt
    except Exception as exc:
        receipt["errors"] = [str(exc)]
        return 1, receipt
    finally:
        write_json(json_sidecar(output, ".synthesis-receipt.json"), receipt)
